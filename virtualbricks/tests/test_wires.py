try:
    import mock
except ImportError:
    mock = None
from twisted.trial import unittest

from virtualbricks import wires, link, settings
from virtualbricks.tests import stubs


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

    def test_live_management(self):
        """
        If set a *sync parameter, the corrisponding left-to-right and right to
        left callbacks must not be called.
        """

        config = {
            "delaysymm": False,
            "delay": 1,
            "delayr": 2
        }
        self.netemu.config["delaysymm"] = True
        self.assertEqual(self.netemu.config["delay"], 0)
        self.assertEqual(self.netemu.config["delayr"], 0)
        self.netemu.cbset_delay = mock.Mock(name="cbset_delay")
        self.netemu.cbset_delayr = mock.Mock(name="cbset_delayr")
        self.netemu.set(config)
        self.netemu.cbset_delay.assert_called_once_with(1)
        self.netemu.cbset_delayr.assert_called_once_with(2)

    if mock is None:
        test_live_management.skip = "Mock library not installed"

    def test_live_management_2(self):
        """Same as precedent but symmetric."""

        config = {
            "delaysymm": True,
            "delay": 1,
            "delayr": 2
        }
        self.netemu.config["delaysymm"] = False
        self.assertEqual(self.netemu.config["delay"], 0)
        self.assertEqual(self.netemu.config["delayr"], 0)
        self.netemu.cbset_delay = mock.Mock(name="cbset_delay",
            side_effect=self.netemu.cbset_delay)
        self.netemu.cbset_delayr = mock.Mock(name="cbset_delayr",
            side_effect=self.netemu.cbset_delayr)
        self.netemu.send = mock.Mock(name="send")
        self.netemu.set(config)
        self.netemu.cbset_delay.assert_called_once_with(1)
        self.netemu.cbset_delayr.assert_called_once_with(2)
        self.netemu.send.assert_called_once_with("delay 1\n")

    if mock is None:
        test_live_management_2.skip = "Mock library not installed"

