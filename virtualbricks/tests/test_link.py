from twisted.trial import unittest

from virtualbricks import link, errors
from virtualbricks.tests import unittest as pyunit, stubs


class TestPlug(unittest.TestCase):

    plug_factory = link.Plug
    sock_factory = link.Sock

    def setUp(self):
        self.factory = stubs.FactoryStub()
        self.brick = stubs.BrickStub(self.factory, "test")
        self.plug = self.plug_factory(self.brick)

    def test_connected(self):
        self.assertFalse(self.plug.connected())
        # self.assertFalse(self.plug.configured())

    @pyunit.skip("This is a know bug")
    def test_erroronloop(self):
        """Setting is not setted in links, this is a know bug"""
        self.plug.antiloop = True
        self.factory.settings.set("erroronloop", False)
        self.assertRaises(errors.NotConnectedError, self.plug.connected)

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
