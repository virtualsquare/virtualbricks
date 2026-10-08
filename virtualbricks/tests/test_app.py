# Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
# Copyright (C) 2026 Virtualbricks team

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


"""The start of Virtualbricks: the locks, the migration, the project."""

import io
import os
import pwd
import stat
import sys

from twisted.internet import defer, task
from twisted.trial import unittest

from virtualbricks import app, locations, locks
from virtualbricks.config import settings, workspace
from virtualbricks.config.settings import (
    AppSettings,
    current_project,
    get_setting,
    set_setting,
    store_settings,
)
from virtualbricks.config.tomlfile import load_toml
from virtualbricks.config.workspace import projects
from virtualbricks.console import control, wire
from virtualbricks.tests import (
    BrickTestCase,
    FakeLogger,
    hold_lock,
    isolate,
    lock_is_free,
    reset_settings,
    use_workspace,
)
from virtualbricks.tests.migrate.fixtures import (
    CONFIG1,
    write_project,
    write_settings,
)

ME = pwd.getpwuid(os.getuid()).pw_name
# the tests of the locks take them; the others take none
CONFIG = {"verbosity": 0, "noterm": True, "lock": locks.NONE}


class FakeAppLogger:

    def __init__(self, config):
        self.events = []

    def start(self, reactor):
        self.events.append("start")

    def stop(self):
        self.events.append("stop")


class FakeReactor:

    def __init__(self):
        self.triggers = []

    def addSystemEventTrigger(self, phase, event, callable, *args):
        self.triggers.append((phase, event, callable, args))

    def shutdown(self):
        for phase, event, callable, args in self.triggers:
            callable(*args)


class Application(app.Application):

    logger_factory = FakeAppLogger

    def install_sys_hooks(self):
        # the tests keep the hooks of the test runner
        pass


class AppTestCase(unittest.TestCase):

    def setUp(self):
        self.root = isolate(self)
        reset_settings(self)
        self.logger = FakeLogger()
        self.patch(app, "logger", self.logger)
        self.patch(workspace, "logger", FakeLogger())
        self.manager = use_workspace(self)
        self.patch(app, "AutosaveTimer", lambda factory: None)
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
        application = Application({**CONFIG, "workspace": "/srv/labs"})
        application.install_workspace()
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
        reactor = FakeReactor()
        d = self.app.run(reactor)
        self.assertEqual(calls, ["migrate"])
        migrated.callback(None)
        self.assertEqual(calls, ["migrate", ("start", reactor)])
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
        # those before the shutdown; the locks go after
        callables = [
            trigger[2]
            for trigger in reactor.triggers
            if trigger[0] == "before"
        ]
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
        application = Application({**CONFIG, "workspace": other})
        application.install_locale = lambda: None
        self.assertNoResult(application.run(FakeReactor()))
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
        application = Application({**CONFIG, **config})
        application.install_locale = lambda: None
        application.start_console = lambda factory: self.started.append(
            factory
        )
        return application

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


class Started(Application):
    """It takes the locks and migrates; its start says the policy."""

    def __init__(self, started, config):
        super().__init__(config)
        self.started = started
        # called by migrate, as the startup migration runs
        self.migrating = None

    def install_locale(self):
        pass

    def migrate(self):
        if self.migrating is not None:
            self.migrating()

    def _start(self, reactor):
        self.started.append(self.config.get("lock", locks.SYSTEM))
        return defer.succeed(None)


class TestLock(unittest.TestCase):

    def setUp(self):
        self.root = isolate(self)
        self.reactor = FakeReactor()
        self.started = []
        # the workspace of the settings
        self.workspace = os.path.join(self.root, ".virtualbricks")

    def application(self, **config):
        return Started(self.started, config)

    def run_app(self, **config):
        return self.application(**config).run(self.reactor)

    def in_workspace(self, folder):
        # as --workspace runs it
        return self.run_app(workspace=folder, lock=locks.WORKSPACE)

    def test_held_until_shutdown(self):
        self.successResultOf(self.run_app(lock=locks.USER))
        self.assertEqual(self.started, [locks.USER])
        self.assertFalse(lock_is_free())
        self.reactor.shutdown()
        self.assertTrue(lock_is_free())

    def test_refused(self):
        hold_lock(self, locks.USER, "bob")
        failure = self.failureResultOf(self.run_app(), SystemExit)
        self.assertEqual(
            str(failure.value),
            "Virtualbricks is running on this machine with --lock user or "
            "--lock workspace, which let others run beside it: start this "
            f"one with one of them as well. Held by process {os.getpid()} of "
            f"{ME}.",
        )
        self.assertEqual(self.started, [])
        self.successResultOf(self.run_app(lock=locks.USER))
        self.assertEqual(self.started, [locks.USER])
        self.reactor.shutdown()

    def test_none_starts_anyway(self):
        hold_lock(self)
        self.successResultOf(self.run_app(lock=locks.NONE))
        self.assertEqual(self.started, [locks.NONE])
        # no lock in the workspace, not even the folder
        self.assertFalse(os.path.exists(self.workspace))

    def test_the_workspace_of_the_settings(self):
        self.successResultOf(self.run_app())
        path = locations.workspace_lock_file(self.workspace)
        self.assertEqual(locks.holders(path), ((os.getpid(), ME),))
        self.reactor.shutdown()
        self.assertEqual(locks.holders(path), ())

    def test_the_workspace_of_the_settings_file(self):
        labs = os.path.join(self.root, "labs")
        settings.write_settings(
            AppSettings(workspace=labs), locations.settings_file()
        )
        self.successResultOf(self.run_app(lock=locks.USER))
        path = locations.workspace_lock_file(labs)
        self.assertEqual(locks.holders(path), ((os.getpid(), ME),))
        self.reactor.shutdown()

    def test_side_by_side(self):
        a = os.path.join(self.root, "labs", "a")
        b = os.path.join(self.root, "labs", "b")
        self.successResultOf(self.in_workspace(a))
        # the folder is made for its lock
        self.assertTrue(os.path.isfile(locations.workspace_lock_file(a)))
        self.successResultOf(self.in_workspace(b))
        self.assertEqual(self.started, [locks.WORKSPACE, locks.WORKSPACE])
        failure = self.failureResultOf(self.in_workspace(a), SystemExit)
        self.assertEqual(
            str(failure.value),
            "Another Virtualbricks is running in the workspace ~/labs/a: "
            "start this one in another, with --workspace. Held by process "
            f"{os.getpid()} of {ME}.",
        )
        # nor the one of the settings, in the system mode
        failure = self.failureResultOf(self.run_app(), SystemExit)
        self.assertIn("--lock user or --lock workspace", str(failure.value))
        self.successResultOf(self.run_app(lock=locks.WORKSPACE))
        self.assertEqual(len(self.started), 3)
        self.reactor.shutdown()

    def test_the_settings_of_2_1_are_converted_alone(self):
        with open(locations.legacy_settings_file(), "w"):
            pass
        refused = []

        def migrating():
            # the user lock alone: no other workspace starts meanwhile
            refused.append(self.in_workspace(os.path.join(self.root, "other")))
            settings.write_settings(AppSettings(), locations.settings_file())

        application = self.application(
            workspace=os.path.join(self.root, "a"), lock=locks.WORKSPACE
        )
        application.migrating = migrating
        self.successResultOf(application.run(self.reactor))
        [d] = refused
        failure = self.failureResultOf(d, SystemExit)
        self.assertIn("--lock user", str(failure.value))
        # then shared: another workspace starts
        self.successResultOf(self.in_workspace(os.path.join(self.root, "b")))
        self.assertEqual(self.started, [locks.WORKSPACE, locks.WORKSPACE])
        self.reactor.shutdown()

    def test_a_workspace_lock_that_cannot_be_opened(self):
        os.makedirs(self.workspace)
        path = locations.workspace_lock_file(self.workspace)
        os.symlink("elsewhere", path)
        failure = self.failureResultOf(self.run_app(), SystemExit)
        self.assertEqual(
            str(failure.value),
            f"Cannot take the lock {path}: Too many levels of symbolic links."
            " With --lock none, Virtualbricks runs without locks.",
        )
        self.assertEqual(self.started, [])

    def test_a_lock_that_cannot_be_opened(self):
        os.symlink("elsewhere", locations.SYSTEM_LOCK_FILE)
        self.addCleanup(os.remove, locations.SYSTEM_LOCK_FILE)
        failure = self.failureResultOf(self.run_app(), SystemExit)
        self.assertEqual(
            str(failure.value),
            f"Cannot take the lock {locations.SYSTEM_LOCK_FILE}: Too many "
            "levels of symbolic links. With --lock none, Virtualbricks runs "
            "without locks.",
        )
        self.assertEqual(self.started, [])


class TestAutosave(BrickTestCase):

    def test_autosave_timer(self):
        calls = []
        self.patch(projects, "autosave", calls.append)
        clock = task.Clock()

        class LoopingCall(task.LoopingCall):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.clock = clock

        self.patch(task, "LoopingCall", LoopingCall)
        timer = app.AutosaveTimer(self.factory, 10)
        clock.advance(10)
        self.assertEqual(calls, [self.factory])
        timer.stop()
