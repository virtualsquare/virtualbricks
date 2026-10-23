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
The tabs of the main window: which pages they are, their switch, and the
bar that floats over them.
"""

from twisted.trial import unittest

from virtualbricks.tests.gui import has_display

if has_display:
    from gi.repository import Gdk, Gtk

    from virtualbricks.gui.mainwindow.tab import (
        FADED_OPACITY,
        FloatingBar,
        Tab,
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


class TestFloatingBar(unittest.TestCase):

    if not has_display:  # pragma: no cover
        skip = "GTK can't open a display"

    def setUp(self):
        self.bar = FloatingBar(spacing=6, margin=6)
        self.addCleanup(self.bar.destroy)

    def pointer(self, signal, detail=None):
        """The pointer in or out of the bar, from or to detail."""

        kind = (
            Gdk.EventType.ENTER_NOTIFY
            if signal == "enter-notify-event"
            else Gdk.EventType.LEAVE_NOTIFY
        )
        event = Gdk.Event.new(kind)
        event.crossing.detail = (
            Gdk.NotifyType.NONLINEAR if detail is None else detail
        )
        self.bar.emit(signal, event)

    def assertFaded(self):
        # GTK keeps it in a byte
        self.assertAlmostEqual(self.bar.get_opacity(), FADED_OPACITY, places=2)

    def assertOpaque(self):
        self.assertEqual(self.bar.get_opacity(), 1.0)

    def test_a_dark_box_with_rounded_corners(self):
        style = self.bar.box.get_style_context()
        self.assertTrue(style.has_class("osd"))
        radius = style.get_property("border-radius", style.get_state())
        self.assertGreater(radius, 0)
        button = Gtk.Button(visible=True)
        self.bar.pack(button)
        self.assertEqual(self.bar.box.get_children(), [button])

    def test_faded_away_from_the_pointer(self):
        self.assertFaded()
        self.pointer("enter-notify-event")
        self.assertOpaque()
        # from the edge to a button and back, the pointer stays over it
        self.pointer("leave-notify-event", Gdk.NotifyType.INFERIOR)
        self.assertOpaque()
        self.pointer("enter-notify-event", Gdk.NotifyType.INFERIOR)
        self.assertOpaque()
        # out from a button
        self.pointer("leave-notify-event", Gdk.NotifyType.VIRTUAL)
        self.assertFaded()

    def test_opaque_while_a_menu_shows(self):
        menu = Gtk.MenuButton(visible=True)
        self.bar.pack(menu)
        self.pointer("enter-notify-event")
        menu.set_active(True)
        # the menu takes the pointer
        self.pointer("leave-notify-event", Gdk.NotifyType.VIRTUAL)
        self.assertOpaque()
        menu.set_active(False)
        self.assertFaded()

    def test_a_toggle_button_is_no_menu(self):
        toggle = Gtk.ToggleButton(visible=True)
        self.bar.pack(toggle)
        toggle.set_active(True)
        self.assertFaded()
