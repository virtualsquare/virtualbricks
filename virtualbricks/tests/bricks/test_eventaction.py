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

from twisted.trial import unittest

from virtualbricks import console
from virtualbricks.config import Kind, Report
from virtualbricks.bricks.eventaction import EventAction


class TestEventAction(unittest.TestCase):

    def setUp(self):
        self.kind = EventAction()
        self.report = Report()
        self.vb = console.VbShellCommand("sw on")
        self.shell = console.ShellCommand("logger hi")

    def test_is_a_kind(self):
        self.assertIsInstance(self.kind, Kind)

    def test_check(self):
        self.kind.check(self.vb)
        self.kind.check(self.shell)

    def test_check_rejects_other_values(self):
        for value in ("sw on", 1, None, ["sw on"], console.String("sw on")):
            self.assertRaises(ValueError, self.kind.check, value)

    def test_to_data(self):
        self.assertEqual(
            self.kind.to_data(self.vb), {"kind": "vb", "command": "sw on"}
        )
        self.assertEqual(
            self.kind.to_data(self.shell),
            {"kind": "shell", "command": "logger hi"},
        )

    def test_from_data(self):
        vb = self.kind.from_data(
            {"kind": "vb", "command": "sw on"}, self.report, "a"
        )
        self.assertIsInstance(vb, console.VbShellCommand)
        self.assertEqual(vb, self.vb)
        shell = self.kind.from_data(
            {"kind": "shell", "command": "logger hi"}, self.report, "a"
        )
        self.assertIsInstance(shell, console.ShellCommand)
        self.assertEqual(shell, self.shell)
        self.assertEqual(list(self.report), [])

    def test_from_data_round_trip(self):
        for action in (self.vb, self.shell):
            data = self.kind.to_data(action)
            self.assertEqual(
                self.kind.from_data(data, self.report, "a"), action
            )

    def test_from_data_reports_unknown_fields(self):
        value = self.kind.from_data(
            {"kind": "shell", "command": "x", "extra": 1}, self.report, "a"
        )
        self.assertIsInstance(value, console.ShellCommand)
        self.assertEqual(
            [str(m) for m in self.report], ["a.extra: unknown field, dropped"]
        )

    def test_from_data_rejects_bad_data(self):
        for data, problem in (
            ("x", "'x' is not a table"),
            (
                {"kind": "python", "command": "x"},
                "'python' is not vb or shell",
            ),
            ({"command": "x"}, "None is not vb or shell"),
            ({"kind": "vb"}, "None is not a command"),
            ({"kind": "vb", "command": 3}, "3 is not a command"),
        ):
            with self.assertRaises(ValueError) as caught:
                self.kind.from_data(data, self.report, "a")
            self.assertEqual(str(caught.exception), problem)

    def test_format(self):
        self.assertEqual(self.kind.format(self.vb), 'vb "sw on"')
        self.assertEqual(self.kind.format(self.shell), 'shell "logger hi"')

    def test_kinds(self):
        self.assertEqual(
            EventAction.kinds,
            {"vb": console.VbShellCommand, "shell": console.ShellCommand},
        )
