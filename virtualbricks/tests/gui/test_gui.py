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


"""The application window: the startup migration and the last project."""

import os

from twisted.internet import defer

from virtualbricks import locations
from virtualbricks.config import workspace
from virtualbricks.config.settings import set_current_project
from virtualbricks.console import projects as console_projects
from virtualbricks.tests import FakeLogger
from virtualbricks.tests.gui import GuiTestCase, has_display
from virtualbricks.tests.migrate.fixtures import (
    CONFIG1,
    write_project,
    write_settings,
)

if has_display:

    from virtualbricks.gui import gui
    from virtualbricks.gui.trash import DesktopTrash
    from virtualbricks.migrate import gui as migrate_gui


class TestStartupMigration(GuiTestCase):

    def setUp(self):
        super().setUp()
        self.shown = []
        self.patch(
            migrate_gui.MigrationWindow,
            "show",
            lambda window: self.shown.append(window),
        )
        self.app = gui.Application.__new__(gui.Application)
        self.app.config = {}

    def test_nothing_to_migrate(self):
        self.assertIsNone(self.app.migrate())
        self.assertEqual(self.shown, [])

    def test_show_the_migration(self):
        workspace = os.path.join(self.root, ".virtualbricks")
        write_settings(locations.legacy_settings_file(), workspace, "lab")
        write_project(workspace, "lab", CONFIG1)
        closed = self.app.migrate()
        window = self.shown[0]
        self.addCleanup(window.window.destroy)
        self.assertTrue(window.fixed)
        self.assertIs(closed, window.closed)
        self.assertEqual(
            [item.name for item in window.migration.items],
            [locations.LEGACY_SETTINGS_FILE, "lab"],
        )

    def test_start_sets_the_title_and_checks_the_programs(self):
        calls = []

        class VBGUI:
            def set_title(self):
                calls.append("title")

            def check_prerequisites(self):
                calls.append("check")

        def start(app, reactor):
            # it opens the last project
            calls.append("open")
            return "quit"

        self.app.gui = VBGUI()
        self.patch(gui.app.Application, "_start", start)
        self.assertEqual(self.app._start("reactor"), "quit")
        # the programs are looked for in the folders of the open project
        self.assertEqual(calls, ["open", "title", "check"])


class TestStartupProject(GuiTestCase):
    """The GUI opens the last project, or says why in the Projects window."""

    def setUp(self):
        super().setUp()
        self.problems = []
        test = self

        class VBGUI:
            def show_start_up_problem(self, message):
                test.problems.append(message)

        self.app = gui.Application.__new__(gui.Application)
        self.app.gui = VBGUI()
        self.logger = FakeLogger()
        self.patch(gui, "logger", self.logger)
        self.patch(workspace, "logger", FakeLogger())

    def test_the_last_project(self):
        self.manager.create("lab")
        set_current_project(self.manager.path, "lab")
        self.app.open_last_project(self.factory)
        self.assertEqual(self.manager.current.name, "lab")
        self.assertEqual(self.problems, [])

    def test_the_first_run(self):
        self.app.open_last_project(self.factory)
        self.assertEqual(self.manager.current.name, "new_project")
        self.assertEqual(self.problems, [])

    def test_a_project_that_is_gone(self):
        set_current_project(self.manager.path, "gone")
        self.app.open_last_project(self.factory)
        self.assertIsNone(self.manager.current)
        [message] = self.problems
        self.assertIn('"gone" that was open last doesn\'t exist', message)
        self.assertEqual(self.logger.levels(), ["warn"])
        # no new_project_N
        self.assertEqual(self.manager.names(), [])

    def test_a_project_that_cannot_be_read(self):
        os.makedirs(self.manager.project_path("lab"))
        with open(self.manager._project_file("lab"), "w") as fp:
            fp.write("[bricks\n")
        set_current_project(self.manager.path, "lab")
        self.app.open_last_project(self.factory)
        [message] = self.problems
        self.assertIn('"lab" that was open last can\'t be opened', message)

    def test_a_bad_name(self):
        set_current_project(self.manager.path, "../x")
        self.app.open_last_project(self.factory)
        self.assertEqual(len(self.problems), 1)


class TestStartupTrash(GuiTestCase):
    """The GUI gives the workspace the trash of the desktop."""

    def test_run_gives_the_workspace_a_trash(self):
        class Observer:
            parent = None

            def set_parent(self, window):
                self.parent = window

            def __call__(self, event):
                pass

        class Publisher:
            def __init__(self):
                self.observers = []

            def addObserver(self, observer):
                self.observers.append(observer)

        class VBGUI:
            window = "window"

            def __init__(self, factory, messages):
                pass

        self.patch(gui, "MessageDialogObserver", Observer)
        self.patch(gui, "globalLogPublisher", Publisher())
        self.patch(gui, "VBGUI", VBGUI)
        # the console opens projects through the main window too
        self.patch(console_projects, "frontend", console_projects.frontend)
        app = gui.Application.__new__(gui.Application)
        app.messages = None
        self.assertIsNone(self.manager.trasher)
        app._run(self.factory)
        self.assertIsInstance(self.manager.trasher, DesktopTrash)
        self.assertIsInstance(app.gui, VBGUI)
        self.assertIsInstance(console_projects.frontend, gui.WindowFrontend)
        self.assertIs(console_projects.frontend.gui, app.gui)


class TestWindowFrontend(GuiTestCase):
    """The console opens, makes and saves projects through the window."""

    def test_through_the_window(self):
        calls = []

        class Window:
            def on_open(self, name):
                calls.append(("open", name))
                return defer.succeed("report")

            def on_new(self, name):
                calls.append(("new", name))
                return defer.succeed(None)

            def on_save(self):
                calls.append(("save",))
                return defer.succeed(None)

        frontend = gui.WindowFrontend(Window())
        self.assertEqual(frontend.open("lab", self.factory), "report")
        frontend.new("lab2", self.factory)
        frontend.save(self.factory)
        self.assertEqual(calls, [("open", "lab"), ("new", "lab2"), ("save",)])
