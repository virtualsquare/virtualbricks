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

"""The events."""

from twisted.internet import task

from virtualbricks import errors
from virtualbricks.bricks.eventaction import (
    ConsoleAction,
    ShellAction,
    StartAction,
)
from virtualbricks.config.schema import ListOf, field_names, kind_of
from virtualbricks.bricks import event as event_module
from virtualbricks.bricks.event import Event, EventConfig, is_event
from virtualbricks.tests import BrickTestCase, FakeLogger


class Recording(ConsoleAction):
    """An action that records that it was performed, and returns a status."""

    performed = []
    status = 0

    def perform(self, factory):
        self.performed.append((self.command, factory))
        return self.status


class Exits(ShellAction):
    """A command of the shell that ends at once with its status."""

    def perform(self, factory):
        return 7


class Failing(ConsoleAction):

    def perform(self, factory):
        raise RuntimeError("the action failed")


class TestEventConfig(BrickTestCase):

    def test_defaults(self):
        event_config = EventConfig()
        self.assertEqual(event_config.actions, [])
        self.assertEqual(event_config.delay, 0)

    def test_actions_are_not_shared(self):
        first, second = EventConfig(), EventConfig()
        first.actions.append(StartAction("a"))
        self.assertEqual(second.actions, [])

    def test_delay_is_an_integer(self):
        event_config = EventConfig()
        event_config.delay = 5
        self.assertRaises(ValueError, setattr, event_config, "delay", "5")
        self.assertRaises(ValueError, setattr, event_config, "delay", 1.5)
        self.assertEqual(event_config.delay, 5)

    def test_actions_are_commands(self):
        self.assertRaises(ValueError, EventConfig, actions=["a on"])
        EventConfig(actions=[ShellAction("ls")])

    def test_the_fields(self):
        self.assertEqual(
            field_names(EventConfig), ["icon", "delay", "actions"]
        )

    def test_the_action_kind(self):
        kind = kind_of(EventConfig, "actions")
        self.assertIsInstance(kind, ListOf)
        self.assertIsInstance(kind.item, event_module.EventAction)


class TestEvent(BrickTestCase):

    def setUp(self):
        super().setUp()
        self.clock = task.Clock()
        self.patch(event_module, "reactor", self.clock)
        self.logger = FakeLogger()
        self.event = self.factory.new_event("boot")
        self.patch(self.event, "logger", self.logger)
        self.changes = []
        self.event.changed.connect(self.changes.append)
        Recording.performed = []
        Recording.status = 0

    def configure(self, delay=3, *actions):
        self.event.update_config({"delay": delay, "actions": list(actions)})
        del self.changes[:]

    def test_type(self):
        self.assertIsInstance(self.event, Event)
        self.assertEqual(self.event.get_type(), "Event")
        self.assertEqual(self.event.name, "boot")
        self.assertIs(self.event.config_factory, EventConfig)

    def test_new_event_has_the_default_config(self):
        self.assertEqual(self.event.config, EventConfig())

    def test_configured(self):
        action = StartAction("a")
        self.assertFalse(self.event.configured())
        self.event.update_config({"delay": 2})
        self.assertFalse(self.event.configured())
        # at once
        self.event.update_config({"delay": 0, "actions": [action]})
        self.assertTrue(self.event.configured())
        self.event.update_config({"delay": 2})
        self.assertTrue(self.event.configured())

    def test_not_running(self):
        self.assertFalse(self.event.is_running())
        self.assertIsNone(self.event.scheduled)

    def test_start_needs_a_configuration(self):
        for delay, actions in ((0, []), (2, [])):
            self.event.update_config({"delay": delay, "actions": actions})
            self.assertRaises(errors.BadConfigError, self.event.start)
        self.assertEqual(self.clock.getDelayedCalls(), [])

    def test_start_schedules_the_actions(self):
        self.configure(3, Recording("a on"))
        deferred = self.event.start()
        self.assertTrue(self.event.is_running())
        [call] = self.clock.getDelayedCalls()
        self.assertEqual(call.getTime(), 3)
        self.assertFalse(deferred.called)
        self.assertEqual(Recording.performed, [])
        self.assertEqual(self.changes, [self.event])

    def test_start_twice(self):
        self.configure(3, Recording("a on"))
        self.event.start()
        self.assertIsNone(self.event.start())
        self.assertEqual(len(self.clock.getDelayedCalls()), 1)
        self.assertEqual(self.changes, [self.event])

    def test_the_actions_run_after_the_delay(self):
        self.configure(3, Recording("a on"), Recording("b on"))
        deferred = self.event.start()
        self.clock.advance(2.9)
        self.assertEqual(Recording.performed, [])
        self.assertFalse(deferred.called)
        self.clock.advance(0.1)
        self.assertEqual(
            Recording.performed,
            [("a on", self.factory), ("b on", self.factory)],
        )
        self.assertFalse(self.event.is_running())
        self.assertEqual(self.clock.getDelayedCalls(), [])
        # the event is over
        self.assertEqual(self.changes, [self.event, self.event])
        return deferred.addCallback(self.assertIs, self.event)

    def test_at_once(self):
        # a delay of 0: when the reactor comes back
        self.configure(0, Recording("a on"))
        deferred = self.event.start()
        self.assertEqual(Recording.performed, [])
        self.clock.advance(0)
        self.assertEqual(Recording.performed, [("a on", self.factory)])
        return deferred.addCallback(self.assertIs, self.event)

    def test_can_run_again(self):
        self.configure(1, Recording("a on"))
        self.event.start()
        self.clock.advance(1)
        self.event.start()
        self.clock.advance(1)
        self.assertEqual(len(Recording.performed), 2)

    def test_the_status_is_logged(self):
        # of a command of the shell
        self.configure(1, Exits("true"), Recording("brick list"))
        self.event.start()
        self.clock.advance(1)
        self.assertEqual(self.logger.levels(), ["info"])
        self.assertEqual(
            self.logger.formatted(), ["Process ended with exit code 7"]
        )

    def test_a_failing_action_is_logged(self):
        self.configure(1, Failing("a on"), Recording("b on"))
        deferred = self.event.start()
        self.clock.advance(1)
        # the other actions still run, and the event finishes
        self.assertEqual(Recording.performed, [("b on", self.factory)])
        self.assertEqual(self.logger.levels(), ["failure"])
        self.assertEqual(
            self.logger.formatted(),
            ['Event boot, action 1, console "a on": the action failed'],
        )
        return deferred.addCallback(self.assertIs, self.event)

    def test_a_refused_action_is_an_error(self):
        # what the console refuses needs no traceback
        self.configure(1, StartAction("nope"), ConsoleAction("nope"))
        self.event.start()
        self.clock.advance(1)
        self.assertEqual(self.logger.levels(), ["error", "error"])
        self.assertEqual(
            self.logger.formatted(),
            [
                "Event boot, action 1, start nope: No brick or event named"
                " nope",
                'Event boot, action 2, console "nope": No command nope; type'
                " help for the commands",
            ],
        )

    def test_stop_cancels_the_actions(self):
        self.configure(3, Recording("a on"))
        self.event.start()
        del self.changes[:]
        self.assertIsNone(self.event.stop())
        self.assertFalse(self.event.is_running())
        self.assertEqual(self.clock.getDelayedCalls(), [])
        self.assertEqual(self.changes, [self.event])
        self.clock.advance(5)
        self.assertEqual(Recording.performed, [])

    def test_stop_when_off(self):
        self.configure(3, Recording("a on"))
        self.assertIsNone(self.event.stop())
        self.assertEqual(self.changes, [])

    def test_set_notifies(self):
        self.event.update_config({"delay": 2})
        self.assertEqual(self.changes, [self.event])

    def test_set_rejects_unknown_options(self):
        self.assertRaises(KeyError, self.event.update_config, {"speed": 1})

    def test_rename(self):
        self.factory.rename_item(self.event, "start")
        self.assertEqual(self.event.name, "start")
        self.assertIs(self.factory.get_event("start"), self.event)
        self.assertIsNone(self.factory.get_event("boot"))

    def test_is_event(self):
        self.assertTrue(is_event(self.event))
        self.assertFalse(is_event(self.factory.new_brick("switch", "sw")))

    def test_dup_event(self):
        self.event.update_config({"delay": 2, "actions": [StartAction("a")]})
        copy = self.factory.duplicate_event(self.event)
        self.assertEqual(copy.config, self.event.config)
        copy.config.actions.append(StartAction("b"))
        self.assertEqual(len(self.event.config.actions), 1)

    def test_del_event_stops_it(self):
        self.configure(3, Recording("a on"))
        self.event.start()
        self.factory.remove_event(self.event)
        self.assertEqual(self.clock.getDelayedCalls(), [])
        self.assertIsNone(self.factory.get_event("boot"))
