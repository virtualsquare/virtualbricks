# Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
# Copyright (C) 2019 Virtualbricks team

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.


"""The brick factory and the start of the application."""

import io
import os
import sys
import stat

from twisted.internet import defer, task
from twisted.trial import unittest

from virtualbricks import brickfactory, errors, locations
from virtualbricks.bricks.eventaction import (
    ConsoleAction,
    StartAction,
    StopAction,
)
from virtualbricks.config.workspace import projects
from virtualbricks.console import control, wire
from virtualbricks.config import workspace
from virtualbricks.config.settings import (
    current_project,
    get_setting,
    set_setting,
    store_settings,
)
from virtualbricks.config.tomlfile import load_toml
from virtualbricks.tests import (
    use_workspace,
    BrickTestCase,
    FakeLogger,
    isolate,
    reset_settings,
)
from virtualbricks.tests.migrate.fixtures import (
    CONFIG1,
    write_project,
    write_settings,
)
from virtualbricks.bricks.virtualmachine import UsbDevice


class TestFactory(BrickTestCase):

    def test_get_event_by_name(self):
        event = self.factory.new_event("boot")
        self.factory.new_image("boot2", "/x")
        self.assertIs(self.factory.get_event("boot"), event)
        self.assertIsNone(self.factory.get_event("boot2"))

    def test_next_name(self):
        self.factory.new_brick("switch", "sw")
        self.factory.new_brick("switch", "sw.1")
        self.assertEqual(self.factory.unused_name("sw"), "sw.2")

    def test_dup_brick(self):
        vm = self.factory.new_brick("qemu", "vm")
        vm.update_config(
            {"memory": 256, "usb_devices": [UsbDevice("1d6b:0002", "hub")]}
        )
        copy = self.factory.duplicate_brick(vm)
        self.assertEqual(copy.config.memory, 256)
        self.assertEqual(copy.config.usb_devices, vm.config.usb_devices)
        self.assertIsNot(copy.config.usb_devices, vm.config.usb_devices)

    def test_rename_event_updates_the_bricks(self):
        event = self.factory.new_event("boot")
        switch = self.factory.new_brick("switch", "sw")
        switch.update_config({"on_start": "boot", "on_stop": "boot"})
        other = self.factory.new_event("other")
        other.update_config({"delay": 1})
        changed = []
        switch.changed.connect(changed.append)
        self.factory.rename_item(event, "start")
        self.assertEqual(switch.config.on_start, "start")
        self.assertEqual(switch.config.on_stop, "start")
        self.assertEqual(changed, [switch])

    def test_check_socket_room(self):
        self.factory.runtime_dir = "/run/user/1000/virtualbricks/" + "x" * 40
        self.factory.check_socket_room("b" * 18)
        with self.assertRaises(errors.InvalidNameError) as cm:
            self.factory.check_socket_room("b" * 19)
        self.assertEqual(
            str(cm.exception),
            "The name is 19 bytes long, and the sockets of this project"
            " leave room for 18",
        )

    def test_check_name(self):
        self.factory.runtime_dir = "/run/vb"
        self.factory.new_brick("switch", "sw")
        self.assertEqual(
            self.factory.check_brick_name("switch", " my switch "), "my_switch"
        )
        self.assertEqual(
            self.factory.check_brick_name("Tap", "t" * 15), "t" * 15
        )
        # in use, too long for the sockets, refused by the kind
        for type, name in (
            ("switch", "sw"),
            ("switch", "s" * 100),
            ("tap", "t" * 16),
        ):
            with self.assertRaises(errors.InvalidNameError, msg=name):
                self.factory.check_brick_name(type, name)
        with self.assertRaises(errors.InvalidTypeError):
            self.factory.check_brick_name("nope", "nope")

    def test_a_project_opens_with_names_no_longer_taken(self):
        # a tap named before the check
        tap = self.factory.new_brick("tap", "t" * 16)
        self.assertEqual(tap.name, "t" * 16)

    def test_a_rename_follows_the_actions(self):
        # the bricks and the events that actions start or stop
        self.factory.runtime_dir = "/run/vb"
        self.factory.new_brick("switch", "sw1")
        later = self.factory.new_event("later")
        boot = self.factory.new_event("boot")
        boot.update_config(
            {
                "actions": [
                    StartAction("sw1"),
                    StopAction("later"),
                    ConsoleAction("brick set sw1 ports=4"),
                ]
            }
        )
        changed = []
        boot.changed.connect(changed.append)
        self.factory.rename_item(self.factory.get_brick("sw1"), "core")
        self.factory.rename_item(later, "after")
        self.assertEqual(
            boot.config.actions,
            [
                StartAction("core"),
                StopAction("after"),
                # a command stays as it is written
                ConsoleAction("brick set sw1 ports=4"),
            ],
        )
        self.assertEqual(changed, [boot, boot])

    def test_rename_brick(self):
        switch = self.factory.new_brick("switch", "sw")
        self.assertEqual(self.factory.rename_item(switch, "sw2"), "sw")
        self.assertEqual(switch.name, "sw2")

    def test_only_rename_changes_the_name(self):
        """The factory's indexes and the references follow a rename only."""

        for item in (
            self.factory.new_brick("switch", "sw"),
            self.factory.new_brick("qemu", "vm"),
            self.factory.new_event("ev"),
            self.factory.new_image("deb", "/lab/deb.qcow2"),
        ):
            name = item.name
            with self.assertRaises(AttributeError):
                item.name = "other"
            self.assertEqual(item.name, name)
            self.factory.rename_item(item, name + "2")
            self.assertEqual(item.name, name + "2")

    def test_autosave_timer(self):
        calls = []
        self.patch(projects, "autosave", calls.append)
        clock = task.Clock()

        class LoopingCall(task.LoopingCall):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.clock = clock

        self.patch(task, "LoopingCall", LoopingCall)
        timer = brickfactory.AutosaveTimer(self.factory, 10)
        clock.advance(10)
        self.assertEqual(calls, [self.factory])
        timer.stop()


CONFIG = {"verbosity": 0, "noterm": True}


class FakeAppLogger:

    def __init__(self, config):
        self.events = []

    def start(self, application):
        self.events.append("start")

    def stop(self):
        self.events.append("stop")


class FakeReactor:

    def __init__(self):
        self.triggers = []

    def addSystemEventTrigger(self, phase, event, callable, *args):
        self.triggers.append((phase, event, callable, args))


class Application(brickfactory.Application):

    logger_factory = FakeAppLogger

    def install_sys_hooks(self):
        # the tests keep the hooks of the test runner
        pass


class AppTestCase(unittest.TestCase):

    def setUp(self):
        self.root = isolate(self)
        reset_settings(self)
        self.logger = FakeLogger()
        self.patch(brickfactory, "logger", self.logger)
        self.patch(workspace, "logger", FakeLogger())
        self.manager = use_workspace(self)
        self.patch(brickfactory, "AutosaveTimer", lambda factory: None)
        # the socket where the Virtualbricks would listen, not a real one
        self.listened = []
        self.patch(
            control,
            "listen",
            lambda factory, socket, reactor: self.listened.append(socket),
        )
        self.app = Application(CONFIG)
        self.app.install_locale = lambda: None


class TestInstall(AppTestCase):

    def test_install_settings(self):
        write_settings(locations.legacy_settings_file(), "/srv/vb")
        self.app.install_settings()
        # the old settings are not read: that's the migration's job
        self.assertEqual(
            get_setting("workspace"),
            os.path.join(self.root, ".virtualbricks"),
        )
        self.assertTrue(os.path.isfile(locations.settings_file()))
        self.assertEqual(
            current_project(get_setting("workspace")),
            locations.DEFAULT_PROJECT,
        )

    def test_install_workspace(self):
        self.app.install_workspace()
        # the setting's, without one on the command line
        self.assertEqual(self.manager.path, get_setting("workspace"))
        app = Application({**CONFIG, "workspace": "/srv/labs"})
        app.install_workspace()
        self.assertEqual(self.manager.path, "/srv/labs")
        # the setting doesn't change
        self.assertEqual(
            get_setting("workspace"), os.path.join(self.root, ".virtualbricks")
        )

    def test_the_workspace_stays_for_the_run(self):
        # whose lock is that of its folder: a new setting is for the next
        # start
        self.app.install_workspace()
        set_setting("workspace", "/srv/labs")
        self.assertEqual(
            self.manager.path, os.path.join(self.root, ".virtualbricks")
        )

    def test_install_home(self):
        self.app.install_home()
        mode = os.stat(locations.runtime_dir()).st_mode
        self.assertTrue(stat.S_ISDIR(mode))
        self.assertEqual(stat.S_IMODE(mode), 0o700)
        # and the folder of the workspace, with its link, for its socket
        self.app.install_workspace()
        self.app.install_home()
        folder = locations.workspace_runtime_dir(self.manager.path)
        link = os.path.join(folder, locations.WORKSPACE_LINK)
        self.assertEqual(os.readlink(link), self.manager.path)


class TestMigrate(AppTestCase):

    def test_nothing_to_migrate(self):
        self.assertIsNone(self.app.migrate())
        self.assertEqual(self.logger.events, [])

    def test_migrate_in_place(self):
        workspace = os.path.join(self.root, ".virtualbricks")
        write_settings(locations.legacy_settings_file(), workspace, "lab")
        write_project(workspace, "lab", CONFIG1)
        self.app.migrate()
        self.assertTrue(
            os.path.isfile(
                os.path.join(workspace, "lab", locations.PROJECT_FILE)
            )
        )
        self.assertEqual(
            load_toml(locations.state_file())["workspaces"],
            [{"path": workspace, "current_project": "lab"}],
        )
        self.assertEqual(
            self.logger.formatted()[-1], "Migration: 1 of 1 projects migrated."
        )


class TestRun(AppTestCase):

    def test_the_migration_comes_first(self):
        calls = []
        migrated = defer.Deferred()

        def migrate():
            calls.append("migrate")
            return migrated

        def start(reactor):
            calls.append(("start", reactor))
            return "quit"

        self.app.migrate = migrate
        self.app._start = start
        d = self.app.run("reactor")
        self.assertEqual(calls, ["migrate"])
        migrated.callback(None)
        self.assertEqual(calls, ["migrate", ("start", "reactor")])
        self.assertEqual(self.successResultOf(d), "quit")

    def test_start_after_a_migration(self):
        workspace = os.path.join(self.root, ".virtualbricks")
        write_settings(locations.legacy_settings_file(), workspace, "lab")
        write_project(workspace, "lab", CONFIG1)
        reactor = FakeReactor()
        d = self.app.run(reactor)
        # it fires when the application quits
        self.assertNoResult(d)
        # the migrated settings and project are the ones in use
        self.assertEqual(get_setting("workspace"), workspace)
        self.assertEqual(self.manager.current.name, "lab")
        self.assertIsNotNone(self.manager.current.settings)
        self.assertEqual(self.app.logger.events, ["start"])
        callables = [trigger[2] for trigger in reactor.triggers]
        self.assertEqual(
            callables,
            [store_settings, self.manager.save, self.app.logger.stop],
        )
        self.assertTrue(os.path.isdir(locations.runtime_dir()))

    def test_fresh_start(self):
        d = self.app.run(FakeReactor())
        self.assertNoResult(d)
        self.assertEqual(self.manager.current.name, locations.DEFAULT_PROJECT)
        self.assertTrue(os.path.isfile(locations.settings_file()))
        self.assertEqual(self.logger.events, [])

    def test_start_in_the_workspace_of_the_command_line(self):
        other = os.path.join(self.root, "labs")
        # its old projects are migrated first, as the setting's would be
        write_project(other, "lab", CONFIG1)
        app = Application({**CONFIG, "workspace": other})
        app.install_locale = lambda: None
        self.assertNoResult(app.run(FakeReactor()))
        self.assertEqual(self.manager.path, other)
        self.assertEqual(
            self.manager.current.path, os.path.join(other, "new_project")
        )
        self.assertEqual(self.manager.names(), ["lab", "new_project"])
        self.assertEqual(current_project(other), "new_project")
        # the setting stays, in the file too
        default = os.path.join(self.root, ".virtualbricks")
        self.assertEqual(get_setting("workspace"), default)
        self.assertEqual(
            load_toml(locations.settings_file())["workspace"], default
        )
        self.assertFalse(os.path.exists(default))


class TestTheConsole(AppTestCase):

    def setUp(self):
        super().setUp()
        self.started = []
        self.out = io.StringIO()
        self.err = io.StringIO()
        self.patch(sys, "stdout", self.out)
        self.patch(sys, "stderr", self.err)

    def application(self, **config):
        app = Application({**CONFIG, **config})
        app.install_locale = lambda: None
        app.start_console = lambda factory: self.started.append(factory)
        return app

    def script(self, text):
        path = os.path.join(self.root, "lab.vb")
        with open(path, "w") as fp:
            fp.write(text)
        return path

    def test_the_console_starts(self):
        self.application(noterm=False).run(FakeReactor())
        self.assertEqual(len(self.started), 1)
        self.application(noterm=True).run(FakeReactor())
        self.assertEqual(len(self.started), 1)

    def test_the_control_sockets(self):
        # none without --listen
        self.application().run(FakeReactor())
        self.assertEqual(self.listened, [])
        sockets = [wire.Socket("/srv/lab.sock"), wire.Socket("/srv/lab2.sock")]
        self.application(sockets=sockets).run(FakeReactor())
        self.assertEqual(self.listened, sockets)

    def test_a_script_first(self):
        path = self.script("brick new switch\n# a comment\n\nbrick new tap\n")
        self.application(noterm=False, run=path).run(FakeReactor())
        self.assertEqual(self.out.getvalue(), "sw1\ntap1\n")
        self.assertEqual(
            [brick.name for brick in self.started[0].bricks], ["sw1", "tap1"]
        )

    def test_a_script_that_fails(self):
        path = self.script("brick new switch\nbrick nope\nbrick new tap\n")
        self.application(noterm=False, run=path).run(FakeReactor())
        self.assertEqual(self.out.getvalue(), "")
        self.assertEqual(
            self.err.getvalue().splitlines()[:2],
            [
                "sw1",
                f"Error: {path}:2: brick has no nope: its verbs are types,"
                " list, new, show, keys, set, unset, start, stop, kill, restart,"
                " pause, continue, suspend, resume, reset, monitor, connect,"
                " disconnect, card add, card set, card remove, rename, duplicate,"
                " delete",
            ],
        )
        # the console starts all the same
        self.assertEqual(len(self.started), 1)
