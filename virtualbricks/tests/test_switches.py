from virtualbricks import switches
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
        sw.cfg.numports = "33"
        self.assertEqual(len(output), 1)
        self.assertEqual(output[0], "port/setnumports 33\n")
        sw.cfg["numports"] = 33
        self.assertEqual(len(output), 1)

    def test_args(self):
        sw1 = switches.Switch(stubs.FactoryStub(), "test_switch")
        sw2 = switches.Switch(stubs.FactoryStub(), "test_switch2")
        self.assertEqual(sw1.args(),
                         ["/home/marco/.virtualenvs/virtualbricks/bin/vde_switch",
                          "-M", "/home/marco/.virtualbricks/test_switch.mgmt",
                          "-n", "32", "-s",
                          "/home/marco/.virtualbricks/test_switch.ctl"])


class TestSwitchWrapper(unittest.TestCase):

    def test_socks(self):
        factory = stubs.FactoryStub()
        sw = switches.SwitchWrapper(factory, "test_switch")
        self.assertEqual(len(sw.socks), 1)
        self.assertIn(sw.socks[0], factory.socks)

