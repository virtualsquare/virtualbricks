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


"""The tap, and the draft of its settings."""

from virtualbricks import errors
from virtualbricks.bricks.draft import Problem
from virtualbricks.bricks.tap import Tap, TapDraft
from virtualbricks.tests import (
    BrickTestCase,
    CommandTestCase,
)


class TestTap(CommandTestCase):

    def test_tap(self):
        tap = self.factory.new_brick("tap", "tap0")
        self.assertFalse(tap.configured())
        sw = self.factory.new_brick("switch", "sw")
        tap.plugs[0].connect(sw.socks[0])
        self.assertTrue(tap.configured())

    def test_a_name_that_an_interface_can_have(self):
        Tap.check_name("t" * 15)
        with self.assertRaises(errors.InvalidNameError) as cm:
            Tap.check_name("t" * 16)
        self.assertEqual(
            str(cm.exception),
            "The interface of this computer takes a tap's name: at most 15"
            " characters, and this one has 16",
        )


class TestTheDraft(BrickTestCase):

    def setUp(self):
        super().setUp()
        self.tap = self.factory.new_brick("tap", "tap0")
        sw = self.factory.new_brick("switch", "sw")
        self.tap.plugs[0].connect(sw.socks[0])

    def test_a_tap_has_one(self):
        self.assertIsInstance(self.tap.draft_factory(self.tap), TapDraft)

    def test_the_addresses_set_by_hand(self):
        draft = TapDraft(self.tap)
        for mode in ("off", "dhcp"):
            draft.set("address_mode", mode)
            for name in ("ip_address", "netmask", "gateway"):
                self.assertFalse(draft.uses(name), (mode, name))
        draft.set("address_mode", "manual")
        for name in ("ip_address", "netmask", "gateway"):
            self.assertTrue(draft.uses(name), name)
        self.assertTrue(draft.uses("address_mode"))

    def test_a_wrong_address(self):
        draft = TapDraft(self.tap)
        draft.set("netmask", "255.255.0.300")
        self.assertEqual(
            draft.errors(),
            [Problem("netmask", '"255.255.0.300" is not an IPv4 address')],
        )
        draft.set("gateway", "")
        self.assertEqual(len(draft.errors()), 1)

    def test_not_set_yet(self):
        draft = TapDraft(self.tap)
        self.assertEqual(draft.note("address_mode"), "")
        draft.set("address_mode", "dhcp")
        self.assertEqual(
            draft.note("address_mode"), "Virtualbricks doesn't set it yet"
        )
        self.assertEqual(draft.note("ip_address"), "")
