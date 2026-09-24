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


"""The capture."""

import os

from virtualbricks.tests import (
    CommandTestCase,
)


class TestCapture(CommandTestCase):

    def test_capture(self):
        capture = self.factory.new_brick("capture", "cap")
        self.assertEqual(capture.get_parameters(), "No interface selected")
        capture.set({"iface": "eth0"})
        self.assertEqual(
            capture.get_parameters(), "Interface eth0 disconnected"
        )
        self.assertFalse(capture.configured())
        self.assertEqual(capture.sock_path(), "")
        sw = self.factory.new_brick("switch", "sw")
        capture.plugs[0].connect(sw.socks[0])
        self.assertEqual(
            capture.get_parameters(), "Interface eth0 plugged to sw "
        )
        self.assertEqual(capture.sock_path(), sw.socks[0].path.rstrip("[]"))
        self.assertTrue(capture.configured())
        self.assertEqual(
            capture.prog(), os.path.join(self.bin, "vde_pcapplug")
        )
