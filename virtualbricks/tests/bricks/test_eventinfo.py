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

"""What the Events tab says about an event, and its actions read and back."""

import dataclasses

from twisted.internet import task

from virtualbricks import console
from virtualbricks.tests import BrickTestCase

from virtualbricks.bricks import eventinfo
from virtualbricks.bricks.eventinfo import (
    Action,
    Kind,
    State,
    missing,
    names,
    read,
    seconds_left,
    state,
    summary,
    triggers,
    write,
)


class Scheduled:
    def __init__(self, time):
        self.time = time

    def getTime(self):
        return self.time

    def cancel(self):
        pass


def vb(command):
    return console.VbShellCommand(command)


class EventInfoTestCase(BrickTestCase):

    def setUp(self):
        super().setUp()
        self.sw1 = self.factory.new_brick("switch", "sw1")
        self.vm1 = self.factory.new_brick("qemu", "vm1")
        self.event = self.factory.new_event("start-lab")
        self.other = self.factory.new_event("start-vms")

    def actions(self, *commands, delay=5):
        self.event.set({"delay": delay, "actions": list(commands)})


class TestState(EventInfoTestCase):

    def test_the_states(self):
        self.assertIs(state(self.event), State.NOT_CONFIGURED)
        self.actions(vb("sw1 on"))
        self.assertIs(state(self.event), State.READY)
        self.event.scheduled = Scheduled(5)
        self.assertIs(state(self.event), State.WAITING)
        self.assertEqual(
            [eventinfo.LABELS[s] for s in State],
            ["Ready", "Waiting", "Not configured"],
        )

    def test_the_seconds_left(self):
        clock = task.Clock()
        self.assertIsNone(seconds_left(self.event, clock))
        self.event.scheduled = Scheduled(12)
        self.assertEqual(seconds_left(self.event, clock), 12)
        clock.advance(0.5)
        # a second that has begun counts
        self.assertEqual(seconds_left(self.event, clock), 12)
        clock.advance(11.5)
        self.assertEqual(seconds_left(self.event, clock), 0)
        clock.advance(1)
        self.assertEqual(seconds_left(self.event, clock), 0)


class TestActions(EventInfoTestCase):

    def test_read(self):
        for command, expected in (
            (vb("sw1 on"), Action(Kind.START_BRICK, "sw1")),
            (vb("sw1 off"), Action(Kind.STOP_BRICK, "sw1")),
            (vb("start-vms on"), Action(Kind.START_EVENT, "start-vms")),
            (vb("start-vms off"), Action(Kind.STOP_EVENT, "start-vms")),
            # a brick that is gone
            (vb("sw9 on"), Action(Kind.START_BRICK, "sw9")),
            (
                vb("vm1 config ram=512"),
                Action(Kind.CONSOLE, "vm1 config ram=512"),
            ),
            (vb("new switch sw3"), Action(Kind.CONSOLE, "new switch sw3")),
            # the console's own command first
            (vb("help on"), Action(Kind.CONSOLE, "help on")),
            (vb("sw1 on now"), Action(Kind.CONSOLE, "sw1 on now")),
            (
                console.ShellCommand("ping -c 3 10.0.0.254"),
                Action(Kind.SHELL, "ping -c 3 10.0.0.254"),
            ),
        ):
            self.assertEqual(read(command, self.factory), expected, command)

    def test_written_back(self):
        for command in (
            vb("sw1 on"),
            vb("sw1 off"),
            vb("start-vms on"),
            vb("start-vms off"),
            vb("vm1 config ram=512"),
            console.ShellCommand("ls -l"),
        ):
            written = write(read(command, self.factory))
            self.assertEqual(str(written), str(command))
            self.assertIs(type(written), type(command))

    def test_missing(self):
        self.assertFalse(
            missing(Action(Kind.START_BRICK, "sw1"), self.factory)
        )
        self.assertTrue(missing(Action(Kind.STOP_BRICK, "sw9"), self.factory))
        self.assertFalse(
            missing(Action(Kind.START_EVENT, "start-vms"), self.factory)
        )
        self.assertTrue(missing(Action(Kind.STOP_EVENT, "gone"), self.factory))
        self.assertIs(
            missing(Action(Kind.CONSOLE, "sw9 x"), self.factory), False
        )
        self.assertIs(missing(Action(Kind.SHELL, "sw9"), self.factory), False)

    def test_an_action_stays_as_it_is(self):
        action = Action(Kind.START_BRICK, "sw1")
        self.assertRaises(
            dataclasses.FrozenInstanceError, setattr, action, "subject", "sw2"
        )


class TestWords(EventInfoTestCase):

    def test_names(self):
        self.assertEqual(names(["sw1"]), "sw1")
        self.assertEqual(names(["sw1", "sw2"]), "sw1 and sw2")
        self.assertEqual(names(["sw1", "sw2", "sw3"]), "sw1, sw2 and sw3")

    def test_no_actions(self):
        self.assertEqual(summary(self.event, self.factory), "No actions yet")

    def test_after_a_delay(self):
        self.factory.new_brick("switch", "sw2")
        self.actions(vb("sw1 on"), vb("sw2 on"))
        self.assertEqual(
            summary(self.event, self.factory), "After 5 s, starts sw1 and sw2"
        )

    def test_at_once(self):
        self.actions(vb("vm1 off"), delay=0)
        self.assertEqual(
            summary(self.event, self.factory), "At once, stops vm1"
        )

    def test_every_kind(self):
        self.factory.new_event("ping")
        self.actions(
            vb("sw1 on"),
            vb("vm1 off"),
            vb("start-vms on"),
            vb("ping on"),
            vb("start-vms off"),
            vb("vm1 on"),
            vb("vm1 config ram=512"),
            console.ShellCommand("logger up"),
        )
        self.assertEqual(
            summary(self.event, self.factory),
            "After 5 s, starts sw1 and vm1, stops vm1, starts the events "
            "start-vms and ping, stops the event start-vms, runs "
            "“vm1 config ram=512”, runs “logger up” on the host",
        )

    def test_the_bricks_that_start_it(self):
        self.actions(vb("sw1 on"))
        self.sw1.set({"on_start": "start-lab"})
        self.vm1.set({"on_stop": "start-lab", "on_start": "start-vms"})
        self.assertEqual(
            triggers(self.event, self.factory.bricks),
            [(self.sw1, "on"), (self.vm1, "off")],
        )
        self.assertEqual(
            summary(self.event, self.factory),
            "After 5 s, starts sw1 · when sw1 starts · when vm1 stops",
        )
        self.assertEqual(
            triggers(self.other, self.factory.bricks), [(self.vm1, "on")]
        )
