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

"""The main window: what closing the windows it opens tells it."""

from twisted.internet import defer

from virtualbricks import ksm
from virtualbricks.config import settings
from virtualbricks.config.settings import (
    get_setting,
    set_current_project,
    set_setting,
)
from virtualbricks.engine import LocalEngine
from virtualbricks.tests import FakeLogger
from virtualbricks.tests.gui import GuiTestCase, has_display

if has_display:
    from gi.repository import Gtk

    from virtualbricks.gui.mainwindow import window
    from virtualbricks.gui.mainwindow.window import MainWindow


class FakeGui:
    """What import_project uses of the main window."""

    def __init__(self, factory):
        self.brickfactory = factory
        self.engine = LocalEngine(factory)
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
        dialog = MainWindow.import_project(
            self.gui, lambda: self.closed.append(True)
        )
        self.assertTrue(dialog.get_root_widget().get_visible())
        self.assertEqual((self.closed, self.gui.titles), ([], 0))
        dialog.get_root_widget().destroy()
        # the title names the project imported and opened, if one was
        self.assertEqual((self.closed, self.gui.titles), ([True], 1))

    def test_nobody_to_tell(self):
        dialog = MainWindow.import_project(self.gui)
        dialog.get_root_widget().destroy()
        self.assertEqual(self.gui.titles, 1)


class TestStartUpProblem(GuiTestCase):
    """The last project can't be opened: the Projects window says why."""

    def setUp(self):
        super().setUp()
        self.gui = FakeGui(self.factory)
        set_current_project(self.manager.path, "gone")

    def test_closed_without_a_project(self):
        window = MainWindow.show_start_up_problem(self.gui, "gone is gone")
        self.assertIs(window, self.gui.projects)
        self.assertEqual(self.gui.problem, "gone is gone")
        window.window.destroy()
        # a new project, as the console does
        self.assertEqual(self.manager.current.name, "new_project_0")
        self.assertEqual(self.gui.titles, 1)

    def test_closed_after_opening_one(self):
        window = MainWindow.show_start_up_problem(self.gui, "gone is gone")
        self.manager.create("lab")
        self.manager.open("lab", self.factory)
        window.window.destroy()
        self.assertEqual(self.manager.current.name, "lab")
        self.assertEqual(self.gui.titles, 0)


class TestWarningAtStart(GuiTestCase):
    """What the warning at start says of KSM and of the programs."""

    def setUp(self):
        super().setUp()
        self.logger = FakeLogger()
        self.patch(window, "logger", self.logger)
        self.missing = []
        self.patch(window, "missing_programs", lambda vde, qemu: self.missing)
        self.available = True
        self.patch(ksm, "ksm_available", lambda: self.available)
        self.patch(ksm, "check_ksm", lambda: False)

    def check(self):
        """The lines of the warning, once the check is over."""

        # the check uses nothing of the main window
        self.successResultOf(MainWindow.check_prerequisites(None))
        return [fields["text"] for _, _, fields in self.logger.events]

    def test_ksm_off_as_the_settings_want(self):
        self.assertEqual(self.check(), [])

    def test_ksm_missing(self):
        set_setting("kernel_samepage_merging", True)
        self.available = False
        self.assertEqual(self.check(), [window.ksm_not_found])
        # the setting stays as it is
        self.assertIs(get_setting("kernel_samepage_merging"), True)

    def test_ksm_still_off_after_the_start(self):
        set_setting("kernel_samepage_merging", True)
        turning = defer.Deferred()
        self.patch(settings, "_ksm_start", turning)
        checking = MainWindow.check_prerequisites(None)
        # it waits for the start to try
        self.assertNoResult(checking)
        turning.callback(False)
        self.successResultOf(checking)
        [(_level, text, fields)] = self.logger.events
        self.assertEqual(text, window.components_not_found)
        self.assertEqual(fields["text"], window.ksm_still_off)

    def test_ksm_turned_on_at_start(self):
        set_setting("kernel_samepage_merging", True)
        self.patch(settings, "_ksm_start", defer.succeed(True))
        self.assertEqual(self.check(), [])

    def test_programs(self):
        self.missing = ["vde_switch (vde2)"]
        set_setting("kernel_samepage_merging", True)
        self.available = False
        self.assertEqual(
            self.check(),
            [
                window.ksm_not_found
                + "\n"
                + window.programs_not_found.format(
                    programs="vde_switch (vde2)"
                )
            ],
        )

    def test_no_warning(self):
        self.missing = ["vde_switch (vde2)"]
        set_setting("warn_missing_programs", False)
        self.assertEqual(self.check(), [])


class TestKsmWarning(GuiTestCase):

    def test_rule(self):
        self.assertIsNone(window.ksm_warning(False, False, False))
        self.assertEqual(
            window.ksm_warning(True, False, False), window.ksm_not_found
        )
        self.assertEqual(
            window.ksm_warning(True, True, False), window.ksm_still_off
        )
        self.assertIsNone(window.ksm_warning(True, True, True))
