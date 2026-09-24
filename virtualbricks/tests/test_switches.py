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


"""The switches."""

from virtualbricks.tests import (
    CommandTestCase,
)


class TestSwitch(CommandTestCase):

    def test_switch_parameters(self):
        switch = self.factory.new_brick("switch", "sw")
        self.assertEqual(switch.get_parameters(), "Ports: 32")
        switch.set({"fstp": True, "hub": True, "numports": 8})
        self.assertEqual(switch.get_parameters(), "Ports: 8, FSTP, HUB")
        self.assertEqual(switch.socks[0].get_free_ports(), 8)
