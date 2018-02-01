# Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
# Copyright (C) 2018 Virtualbricks team

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

from twisted.trial import unittest
from twisted.python import log
from twisted.internet import defer

from virtualbricks import link, errors, settings
from virtualbricks.tests import stubs


class TestPlug(unittest.TestCase):

    plug_factory = link.Plug
    sock_factory = link.Sock

    def setUp(self):
        self.factory = stubs.FactoryStub()
        self.brick = stubs.BrickStub(self.factory, "test")
        self.plug = self.plug_factory(self.brick)
        self.log = []
        log.addObserver(self.log.append)
        self.addCleanup(log.removeObserver, self.log.append)

    def test_connected(self):
        result = []
        self.plug.connected().addErrback(result.append)
        self.assertEqual(len(result), 1)
        result[0].trap(errors.NotConnectedError)

    def test_connected_erroronloop(self):
        self.plug._antiloop = True
        settings.set("erroronloop", False)
        result = []
        self.plug.connected().addErrback(result.append)
        self.assertEqual(len(result), 1)
        result[0].trap(errors.LinkLoopError)
        self.assertEqual(0, len(self.log))
        self.plug._antiloop = True
        settings.set("erroronloop", True)
        self.plug.connected().addErrback(result.append)
        self.assertEqual(len(result), 2)
        result[1].trap(errors.LinkLoopError)
        self.assertEqual(1, len(self.log))
        self.plug.connected().addErrback(result.append)
        self.assertEqual(len(result), 3)
        result[2].trap(errors.NotConnectedError)
        self.assertEqual(1, len(self.log))

    def test_connected_poweron(self):
        self.brick.poweron = lambda: defer.succeed(self.brick)
        sock = self.sock_factory(self.brick)
        self.plug.connect(sock)
        result = []
        self.plug.connected().addCallback(result.append)
        self.assertEqual(result, [self.brick])
        self.assertFalse(self.plug._antiloop)

    def test_connect(self):
        self.assertFalse(self.plug.configured())
        if __debug__:
            self.assertRaises(AssertionError, self.plug.disconnect)
        self.assertFalse(self.plug.configured())
        if __debug__:
            self.assertRaises(AssertionError, self.plug.connect, None)
            self.assertFalse(self.plug.configured())
        sock = self.sock_factory(self.brick)
        self.plug.connect(sock)
        self.assertIs(self.plug.sock, sock)
        self.assertTrue(self.plug.configured())
        self.plug.disconnect()
        self.assertFalse(self.plug.configured())

    def test_disconnect(self):
        """
        Test that after a disconnect there are no more references to plug.
        """
        sock = self.sock_factory(self.brick)
        self.plug.connect(sock)
        self.plug.disconnect()
        self.assertEqual(sock.plugs, [])


class TestSock(unittest.TestCase):

    plug_factory = link.Plug
    sock_factory = link.Sock

    def setUp(self):
        self.factory = stubs.FactoryStub()
        self.brick = stubs.BrickStub(self.factory, "test")
        self.sock = self.sock_factory(self.brick)

    # @unittest.skip("test outdated")
    # def test_free_ports(self):
    #     # socks works only with switches?
    #     self.assertRaises(AttributeError, self.sock.get_free_ports)
    #     self.brick.cfg["numports"] = 32
    #     self.assertEqual(self.sock.get_free_ports(), 32)
    #     plug = self.plug_factory(self.brick)
    #     plug.connect(self.sock)
    #     self.assertEqual(self.sock.get_free_ports(), 31)

    def test_has_valid_path(self):
        filename = self.mktemp()
        with open(filename, "w"):
            pass
        self.sock.path = filename
        self.assertTrue(self.sock.has_valid_path())
