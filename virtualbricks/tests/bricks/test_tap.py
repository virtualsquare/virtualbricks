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


"""The tap."""

import os

from virtualbricks.config import settings
from virtualbricks.tests import (
    CommandTestCase,
)


class TestTap(CommandTestCase):

    def tap(self, **values):
        tap = self.factory.new_brick("tap", "tap0")
        tap.set(values)
        commands = []
        self.patch(os, "system", commands.append)
        # post_poweron is never called and calls a method that is not there
        tap.start_related_events = lambda on: None
        return tap, commands

    def test_tap(self):
        tap, _ = self.tap()
        self.assertEqual(tap.get_parameters(), "disconnected")
        sw = self.factory.new_brick("switch", "sw")
        tap.plugs[0].connect(sw.socks[0])
        self.assertEqual(tap.get_parameters(), "plugged to sw ")
        self.assertEqual(tap.prog(), os.path.join(self.bin, "vde_plug2tap"))

    def test_tap_address(self):
        settings.set("sudo", "/usr/bin/sudo")
        for needsudo, prefix in ((False, ""), (True, "/usr/bin/sudo ")):
            tap, commands = self.tap(
                mode="manual", ip="10.1.0.2", nm="255.255.0.0", gw="10.1.0.1"
            )
            self.patch(tap, "needsudo", lambda: needsudo)
            tap.post_poweron()
            quote = '"' if needsudo else ""
            self.assertEqual(
                commands,
                [
                    f"{prefix}{quote}/sbin/ifconfig tap0 10.1.0.2 netmask "
                    f"255.255.0.0{quote}",
                    f"{prefix}{quote}/sbin/route add default gw 10.1.0.1 dev "
                    f"tap0{quote}",
                ],
            )
            self.factory.del_brick(tap)

    def test_tap_without_gateway_and_dhcp(self):
        tap, commands = self.tap(mode="manual", gw="")
        self.patch(tap, "needsudo", lambda: False)
        tap.post_poweron()
        self.assertEqual(len(commands), 1)
        tap.set({"mode": "dhcp"})
        tap.post_poweron()
        self.assertEqual(commands[-1], "dhclient tap0")
        self.patch(tap, "needsudo", lambda: True)
        tap.post_poweron()
        self.assertEqual(
            commands[-1], f'{settings.get("sudo")} "dhclient tap0"'
        )
