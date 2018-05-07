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

import os
import errno
import signal

from twisted.trial import unittest
from twisted.internet import error, defer
from twisted.test import proto_helpers

from virtualbricks import errors, link, bricks
from virtualbricks.tests import stubs, successResultOf


def kill(passthru, brick):
    return brick.poweroff(kill=True).addBoth(lambda _: passthru)


def patchr(passthru, patch):
    patch.restore()
    return passthru


class SleepBrick(stubs.BrickStub):

    def prog(self):
        return "sleep"

    def args(self):
        return ["sleep", "2"]

    def configured(self):
        return True


class TestBricks(unittest.TestCase):

    def setUp(self):
        self.factory = stubs.FactoryStub()
        self.brick = stubs.BrickStub(self.factory, "test")
    #_cmd_line().sort() rende il test green... per quale motivo...
    def test_args(self):
        self.assertEqual(self.brick.build_cmd_line(),
                         ["-a", "arg1", "-c", "-d", "d"])
        self.assertEqual(self.brick.args(),
                         ["true", "-a", "arg1", "-c", "-d", "d"])

    def test_poweron_badconfig(self):
        self.brick.proc = object()
        result = []
        self.brick.poweron().addCallback(result.append)
        self.assertEqual(result, [self.brick])
        self.brick.proc = None
        result = []
        self.brick.poweron().addErrback(result.append)
        self.assertEqual(len(result), 1)
        result[0].trap(errors.BadConfigError)

    def test_poweron(self):

        def continue_test(brick):
            self.assertIs(brick._started_d, None)

        self.brick.configured = lambda: True
        d = self.brick.poweron()
        d.addCallback(continue_test).addBoth(kill, self.brick)
        return d

    def test_poweron_notconnected(self):
        self.brick.configured = lambda: True
        plug = link.Plug(self.brick)
        self.brick.plugs.append(plug)
        result = []
        self.brick.poweron().addErrback(result.append)
        self.assertEqual(len(result), 1)
        result[0].trap(errors.NotConnectedError)

    def test_poweron_error_on_spawn(self):

        def spawnProcess(*a, **kw):
            raise IOError(errno.EAGAIN, os.strerror(errno.EAGAIN))

        from twisted.internet import reactor
        self.patch(reactor, "spawnProcess", spawnProcess)
        self.brick.configured = lambda: True
        result = []
        self.brick.poweron().addErrback(result.append)
        result[0].trap(IOError)

    def test_poweroff_not_running(self):
        """
        If the brick is not started, poweroff succeed and return the last
        status or None if the last status is not set.
        """

        self.assertEqual(successResultOf(self, self.brick.poweroff()),
                         (self.brick, None))

    def test_poweroff(self):

        def check_result(result):
            self.assertIs(result[0], brick)
            self.assertIsInstance(result[1].value, error.ProcessTerminated)
            self.assertEqual(result[1].value.signal, signal.SIGTERM)

        def do_poweroff(brick):
            return brick.poweroff().addCallback(check_result)

        brick = SleepBrick(self.factory, "test")
        return brick.poweron().addCallbacks(do_poweroff).addBoth(kill, brick)

    def test_poweroff_raise_OSError(self):

        def signal_process(signo):
            raise OSError(42, "The meaning of file")

        def check(failure):
            failure.trap(OSError)
            self.assertEqual(failure.value.errno, 42)

        def continue_test(brick):
            self.assertIsNot(brick.proc, None)
            patch = self.patch(brick.proc, "signal_process", signal_process)
            d = brick.poweroff()
            return self.assertFailure(d, OSError).addBoth(patchr, patch)

        self.brick.configured = lambda: True
        d = self.brick.poweron()
        d.addCallback(continue_test).addBoth(kill, self.brick)
        return d

    def test_poweroff_raise_ProcessExitedAlready(self):

        def signal_process(signo):
            raise error.ProcessExitedAlready()

        def check(result, brick):
            self.assertEqual(result[0], brick)
            result[1].trap(error.ProcessDone)

        def continue_test(brick):
            self.assertIsNot(brick.proc, None)
            patch = self.patch(brick.proc, "signal_process", signal_process)
            d = self.brick.poweroff().addCallback(check, brick)
            d.addBoth(patchr, patch)
            return d

        self.brick.configured = lambda: True
        d = self.brick.poweron()
        d.addCallback(continue_test).addBoth(kill, self.brick)
        return d

    def test_signal_process(self):
        pass


class TestVDEProcessProtocol(unittest.TestCase):

    CMD1 = b"bandwidth LR 125000"
    CMD2 = b"bandwidth RL 120000"
    PROMPT = b"vde$ "

    def setUp(self):
        brick = bricks.Brick(stubs.Factory(), "test")
        brick._started_d = defer.Deferred()
        brick._exited_d = defer.Deferred()
        self.proto = bricks.VDEProcessProtocol(brick)
        self.transport = proto_helpers.StringTransport()
        self.transport.pid = -1
        self.proto.makeConnection(self.transport)

    def test_enqueue(self):
        """Until ACKs are received, the commands are queued."""

        self.proto.send_command(self.CMD1)
        self.proto.send_command(self.CMD2)
        self.assertEqual(list(self.proto.queue), [self.CMD1, self.CMD2])

    def test_dequeue(self):
        """The queue is a FIFO, remove the oldest command sent."""

        self.proto.send_command(self.CMD1)
        self.proto.send_command(self.CMD2)
        self.proto.data_received(self.PROMPT)
        self.assertEqual(list(self.proto.queue), [self.CMD2])

    def test_too_much_ack(self):
        """
        If too many ACKs are sent by the process, shutdown the connection.
        """

        self.proto.send_command(self.CMD1)
        self.proto.data_received(self.PROMPT)
        self.assertEqual(len(self.proto.queue), 0)
        self.proto.data_received(self.PROMPT)
        self.assertTrue(self.transport.disconnecting)
