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

"""The window of New Event: the name checked, the delay, Create."""

from virtualbricks.engine import LocalEngine
from virtualbricks.tests.gui import GuiTestCase, has_display

if has_display:
    from gi.repository import Gtk

    from virtualbricks.gui.mainwindow.events.eventeditor import MAX_DELAY
    from virtualbricks.gui.mainwindow.events.newevent import NewEventDialog


class FakeGui:
    def __init__(self, factory):
        self.brickfactory = factory
        self.engine = LocalEngine(factory)
        self.configured = []

    def curtain_up(self, event):
        self.configured.append(event)


class NewEventTestCase(GuiTestCase):

    def setUp(self):
        super().setUp()
        self.gui = FakeGui(self.factory)
        self.destroyed = []

    def dialog(self):
        dialog = NewEventDialog(self.gui)
        dialog.dialog.connect("destroy", self.destroyed.append)
        self.addCleanup(dialog.dialog.destroy)
        return dialog

    def type(self, dialog, name):
        dialog.name_entry.set_text(name)
        message = dialog.name_message
        return (
            dialog.create_button.get_sensitive(),
            message.get_text() if message.get_visible() else None,
        )

    def events(self):
        return [event.name for event in self.factory.events]


class TestTheWindow(NewEventTestCase):

    def test_its_parts(self):
        dialog = self.dialog()
        self.assertEqual(dialog.dialog.get_title(), "New Event")
        self.assertEqual(dialog.create_button.get_label(), "Create")
        self.assertTrue(
            dialog.create_button.get_style_context().has_class(
                "suggested-action"
            )
        )
        grid = dialog.name_entry.get_parent()
        name = grid.get_child_at(0, 0)
        wait = grid.get_child_at(0, 2)
        spin, seconds = grid.get_child_at(1, 2).get_children()
        self.assertEqual(name.get_text(), "Name")
        self.assertIs(name.get_mnemonic_widget(), dialog.name_entry)
        self.assertEqual(wait.get_text(), "Wait")
        self.assertIs(wait.get_mnemonic_widget(), dialog.delay)
        self.assertIs(spin, dialog.delay)
        self.assertEqual(seconds.get_text(), "seconds")
        # Enter creates, from either field
        self.assertTrue(dialog.name_entry.get_activates_default())
        self.assertTrue(dialog.delay.get_activates_default())

    def test_what_it_suggests(self):
        dialog = self.dialog()
        self.assertEqual(dialog.name_entry.get_text(), "new_event")
        self.assertEqual(dialog.delay.get_value_as_int(), 10)
        self.assertEqual(dialog.delay.get_adjustment().get_upper(), MAX_DELAY)
        self.assertEqual(self.type(dialog, "new_event"), (True, None))

    def test_a_free_name(self):
        self.factory.new_event("new_event")
        dialog = self.dialog()
        self.assertEqual(dialog.name_entry.get_text(), "new_event.1")


class TestTheName(NewEventTestCase):

    def test_bad_names(self):
        self.factory.new_brick("switch", "sw1")
        self.factory.new_event("boot")
        dialog = self.dialog()
        for name, message in (
            ("", "A name can't be empty"),
            ("1st", "A name starts with a letter"),
            # a brick's too: the console would read "sw1 on" as the brick
            ("sw1", "sw1 is the name of a brick"),
            ("boot", "boot is the name of an event"),
            (" boot ", "boot is the name of an event"),
        ):
            self.assertEqual(self.type(dialog, name), (False, message), name)
        self.assertEqual(self.type(dialog, "start lab"), (True, None))

    def test_create_waits_for_a_good_name(self):
        # the factory would make an event with a brick's name
        self.factory.new_brick("switch", "sw1")
        dialog = self.dialog()
        self.type(dialog, "sw1")
        dialog.dialog.response(Gtk.ResponseType.OK)
        self.assertEqual(self.events(), [])
        self.assertEqual(self.destroyed, [])


class TestCreate(NewEventTestCase):

    def test_create(self):
        dialog = self.dialog()
        self.type(dialog, "start lab")
        dialog.delay.set_value(5)
        dialog.dialog.response(Gtk.ResponseType.OK)
        event = self.factory.get_event("start_lab")
        self.assertEqual(event.config.delay, 5)
        self.assertEqual(event.config.actions, [])
        # its settings, to add its actions
        self.assertEqual(self.gui.configured, [event])
        self.assertEqual(len(self.destroyed), 1)

    def test_a_delay_typed(self):
        dialog = self.dialog()
        dialog.delay.set_text("30")
        dialog.dialog.response(Gtk.ResponseType.OK)
        event = self.factory.get_event("new_event")
        self.assertEqual(event.config.delay, 30)

    def test_cancel(self):
        dialog = self.dialog()
        dialog.dialog.response(Gtk.ResponseType.CANCEL)
        self.assertEqual(self.events(), [])
        self.assertEqual(self.gui.configured, [])
        self.assertEqual(len(self.destroyed), 1)
