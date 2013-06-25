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

    def get_real_plug(self):
        return self.plug

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
        self.plug.disconnect()
        self.assertFalse(self.plug.configured())
        self.assertFalse(self.plug.connect(None))
        self.assertFalse(self.plug.configured())
        self.assertTrue(self.plug.connect(self.sock_factory(self.brick)))
        self.assertTrue(self.plug.configured())
        self.plug.disconnect()
        self.assertFalse(self.plug.configured())

    def test_connect_maybe_a_bug(self):
        """When a plug is disconnected leave its traces on socks."""
        sock = self.sock_factory(self.brick)
        self.plug.connect(sock)
        self.plug.disconnect()
        self.assertEqual(sock.plugs, [self.get_real_plug()])


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
