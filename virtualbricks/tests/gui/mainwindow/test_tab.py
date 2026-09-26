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

"""
The tabs of the main window: which pages they are, their switch, and the
menu of a list.
"""

from twisted.trial import unittest

from virtualbricks.tests.gui import has_display

if has_display:
    from gi.repository import Gdk, Gtk

    from virtualbricks.gui.mainwindow import tab
    from virtualbricks.gui.mainwindow.tab import (
        Tab,
        popup_menu,
        switch,
        tabs,
    )

    class FakeTab(Tab, Gtk.Box):
        def __init__(self, name, heard):
            super().__init__(visible=True)
            self.name = name
            self.heard = heard

        def on_shown(self):
            self.heard.append(("shown", self.name))

        def on_left(self):
            self.heard.append(("left", self.name))


class TestTabs(unittest.TestCase):

    if not has_display:  # pragma: no cover
        skip = "GTK can't open a display"

    def setUp(self):
        self.heard = []
        self.notebook = Gtk.Notebook()
        self.addCleanup(self.notebook.destroy)

    def add(self, page):
        self.notebook.append_page(page, None)
        return page

    def test_the_tabs_of_a_notebook(self):
        first = self.add(FakeTab("first", self.heard))
        self.add(Gtk.Box(visible=True))
        last = self.add(FakeTab("last", self.heard))
        self.assertEqual(tabs(self.notebook), [first, last])

    def test_the_switch(self):
        self.notebook.connect(
            "switch-page", lambda notebook, page, n: switch(notebook, page)
        )
        # the first page shows, no page goes
        self.add(FakeTab("bricks", self.heard))
        self.add(Gtk.Box(visible=True))
        self.add(FakeTab("readme", self.heard))
        self.notebook.set_current_page(2)
        self.notebook.set_current_page(1)
        self.notebook.set_current_page(0)
        self.assertEqual(
            self.heard,
            [
                ("shown", "bricks"),
                ("left", "bricks"),
                ("shown", "readme"),
                ("left", "readme"),
                ("shown", "bricks"),
            ],
        )

    def test_the_hooks_do_nothing(self):
        plain = Tab()
        for hook in (
            plain.on_open,
            plain.on_save,
            plain.on_quit,
            plain.on_shown,
            plain.on_left,
        ):
            self.assertIsNone(hook())


class FakeMenu:
    def __init__(self, shown, value):
        self.shown = shown
        self.value = value

    def popup(self, button, time, gui):
        self.shown.append((self.value, button, gui))


class TestPopupMenu(unittest.TestCase):

    if not has_display:  # pragma: no cover
        skip = "GTK can't open a display"

    def setUp(self):
        self.menus = []
        self.patch(tab, "IMenu", lambda value: FakeMenu(self.menus, value))
        store = Gtk.ListStore(object)
        for value in ("sw1", "sw2"):
            store.append((value,))
        self.view = Gtk.TreeView(visible=True, model=store)
        column = Gtk.TreeViewColumn(title="Name")
        column.pack_start(Gtk.CellRendererText(), False)
        self.view.append_column(column)
        self.window = Gtk.OffscreenWindow()
        self.addCleanup(self.window.destroy)
        # the focus is somewhere else first
        box = Gtk.Box(visible=True)
        box.pack_start(Gtk.Entry(visible=True), False, False, 0)
        box.pack_start(self.view, True, True, 0)
        self.window.add(box)
        self.window.show()
        self.row = self.view.get_background_area(Gtk.TreePath(1), None)

    def release(self, button, y):
        event = Gdk.Event.new(Gdk.EventType.BUTTON_RELEASE)
        event.button.button = button
        event.button.x = self.row.x + 1
        event.button.y = y
        return popup_menu(self.view, event.button, "gui")

    def test_on_a_row(self):
        self.assertTrue(self.release(3, self.row.y + 1))
        self.assertEqual(self.menus, [("sw2", 3, "gui")])
        path, _column = self.view.get_cursor()
        self.assertEqual(path.get_indices(), [1])
        self.assertIs(self.window.get_focus(), self.view)

    def test_not_on_a_row(self):
        self.assertTrue(self.release(3, self.row.y + 10 * self.row.height))
        self.assertEqual(self.menus, [])

    def test_not_the_right_button(self):
        self.assertIsNone(self.release(1, self.row.y + 1))
        self.assertEqual(self.menus, [])
