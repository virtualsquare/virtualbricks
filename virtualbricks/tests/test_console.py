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
        self.assertIn("numports = 32", self.lines)
        self.assertIn('pon_vbevent = ""', self.lines)

    def test_config(self):
        switch = self.factory.new_brick("switch", "sw")
        self.protocol.brick_action(switch, ["config", "numports=4"])
        self.assertEqual(switch.config.numports, 4)
        self.protocol.brick_action(switch, ["config", "nope=4"])
        self.protocol.brick_action(switch, ["config", "numports=500"])
        self.assertEqual(
            self.lines, ["No such parameter nope", "500 is outside 1–128"]
        )

    def test_settings(self):
        config = console.ConfigurationProtocol(self.factory)
        config.sendLine = self.lines.append
        config.do_get("femaleplugs")
        config.do_set("femaleplugs", "yes")
        config.do_get("femaleplugs")
        config.do_set("cowfmt", "qed")
        config.do_get("python")
        config.do_set("python", "1")
        self.assertEqual(
            self.lines,
            [
                "femaleplugs = false",
                "femaleplugs = true",
                '"qed" is not one of cow, qcow, qcow2',
                "No such option python",
                "No such option python",
            ],
        )
