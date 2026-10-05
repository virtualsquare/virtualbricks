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

"""The actions of an event."""

from twisted.internet import defer
from twisted.trial import unittest

from virtualbricks.bricks.eventaction import (
    ConsoleAction,
    EventAction,
    ShellAction,
    StartAction,
    StopAction,
    describe,
)
from virtualbricks.config.report import Report
from virtualbricks.config.schema import Kind
from virtualbricks.console.command import CommandError
from virtualbricks.tests import BrickTestCase

ACTIONS = [
    (StartAction("sw1"), {"kind": "start", "target": "sw1"}),
    (StopAction("boot"), {"kind": "stop", "target": "boot"}),
    (
        ConsoleAction("brick set vm1 memory=512"),
        {"kind": "console", "command": "brick set vm1 memory=512"},
    ),
    (ShellAction("logger hi"), {"kind": "shell", "command": "logger hi"}),
]


class TestEventAction(unittest.TestCase):

    def setUp(self):
        self.kind = EventAction()
        self.report = Report()

    def test_is_a_kind(self):
        self.assertIsInstance(self.kind, Kind)

    def test_check(self):
        for action, _data in ACTIONS:
            self.kind.check(action)
        for value in ("sw on", 1, None, ["sw on"], {"kind": "start"}):
            self.assertRaises(ValueError, self.kind.check, value)

    def test_data_both_ways(self):
        for action, data in ACTIONS:
            self.assertEqual(self.kind.to_data(action), data)
            self.assertEqual(
                self.kind.from_data(data, self.report, "a"), action
            )
        self.assertEqual(len(self.report), 0)

    def test_what_is_wrong(self):
        for data, error in (
            ("sw1 on", "'sw1 on' is not a table"),
            (
                {"kind": "vb", "command": "sw1 on"},
                "'vb' is not start, stop, console or shell",
            ),
            ({"kind": "start"}, "target None is not a target"),
            (
                {"kind": "shell", "command": " "},
                "command ' ' is not a command",
            ),
        ):
            exc = self.assertRaises(
                ValueError, self.kind.from_data, data, self.report, "a"
            )
            self.assertEqual(str(exc), error)

    def test_unknown_fields(self):
        action = self.kind.from_data(
            {"kind": "start", "target": "sw1", "when": 1}, self.report, "a"
        )
        self.assertEqual(action, StartAction("sw1"))
        self.assertEqual(
            [str(message) for message in self.report],
            ["a.when: unknown field, dropped"],
        )

    def test_in_words(self):
        self.assertEqual(
            [describe(action) for action, _data in ACTIONS],
            [
                "start sw1",
                "stop boot",
                'console "brick set vm1 memory=512"',
                'shell "logger hi"',
            ],
        )
        self.assertEqual(self.kind.format(StartAction("sw1")), "start sw1")


class TestPerform(BrickTestCase):

    def setUp(self):
        super().setUp()
        self.factory.runtime_dir = "/run/vb"
        self.done = []
        self.sw1 = self.factory.new_brick("switch", "sw1")
        self.sw1.start = lambda resume="": defer.succeed(
            self.done.append("sw1 on")
        )
        self.sw1.poweroff = lambda kill=False: defer.succeed(
            self.done.append("sw1 off")
        )
        self.boot = self.factory.new_event("boot")
        self.boot.start = lambda: self.done.append("boot on")
        self.boot.poweroff = lambda: self.done.append("boot off")

    def test_start_and_stop(self):
        for action in (
            StartAction("sw1"),
            StopAction("sw1"),
            StartAction("boot"),
            StopAction("boot"),
        ):
            self.successResultOf(action.perform(self.factory))
        self.assertEqual(
            self.done, ["sw1 on", "sw1 off", "boot on", "boot off"]
        )

    def test_a_target_not_there(self):
        failure = self.failureResultOf(
            defer.maybeDeferred(StartAction("nope").perform, self.factory)
        )
        self.assertEqual(
            failure.getErrorMessage(), "No brick or event named nope"
        )

    def test_a_console_command(self):
        answer = self.successResultOf(
            ConsoleAction("brick new tap").perform(self.factory)
        )
        self.assertEqual(answer, ["tap1"])
        failure = self.failureResultOf(
            ConsoleAction("brick new nope").perform(self.factory)
        )
        failure.trap(CommandError)
