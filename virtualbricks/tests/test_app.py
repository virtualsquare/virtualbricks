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

"""The steps of a Virtualbricks without the windows: app.Application."""

import io
import os
import stat
import sys
import threading

from twisted.internet import defer, task
from twisted.logger import LogLevel
from twisted.trial import unittest

from virtualbricks import app, locations, locks, sockets
from virtualbricks.brickfactory import BrickFactory
from virtualbricks.cli import NO_GUI, CommandLineOptions
from virtualbricks.config import settings, workspace
from virtualbricks.config.settings import (
    current_project,
    get_setting,
    set_setting,
)
from virtualbricks.config.tomlfile import load_toml
from virtualbricks.tests import (
    FakeLogger,
    isolate,
    make_factory,
    reset_settings,
    use_workspace,
)
from virtualbricks.tests.migrate.fixtures import (
    CONFIG1,
    write_project,
    write_settings,
)

# what the observer of --logger, named by test_a_logger, was given
OBSERVED = []


def observer(event):
    OBSERVED.append(event)


def event(text, level=LogLevel.info):
    return {
        "log_format": text,
        "log_level": level,
        "log_namespace": "virtualbricks.tests",
        "log_time": 0.0,
    }


class AppTestCase(unittest.TestCase):

    def setUp(self):
        self.root = isolate(self)
        reset_settings(self)
        self.logger = FakeLogger()
        self.patch(app, "logger", self.logger)
        self.patch(workspace, "logger", FakeLogger())
        self.manager = use_workspace(self)

    def application(self, mode=NO_GUI, **options):
        # the folder that take_locks() gives: --workspace, or the setting's
        folder = options.get("workspace") or os.path.join(
            self.root, ".virtualbricks"
        )
        return app.Application(CommandLineOptions(mode, **options), folder)


class TestLogLevel(unittest.TestCase):

    def test_the_verbosity(self):
        self.assertEqual(app.log_level(2), LogLevel.debug)
        self.assertEqual(app.log_level(1), LogLevel.debug)
        self.assertEqual(app.log_level(0), LogLevel.info)
        self.assertEqual(app.log_level(-1), LogLevel.warn)
        self.assertEqual(app.log_level(-2), LogLevel.error)


class TestLogging(AppTestCase):

    def test_none(self):
        # without --logfile and --logger, nothing is written
        self.assertEqual(self.application().get_log_observers(), [])

    def test_a_logger(self):
        # the observer itself, as --logger names it, which gets everything
        self.patch(sys.modules[__name__], "OBSERVED", [])
        name = f"{__name__}.observer"
        [found] = self.application(logger=name).get_log_observers()
        self.assertIs(found, observer)

    def test_a_logger_that_isnt_there(self):
        error = self.assertRaises(
            SystemExit,
            self.application(logger="no.such.thing").get_log_observers,
        )
        self.assertTrue(
            str(error).startswith(
                "Logger 'no.such.thing' could not be imported: "
            ),
            str(error),
        )

    def test_the_standard_output(self):
        out = io.StringIO()
        self.patch(sys, "stdout", out)
        [found] = self.application(logfile="-").get_log_observers()
        found(event("seen"))
        found(event("not seen", LogLevel.debug))
        self.assertIn("seen", out.getvalue())
        self.assertNotIn("not seen", out.getvalue())

    def test_a_file(self):
        path = os.path.join(self.root, "vb.log")
        [found] = self.application(
            logfile=path, verbosity=1
        ).get_log_observers()
        found(event("a detail", LogLevel.debug))
        with open(path) as fp:
            self.assertIn("a detail", fp.read())

    def test_quieter(self):
        out = io.StringIO()
        self.patch(sys, "stdout", out)
        [found] = self.application(
            logfile="-", verbosity=-1
        ).get_log_observers()
        found(event("info"))
        found(event("a warning", LogLevel.warn))
        self.assertEqual(out.getvalue().count("\n"), 1)
        self.assertIn("a warning", out.getvalue())

    def test_install_logging(self):
        begun = []

        class Beginner:
            def beginLoggingTo(self, observers, redirectStandardIO=True):
                begun.append((observers, redirectStandardIO))

        self.patch(app, "globalLogBeginner", Beginner())
        self.application(logger=f"{__name__}.observer").install_logging()
        # the console uses the standard streams
        self.assertEqual(begun, [([observer], False)])

    def test_stop_logger(self):
        self.application().stop_logger()
        self.assertEqual(self.logger.formatted(), [app.shut_down])


class TestHooks(AppTestCase):

    def setUp(self):
        super().setUp()
        self.patch(sys, "excepthook", sys.excepthook)
        self.patch(threading, "excepthook", threading.excepthook)
        self.default = []
        self.patch(
            sys,
            "__excepthook__",
            lambda *args: self.default.append(args[0]),
        )

    def uncaught(self):
        """What the error logged says: its failure, and its message."""

        [(level, text, fields)] = self.logger.events
        self.assertEqual((level, text), ("error", app.uncaught_exception))
        return fields["log_failure"].type, fields["error"]()

    def test_install_sys_hooks(self):
        self.application().install_sys_hooks()
        self.assertIs(sys.excepthook, app.excepthook)
        self.assertIs(threading.excepthook, app.thread_excepthook)

    def test_an_uncaught_exception(self):
        try:
            raise ValueError("boom")
        except ValueError:
            app.excepthook(*sys.exc_info())
        self.assertEqual(self.uncaught(), (ValueError, "boom"))
        self.assertEqual(self.default, [])

    def test_exit_and_interrupt(self):
        # as Python says them
        app.excepthook(SystemExit, SystemExit(2), None)
        app.excepthook(KeyboardInterrupt, KeyboardInterrupt(), None)
        self.assertEqual(self.default, [SystemExit, KeyboardInterrupt])
        self.assertEqual(self.logger.events, [])

    def test_a_thread(self):
        # a thread may exit silently, as with threading's own hook
        app.thread_excepthook(
            threading.ExceptHookArgs([SystemExit, SystemExit(), None, None])
        )
        self.assertEqual(self.logger.events, [])
        self.assertEqual(self.default, [])
        app.thread_excepthook(
            threading.ExceptHookArgs(
                [ValueError, ValueError("in a thread"), None, None]
            )
        )
        self.assertEqual(self.uncaught(), (ValueError, "in a thread"))


class TestMigrate(AppTestCase):

    def test_nothing_to_migrate(self):
        self.assertIsNone(self.application().migrate())
        self.assertEqual(self.logger.events, [])

    def test_migrate_in_place(self):
        folder = os.path.join(self.root, ".virtualbricks")
        write_settings(locations.legacy_settings_file(), folder, "lab")
        write_project(folder, "lab", CONFIG1)
        self.assertIsNone(self.application().migrate())
        self.assertTrue(
            os.path.isfile(os.path.join(folder, "lab", locations.PROJECT_FILE))
        )
        self.assertEqual(
            load_toml(locations.state_file())["workspaces"],
            [{"path": folder, "current_project": "lab"}],
        )
        self.assertEqual(
            self.logger.formatted()[-1], "Migration: 1 of 1 projects migrated."
        )


class FakeLock:

    def __init__(self, error=None):
        self.error = error
        self.shared = 0

    def share_user(self):
        if self.error is not None:
            raise self.error
        self.shared += 1


class TestShareUserLock(AppTestCase):

    def test_no_lock(self):
        # the windows of another Virtualbricks take none
        self.application().share_user_lock(None)

    def test_shared(self):
        lock = FakeLock()
        self.application().share_user_lock(lock)
        self.assertEqual(lock.shared, 1)

    def test_taken_in_between(self):
        held = locks.Held(locks.WORKSPACE, locks.USER, "/run/vb/user.lock")
        error = self.assertRaises(
            SystemExit,
            self.application().share_user_lock,
            FakeLock(held),
        )
        self.assertEqual(str(error), str(held))


class TestSettings(AppTestCase):

    def test_install_settings(self):
        write_settings(locations.legacy_settings_file(), "/srv/vb")
        self.application().install_settings()
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

    def test_store_settings(self):
        application = self.application()
        application.install_settings()
        set_setting("terminal", "xterm")
        application.store_settings()
        self.assertEqual(
            load_toml(locations.settings_file())["terminal"], "xterm"
        )

    def test_install_workspace(self):
        self.application().install_workspace()
        # the setting's, without one on the command line
        self.assertEqual(self.manager.path, get_setting("workspace"))
        other = os.path.join(self.root, "labs")
        self.application(workspace=other).install_workspace()
        self.assertEqual(self.manager.path, other)
        # the setting doesn't change
        self.assertEqual(
            get_setting("workspace"), os.path.join(self.root, ".virtualbricks")
        )

    def test_the_workspace_stays_for_the_run(self):
        # whose lock is that of its folder: a new setting is for the next
        # start
        self.application().install_workspace()
        set_setting("workspace", "/srv/labs")
        self.assertEqual(
            self.manager.path, os.path.join(self.root, ".virtualbricks")
        )

    def test_the_runtime_folder(self):
        self.application().install_workspace()
        mode = os.stat(locations.runtime_dir()).st_mode
        self.assertTrue(stat.S_ISDIR(mode))
        self.assertEqual(stat.S_IMODE(mode), 0o700)
        # and the folder of the workspace, with its link, for its socket
        folder = locations.workspace_runtime_dir(self.manager.path)
        link = os.path.join(folder, locations.WORKSPACE_LINK)
        self.assertEqual(os.readlink(link), self.manager.path)


class TestFactory(AppTestCase):

    def test_install_factory(self):
        # the bricks of this process, whose quit ends the run
        application = self.application()
        factory = application.install_factory("reactor")
        self.assertIsInstance(factory, BrickFactory)
        self.assertNoResult(application.done)
        factory.quit()
        self.assertIsNone(self.successResultOf(application.done))


class TestProject(AppTestCase):

    def setUp(self):
        super().setUp()
        self.app = self.application()
        self.app.install_settings()
        self.app.install_workspace()
        self.factory = make_factory(self)

    def test_open_last_project(self):
        self.app.open_last_project(self.factory)
        self.assertEqual(self.manager.current.name, locations.DEFAULT_PROJECT)

    def test_save_project(self):
        self.app.open_last_project(self.factory)
        self.factory.new_brick("switch", "sw1")
        self.app.save_project(self.factory)
        with open(self.manager.current.project_file) as fp:
            self.assertIn("sw1", fp.read())


class TestListen(AppTestCase):

    def setUp(self):
        super().setUp()
        self.listened = []
        self.patch(
            app,
            "listen",
            lambda factory, socket, reactor: self.listened.append(
                (factory, socket, reactor)
            ),
        )

    def test_none_without_it(self):
        self.application().start_listening("factory", "reactor")
        self.assertEqual(self.listened, [])

    def test_each_socket(self):
        given = (
            sockets.Socket("/srv/lab.sock"),
            sockets.Socket("/srv/lab2.sock"),
        )
        self.application(listen=given).start_listening("factory", "reactor")
        self.assertEqual(
            self.listened,
            [("factory", socket, "reactor") for socket in given],
        )


class TestTimers(AppTestCase):

    def setUp(self):
        super().setUp()
        self.clock = clock = task.Clock()

        class LoopingCall(task.LoopingCall):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.clock = clock

        self.patch(task, "LoopingCall", LoopingCall)
        self.calls = []

    def test_autosave(self):
        self.patch(app.projects, "autosave", lambda f: self.calls.append(f))
        self.application().install_autosave_timer("factory", 10)
        self.assertEqual(self.calls, [])
        self.clock.advance(10)
        self.assertEqual(self.calls, ["factory"])

    def test_the_switch_wrappers(self):
        self.patch(app, "look_all", lambda f: self.calls.append(f))
        self.application().install_switch_wrapper_timer("factory")
        self.assertEqual(self.calls, [])
        self.clock.advance(app.LOOK_EVERY)
        self.clock.advance(app.LOOK_EVERY)
        self.assertEqual(self.calls, ["factory", "factory"])


class TestTheConsole(AppTestCase):

    def setUp(self):
        super().setUp()
        # the bricks are those of an open project, with its settings
        settings.use_project(settings.ProjectSettings())
        self.factory = make_factory(self)
        self.out = io.StringIO()
        self.err = io.StringIO()
        self.patch(sys, "stdout", self.out)
        self.patch(sys, "stderr", self.err)

    def script(self, text):
        path = os.path.join(self.root, "lab.vb")
        with open(path, "w") as fp:
            fp.write(text)
        return path

    def test_no_window(self):
        created = self.application().create_main_window(self.factory, None)
        self.assertIsNone(self.successResultOf(defer.ensureDeferred(created)))

    def test_a_script(self):
        path = self.script("brick new switch\n# a comment\n\nbrick new tap\n")
        self.successResultOf(
            self.application(run=path).run_script(self.factory)
        )
        self.assertEqual(self.out.getvalue(), "sw1\ntap1\n")
        self.assertEqual(
            [brick.name for brick in self.factory.bricks], ["sw1", "tap1"]
        )

    def test_a_script_that_fails(self):
        path = self.script("brick new switch\nbrick nope\nbrick new tap\n")
        self.successResultOf(
            self.application(run=path).run_script(self.factory)
        )
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

    def test_start_console(self):
        started = []
        self.patch(
            app,
            "start",
            lambda factory, namespace: started.append((factory, namespace)),
        )
        self.application().start_console(self.factory)
        self.assertEqual(started, [(self.factory, {})])
