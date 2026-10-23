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

"""The commands of the events."""

from twisted.internet import defer

from virtualbricks.bricks import event as event_module
from virtualbricks.bricks.eventinfo import Action, Kind, write
from virtualbricks.tests.console import ConsoleTestCase


class EventsTestCase(ConsoleTestCase):

    def setUp(self):
        super().setUp()
        # the events wait on the clock of the commands
        self.patch(event_module, "reactor", self.clock())
        self.factory.runtime_dir = "/run/vb"
        self.sw1 = self.factory.new_brick("switch", "sw1")
        self.vm1 = self.factory.new_brick("qemu", "vm1")

    def event(self, name, *actions, delay=0):
        event = self.factory.new_event(name)
        event.update_config(
            {"delay": delay, "actions": [write(a) for a in actions]}
        )
        return event


class TestMakeAndShow(EventsTestCase):

    def test_new(self):
        self.assertEqual(self.run_line("event new"), ["new_event"])
        self.assertEqual(self.run_line("event new"), ["new_event.1"])
        self.assertEqual(self.run_line("event new 'boot lab'"), ["boot_lab"])
        self.assertEqual(
            self.fails("event new sw1"), "sw1 is the name of a brick"
        )

    def test_list(self):
        self.assertEqual(self.run_line("event list"), ["No events"])
        self.event("boot", Action(Kind.START_BRICK, "vm1"), delay=5)
        self.event("empty")
        self.assertEqual(
            self.run_line("event list"),
            [
                "NAME   STATE           WHAT IT DOES",
                "boot   Ready           After 5 s, starts vm1",
                "empty  Not configured  No actions yet",
            ],
        )

    def test_show(self):
        self.event(
            "boot",
            Action(Kind.START_BRICK, "vm1"),
            Action(Kind.CONSOLE, "brick set vm1 memory=1024"),
            Action(Kind.SHELL, "logger up"),
            delay=5,
        )
        self.sw1.update_config({"on_stop": "boot"})
        self.assertEqual(
            self.run_line("event show boot"),
            [
                "boot  Ready",
                "delay = 5",
                "1  start vm1",
                "2  console 'brick set vm1 memory=1024'",
                "3  shell 'logger up'",
                "started by sw1, its on_stop",
            ],
        )

    def test_set(self):
        event = self.event("boot")
        self.assertEqual(self.run_line("event set boot delay=12"), [])
        self.assertEqual(event.config.delay, 12)
        self.assertEqual(
            self.fails("event set boot delay=x"),
            "boot delay: 'x' is not an integer",
        )
        self.assertEqual(
            self.fails("event set boot actions=x"),
            "event action add, remove and move change the actions",
        )
        self.assertEqual(
            self.fails("event set boot nope=1"), "boot has no key nope"
        )


class TestActions(EventsTestCase):

    def test_add(self):
        self.event("boot")
        self.event("later")
        self.assertEqual(
            self.run_line("event action add boot start vm1"), ["1  start vm1"]
        )
        self.run_line("event action add boot stop later")
        self.run_line('event action add boot console "brick set vm1 cpus=2"')
        self.assertEqual(
            self.run_line("event action add boot shell 'logger up' --at 2"),
            [
                "1  start vm1",
                "2  shell 'logger up'",
                "3  stop later",
                "4  console 'brick set vm1 cpus=2'",
            ],
        )

    def test_what_is_wrong(self):
        self.event("boot")
        self.assertEqual(
            self.fails("event action add boot start nope"),
            "No brick or event named nope",
        )
        self.assertEqual(
            self.fails("event action add boot start"), "start needs a subject"
        )
        # checked as the parser reads it: the names, not the keys
        self.assertEqual(
            self.fails('event action add boot console "brick set vm2 x=1"'),
            "brick set vm2 x=1: No brick named vm2",
        )
        self.assertEqual(
            self.fails("event action add boot console nope"),
            "nope: No command nope; type help for the commands",
        )
        self.assertEqual(
            self.fails("event action add boot start vm1 --at 3"),
            "boot has no action 3",
        )
        self.assertEqual(self.run_line("event show boot")[2:], [])

    def test_remove_and_move(self):
        self.event(
            "boot",
            Action(Kind.START_BRICK, "sw1"),
            Action(Kind.START_BRICK, "vm1"),
            Action(Kind.SHELL, "logger up"),
        )
        self.assertEqual(
            self.run_line("event action move boot 3 1"),
            ["1  shell 'logger up'", "2  start sw1", "3  start vm1"],
        )
        self.assertEqual(
            self.run_line("event action remove boot 1 3"), ["1  start sw1"]
        )
        self.assertEqual(
            self.fails("event action remove boot 2"), "boot has no action 2"
        )


class TestStartAndStop(EventsTestCase):

    def test_start_and_stop(self):
        event = self.event("boot", Action(Kind.START_BRICK, "vm1"), delay=7)
        self.event("empty")
        self.assertEqual(
            self.run_line("event start boot"),
            ["boot runs its actions in 7 s"],
        )
        self.assertEqual(
            self.run_line("event start boot"), ["boot waits already"]
        )
        self.clock().advance(2)
        self.assertEqual(
            self.run_line("event list")[1].split()[:3],
            ["boot", "Waiting,", "5"],
        )
        self.assertEqual(self.run_line("event stop boot"), [])
        self.assertIsNone(event.scheduled)
        self.assertEqual(
            self.run_line("event stop boot"), ["boot isn't waiting"]
        )
        self.assertEqual(
            self.fails("event start empty"), "empty has no action"
        )

    def test_run_now(self):
        started = []
        self.vm1.start = lambda resume="": defer.succeed(started.append("vm1"))
        self.event("boot", Action(Kind.START_BRICK, "vm1"), delay=60)
        self.assertEqual(
            self.run_line("event run boot"), ["boot ran its actions"]
        )
        self.assertEqual(started, ["vm1"])


class TestNames(EventsTestCase):

    def test_rename(self):
        self.event("boot")
        self.sw1.update_config({"on_start": "boot"})
        self.assertEqual(self.run_line("event rename boot up"), [])
        self.assertEqual(self.sw1.config.on_start, "up")
        self.assertEqual(
            self.run_line("event rename up 'up again'"), ["up_again"]
        )

    def test_duplicate_and_delete(self):
        self.event("boot", Action(Kind.START_BRICK, "vm1"), delay=3)
        self.assertEqual(self.run_line("event duplicate boot"), ["boot2"])
        self.assertEqual(self.run_line("event duplicate boot up"), ["up"])
        copy = self.factory.get_event("up")
        self.assertEqual(copy.config.delay, 3)
        self.assertEqual(self.run_line("event delete boot boot2"), [])
        self.assertEqual([e.name for e in self.factory.events], ["up"])

    def test_delete_forgets_the_event(self):
        self.event("boot", Action(Kind.START_BRICK, "vm1"))
        later = self.event(
            "later",
            Action(Kind.STOP_EVENT, "boot"),
            Action(Kind.START_BRICK, "sw1"),
        )
        self.sw1.update_config({"on_start": "boot"})
        self.vm1.update_config({"on_stop": "boot"})
        self.assertEqual(self.run_line("event delete boot"), [])
        self.assertEqual(
            later.config.actions, [write(Action(Kind.START_BRICK, "sw1"))]
        )
        self.assertEqual(self.sw1.config.on_start, "")
        self.assertEqual(self.vm1.config.on_stop, "")
