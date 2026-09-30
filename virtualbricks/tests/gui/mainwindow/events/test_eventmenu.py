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

"""The menu of an event: its items, when they are enabled, what they do."""

from twisted.internet import task

from virtualbricks.bricks import event as event_module
from virtualbricks.bricks.eventaction import StartAction
from virtualbricks.tests import FakeLogger
from virtualbricks.tests.gui import GuiTestCase, has_display
from virtualbricks.tests.gui.mainwindow.bricks.test_brickmenu import (
    attribute,
    content,
)

if has_display:
    from gi.repository import Gdk, Gtk

    from virtualbricks.gui.mainwindow.events import eventmenu
    from virtualbricks.gui.mainwindow.events.eventmenu import (
        EventActions,
        menu,
        popup,
    )


class Recording(StartAction):
    """An action that records that it was performed."""

    performed = []

    def perform(self, factory):
        self.performed.append(f"{self.target} on")
        return 0


class FakeGui:
    def __init__(self, factory):
        self.brickfactory = factory
        self.window = object()
        self.calls = []

    def curtain_up(self, event):
        self.calls.append(("configure", event))

    def ask_remove_event(self, event):
        self.calls.append(("delete", event))


class FakeDialog:
    def __init__(self, shown, *args):
        self.shown = shown
        self.args = args

    def show(self, parent):
        self.shown.append((self.args, parent))


class EventMenuTestCase(GuiTestCase):

    def setUp(self):
        super().setUp()
        self.clock = task.Clock()
        self.patch(event_module, "reactor", self.clock)
        self.gui = FakeGui(self.factory)
        Recording.performed = []

    def event(self, name, delay=5, *commands):
        event = self.factory.new_event(name)
        self.patch(event, "logger", FakeLogger())
        event.update_config(
            {
                "delay": delay,
                "actions": [
                    Recording(command.removesuffix(" on"))
                    for command in commands
                ],
            }
        )
        return event

    def ready(self, name="ev"):
        return self.event(name, 5, "sw1 on")

    def waiting(self, name="ev"):
        event = self.ready(name)
        event.poweron()
        return event


class TestTheMenu(EventMenuTestCase):

    def test_an_event(self):
        self.assertEqual(
            content(menu(self.ready())),
            [
                ["Start", "Run Now", "Configure…"],
                ["Rename…", "Duplicate"],
                ["Delete…"],
            ],
        )

    def test_a_waiting_event(self):
        self.assertEqual(
            content(menu(self.waiting()))[0],
            ["Stop", "Run Now", "Configure…"],
        )

    def test_an_event_without_actions(self):
        # the same items, some disabled
        self.assertEqual(
            content(menu(self.event("draft")))[0],
            ["Start", "Run Now", "Configure…"],
        )

    def test_the_keys(self):
        event = self.ready()
        model = menu(event, keys=True)
        self.assertEqual(attribute(model, [0, 2], "accel"), "Return")
        self.assertEqual(attribute(model, [1, 0], "accel"), "F2")
        self.assertEqual(attribute(model, [2, 0], "accel"), "Delete")
        for path in ([0, 0], [0, 1], [1, 1]):
            self.assertIsNone(attribute(model, path, "accel"), path)
        model = menu(event)
        self.assertIsNone(attribute(model, [0, 2], "accel"))

    def test_every_item_has_its_action(self):
        event = self.ready()
        actions = set(EventActions(self.gui, event).list_actions())
        model = menu(event)
        used = set()
        for i in range(model.get_n_items()):
            section = model.get_item_link(i, "section")
            for j in range(section.get_n_items()):
                action = section.get_item_attribute_value(j, "action")
                used.add(action.unpack())
        self.assertEqual({name.partition(".")[2] for name in used}, actions)
        self.assertEqual({name.partition(".")[0] for name in used}, {"event"})


class TestWhatIsEnabled(EventMenuTestCase):

    ALL = [
        "configure",
        "delete",
        "duplicate",
        "rename",
        "run-now",
        "startstop",
    ]

    def enabled(self, event):
        actions = EventActions(self.gui, event)
        return sorted(
            name
            for name in actions.list_actions()
            if actions.get_action_enabled(name)
        )

    def test_a_ready_event(self):
        self.assertEqual(self.enabled(self.ready()), self.ALL)

    def test_at_once(self):
        # a delay of 0 is ready too
        self.assertEqual(self.enabled(self.event("ev", 0, "sw1 on")), self.ALL)

    def test_an_event_without_actions(self):
        # it can't start, and has nothing to run
        self.assertEqual(
            self.enabled(self.event("draft")),
            ["configure", "delete", "duplicate", "rename"],
        )

    def test_a_waiting_event(self):
        # it can stop, and run now, but not be renamed
        enabled = self.enabled(self.waiting())
        self.assertEqual(
            enabled, [name for name in self.ALL if name != "rename"]
        )

    def test_update(self):
        event = self.ready()
        actions = EventActions(self.gui, event)
        event.poweron()
        self.assertTrue(actions.get_action_enabled("rename"))
        actions.update()
        self.assertFalse(actions.get_action_enabled("rename"))


class TestWhatTheItemsDo(EventMenuTestCase):

    def test_the_gui(self):
        event = self.ready()
        actions = EventActions(self.gui, event)
        actions.activate_action("configure", None)
        actions.activate_action("delete", None)
        self.assertEqual(
            self.gui.calls, [("configure", event), ("delete", event)]
        )

    def test_rename(self):
        shown = []
        self.patch(eventmenu, "RenameDialog", lambda *a: FakeDialog(shown, *a))
        event = self.ready()
        EventActions(self.gui, event).activate_action("rename", None)
        self.assertEqual(shown, [((self.factory, event), self.gui.window)])

    def test_duplicate(self):
        event = self.ready()
        EventActions(self.gui, event).activate_action("duplicate", None)
        copy = self.factory.get_event("copy_of_ev")
        self.assertEqual(copy.config, event.config)

    def test_start_and_stop(self):
        event = self.ready()
        actions = EventActions(self.gui, event)
        actions.activate_action("startstop", None)
        self.assertIsNotNone(event.scheduled)
        actions.activate_action("startstop", None)
        self.assertIsNone(event.scheduled)
        self.clock.advance(5)
        self.assertEqual(Recording.performed, [])

    def test_run_now(self):
        event = self.event("ev", 5, "sw1 on", "sw2 on")
        EventActions(self.gui, event).activate_action("run-now", None)
        self.assertEqual(Recording.performed, ["sw1 on", "sw2 on"])
        # it doesn't start the event
        self.assertIsNone(event.scheduled)
        self.assertEqual(self.clock.getDelayedCalls(), [])

    def test_run_now_while_waiting(self):
        # the wait goes on, and runs the actions again at its end
        event = self.waiting()
        scheduled = event.scheduled
        self.clock.advance(2)
        EventActions(self.gui, event).activate_action("run-now", None)
        self.assertEqual(Recording.performed, ["sw1 on"])
        self.assertIs(event.scheduled, scheduled)
        self.assertEqual(scheduled.getTime(), 5)
        self.clock.advance(3)
        self.assertEqual(Recording.performed, ["sw1 on", "sw1 on"])
        self.assertIsNone(event.scheduled)


class TestPopup(EventMenuTestCase):

    def test_at_the_pointer(self):
        shown = []
        self.patch(
            Gtk.Menu,
            "popup_at_pointer",
            lambda menu, event: shown.append(event),
        )
        event = self.ready()
        widget = Gtk.Button()
        self.addCleanup(widget.destroy)
        click = Gdk.Event.new(Gdk.EventType.BUTTON_PRESS)
        result = popup(widget, click, self.gui, event)
        self.addCleanup(result.destroy)
        self.assertEqual(shown, [click])
        self.assertIs(result.get_attach_widget(), widget)
        actions = result.get_action_group("event")
        self.assertIsInstance(actions, EventActions)
        self.assertIs(actions.event, event)
        labels = [
            child.get_label()
            for child in result.get_children()
            if not isinstance(child, Gtk.SeparatorMenuItem)
        ]
        self.assertEqual(labels[:3], ["Start", "Run Now", "Configure…"])
        # no keys, unless asked
        configure = result.get_children()[2]
        self.assertEqual(configure.get_property("accel"), "")
        with_keys = popup(widget, click, self.gui, event, keys=True)
        self.addCleanup(with_keys.destroy)
        configure = with_keys.get_children()[2]
        self.assertEqual(configure.get_property("accel"), "Return")

    def test_under_a_widget(self):
        # for the Menu key: no event
        shown = []
        self.patch(
            Gtk.Menu,
            "popup_at_widget",
            lambda menu, widget, anchor, gravity, event: shown.append(
                (widget, anchor, gravity, event)
            ),
        )
        widget = Gtk.Button()
        self.addCleanup(widget.destroy)
        result = popup(widget, None, self.gui, self.ready())
        self.addCleanup(result.destroy)
        self.assertEqual(
            shown,
            [(widget, Gdk.Gravity.SOUTH_EAST, Gdk.Gravity.NORTH_EAST, None)],
        )
