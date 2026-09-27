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
The Events tab: the rows of the events and their countdown, the row above
the list, the page of a project without events, the keys and the settings.
"""

from twisted.internet import task

from virtualbricks import console
from virtualbricks.bricks import event as event_module
from virtualbricks.tests import FakeLogger
from virtualbricks.tests.gui import GuiTestCase, has_display

if has_display:
    from gi.repository import Gdk, Gtk

    from virtualbricks.gui.mainwindow.events import eventmenu, tab
    from virtualbricks.gui.mainwindow.events.eventeditor import EventEditor
    from virtualbricks.gui.mainwindow.events.tab import EventsTab, count


class Recording(console.VbShellCommand):
    """An action that records that it was performed."""

    performed = []

    def perform(self, factory):
        self.performed.append(str(self))
        return 0


class FakeGui:
    def __init__(self, factory):
        self.brickfactory = factory
        self.window = object()
        self.configured = []
        self.removed = []
        self.tab = None

    def curtain_up(self, event):
        self.configured.append(event)

    def curtain_down(self):
        # the panels close the settings through the window
        self.tab.close_settings()

    def ask_remove_event(self, event):
        self.removed.append(event)


class FakeDialog:
    def __init__(self, shown, *args):
        self.shown = shown
        self.args = args

    def show(self, parent):
        self.shown.append((self.args, parent))


class EventsTestCase(GuiTestCase):

    def setUp(self):
        super().setUp()
        self.clock = task.Clock()
        self.patch(event_module, "reactor", self.clock)
        Recording.performed = []
        self.gui = FakeGui(self.factory)
        self.ev = self.event("start-vms", 5, "vm1 on")
        self.tab = EventsTab(self.gui, self.factory, self.clock)
        self.gui.tab = self.tab
        self.addCleanup(self.tab.destroy)
        # a test that quits says so
        self.addCleanup(lambda: self.tab.on_quit())

    def event(self, name, delay=5, *commands):
        event = self.factory.new_event(name)
        self.patch(event, "logger", FakeLogger())
        event.set(
            {
                "delay": delay,
                "actions": [Recording(command) for command in commands],
            }
        )
        return event

    def row(self, event=None):
        return self.tab.list.row_of(self.ev if event is None else event)

    def listed(self):
        return [
            row.item
            for row in self.tab.list.get_children()
            if self.tab.list._visible(row)
        ]

    def select(self, event):
        row = self.row(event)
        self.tab.list.select_row(row)
        return row

    def press(self, keyval, state=0):
        event = Gdk.Event.new(Gdk.EventType.KEY_PRESS)
        event.key.keyval = keyval
        event.key.state = Gdk.ModifierType(state)
        event.key.window = self.tab.get_window()
        seat = Gdk.Display.get_default().get_default_seat()
        event.set_device(seat.get_keyboard())
        return self.tab.on_list_key_press(self.tab.list, event.key)

    def show(self):
        window = Gtk.OffscreenWindow()
        self.addCleanup(window.destroy)
        window.set_size_request(900, 400)
        window.add(self.tab)
        window.show()
        return window


class TestTheRows(EventsTestCase):

    def test_a_ready_event(self):
        row = self.row()
        self.assertEqual(row.name.get_text(), "start-vms")
        self.assertEqual(row.detail.get_text(), "After 5 s, starts vm1")
        self.assertEqual(row.state_label.get_text(), "Ready")
        self.assertTrue(row.dot.get_visible())
        self.assertFalse(row.warning.get_visible())
        self.assertIsNone(row.state.get_tooltip_text())
        self.assertTrue(row.startstop.get_sensitive())
        self.assertEqual(row.startstop.get_tooltip_text(), "Start start-vms")

    def test_an_event_without_actions(self):
        row = self.row(self.event("draft"))
        self.assertEqual(row.detail.get_text(), "No actions yet")
        self.assertEqual(row.state_label.get_text(), "Not configured")
        self.assertFalse(row.dot.get_visible())
        self.assertTrue(row.warning.get_visible())
        self.assertEqual(
            row.state.get_tooltip_text(), "Add an action to draft first"
        )
        self.assertFalse(row.startstop.get_sensitive())

    def test_a_waiting_event(self):
        self.ev.poweron()
        row = self.row()
        self.assertEqual(row.state_label.get_text(), "Waiting · 5 s")
        self.assertTrue(row.dot.get_style_context().has_class("waiting"))
        self.assertEqual(row.icon.get_opacity(), 1.0)
        self.assertEqual(row.startstop.get_tooltip_text(), "Stop start-vms")
        # the menu of the row follows
        self.assertFalse(row.actions.get_action_enabled("rename"))

    def test_the_countdown(self):
        self.clock.advance(0.5)
        self.ev.poweron()
        label = self.row().state_label
        seen = [label.get_text()]
        for _ in range(4):
            self.clock.advance(1)
            seen.append(label.get_text())
        self.assertEqual(
            seen,
            [
                "Waiting · 5 s",
                "Waiting · 4 s",
                "Waiting · 3 s",
                "Waiting · 2 s",
                "Waiting · 1 s",
            ],
        )
        self.clock.advance(1)
        self.assertEqual(Recording.performed, ["vm1 on"])
        self.assertEqual(label.get_text(), "Ready")

    def test_only_while_an_event_waits(self):
        self.assertEqual(self.clock.getDelayedCalls(), [])
        self.ev.poweron()
        # the wait, and the countdown
        self.assertEqual(len(self.clock.getDelayedCalls()), 2)
        other = self.event("other", 9, "vm2 on")
        other.poweron()
        self.assertEqual(len(self.clock.getDelayedCalls()), 3)
        self.ev.poweroff()
        self.assertEqual(len(self.clock.getDelayedCalls()), 2)
        self.clock.advance(9)
        self.assertEqual(self.clock.getDelayedCalls(), [])

    def test_the_bricks_that_start_it(self):
        row = self.row()
        sw = self.factory.new_brick("switch", "sw1")
        sw.set({"pon_vbevent": "start-vms"})
        self.assertEqual(
            row.detail.get_text(), "After 5 s, starts vm1 · when sw1 starts"
        )
        self.factory.rename(sw, "sw9")
        self.assertEqual(
            row.detail.get_text(), "After 5 s, starts vm1 · when sw9 starts"
        )
        self.factory.dup_brick(sw)
        self.assertEqual(
            row.detail.get_text(),
            "After 5 s, starts vm1 · when sw9 starts · when copy_of_sw9 "
            "starts",
        )
        self.factory.del_brick(sw)
        self.assertEqual(
            row.detail.get_text(),
            "After 5 s, starts vm1 · when copy_of_sw9 starts",
        )

    def test_the_rows_follow_the_events(self):
        other = self.event("other", 1, "vm2 on")
        self.assertEqual(self.listed(), [self.ev, other])
        self.assertEqual(
            self.row(other).detail.get_text(), "After 1 s, starts vm2"
        )
        self.factory.del_event(self.ev)
        self.assertEqual(self.listed(), [other])
        self.assertIsNone(self.row())

    def test_start_and_stop(self):
        row = self.row()
        row.startstop.clicked()
        self.assertIsNotNone(self.ev.scheduled)
        row.startstop.clicked()
        self.assertIsNone(self.ev.scheduled)
        self.assertEqual(self.clock.getDelayedCalls(), [])

    def test_after_quit(self):
        row = self.row()
        self.ev.poweron()
        self.tab.on_quit()
        self.assertEqual(len(self.clock.getDelayedCalls()), 1)
        self.factory.new_brick("switch", "sw1").set(
            {"pon_vbevent": "start-vms"}
        )
        self.assertEqual(row.detail.get_text(), "After 5 s, starts vm1")
        self.ev.poweroff()
        self.tab.on_quit = lambda: None


class TestTheRowAboveTheList(EventsTestCase):

    def test_its_words(self):
        tab = self.tab
        self.assertEqual(tab.title, "_Events")
        self.assertEqual(tab.new_button.get_label(), "New Event")
        self.assertEqual(tab.search.get_placeholder_text(), "Search events")
        self.assertEqual(tab.running_button.get_label(), "Waiting")
        self.assertEqual(tab.count.get_text(), "0 of 1 waiting")
        self.event("other", 1, "vm2 on").poweron()
        self.assertEqual(tab.count.get_text(), "1 of 2 waiting")

    def test_the_count(self):
        self.assertEqual(count([]), "0 of 0 waiting")
        self.ev.poweron()
        self.assertEqual(count([self.ev]), "1 of 1 waiting")

    def test_new_event(self):
        shown = []
        self.patch(tab, "NewEventDialog", lambda *a: FakeDialog(shown, *a))
        self.tab.new_button.clicked()
        self.assertEqual(shown, [((self.gui,), self.gui.window)])

    def test_start_all_starts_what_can(self):
        # an event without actions doesn't stop the others
        draft = self.event("draft")
        other = self.event("other", 1, "vm2 on")
        self.tab.start_button.clicked()
        self.assertIsNotNone(self.ev.scheduled)
        self.assertIsNone(draft.scheduled)
        self.assertIsNotNone(other.scheduled)
        # and what waits waits on
        scheduled = other.scheduled
        self.clock.advance(0.5)
        self.tab.start_all()
        self.assertIs(other.scheduled, scheduled)

    def test_stop_all_stops_what_waits(self):
        other = self.event("other", 1, "vm2 on")
        self.ev.poweron()
        other.poweron()
        self.tab.stop_button.clicked()
        self.assertIsNone(self.ev.scheduled)
        self.assertIsNone(other.scheduled)
        self.clock.advance(5)
        self.assertEqual(Recording.performed, [])

    def test_the_buttons_for_all_events(self):
        tab = self.tab
        self.assertTrue(tab.start_button.get_sensitive())
        self.assertFalse(tab.stop_button.get_sensitive())
        self.ev.poweron()
        self.assertFalse(tab.start_button.get_sensitive())
        self.assertTrue(tab.stop_button.get_sensitive())
        # nothing to start in an event without actions
        self.ev.poweroff()
        self.ev.set({"actions": []})
        self.assertFalse(tab.start_button.get_sensitive())

    def test_the_search(self):
        self.event("ping-gateway", 1, "vm2 on")
        self.tab.list.set_search("VMS")
        self.assertEqual(self.listed(), [self.ev])
        # by name only: not "event"
        self.tab.list.set_search("event")
        self.assertEqual(self.listed(), [])
        self.assertEqual(
            self.tab.list.placeholder.get_text(), "No event matches “event”"
        )

    def test_the_waiting_events(self):
        other = self.event("other", 1, "vm2 on")
        self.tab.running_button.set_active(True)
        self.assertEqual(self.listed(), [])
        self.assertEqual(
            self.tab.list.placeholder.get_text(), "No event is waiting"
        )
        other.poweron()
        self.assertEqual(self.listed(), [other])
        self.clock.advance(1)
        self.assertEqual(self.listed(), [])


class TestAProjectWithoutEvents(EventsTestCase):

    def setUp(self):
        super().setUp()
        self.factory.del_event(self.ev)

    def test_the_page(self):
        tab = self.tab
        self.assertIs(tab.pages.get_visible_child(), tab.empty)
        image, title, words, button = tab.empty.get_children()
        self.assertEqual(title.get_text(), "No Events Yet")
        self.assertEqual(
            words.get_text(),
            "An event waits, then starts or stops bricks, or runs commands. "
            "Add one to script the lab.",
        )
        self.assertEqual(button.get_label(), "New Event")
        self.assertIsNotNone(image.get_pixbuf())
        self.assertEqual(tab.count.get_text(), "")
        self.assertFalse(tab.start_button.get_sensitive())

    def test_the_first_event(self):
        self.event("first")
        self.assertEqual(self.tab.pages.get_visible_child_name(), "list")


class TestTheKeysAndTheMouse(EventsTestCase):

    def test_delete(self):
        self.select(self.ev)
        self.assertTrue(self.press(Gdk.KEY_Delete))
        self.assertEqual(self.gui.removed, [self.ev])

    def test_rename(self):
        shown = []
        self.patch(eventmenu, "RenameDialog", lambda *a: FakeDialog(shown, *a))
        self.select(self.ev)
        self.assertTrue(self.press(Gdk.KEY_F2))
        self.assertEqual(shown, [((self.factory, self.ev), self.gui.window)])
        # not while it waits
        self.ev.poweron()
        self.assertTrue(self.press(Gdk.KEY_F2))
        self.assertEqual(len(shown), 1)

    def test_the_menu(self):
        shown = []
        self.patch(
            eventmenu, "popup", lambda *args: shown.append(args) or "menu"
        )
        row = self.select(self.ev)
        self.assertTrue(self.press(Gdk.KEY_Menu))
        self.assertEqual(
            shown, [(row.menu_button, None, self.gui, self.ev, True)]
        )
        self.assertEqual(self.tab._menu, "menu")

    def test_the_menu_of_a_row(self):
        # the menu of the event, without keys, and its actions
        row = self.row()
        section = row.menu_model().get_item_link(0, "section")
        self.assertEqual(
            section.get_item_attribute_value(1, "label").unpack(), "Run Now"
        )
        self.assertIsNone(section.get_item_attribute_value(2, "accel"))
        self.assertIsInstance(row.actions, eventmenu.EventActions)
        self.assertIs(row.actions.event, self.ev)
        self.assertIs(row.get_action_group("event"), row.actions)

    def test_a_double_click_configures(self):
        self.tab.list.emit("row-activated", self.row())
        self.assertEqual(self.gui.configured, [self.ev])


class TestTheSettings(EventsTestCase):

    def test_the_settings(self):
        tab = self.tab
        self.show()
        tab.configure(self.ev)
        self.assertIs(tab.get_visible_child(), tab.settings)
        head = tab.settings.get_children()[0]
        _image, text = head.get_children()
        name, words = text.get_children()
        self.assertEqual(name.get_text(), "start-vms")
        self.assertEqual(words.get_text(), "Event settings")
        self.assertIsInstance(tab._controller, EventEditor)
        tab._controller.delay.set_value(7)
        tab.ok_button.clicked()
        self.assertEqual(self.ev.config.delay, 7)
        self.assertIs(tab.get_visible_child(), tab.main_page)
        self.assertEqual(self.row().detail.get_text(), "After 7 s, starts vm1")

    def test_cancel(self):
        self.tab.configure(self.ev)
        self.tab._controller.delay.set_value(7)
        self.tab.cancel_button.clicked()
        self.assertEqual(self.ev.config.delay, 5)
        self.assertIsNone(self.tab.configuring)

    def test_deleting_the_event(self):
        self.tab.configure(self.ev)
        self.factory.del_event(self.ev)
        self.assertIsNone(self.tab.configuring)
        self.assertIs(self.tab.get_visible_child(), self.tab.main_page)
