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

"""
The steps of a Virtualbricks with the windows: gui.app.Application, the
error dialogs and the console through the main window.
"""

import os
import types

from twisted.internet import defer
from twisted.logger import LogLevel
from twisted.trial import unittest

from virtualbricks import ksm, locations
from virtualbricks.cli import GUI, CommandLineOptions
from virtualbricks.config import settings
from virtualbricks.config.settings import set_current_project, set_setting
from virtualbricks.console import projects as console_projects
from virtualbricks.engine import LocalEngine
from virtualbricks.tests import FakeLogger
from virtualbricks.tests.gui import GuiTestCase, has_display
from virtualbricks.tests.migrate.fixtures import (
    CONFIG1,
    write_project,
    write_settings,
)

if has_display:
    from gi.repository import Gtk

    from virtualbricks.gui import app as gui_app
    from virtualbricks.gui.messages import MessageLog
    from virtualbricks.gui.trash import DesktopTrash
    from virtualbricks.migrate import gui as migrate_gui


def application(mode=GUI, **options):
    return gui_app.Application(CommandLineOptions(mode, **options))


def error(text, level=LogLevel.error, **fields):
    return {
        "log_format": text,
        "log_level": level,
        "log_namespace": "virtualbricks.tests",
        **fields,
    }


class FakeWindow:
    """A toplevel, as find_parent asks it."""

    def __init__(self, role=None, active=False, visible=True, popup=False):
        self.role = role
        self.active = active
        self.visible = visible
        self.kind = Gtk.WindowType.POPUP if popup else Gtk.WindowType.TOPLEVEL

    def get_window_type(self):
        return self.kind

    def get_visible(self):
        return self.visible

    def is_active(self):
        return self.active

    def get_role(self):
        return self.role


class TestFindParent(GuiTestCase):
    """The parent of an error dialog, among the toplevels of the process."""

    def setUp(self):
        super().setUp()
        self.toplevels = []
        window = type(
            "Window",
            (FakeWindow,),
            {"list_toplevels": staticmethod(lambda: self.toplevels)},
        )
        self.patch(
            gui_app,
            "Gtk",
            types.SimpleNamespace(Window=window, WindowType=Gtk.WindowType),
        )
        self.window = window

    def test_none(self):
        self.assertIsNone(gui_app.find_parent())

    def test_the_window_the_user_is_in(self):
        main = self.window(gui_app.MAIN_ROLE)
        settings = self.window(active=True)
        self.toplevels[:] = [main, settings]
        self.assertIs(gui_app.find_parent(), settings)

    def test_else_the_main_window(self):
        main = self.window(gui_app.MAIN_ROLE)
        self.toplevels[:] = [self.window(), main]
        self.assertIs(gui_app.find_parent(), main)

    def test_not_menus_hidden_windows_or_widgets(self):
        self.toplevels[:] = [
            # what isn't a window, as the stubs say it may be
            object(),
            self.window(gui_app.MAIN_ROLE, active=True, popup=True),
            self.window(gui_app.MAIN_ROLE, active=True, visible=False),
            self.window(),
        ]
        self.assertIsNone(gui_app.find_parent())


class FakeDialog:

    made = []

    def __init__(self, **properties):
        self.properties = properties
        self.handlers = {}
        self.shown = False
        self.destroyed = False
        self.made.append(self)

    def set_property(self, name, value):
        self.properties[name] = value

    def connect(self, signal, handler):
        self.handlers[signal] = handler

    def show(self):
        self.shown = True

    def destroy(self):
        self.destroyed = True


class TestMessageDialogObserver(GuiTestCase):

    def setUp(self):
        super().setUp()
        self.patch(FakeDialog, "made", [])
        self.patch(
            gui_app,
            "Gtk",
            types.SimpleNamespace(
                MessageDialog=FakeDialog,
                MessageType=Gtk.MessageType,
                ButtonsType=Gtk.ButtonsType,
            ),
        )
        self.patch(gui_app, "find_parent", lambda: "the parent")

    def test_a_dialog(self):
        gui_app.MessageDialogObserver()(
            error("Cannot open {name}", name="lab")
        )
        [dialog] = FakeDialog.made
        self.assertEqual(
            dialog.properties,
            {
                "transient_for": "the parent",
                "modal": True,
                "message_type": Gtk.MessageType.ERROR,
                "buttons": Gtk.ButtonsType.CLOSE,
                "text": "Cannot open lab",
            },
        )
        self.assertTrue(dialog.shown)
        # Close
        dialog.handlers["response"](dialog, Gtk.ResponseType.CLOSE)
        self.assertTrue(dialog.destroyed)


class TestNow(unittest.TestCase):

    if not has_display:  # pragma: no cover
        skip = "GTK can't open a display"

    def test_a_result(self):
        self.assertEqual(gui_app._now(defer.succeed("report")), "report")

    def test_a_failure(self):
        self.assertRaises(
            ValueError, gui_app._now, defer.fail(ValueError("no"))
        )


class TestWindowFrontend(GuiTestCase):
    """The console opens, makes and saves projects through the window."""

    def test_through_the_window(self):
        calls = []

        def open_project(name):
            calls.append(("open", name))
            return defer.succeed("report")

        def new_project(name):
            calls.append(("new", name))
            return defer.succeed(None)

        def save_project():
            calls.append(("save",))
            return defer.succeed(None)

        frontend = gui_app.WindowFrontend(
            open_project=open_project,
            new_project=new_project,
            save_project=save_project,
        )
        self.assertEqual(frontend.open("lab", self.factory), "report")
        frontend.new("lab2", self.factory)
        frontend.save(self.factory)
        self.assertEqual(calls, [("open", "lab"), ("new", "lab2"), ("save",)])


class Recording:
    """An observer that keeps the events, in got."""

    def __init__(self, *args):
        self.args = args
        self.got = []

    def __call__(self, event):
        self.got.append(event)


class TestLogObservers(GuiTestCase):

    def setUp(self):
        super().setUp()
        self.patch(gui_app, "MessageLogObserver", Recording)
        self.patch(gui_app, "MessageDialogObserver", Recording)
        self.app = application()
        self.messages, self.dialogs = self.app.get_log_observers()

    def emit(self, event):
        self.messages(event)
        self.dialogs(event)

    def test_the_messages(self):
        # those of the window Logs, of this run
        self.assertIsInstance(self.app.gui_message_log, MessageLog)
        self.assertEqual(
            self.messages._observer.args, (self.app.gui_message_log,)
        )
        self.emit(error("debug", LogLevel.debug))
        self.emit(error("info", LogLevel.info))
        self.assertEqual(
            [event["log_format"] for event in self.messages._observer.got],
            ["info"],
        )

    def test_the_errors(self):
        self.emit(error("a warning", LogLevel.warn))
        self.emit(error("an error"))
        self.emit(error("critical", LogLevel.critical))
        self.emit(error("hidden", hide_to_user=True))
        self.assertEqual(
            [event["log_format"] for event in self.dialogs._observer.got],
            ["an error", "critical"],
        )

    def test_and_the_file(self):
        path = os.path.join(self.root, "vb.log")
        found = application(logfile=path).get_log_observers()
        self.assertEqual(len(found), 3)


class TestMigrate(GuiTestCase):

    def setUp(self):
        super().setUp()
        self.shown = []
        self.patch(
            migrate_gui.MigrationWindow,
            "show",
            lambda window: self.shown.append(window),
        )

    def old_files(self):
        folder = os.path.join(self.root, ".virtualbricks")
        write_settings(locations.legacy_settings_file(), folder, "lab")
        write_project(folder, "lab", CONFIG1)

    def test_nothing_to_migrate(self):
        self.assertIsNone(application().migrate())
        self.assertEqual(self.shown, [])

    def test_show_the_migration(self):
        self.old_files()
        closed = application().migrate()
        window = self.shown[0]
        self.addCleanup(window.window.destroy)
        self.assertTrue(window.fixed)
        self.assertIs(closed, window.closed)
        self.assertEqual(
            [item.name for item in window.migration.items],
            [locations.LEGACY_SETTINGS_FILE, "lab"],
        )


class TestOpenLastProject(GuiTestCase):
    """The GUI opens the last project, or says why in the Projects window."""

    def setUp(self):
        super().setUp()
        self.logger = FakeLogger()
        self.patch(gui_app, "logger", self.logger)
        self.app = application()

    def test_the_last_project(self):
        self.manager.create("lab")
        set_current_project(self.manager.path, "lab")
        self.app.open_last_project(self.factory)
        self.assertEqual(self.manager.current.name, "lab")
        self.assertIsNone(self.app.start_up_problem)

    def test_the_first_run(self):
        self.app.open_last_project(self.factory)
        self.assertEqual(self.manager.current.name, "new_project")
        self.assertIsNone(self.app.start_up_problem)

    def test_a_project_that_is_gone(self):
        set_current_project(self.manager.path, "gone")
        self.app.open_last_project(self.factory)
        self.assertIsNone(self.manager.current)
        self.assertIn(
            '"gone" that was open last doesn\'t exist',
            self.app.start_up_problem,
        )
        self.assertEqual(self.logger.levels(), ["warn"])
        # no new_project_N
        self.assertEqual(self.manager.names(), [])

    def test_a_project_that_cannot_be_read(self):
        os.makedirs(self.manager.project_path("lab"))
        with open(self.manager._project_file("lab"), "w") as fp:
            fp.write("[bricks\n")
        set_current_project(self.manager.path, "lab")
        self.app.open_last_project(self.factory)
        self.assertIn(
            '"lab" that was open last can\'t be opened',
            self.app.start_up_problem,
        )

    def test_a_bad_name(self):
        set_current_project(self.manager.path, "../x")
        self.app.open_last_project(self.factory)
        self.assertIsNotNone(self.app.start_up_problem)


class FakeMainWindow:

    made = []

    def __init__(self, engine, messages):
        self.engine = engine
        self.messages = messages
        self.calls = []
        self.made.append(self)

    def set_title(self):
        self.calls.append("title")

    def show_start_up_problem(self, message):
        self.calls.append(("problem", message))

    def on_open(self, name):
        pass

    def on_new(self, name, description=""):
        pass

    def on_save(self):
        pass


class TestCreateMainWindow(GuiTestCase):

    def setUp(self):
        super().setUp()
        self.patch(FakeMainWindow, "made", [])
        self.patch(gui_app, "MainWindow", FakeMainWindow)
        # the console opens projects through the main window
        self.patch(console_projects, "frontend", console_projects.frontend)
        self.checked = defer.Deferred()
        self.app = application()
        self.app.gui_message_log = MessageLog()
        self.app.check_prerequisites = lambda: self.checked

    def create(self):
        return defer.ensureDeferred(
            self.app.create_main_window(self.factory, "reactor")
        )

    def test_the_main_window(self):
        created = self.create()
        [window] = FakeMainWindow.made
        self.assertIs(self.app.main_window, window)
        self.assertIsInstance(window.engine, LocalEngine)
        self.assertIs(window.engine.factory, self.factory)
        self.assertIs(window.messages, self.app.gui_message_log)
        self.assertEqual(window.calls, ["title"])
        # removing a project moves it to the trash of the desktop
        self.assertIsInstance(self.manager.trasher, DesktopTrash)
        self.assertIsInstance(
            console_projects.frontend, gui_app.WindowFrontend
        )
        frontend = console_projects.frontend
        self.assertEqual(
            [
                frontend.open_project,
                frontend.new_project,
                frontend.save_project,
            ],
            [window.on_open, window.on_new, window.on_save],
        )
        # the programs and KSM are checked before it goes on
        self.assertNoResult(created)
        self.checked.callback(None)
        self.assertIsNone(self.successResultOf(created))
        self.assertEqual(window.calls, ["title"])

    def test_the_problem_of_the_last_project(self):
        self.app.start_up_problem = "lab is gone"
        created = self.create()
        [window] = FakeMainWindow.made
        self.assertEqual(window.calls, ["title"])
        self.checked.callback(None)
        self.successResultOf(created)
        self.assertEqual(window.calls, ["title", ("problem", "lab is gone")])


class TestCheckPrerequisites(GuiTestCase):

    def setUp(self):
        super().setUp()
        # the folders of the programs are those of the open project
        settings.use_project(settings.ProjectSettings())
        self.logger = FakeLogger()
        self.patch(gui_app, "logger", self.logger)
        self.missing = []
        self.patch(gui_app, "missing_programs", lambda vde, qemu: self.missing)
        self.available = True
        self.patch(ksm, "ksm_available", lambda: self.available)
        self.running = True
        self.patch(gui_app, "ksm_started", lambda: defer.succeed(self.running))

    def warning(self):
        self.successResultOf(application().check_prerequisites())
        if not self.logger.events:
            return None
        [(level, text, fields)] = self.logger.events
        self.assertEqual(
            (level, text), ("error", gui_app.components_not_found)
        )
        return fields["text"]

    def test_nothing_lacks(self):
        self.assertIsNone(self.warning())

    def test_missing_programs(self):
        self.missing = ["vde_switch (vde2)", "qemu-img (qemu-utils)"]
        self.assertEqual(
            self.warning(),
            gui_app.programs_not_found.format(
                programs="vde_switch (vde2), qemu-img (qemu-utils)"
            ),
        )

    def test_no_ksm(self):
        set_setting("kernel_samepage_merging", True)
        self.available = False
        self.missing = ["vde_switch (vde2)"]
        self.assertEqual(
            self.warning(),
            gui_app.ksm_not_found
            + "\n"
            + gui_app.programs_not_found.format(programs="vde_switch (vde2)"),
        )

    def test_ksm_still_off(self):
        set_setting("kernel_samepage_merging", True)
        self.running = False
        self.assertEqual(self.warning(), gui_app.ksm_still_off)

    def test_the_alert_turned_off(self):
        set_setting("warn_missing_programs", False)
        self.missing = ["vde_switch (vde2)"]
        self.assertIsNone(self.warning())


class TestConsoleNamespace(GuiTestCase):

    def test_the_main_window(self):
        app = application()
        app.main_window = "the main window"
        self.assertEqual(
            app.get_console_namespace(), {"main_window": "the main window"}
        )


class TestKsmWarning(unittest.TestCase):

    if not has_display:  # pragma: no cover
        skip = "GTK can't open a display"

    def test_what_it_says(self):
        warning = gui_app.ksm_warning
        self.assertIsNone(warning(False, False, False))
        self.assertEqual(warning(True, False, False), gui_app.ksm_not_found)
        self.assertEqual(warning(True, True, False), gui_app.ksm_still_off)
        self.assertIsNone(warning(True, True, True))


class TestShouldShowToUser(unittest.TestCase):

    if not has_display:  # pragma: no cover
        skip = "GTK can't open a display"

    def test_the_errors(self):
        show = gui_app.should_show_to_user
        no, maybe = gui_app.PredicateResult.no, gui_app.PredicateResult.maybe
        self.assertIs(show(error("x", LogLevel.info)), no)
        self.assertIs(show(error("x", LogLevel.warn)), no)
        self.assertIs(show(error("x")), maybe)
        self.assertIs(show(error("x", LogLevel.critical)), maybe)
        self.assertIs(show(error("x", hide_to_user=True)), no)
