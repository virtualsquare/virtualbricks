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

"""F1 in a window opens its page of the guide; a file chooser calls back."""

from twisted.trial import unittest

from virtualbricks.tests.gui import has_display

if has_display:
    from gi.repository import Gdk, Gtk

    from virtualbricks.gui.dialogs import base
    from virtualbricks.gui.dialogs.base import Window

    class Plain(Window):
        """A window without a page: F1 opens the index."""

        def build_ui(self):
            self.window = Gtk.Window()

        def get_root_widget(self):
            return self.window

    class Named(Plain):
        help_page = "settings"


class FakeChooser:
    """A file chooser that never shows: respond() answers as its user."""

    def __init__(self, filename):
        self.filename = filename
        self.modal = self.shown = self.destroyed = False
        self.handlers = []

    def set_modal(self, modal):
        self.modal = modal

    def connect(self, signal, handler):
        assert signal == "response", signal
        self.handlers.append(handler)

    def show(self):
        self.shown = True

    def get_filename(self):
        return self.filename

    def destroy(self):
        self.destroyed = True

    def respond(self, response):
        for handler in self.handlers:
            handler(self, response)


class TestF1(unittest.TestCase):

    if not has_display:  # pragma: no cover
        skip = "GTK can't open a display"

    def setUp(self):
        self.opened = []
        self.patch(
            base,
            "show_help",
            lambda window, page=None: self.opened.append((window, page)),
        )

    def press(self, window, keyval, state=0):
        """Whether the root widget of window took the key."""

        root = window.get_root_widget()
        self.addCleanup(root.destroy)
        event = Gdk.Event.new(Gdk.EventType.KEY_PRESS)
        event.key.keyval = keyval
        event.key.state = Gdk.ModifierType(state)
        return root.emit("key-press-event", event)

    def test_its_page(self):
        window = Named()
        self.assertTrue(self.press(window, Gdk.KEY_F1))
        self.assertEqual(self.opened, [(window.window, "settings")])

    def test_the_index(self):
        window = Plain()
        self.assertTrue(self.press(window, Gdk.KEY_F1))
        self.assertEqual(self.opened, [(window.window, None)])

    def test_num_lock(self):
        window = Named()
        self.assertTrue(
            self.press(window, Gdk.KEY_F1, Gdk.ModifierType.MOD2_MASK)
        )
        self.assertEqual(self.opened, [(window.window, "settings")])

    def test_not_with_a_modifier(self):
        # Ctrl+F1 shows a tooltip
        for state in (
            Gdk.ModifierType.CONTROL_MASK,
            Gdk.ModifierType.SHIFT_MASK,
            Gdk.ModifierType.MOD1_MASK,
        ):
            self.assertFalse(self.press(Named(), Gdk.KEY_F1, state))
        self.assertEqual(self.opened, [])

    def test_another_key(self):
        self.assertFalse(self.press(Named(), Gdk.KEY_F2))
        self.assertEqual(self.opened, [])


class TestAskFile(unittest.TestCase):

    if not has_display:  # pragma: no cover
        skip = "GTK can't open a display"

    def ask(self, response):
        """What ask_file() gives once its chooser has response."""

        chooser = FakeChooser("/lab/deb.qcow2")
        answers = []
        base.ask_file(chooser, answers.append)
        self.assertTrue(chooser.shown)
        self.assertTrue(chooser.modal)
        # kept while it shows
        self.assertIn(chooser, base._choosers)
        self.assertEqual(answers, [])
        chooser.respond(response)
        self.assertTrue(chooser.destroyed)
        self.assertNotIn(chooser, base._choosers)
        return answers

    def test_chosen(self):
        self.assertEqual(self.ask(Gtk.ResponseType.ACCEPT), ["/lab/deb.qcow2"])

    def test_cancelled(self):
        self.assertEqual(self.ask(Gtk.ResponseType.CANCEL), [None])
        self.assertEqual(self.ask(Gtk.ResponseType.DELETE_EVENT), [None])
