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


"""The switch, and the draft of its settings: a port for each plug in it."""

from virtualbricks.bricks.draft import Problem
from virtualbricks.bricks.switch import SwitchConfig, SwitchDraft
from virtualbricks.config.schema import info_of
from virtualbricks.tests import (
    BrickTestCase,
    CommandTestCase,
)


class TestSwitch(CommandTestCase):

    def test_switch_parameters(self):
        switch = self.factory.new_brick("switch", "sw")
        self.assertEqual(switch.get_parameters(), "Ports: 32")
        switch.set({"fast_spanning_tree": True, "hub_mode": True, "ports": 8})
        self.assertEqual(switch.get_parameters(), "Ports: 8, FSTP, HUB")
        self.assertEqual(switch.socks[0].get_free_ports(), 8)


class TestTheDraft(BrickTestCase):

    def setUp(self):
        super().setUp()
        self.switch = self.factory.new_brick("switch", "sw1")

    def plug(self, kind, name, count=1):
        brick = self.factory.new_brick(kind, name)
        for _ in range(count):
            brick.add_plug(self.switch.socks[0])
        return brick

    def test_a_switch_has_one(self):
        self.assertIsInstance(
            self.switch.draft_factory(self.switch), SwitchDraft
        )

    def test_nothing_plugged(self):
        draft = SwitchDraft(self.switch)
        self.assertEqual(draft.plugged(), [])
        self.assertEqual(draft.limits("ports"), (1, 128))
        self.assertEqual(draft.note("ports"), "")
        self.assertEqual(draft.check(), [])

    def test_a_port_for_each_plug(self):
        # a machine with two cards in the switch, and a wire's end
        self.plug("qemu", "vm1", 2)
        wire = self.factory.new_brick("wire", "w1")
        wire.plugs[0].connect(self.switch.socks[0])
        draft = SwitchDraft(self.switch)
        self.assertEqual(
            [brick.name for brick in draft.plugged()], ["vm1", "w1"]
        )
        self.assertEqual(draft.limits("ports"), (3, 128))
        self.assertEqual(draft.limits("hub_mode"), (None, None))
        self.assertEqual(
            draft.note("ports"), "at least 3: vm1, w1 plug into sw1"
        )
        self.assertEqual(draft.note("hub_mode"), "")
        draft.set("ports", 2)
        self.assertEqual(
            draft.check(),
            [Problem("ports", "sw1 needs 3 ports, one for each plug")],
        )
        draft.set("ports", 3)
        self.assertEqual(draft.check(), [])

    def test_one_brick(self):
        self.plug("qemu", "vm1", 2)
        draft = SwitchDraft(self.switch)
        self.assertEqual(draft.note("ports"), "at least 2: vm1 plugs into sw1")

    def test_the_labels(self):
        self.assertEqual(
            [
                (
                    info_of(SwitchConfig, name).label,
                    info_of(SwitchConfig, name).help,
                )
                for name in ("ports", "hub_mode", "fast_spanning_tree")
            ],
            [
                ("Ports", "Number of ports"),
                ("Hub mode", "Send every packet to every port, as a hub"),
                ("Fast spanning tree", "Run the fast spanning tree protocol"),
            ],
        )
