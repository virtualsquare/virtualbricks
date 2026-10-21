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
from virtualbricks.tests.gui.test_drop import takes_files

if has_display:
    from gi.repository import Gdk, Gtk

    from virtualbricks.gui.dialogs import base
    from virtualbricks.gui.dialogs.importdialog import ImportDialog
    from virtualbricks.gui.mainwindow import window
    from virtualbricks.gui.mainwindow.readme import ReadmeTab
    from virtualbricks.gui.mainwindow.rowtab import RowsTab
    from virtualbricks.gui.mainwindow.tab import tabs
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
        self.chosen = []
        self.patch(
            ImportDialog, "choose", lambda dialog, p: self.chosen.append(p)
        )

    def on_closed(self):
        self.closed.append(True)

    def test_closed(self):
        dialog = MainWindow.import_archive(self.gui, "/a.vbp", self.on_closed)
        self.assertTrue(dialog.get_root_widget().get_visible())
        self.assertEqual(self.chosen, ["/a.vbp"])
        self.assertIs(dialog.get_root_widget().get_transient_for(), None)
        self.assertEqual((self.closed, self.gui.titles), ([], 0))
        dialog.get_root_widget().destroy()
        # the title names the project imported and opened, if one was
        self.assertEqual((self.closed, self.gui.titles), ([True], 1))

    def test_nobody_to_tell(self):
        dialog = MainWindow.import_archive(self.gui, "/a.vbp")
        dialog.get_root_widget().destroy()
        self.assertEqual(self.gui.titles, 1)

    def test_above_another_window(self):
        # as the Projects window, which a file chooser leaves on top
        other = Gtk.Window()
        self.addCleanup(other.destroy)
        dialog = MainWindow.import_archive(self.gui, "/a.vbp", None, other)
        self.assertIs(dialog.get_root_widget().get_transient_for(), other)
        dialog.get_root_widget().destroy()


class TestImportProject(GuiTestCase):
    """The archive first: the Import window opens on the one chosen."""

    def setUp(self):
        super().setUp()
        self.gui = FakeGui(self.factory)
        self.gui.window = Gtk.Window()
        self.addCleanup(self.gui.window.destroy)
        self.imported = []
        self.gui.import_archive = lambda *args: self.imported.append(args)
        self.asked = []
        self.patch(
            window,
            "ask_archive",
            lambda parent, done: self.asked.append((parent, done)),
        )

    def on_closed(self):
        pass

    def test_asked_above_the_main_window(self):
        MainWindow.import_project(self.gui, self.on_closed)
        [(parent, done)] = self.asked
        self.assertIs(parent, self.gui.window)
        # no window until it's chosen; none if the chooser is cancelled
        self.assertEqual(self.imported, [])
        done("/a.vbp")
        self.assertEqual(self.imported, [("/a.vbp", self.on_closed, None)])

    def test_asked_above_another_window(self):
        other = Gtk.Window()
        self.addCleanup(other.destroy)
        MainWindow.import_project(self.gui, None, None, other)
        [(parent, done)] = self.asked
        self.assertIs(parent, other)
        # the Import window above it too
        done("/a.vbp")
        self.assertEqual(self.imported, [("/a.vbp", None, other)])

    def test_an_archive_given(self):
        MainWindow.import_project(self.gui, self.on_closed, "/a.vbp")
        self.assertEqual(self.asked, [])
        self.assertEqual(self.imported, [("/a.vbp", self.on_closed, None)])


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


class TestTheTabs(GuiTestCase):

    def test_the_disks_show_the_images(self):
        gui = MainWindow(LocalEngine(self.factory))
        self.addCleanup(gui.window.destroy)
        gui.bricks.show_images()
        notebook = gui.main_notebook
        self.assertEqual(
            notebook.get_current_page(), notebook.page_num(gui.images)
        )
        self.assertNotEqual(notebook.page_num(gui.images), 0)


class TestDrop(GuiTestCase):
    """Archives dropped on the window are imported, a window each."""

    def setUp(self):
        super().setUp()
        self.gui = MainWindow(LocalEngine(self.factory))
        self.addCleanup(self.gui.window.destroy)
        self.logger = FakeLogger()
        self.patch(window, "logger", self.logger)
        self.imported = []
        self.gui.import_archive = lambda path: self.imported.append(path)

    def test_the_window_takes_files(self):
        # its content, menus and tabs, all of it
        self.assertTrue(takes_files(self.gui.window.get_child()))
        # nothing in it takes the drop first, but the fields of text
        found = []
        for tab in tabs(self.gui.main_notebook):
            if isinstance(tab, RowsTab):
                self.assertIsNone(tab.search.drag_dest_get_target_list())
                found.append(tab.help_page)
            elif isinstance(tab, ReadmeTab):
                self.assertIsNone(tab.preview.drag_dest_get_target_list())
                found.append(tab.help_page)
        self.assertEqual(len(found), 4)

    def test_archives_dropped(self):
        self.gui.import_files(["/home/a.vbp", "/home/b.tar.gz"], [])
        self.assertEqual(self.imported, ["/home/a.vbp", "/home/b.tar.gz"])
        self.assertEqual(self.logger.events, [])

    def test_what_isnt_a_file_here(self):
        self.gui.import_files(
            ["/home/a.vbp"], ["https://example.org/lab.vbp", "/home/labs"]
        )
        # the archive all the same
        self.assertEqual(self.imported, ["/home/a.vbp"])
        self.assertEqual(self.logger.levels(), ["error"])
        self.assertEqual(
            self.logger.formatted(),
            [
                "Only the files of this computer can be imported, not "
                "https://example.org/lab.vbp, /home/labs"
            ],
        )


class TestTrayIcon(GuiTestCase):
    """The tray icon follows its setting, whatever changes it."""

    def setUp(self):
        super().setUp()
        # windows show and hide only here, not on the display
        self.visible = set()
        self.patch(Gtk.Window, "show", lambda w: self.visible.add(w))
        self.patch(Gtk.Window, "hide", lambda w: self.visible.discard(w))
        self.patch(Gtk.Window, "get_visible", lambda w: w in self.visible)

    def main_window(self):
        gui = MainWindow(LocalEngine(self.factory))
        self.addCleanup(gui.window.destroy)
        return gui

    def test_at_start(self):
        gui = self.main_window()
        self.assertTrue(gui.status_icon.get_visible())
        self.assertIn(gui.window, self.visible)

    def test_none_at_start(self):
        set_setting("tray_icon", False)
        gui = self.main_window()
        self.assertFalse(gui.status_icon.get_visible())
        self.assertIn(gui.window, self.visible)

    def test_follows_the_setting(self):
        gui = self.main_window()
        set_setting("tray_icon", False)
        self.assertFalse(gui.status_icon.get_visible())
        set_setting("tray_icon", True)
        self.assertTrue(gui.status_icon.get_visible())
        # the window stays as it was
        self.assertIn(gui.window, self.visible)

    def test_shows_the_hidden_window(self):
        gui = self.main_window()
        gui.window_toggle()
        self.assertNotIn(gui.window, self.visible)
        set_setting("tray_icon", False)
        # else nothing would show it again
        self.assertIn(gui.window, self.visible)
        self.assertEqual(
            gui.status_icon.get_tooltip_text(), "Virtualbricks visible"
        )


class TestHelp(GuiTestCase):
    """
    Help: Contents opens the index of the guide, F1 the page of the tab in
    view; About doesn't take F1.
    """

    def setUp(self):
        super().setUp()
        self.opened = []

        def show_help(parent, page=None):
            self.opened.append((parent, page))

        # Contents, and F1 of the window
        self.patch(window, "show_help", show_help)
        self.patch(base, "show_help", show_help)
        self.abouts = []
        self.patch(window, "AboutDialog", lambda: self.abouts.append(1))
        self.gui = MainWindow(LocalEngine(self.factory))
        self.addCleanup(self.gui.window.destroy)

    def help_items(self):
        menubar = self.gui.menubar
        return menubar.get_children()[-1].get_submenu().get_children()

    def press(self, keyval, state=0):
        event = Gdk.Event.new(Gdk.EventType.KEY_PRESS)
        event.key.keyval = keyval
        event.key.state = Gdk.ModifierType(state)
        event.key.window = self.gui.window.get_window()
        return self.gui.window.emit("key-press-event", event)

    def test_the_items(self):
        labels = [
            item.get_label()
            for item in self.help_items()
            if not isinstance(item, Gtk.SeparatorMenuItem)
        ]
        self.assertEqual(labels, ["_Contents", "gtk-about"])

    def test_contents(self):
        contents = self.help_items()[0]
        contents.activate()
        self.assertEqual(self.opened, [(self.gui.window, None)])
        # F1 shows beside it
        self.assertEqual(contents.get_child().get_accel(), (Gdk.KEY_F1, 0))

    def test_f1(self):
        self.assertTrue(self.press(Gdk.KEY_F1))
        self.assertEqual(self.opened, [(self.gui.window, "bricks")])
        self.assertEqual(self.abouts, [])

    def test_f1_on_another_tab(self):
        notebook = self.gui.main_notebook
        for page, title in (
            ("events", "_Events"),
            ("images", "_Images"),
            ("topology", "_Topology"),
            ("readme", "Readme"),
        ):
            [tab] = [
                tab for tab in notebook.get_children() if tab.title == title
            ]
            notebook.set_current_page(notebook.page_num(tab))
            self.assertEqual(self.gui.help_page, page)

    def test_not_ctrl_f1(self):
        self.assertFalse(self.press(Gdk.KEY_F1, Gdk.ModifierType.CONTROL_MASK))
        self.assertEqual(self.opened, [])
