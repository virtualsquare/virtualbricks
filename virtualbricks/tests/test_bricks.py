import os
import errno
import signal

from twisted.trial import unittest
from twisted.internet import error

from virtualbricks import errors, link
from virtualbricks.tests import stubs


def kill(passthru, brick):
    return brick.poweroff(kill=True).addBoth(lambda _: passthru)

def patchr(passthru, patch):
    patch.restore()
    return passthru


class TestBricks(unittest.TestCase):

    def setUp(self):
        self.factory = stubs.FactoryStub()
        self.brick = stubs.BrickStub(self.factory, "test")

    def test_get_cbset(self):
        cbset = self.brick.get_cbset("supercalifragilistichespiralidoso")
        self.assertIs(cbset, None)

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
            self.assertEqual(sig, [brick])
            self.assertIs(brick._started_d, None)

        self.brick.configured = lambda: True
        sig = []
        self.brick.signal_connect("changed", lambda b: sig.append(b))
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

    def test_poweroff(self):

        def check_result(result):
            self.assertIs(result[0], self.brick)
            self.assertIsInstance(result[1].value, error.ProcessTerminated)
            self.assertEqual(result[1].value.signal, signal.SIGTERM)

        def do_poweroff(brick):
            return brick.poweroff().addCallback(check_result)

        result = []
        self.brick.poweroff().addCallback(result.append)
        self.assertEqual(result, [(self.brick, None)])
        self.brick.configured = lambda : True
        d = self.brick.poweron()
        return d.addCallbacks(do_poweroff).addBoth(kill, self.brick)

    def test_poweroff_raise_OSError(self):

        def signalProcess(signo):
            raise OSError(42, "The meaning of file")

        def check(failure):
            failure.trap(OSError)
            self.assertEqual(failure.value.errno, 42)

        def continue_test(brick):
            self.assertIsNot(brick.proc, None)
            patch = self.patch(brick.proc, "signalProcess", signalProcess)
            d = brick.poweroff()
            return self.assertFailure(d, OSError).addBoth(patchr, patch)

        self.brick.configured = lambda: True
        d = self.brick.poweron()
        d.addCallback(continue_test).addBoth(kill, self.brick)
        return d

    def test_poweroff_raise_ProcessExitedAlready(self):

        def signalProcess(signo):
            raise error.ProcessExitedAlready()

        def check(result, brick):
            self.assertEqual(result[0], brick)
            result[1].trap(error.ProcessDone)

        def continue_test(brick):
            self.assertIsNot(brick.proc, None)
            patch = self.patch(brick.proc, "signalProcess", signalProcess)
            d = self.brick.poweroff().addCallback(check, brick)
            d.addBoth(patchr, patch)
            return d

        self.brick.configured = lambda: True
        d = self.brick.poweron()
        d.addCallback(continue_test).addBoth(kill, self.brick)
        return d
