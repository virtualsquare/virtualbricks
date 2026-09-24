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


"""The events and their actions."""

from virtualbricks import console
from virtualbricks.config import Report
from virtualbricks.events import EventAction, EventConfig
from virtualbricks.tests import (
    BrickTestCase,
)


class TestEvents(BrickTestCase):

    def test_action_kind(self):
        kind = EventAction()
        report = Report()
        vb = console.VbShellCommand("sw on")
        shell = console.ShellCommand("logger hi")
        kind.check(vb)
        self.assertRaises(ValueError, kind.check, "sw on")
        self.assertEqual(kind.to_data(vb), {"kind": "vb", "command": "sw on"})
        self.assertEqual(
            kind.to_data(shell), {"kind": "shell", "command": "logger hi"}
        )
        value = kind.from_data(
            {"kind": "shell", "command": "x", "extra": 1}, report, "a"
        )
        self.assertIsInstance(value, console.ShellCommand)
        self.assertEqual(
            [str(m) for m in report], ["a.extra: unknown field, dropped"]
        )
        for bad in ("x", {"kind": "python", "command": "x"}, {"kind": "vb"}):
            self.assertRaises(ValueError, kind.from_data, bad, report, "a")
        self.assertEqual(kind.format(vb), 'vb "sw on"')
        self.assertEqual(kind.format(shell), 'shell "logger hi"')

    def test_config(self):
        event = self.factory.new_event("boot")
        self.assertEqual(event.config, EventConfig())
        event.set({"delay": 2, "actions": [console.VbShellCommand("a on")]})
        self.assertTrue(event.configured())
        self.assertIn("Delay: 2", event.get_parameters())
        event.set({"actions": [console.ShellCommand("ls")]})
        self.assertIn('"*ls"', event.get_parameters())

    def test_dup_event(self):
        event = self.factory.new_event("boot")
        event.set({"delay": 2, "actions": [console.VbShellCommand("a on")]})
        copy = self.factory.dup_event(event)
        self.assertEqual(copy.config, event.config)
        copy.config.actions.append(console.VbShellCommand("b on"))
        self.assertEqual(len(event.config.actions), 1)
