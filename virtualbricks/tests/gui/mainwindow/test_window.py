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

"""The main window: what closing the windows it opens tells it."""

from virtualbricks.config.settings import set_current_project
from virtualbricks.tests.gui import GuiTestCase, has_display

if has_display:
    from gi.repository import Gtk

    from virtualbricks.gui.mainwindow.window import VBGUI


class FakeGui:
    """What import_project uses of the main window."""

    def __init__(self, factory):
        self.brickfactory = factory
        self.window = None
        self.titles = 0

    def set_title(self):
        self.titles += 1

    def show_projects(self, problem=None):
        self.problem = problem
        self.projects = FakeWindow()
        return self.projects


class FakeWindow:
    """The Projects window."""

    def __init__(self):
        self.window = Gtk.Window()

    def get_root_widget(self):
        return self.window


class TestImport(GuiTestCase):

    def setUp(self):
        super().setUp()
        self.gui = FakeGui(self.factory)
        self.closed = []

    def test_closed(self):
        dialog = VBGUI.import_project(
            self.gui, lambda: self.closed.append(True)
        )
        self.assertTrue(dialog.get_root_widget().get_visible())
        self.assertEqual((self.closed, self.gui.titles), ([], 0))
        dialog.get_root_widget().destroy()
        # the title names the project imported and opened, if one was
        self.assertEqual((self.closed, self.gui.titles), ([True], 1))

    def test_nobody_to_tell(self):
        dialog = VBGUI.import_project(self.gui)
        dialog.get_root_widget().destroy()
        self.assertEqual(self.gui.titles, 1)


class TestStartUpProblem(GuiTestCase):
    """The last project can't be opened: the Projects window says why."""

    def setUp(self):
        super().setUp()
        self.gui = FakeGui(self.factory)
        set_current_project("gone")

    def test_closed_without_a_project(self):
        window = VBGUI.show_start_up_problem(self.gui, "gone is gone")
        self.assertIs(window, self.gui.projects)
        self.assertEqual(self.gui.problem, "gone is gone")
        window.window.destroy()
        # a new project, as the console does
        self.assertEqual(self.manager.current.name, "new_project_0")
        self.assertEqual(self.gui.titles, 1)

    def test_closed_after_opening_one(self):
        window = VBGUI.show_start_up_problem(self.gui, "gone is gone")
        self.manager.create("lab")
        self.manager.open("lab", self.factory)
        window.window.destroy()
        self.assertEqual(self.manager.current.name, "lab")
        self.assertEqual(self.gui.titles, 0)
