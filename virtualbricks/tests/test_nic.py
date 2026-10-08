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

"""The MAC addresses of the network cards."""

import os
import random

from twisted.trial import unittest

from virtualbricks.nic import is_valid_mac, random_mac


class TestRandomMac(unittest.TestCase):

    def urandom(self, octets):
        requested = []

        def urandom(size):
            requested.append(size)
            return octets[:size]

        self.patch(os, "urandom", urandom)
        return requested

    def test_six_random_octets(self):
        requested = self.urandom(bytes.fromhex("feedfacecafe"))
        self.assertEqual(random_mac(), "fe:ed:fa:ce:ca:fe")
        self.assertEqual(requested, [6])

    def test_unicast_and_locally_administered(self):
        # bit 0 of the first octet is cleared, bit 1 set, the others kept
        for first, expected in (
            (0x00, "02"),
            (0x01, "02"),
            (0x03, "02"),
            (0xFF, "fe"),
            (0x53, "52"),
        ):
            self.urandom(bytes([first]) + bytes.fromhex("0123456789"))
            self.assertEqual(random_mac(), f"{expected}:01:23:45:67:89")

    def test_a_valid_address(self):
        mac = random_mac()
        self.assertTrue(is_valid_mac(mac))
        self.assertEqual(mac, mac.lower())
        first = int(mac[:2], 16)
        self.assertEqual(first & 0x03, 0x02)

    def test_different_each_time(self):
        macs = {random_mac() for _ in range(1000)}
        self.assertEqual(len(macs), 1000)

    def test_the_random_module_is_left_alone(self):
        self.addCleanup(random.setstate, random.getstate())
        random.seed(7)
        expected = random.random()
        random.seed(7)
        random_mac()
        self.assertEqual(random.random(), expected)


class TestIsValidMac(unittest.TestCase):

    def test_valid(self):
        for mac in (
            "00:aa:79:71:be:61",
            "52:54:00:AB:CD:EF",
            "fe:Ed:fa:cE:ca:fe",
        ):
            self.assertTrue(is_valid_mac(mac), mac)

    def test_invalid(self):
        for mac in (
            "",
            "00:aa:79:71:be",
            "00:aa:79:71:be:61:01",
            "00-aa-79-71-be-61",
            "00aa.7971.be61",
            "0:aa:79:71:be:61",
            "000:aa:79:71:be:61",
            "00:aa:79:71:be:6g",
            " 00:aa:79:71:be:61",
            "00:aa:79:71:be:61 ",
            "00:aa:79:71:be:61\n",
        ):
            self.assertFalse(is_valid_mac(mac), repr(mac))
