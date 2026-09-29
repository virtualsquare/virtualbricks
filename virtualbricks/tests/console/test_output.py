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

"""The shapes of the answers."""

from twisted.trial import unittest

from virtualbricks.console.output import pairs, table, width


class TestTable(unittest.TestCase):

    def test_columns(self):
        self.assertEqual(
            table(
                [
                    ("router", "Virtual machine", "running"),
                    ("sw1", "Switch", ""),
                ],
                ["NAME", "KIND", "STATE"],
            ),
            [
                "NAME    KIND             STATE",
                "router  Virtual machine  running",
                "sw1     Switch",
            ],
        )

    def test_without_headers(self):
        self.assertEqual(
            table([("a", "b"), ("ccc", "d")]), ["a    b", "ccc  d"]
        )
        self.assertEqual(table([]), [])

    def test_wide_characters(self):
        # a Chinese name takes two columns a character
        self.assertEqual(width("交换机"), 6)
        self.assertEqual(
            table([("交换机", "x"), ("sw", "y")]),
            ["交换机  x", "sw      y"],
        )


class TestPairs(unittest.TestCase):

    def test_pairs(self):
        self.assertEqual(
            pairs(
                [("ports", "32"), ("hub_mode", "false")],
                {"hub_mode": "not used"},
            ),
            ["ports = 32", "hub_mode = false  # not used"],
        )
