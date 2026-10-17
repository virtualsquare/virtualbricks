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

"""The plugs."""

from twisted.internet import defer

from virtualbricks import errors
from virtualbricks.bricks.plug import Plug
from virtualbricks.bricks.sock import Sock
from virtualbricks.tests import BrickTestCase


class FakeBrick:
    """A brick that only knows how to be powered on."""

    def __init__(self, result=None):
        self.result = result
        self.start_calls = 0

    def start(self):
        self.start_calls += 1
        if self.result is None:
            return defer.succeed(self)
        return self.result


class TestPlug(BrickTestCase):

    def setUp(self):
        super().setUp()
        self.brick = FakeBrick()
        self.plug = Plug(self.brick)
        self.other = FakeBrick()
        self.sock = Sock(self.other, "other_port")

    def test_new_plug(self):
        self.assertIs(self.plug.brick, self.brick)
        self.assertIsNone(self.plug.sock)
        self.assertEqual(self.plug.mode, "vde")
        self.assertEqual(self.plug.model, "")
        self.assertEqual(self.plug.mac, "")

    def test_not_configured(self):
        self.assertFalse(self.plug.configured())

    def test_connect(self):
        self.plug.connect(self.sock)
        self.assertIs(self.plug.sock, self.sock)
        self.assertEqual(self.sock.plugs, [self.plug])
        self.assertTrue(self.plug.configured())

    def test_connect_many_plugs(self):
        second = Plug(FakeBrick())
        self.plug.connect(self.sock)
        second.connect(self.sock)
        self.assertEqual(self.sock.plugs, [self.plug, second])

    def test_connect_to_nothing(self):
        self.assertRaises(AssertionError, self.plug.connect, None)
        self.assertIsNone(self.plug.sock)

    def test_disconnect(self):
        self.plug.connect(self.sock)
        self.plug.disconnect()
        self.assertIsNone(self.plug.sock)
        self.assertEqual(self.sock.plugs, [])
        self.assertFalse(self.plug.configured())

    def test_disconnect_keeps_the_other_plugs(self):
        second = Plug(FakeBrick())
        self.plug.connect(self.sock)
        second.connect(self.sock)
        self.plug.disconnect()
        self.assertEqual(self.sock.plugs, [second])
        self.assertIs(second.sock, self.sock)

    def test_disconnect_when_not_connected(self):
        self.assertRaises(AssertionError, self.plug.disconnect)

    def test_disconnect_when_the_sock_forgot_the_plug(self):
        self.plug.connect(self.sock)
        self.sock.plugs.remove(self.plug)
        self.assertRaises(AssertionError, self.plug.disconnect)

    def test_reconnect(self):
        third = Sock(FakeBrick(), "third_port")
        self.plug.connect(self.sock)
        self.plug.disconnect()
        self.plug.connect(third)
        self.assertEqual(self.sock.plugs, [])
        self.assertEqual(third.plugs, [self.plug])

    def test_connected_when_not_connected(self):
        deferred = self.plug.connected()
        return self.assertFailure(deferred, errors.NotConnectedError)

    def test_connected_to_a_sock_without_a_brick(self):
        self.plug.connect(Sock(None, "orphan"))
        deferred = self.plug.connected()
        return self.assertFailure(deferred, errors.NotConnectedError)

    def test_connected_powers_on_the_other_brick(self):
        self.plug.connect(self.sock)
        deferred = self.plug.connected()
        self.assertEqual(self.other.start_calls, 1)
        self.assertEqual(self.brick.start_calls, 0)
        return deferred.addCallback(self.assertIs, self.other)

    def test_connected_waits_for_the_other_brick(self):
        pending = defer.Deferred()
        self.other.result = pending
        self.plug.connect(self.sock)
        deferred = self.plug.connected()
        self.assertFalse(deferred.called)
        pending.callback("started")
        return deferred.addCallback(self.assertEqual, "started")

    def test_connected_passes_on_the_failure(self):
        self.other.result = defer.fail(errors.BadConfigError("no switch"))
        self.plug.connect(self.sock)
        deferred = self.plug.connected()
        return self.assertFailure(deferred, errors.BadConfigError)

    def test_connected_to_its_own_brick(self):
        # a virtual machine plugged into its own socket card
        sock = Sock(self.brick, "own_port")
        self.plug.connect(sock)
        deferred = self.plug.connected()
        self.assertEqual(self.brick.start_calls, 0)
        return deferred.addCallback(self.assertIs, self.brick)

    def test_connected_again_while_the_other_brick_starts(self):
        # as when the start of this brick failed by another plug, and it's
        # started again: not a loop, the other brick is asked again
        self.other.result = defer.Deferred()
        self.plug.connect(self.sock)
        first = self.plug.connected()
        second = self.plug.connected()
        self.assertEqual(self.other.start_calls, 2)
        self.assertNoResult(first)
        self.assertIs(second, self.other.result)
