from twisted.internet import defer

from virtualbricks import switches, errors
from virtualbricks.tests import unittest, stubs


def patch_brick(brick, output, input):
    brick.send = output.append
    brick.recv = input.pop


class TestSwitch(unittest.TestCase):

    def test_socks(self):
        factory = stubs.FactoryStub()
        sw = switches.Switch(factory, "test_switch")
        self.assertEqual(len(sw.socks), 1)
        self.assertIn(sw.socks[0], factory.socks)

    def test_base(self):
        sw = switches.Switch(stubs.FactoryStub(), "test_switch")
        self.assertEqual(len(sw.socks), 1)
        self.assertEqual(sw.socks[0].path, sw.path())
        self.assertIs(sw.proc, None)

    def test_live_management_callbacks(self):
        sw = switches.Switch(stubs.FactoryStub(), "test_switch")
        output, input = [], []
        patch_brick(sw, output, input)
        input.append("ok")
        sw.set({"numports": 33})
        self.assertEqual(len(output), 1)
        self.assertEqual(output[0], "port/setnumports 33\n")
        sw.config["numports"] = 33
        self.assertEqual(len(output), 1)

    def test_args(self):
        sw1 = switches.Switch(stubs.FactoryStub(), "test_switch")
        self.assertEqual(sw1.args(),
             ["/home/marco/.virtualenvs/virtualbricks/bin/vde_switch",
              "-M", "/home/marco/.virtualbricks/test_switch.mgmt",
              "-n", "32", "-s",
              "/home/marco/.virtualbricks/test_switch.ctl"])


class TestSwitchWrapper(unittest.TestCase):

    def setUp(self):
        self.factory = stubs.FactoryStub()
        self.sw = switches.SwitchWrapper(self.factory, "test_switch")

    def test_socks(self):
        self.assertEqual(len(self.sw.socks), 1)
        self.assertIn(self.sw.socks[0], self.factory.socks)

    def test_poweron(self):
        """
        SwitchWrapper uses a custom poweron method, assure that it respect the
        interface.
        """
        self.sw.proc = object()
        result = []
        self.sw.poweron().addCallbacks(result.append)
        self.assertEqual(result, [self.sw])
        self.sw.proc = None
        sockfile = self.mktemp()
        open(sockfile, "w").close()
        self.sw.config["path"] = sockfile
        self.sw.poweron().addCallback(result.append)
        self.assertEqual(result, [self.sw] * 2)
        self.sw.proc = None
        self.sw.config["path"] = ""
        deferred = self.sw.poweron()
        self.assertFailure(deferred, errors.BadConfigError)

    def test_poweroff(self):
        self.sw.proc = object()
        result = []
        self.sw.poweroff().addCallback(result.append)
        self.assertIs(self.sw.proc, None)
        self.assertEqual(result, [(self.sw, None)])
