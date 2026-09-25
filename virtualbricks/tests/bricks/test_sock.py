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

"""The sockets."""

import os

from virtualbricks.bricks.sock import Sock
from virtualbricks.tests import BrickTestCase


class TestSock(BrickTestCase):

    def setUp(self):
        super().setUp()
        self.switch = self.factory.new_brick("switch", "sw")

    def test_new_sock(self):
        sock = Sock(self.switch, "sw_port")
        self.assertIs(sock.brick, self.switch)
        self.assertEqual(sock.path, "sw_port")
        self.assertEqual(sock.nickname, "sw_port")
        self.assertEqual(sock.plugs, [])
        self.assertEqual(sock.mode, "sock")

    def test_the_name_is_optional(self):
        sock = Sock(self.switch)
        self.assertEqual((sock.path, sock.nickname), ("", ""))

    def test_the_plugs_are_not_shared(self):
        first, second = Sock(self.switch), Sock(self.switch)
        first.plugs.append(object())
        self.assertEqual(second.plugs, [])

    def test_the_sock_of_a_brick(self):
        [sock] = self.switch.socks
        self.assertIs(sock.brick, self.switch)
        self.assertEqual(sock.nickname, "sw_port")
        self.assertEqual(sock.path, self.switch.path())
        self.assertIn(sock, self.factory.socks)

    def test_free_ports(self):
        sock = self.switch.socks[0]
        self.assertEqual(sock.get_free_ports(), 32)
        self.switch.set({"numports": 4})
        self.assertEqual(sock.get_free_ports(), 4)

    def test_free_ports_of_the_plugs(self):
        self.switch.set({"numports": 4})
        sock = self.switch.socks[0]
        taps = []
        for name in ("t1", "t2", "t3"):
            tap = self.factory.new_brick("tap", name)
            tap.plugs[0].connect(sock)
            taps.append(tap)
        self.assertEqual(sock.get_free_ports(), 1)
        taps[0].plugs[0].disconnect()
        self.assertEqual(sock.get_free_ports(), 2)

    def test_valid_path(self):
        directory = os.path.abspath(self.mktemp())
        os.makedirs(directory)
        sock = Sock(self.switch, os.path.join(directory, "sw.ctl"))
        # only the directory has to be writable: the socket isn't there yet
        self.assertTrue(sock.has_valid_path())
        os.mkdir(os.path.join(directory, "sw.ctl"))
        self.assertTrue(sock.has_valid_path())

    def test_invalid_path(self):
        missing = os.path.join(os.path.abspath(self.mktemp()), "sw.ctl")
        self.assertFalse(Sock(self.switch, missing).has_valid_path())
        self.assertFalse(Sock(self.switch).has_valid_path())

    def test_read_only_directory(self):
        if os.geteuid() == 0:
            self.skipTest("root can write to any directory")
        directory = os.path.abspath(self.mktemp())
        os.makedirs(directory)
        os.chmod(directory, 0o500)
        self.addCleanup(os.chmod, directory, 0o700)
        sock = Sock(self.switch, os.path.join(directory, "sw.ctl"))
        self.assertFalse(sock.has_valid_path())

    def test_the_brick_has_a_valid_path_once_its_directory_exists(self):
        sock = self.switch.socks[0]
        self.assertFalse(sock.has_valid_path())
        os.makedirs(os.path.dirname(sock.path))
        self.assertTrue(sock.has_valid_path())
        self.assertTrue(self.switch.configured())
