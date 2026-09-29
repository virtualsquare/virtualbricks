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


"""The commands of the console."""

from virtualbricks import console
from virtualbricks.tests import (
    BrickTestCase,
)


class TestConsole(BrickTestCase):

    def setUp(self):
        super().setUp()
        self.protocol = console.VBProtocol(self.factory)
        self.lines = []
        self.protocol.sendLine = self.lines.append

    def test_show(self):
        switch = self.factory.new_brick("switch", "sw")
        self.protocol.brick_action(switch, ["show"])
        self.assertIn("ports = 32", self.lines)
        self.assertIn('on_start = ""', self.lines)

    def test_show_what_is_not_used(self):
        vm = self.factory.new_brick("qemu", "vm")
        vm.set({"use_vnc": True, "headless": True, "cdrom": "device"})
        self.protocol.brick_action(vm, ["show"])
        # what keeps each out of use, along the chain for vnc_display
        for line in (
            "headless = true",
            "use_vnc = true  # not used: headless is true",
            "vnc_display = 1  # not used: headless is true",
            'cdrom_image = ""  # not used: cdrom is "device"',
            'cdrom_device = ""',
            "gdb_port = 1234  # not used: use_gdb is false",
        ):
            self.assertIn(line, self.lines)

    def test_new(self):
        self.factory.runtime_dir = "/run/vb"
        self.protocol.do_new("switch", "sw")
        self.protocol.do_new("tap", "tap_of_the_lab_1")
        self.protocol.do_new("nope", "x")
        self.assertEqual([brick.name for brick in self.factory.bricks], ["sw"])
        self.assertEqual(
            self.lines,
            [
                "The interface of this computer takes a tap's name: at most"
                " 15 characters, and this one has 16",
                "Invalid brick type nope",
            ],
        )

    def test_config(self):
        switch = self.factory.new_brick("switch", "sw")
        self.protocol.brick_action(switch, ["config", "ports=4"])
        self.assertEqual(switch.config.ports, 4)
        self.protocol.brick_action(switch, ["config", "nope=4"])
        self.protocol.brick_action(switch, ["config", "ports=500"])
        self.assertEqual(
            self.lines, ["No such parameter nope", "500 is outside 1–128"]
        )

    def test_settings(self):
        config = console.ConfigurationProtocol(self.factory)
        config.sendLine = self.lines.append
        config.do_get("allow_female_plugs")
        config.do_set("allow_female_plugs", "yes")
        config.do_get("allow_female_plugs")
        config.do_set("cow_format", "qed")
        config.do_get("python")
        config.do_set("python", "1")
        self.assertEqual(
            self.lines,
            [
                "allow_female_plugs = false",
                "allow_female_plugs = true",
                '"qed" is not one of cow, qcow, qcow2',
                "No such option python",
                "No such option python",
            ],
        )
