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

"""The tabs of the main window: which pages they are, and their switch."""

from twisted.trial import unittest

from virtualbricks.tests.gui import has_display

if has_display:
    from gi.repository import Gtk

    from virtualbricks.gui.mainwindow.tab import Tab, switch, tabs

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
        tab = Tab()
        for hook in (
            tab.on_open,
            tab.on_save,
            tab.on_quit,
            tab.on_shown,
            tab.on_left,
        ):
            self.assertIsNone(hook())
