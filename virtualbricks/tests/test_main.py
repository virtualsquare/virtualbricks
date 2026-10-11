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

"""The start of Virtualbricks: the locks, the reactor, the mode, the run."""

import os
import pwd
import sys

from twisted.internet import defer, task
from twisted.logger import globalLogPublisher
from twisted.trial import unittest

from virtualbricks import (
    __version__,
    app,
    i18n,
    locations,
    locks,
    main,
    sockets,
)
from virtualbricks.cli import (
    COMMAND,
    GUI,
    NO_GUI,
    REMOTE,
    CommandLineOptions,
)
from virtualbricks.config import settings, workspace
from virtualbricks.config.settings import (
    AppSettings,
    current_project,
    get_setting,
)
from virtualbricks.config.tomlfile import load_toml
from virtualbricks.console import client
from virtualbricks.tests import (
    FakeLogger,
    hold_lock,
    isolate,
    lock_is_free,
    make_factory,
    release,
    reset_settings,
    use_workspace,
)
from virtualbricks.tests.gui import has_display
from virtualbricks.tests.migrate.fixtures import (
    CONFIG1,
    write_project,
    write_settings,
)

ME = pwd.getpwuid(os.getuid()).pw_name


class FakeReactor:

    def __init__(self):
        self.triggers = []

    def addSystemEventTrigger(self, phase, event, callable, *args):
        self.triggers.append((phase, event, callable, args))

    def shutdown(self):
        for phase in ("before", "during", "after"):
            for when, _event, callable, args in self.triggers:
                if when == phase:
                    callable(*args)


class TestTakeLocks(unittest.TestCase):

    def setUp(self):
        self.root = isolate(self)
        # the workspace of the settings
        self.workspace = os.path.join(self.root, ".virtualbricks")

    def take(self, **options):
        lock = main.take_locks(CommandLineOptions(NO_GUI, **options))
        self.addCleanup(release, lock)
        return lock

    def refused(self, **options):
        return str(self.assertRaises(SystemExit, self.take, **options))

    def in_workspace(self, folder):
        # as --workspace runs it
        return self.take(workspace=folder, lock=locks.WORKSPACE)

    def test_held_until_released(self):
        lock = self.take(lock=locks.USER)
        self.assertFalse(lock_is_free())
        lock.release()
        self.assertTrue(lock_is_free())

    def test_refused(self):
        hold_lock(self, locks.USER, "bob")
        self.assertEqual(
            self.refused(),
            "Virtualbricks is running on this machine with --lock user or "
            "--lock workspace, which let others run beside it: start this "
            f"one with one of them as well. Held by process {os.getpid()} of "
            f"{ME}.",
        )
        self.take(lock=locks.USER)

    def test_none_starts_anyway(self):
        hold_lock(self)
        self.take(lock=locks.NONE)
        # no lock in the workspace, not even the folder
        self.assertFalse(os.path.exists(self.workspace))

    def test_the_workspace_of_the_settings(self):
        lock = self.take()
        path = locations.workspace_lock_file(self.workspace)
        self.assertEqual(locks.holders(path), ((os.getpid(), ME),))
        lock.release()
        self.assertEqual(locks.holders(path), ())

    def test_the_workspace_of_the_settings_file(self):
        labs = os.path.join(self.root, "labs")
        settings.write_settings(
            AppSettings(workspace=labs), locations.settings_file()
        )
        self.take(lock=locks.USER)
        path = locations.workspace_lock_file(labs)
        self.assertEqual(locks.holders(path), ((os.getpid(), ME),))

    def test_side_by_side(self):
        a = os.path.join(self.root, "labs", "a")
        b = os.path.join(self.root, "labs", "b")
        self.in_workspace(a)
        # the folder is made for its lock
        self.assertTrue(os.path.isfile(locations.workspace_lock_file(a)))
        self.in_workspace(b)
        self.assertEqual(
            str(self.assertRaises(SystemExit, self.in_workspace, a)),
            "Another Virtualbricks is running in the workspace ~/labs/a: "
            "start this one in another, with --workspace. Held by process "
            f"{os.getpid()} of {ME}.",
        )
        # nor the one of the settings, in the system mode
        self.assertIn("--lock user or --lock workspace", self.refused())
        self.take(lock=locks.WORKSPACE)

    def test_the_settings_of_2_1_are_converted_alone(self):
        with open(locations.legacy_settings_file(), "w"):
            pass
        lock = self.in_workspace(os.path.join(self.root, "a"))
        # the user lock alone: no other workspace starts meanwhile
        error = self.assertRaises(
            SystemExit, self.in_workspace, os.path.join(self.root, "other")
        )
        self.assertIn("--lock user", str(error))
        # converted, then shared: another workspace starts
        settings.write_settings(AppSettings(), locations.settings_file())
        lock.share_user()
        self.in_workspace(os.path.join(self.root, "b"))

    def test_a_workspace_lock_that_cannot_be_opened(self):
        os.makedirs(self.workspace)
        path = locations.workspace_lock_file(self.workspace)
        os.symlink("elsewhere", path)
        self.assertEqual(
            self.refused(),
            f"Cannot take the lock {path}: Too many levels of symbolic links."
            " With --lock none, Virtualbricks runs without locks.",
        )
        # the locks taken before it are released
        self.assertTrue(lock_is_free())

    def test_a_lock_that_cannot_be_opened(self):
        os.symlink("elsewhere", locations.SYSTEM_LOCK_FILE)
        self.addCleanup(os.remove, locations.SYSTEM_LOCK_FILE)
        self.assertEqual(
            self.refused(),
            f"Cannot take the lock {locations.SYSTEM_LOCK_FILE}: Too many "
            "levels of symbolic links. With --lock none, Virtualbricks runs "
            "without locks.",
        )


class TestInstallReactor(unittest.TestCase):

    def setUp(self):
        import gi
        from twisted.internet import default, gireactor

        self.installed = []
        self.patch(default, "install", lambda: self.installed.append("epoll"))
        self.patch(gireactor, "install", lambda: self.installed.append("gi"))
        self.patch(
            gi,
            "require_version",
            lambda name, version: self.installed.append((name, version)),
        )

    def test_without_the_windows(self):
        main.install_reactor(CommandLineOptions(NO_GUI))
        self.assertEqual(self.installed, ["epoll"])

    def test_the_windows(self):
        for mode in (GUI, REMOTE):
            del self.installed[:]
            main.install_reactor(CommandLineOptions(mode))
            self.assertEqual(
                self.installed, [("Gtk", "3.0"), ("Gdk", "3.0"), "gi"]
            )

    def test_not_for_a_command(self):
        self.assertRaises(
            AssertionError, main.install_reactor, CommandLineOptions(COMMAND)
        )
        self.assertEqual(self.installed, [])


class TestInstallApplication(unittest.TestCase):

    def test_without_the_windows(self):
        application = main.install_application(CommandLineOptions(NO_GUI))
        self.assertIs(type(application), app.Application)
        self.assertEqual(application.options, CommandLineOptions(NO_GUI))

    def test_the_windows(self):
        if not has_display:  # pragma: no cover
            raise unittest.SkipTest("GTK can't open a display")
        from virtualbricks.gui import app as gui_app

        self.assertIs(
            type(main.install_application(CommandLineOptions(GUI))),
            gui_app.Application,
        )
        self.assertIs(
            type(main.install_application(CommandLineOptions(REMOTE))),
            gui_app.RemoteApplication,
        )

    def test_not_for_a_command(self):
        self.assertRaises(
            AssertionError,
            main.install_application,
            CommandLineOptions(COMMAND),
        )


class FakeLock:

    def release(self):
        pass


class RecordingApplication:
    """
    Each step of the run, in calls; migrated and ran are what the migration
    and the script give.
    """

    def __init__(self, options):
        self.options = options
        self.calls = []
        self.migrated = None
        self.ran = None

    def install_logging(self):
        self.calls.append("install_logging")

    def stop_logger(self):
        self.calls.append("stop_logger")

    def migrate(self):
        self.calls.append("migrate")
        return self.migrated

    def share_user_lock(self, lock):
        self.calls.append(("share_user_lock", lock))

    def install_settings(self):
        self.calls.append("install_settings")

    def store_settings(self):
        self.calls.append("store_settings")

    def install_workspace(self):
        self.calls.append("install_workspace")

    def install_factory(self, reactor):
        self.calls.append(("install_factory", reactor))
        self.factory = make_factory()
        return self.factory

    def open_last_project(self, factory):
        self.calls.append(("open_last_project", factory))

    def save_project(self, factory):
        self.calls.append("save_project")

    def start_listening(self, factory, reactor):
        self.calls.append(("start_listening", reactor))

    def install_autosave_timer(self, factory):
        self.calls.append("install_autosave_timer")

    def install_switch_wrapper_timer(self, factory):
        self.calls.append("install_switch_wrapper_timer")

    async def create_main_window(self, factory, reactor):
        self.calls.append(("create_main_window", reactor))

    def run_script(self, factory):
        self.calls.append("run_script")
        return self.ran

    def start_console(self, factory):
        self.calls.append("start_console")

    def install_sys_hooks(self):
        self.calls.append("install_sys_hooks")


class TestRun(unittest.TestCase):

    def setUp(self):
        self.reactor = FakeReactor()
        self.made = []
        # what the migration and the script give, once they are over
        self.migrated = None
        self.ran = defer.succeed([])
        self.patch(main, "install_application", self.application)
        self.events = []
        globalLogPublisher.addObserver(self.events.append)
        self.addCleanup(globalLogPublisher.removeObserver, self.events.append)

    def application(self, options):
        application = RecordingApplication(options)
        application.migrated = self.migrated
        application.ran = self.ran
        self.made.append(application)
        return application

    def run_main(self, lock=None, **options):
        options.setdefault("no_term", True)
        done = defer.ensureDeferred(
            main.run(self.reactor, CommandLineOptions(NO_GUI, **options), lock)
        )
        [application] = self.made
        return done, application

    def test_the_steps(self):
        lock = FakeLock()
        done, application = self.run_main(lock, no_term=False)
        self.assertEqual(
            application.calls,
            [
                "install_logging",
                "migrate",
                ("share_user_lock", lock),
                "install_settings",
                "install_workspace",
                ("install_factory", self.reactor),
                ("open_last_project", application.factory),
                ("start_listening", self.reactor),
                "install_autosave_timer",
                "install_switch_wrapper_timer",
                ("create_main_window", self.reactor),
                "start_console",
                "install_sys_hooks",
            ],
        )
        factory = application.factory
        self.assertEqual(
            self.reactor.triggers,
            [
                ("after", "shutdown", lock.release, ()),
                ("after", "shutdown", application.stop_logger, ()),
                ("before", "shutdown", application.store_settings, ()),
                ("before", "shutdown", application.save_project, (factory,)),
            ],
        )
        # it runs until the factory of the application quits
        self.assertNoResult(done)
        factory.quit()
        self.assertIsNone(self.successResultOf(done))

    def test_it_says_it_starts(self):
        self.run_main()
        [said] = [
            event
            for event in self.events
            if event.get("log_format") == main.starts
        ]
        self.assertEqual(said["log_namespace"], "virtualbricks.main")
        self.assertEqual(said["version"], __version__)
        self.assertEqual(said["reactor"], f"{__name__}.FakeReactor")

    def test_the_migration_comes_first(self):
        self.migrated = defer.Deferred()
        done, application = self.run_main()
        self.assertEqual(application.calls, ["install_logging", "migrate"])
        self.migrated.callback(None)
        self.assertEqual(application.calls[-1], "install_sys_hooks")
        self.assertNoResult(done)

    def test_without_a_lock(self):
        # the windows of another Virtualbricks
        _done, application = self.run_main()
        self.assertIn(("share_user_lock", None), application.calls)
        self.assertNotIn(
            "after",
            [
                when
                for when, _event, callable, _args in self.reactor.triggers
                if callable != application.stop_logger
            ],
        )

    def test_a_script_then_the_console(self):
        self.ran = defer.Deferred()
        _done, application = self.run_main(run="/srv/lab.vb", no_term=False)
        self.assertEqual(application.calls[-1], "run_script")
        self.ran.callback([])
        self.assertEqual(
            application.calls[-3:],
            ["run_script", "start_console", "install_sys_hooks"],
        )

    def test_no_console(self):
        _done, application = self.run_main(no_term=True)
        self.assertNotIn("start_console", application.calls)
        self.assertEqual(application.calls[-1], "install_sys_hooks")


class QuietApplication(app.Application):
    """Without the windows, as the tests run it: no log, timer or hook."""

    factories = []

    def install_logging(self):
        pass

    def install_autosave_timer(self, factory, interval=180):
        pass

    def install_switch_wrapper_timer(self, factory, interval=1.0):
        pass

    def open_last_project(self, factory):
        self.factories.append(factory)
        super().open_last_project(factory)

    def install_sys_hooks(self):
        # the tests keep the hooks of the test runner
        pass


class TestRunWithoutTheWindows(unittest.TestCase):

    def setUp(self):
        self.root = isolate(self)
        reset_settings(self)
        self.patch(app, "logger", FakeLogger())
        self.patch(workspace, "logger", FakeLogger())
        self.manager = use_workspace(self)
        self.listened = []
        self.patch(
            app,
            "listen",
            lambda factory, socket, reactor: self.listened.append(socket),
        )
        self.patch(QuietApplication, "factories", [])
        self.patch(main, "install_application", QuietApplication)
        self.reactor = FakeReactor()

    def run_main(self, **options):
        return defer.ensureDeferred(
            main.run(
                self.reactor,
                CommandLineOptions(NO_GUI, no_term=True, **options),
                None,
            )
        )

    def test_fresh_start(self):
        done = self.run_main()
        self.assertNoResult(done)
        self.assertEqual(self.manager.current.name, locations.DEFAULT_PROJECT)
        self.assertTrue(os.path.isfile(locations.settings_file()))
        self.assertTrue(os.path.isdir(locations.runtime_dir()))
        self.assertEqual(self.listened, [])

    def test_start_after_a_migration(self):
        folder = os.path.join(self.root, ".virtualbricks")
        write_settings(locations.legacy_settings_file(), folder, "lab")
        write_project(folder, "lab", CONFIG1)
        self.assertNoResult(self.run_main())
        # the migrated settings and project are the ones in use
        self.assertEqual(get_setting("workspace"), folder)
        self.assertEqual(self.manager.current.name, "lab")
        self.assertIsNotNone(self.manager.current.settings)

    def test_start_in_the_workspace_of_the_command_line(self):
        other = os.path.join(self.root, "labs")
        # its old projects are migrated first, as the setting's would be
        write_project(other, "lab", CONFIG1)
        self.assertNoResult(self.run_main(workspace=other))
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

    def test_the_control_sockets(self):
        given = (sockets.Socket(os.path.join(self.root, "lab.sock")),)
        self.run_main(listen=given)
        self.assertEqual(self.listened, list(given))

    def test_quit(self):
        done = self.run_main()
        [factory] = QuietApplication.factories
        factory.new_brick("switch", "sw1")
        factory.quit()
        self.assertIsNone(self.successResultOf(done))
        # at the shutdown, the settings and the project are saved
        self.reactor.shutdown()
        with open(self.manager.current.project_file) as fp:
            self.assertIn("sw1", fp.read())


class TestMain(unittest.TestCase):

    def setUp(self):
        isolate(self)
        self.calls = []
        self.patch(i18n, "install", lambda: self.calls.append("i18n"))
        self.patch(main, "take_locks", self.take_locks)
        self.patch(
            main,
            "install_reactor",
            lambda options: self.calls.append(("reactor", options.mode)),
        )
        self.patch(task, "react", self.react)
        self.patch(client, "main", self.client)

    def take_locks(self, options):
        self.calls.append(("locks", options.mode))
        return "the lock"

    def react(self, run, args):
        self.calls.append(("react", run, args[0].mode, args[1]))

    def client(self, words, target, script=None, workspace=None):
        self.calls.append(("client", words, target, script, workspace))
        return 3

    def main(self, *args):
        self.patch(sys, "argv", ["virtualbricks", *args])
        main.main()

    def test_without_the_windows(self):
        self.main("--no-gui")
        self.assertEqual(
            self.calls,
            [
                "i18n",
                ("locks", NO_GUI),
                ("reactor", NO_GUI),
                ("react", main.run, NO_GUI, "the lock"),
            ],
        )

    def test_the_windows(self):
        self.main()
        self.assertEqual(
            self.calls,
            [
                "i18n",
                ("locks", GUI),
                ("reactor", GUI),
                ("react", main.run, GUI, "the lock"),
            ],
        )

    def test_the_windows_of_another_virtualbricks(self):
        # no lock: the Virtualbricks there has its own
        self.main("--connect", "tcp:lab.example:8765")
        self.assertEqual(
            self.calls,
            [
                "i18n",
                ("reactor", REMOTE),
                ("react", main.run, REMOTE, None),
            ],
        )

    def test_a_command(self):
        # no lock and no reactor: its status is that of the answer
        error = self.assertRaises(SystemExit, self.main, "--command", "status")
        self.assertEqual(error.code, 3)
        self.assertEqual(
            self.calls, ["i18n", ("client", ("status",), None, None, None)]
        )

    def test_a_script(self):
        script = os.path.join(os.environ["HOME"], "lab.vb")
        with open(script, "w") as fp:
            fp.write("status\n")
        target = "tcp:lab.example:8765"
        error = self.assertRaises(
            SystemExit, self.main, "--connect", target, "--run", script
        )
        self.assertEqual(error.code, 3)
        self.assertEqual(
            self.calls,
            [
                "i18n",
                (
                    "client",
                    (),
                    sockets.parse_socket(target, True),
                    script,
                    None,
                ),
            ],
        )

    def test_a_wrong_command_line(self):
        error = self.assertRaises(SystemExit, self.main, "--nope")
        self.assertEqual(
            str(error), "virtualbricks: unrecognized arguments: --nope"
        )
        self.assertEqual(self.calls, ["i18n"])
