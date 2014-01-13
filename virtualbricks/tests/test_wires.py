from twisted.trial import unittest

from virtualbricks import wires, link, settings
from virtualbricks.tests import stubs


class TestNetemuProcess(unittest.TestCase):
    pass


class TestNetemu(unittest.TestCase):

    def setUp(self):
        self.factory = stubs.FactoryStub()
        self.netemu = wires.Netemu(self.factory, "test_netemu")

    def test_args(self):
        """Test that the brick is started with the desired arguments."""

        cfg = {"bandwidthsymm": False,
               "bandwidth": 125000,
               "bandwidthr": 126000,
               "delaysymm": True,
               "delay": 10,
               "delayr": 20,
               "chanbufsizesymm": True,
               "chanbufsize": 75000,
               "chanbufsizer": 75000,
               "losssymm": False,
               "loss": 100,
               "lossr": 0}
        self.netemu.set(cfg)
        sock1 = link.Sock(None, "sock1")
        self.netemu.connect(sock1)
        sock2 = link.Sock(None, "sock2")
        self.netemu.connect(sock2)
        args = ["vde-netemu", "-v", "sock1:sock2", "-b", "LR 125000", "-b",
                "RL 126000", "-d", "10", "-c", "75000", "-l", "LR 100", "-l",
                "RL 0", "-M",
                "{0}/test_netemu.mgmt".format(settings.VIRTUALBRICKS_HOME),
                "--nofifo"]
        self.assertEqual(self.netemu.args(), args)
