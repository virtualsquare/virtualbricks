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

import os
import stat

from twisted.internet import defer, task
from twisted.trial import unittest

from virtualbricks import brickfactory, errors, locations
from virtualbricks.config.workspace import projects
from virtualbricks.config import workspace
from virtualbricks.config.settings import (
    current_project,
    get_setting,
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
        self.factory.new_disk_image("boot2", "/x")
        self.assertIs(self.factory.get_event_by_name("boot"), event)
        self.assertIsNone(self.factory.get_event_by_name("boot2"))

    def test_next_name(self):
        self.factory.new_brick("switch", "sw")
        self.factory.new_brick("switch", "sw.1")
        self.assertEqual(self.factory.next_name("sw"), "sw.2")

    def test_dup_brick(self):
        vm = self.factory.new_brick("qemu", "vm")
        vm.set({"memory": 256, "usb_devices": [UsbDevice("1d6b:0002", "hub")]})
        copy = self.factory.dup_brick(vm)
        self.assertEqual(copy.config.memory, 256)
        self.assertEqual(copy.config.usb_devices, vm.config.usb_devices)
        self.assertIsNot(copy.config.usb_devices, vm.config.usb_devices)

    def test_rename_event_updates_the_bricks(self):
        event = self.factory.new_event("boot")
        switch = self.factory.new_brick("switch", "sw")
        switch.set({"on_start": "boot", "on_stop": "boot"})
        other = self.factory.new_event("other")
        other.set({"delay": 1})
        changed = []
        switch.changed.connect(changed.append)
        self.factory.rename(event, "start")
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

    def test_rename_brick(self):
        switch = self.factory.new_brick("switch", "sw")
        self.assertEqual(self.factory.rename(switch, "sw2"), "sw")
        self.assertEqual(switch.name, "sw2")

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


CONFIG = {"verbosity": 0, "daemon": False, "noterm": True}


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
        self.assertEqual(current_project(), locations.DEFAULT_PROJECT)

    def test_install_home(self):
        self.app.install_home()
        mode = os.stat(locations.runtime_dir()).st_mode
        self.assertTrue(stat.S_ISDIR(mode))
        self.assertEqual(stat.S_IMODE(mode), 0o700)


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
            load_toml(locations.state_file())["current_project"], "lab"
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
