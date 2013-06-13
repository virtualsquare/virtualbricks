from virtualbricks import tunnels
from virtualbricks.tests import unittest, stubs


class TestTunnelListen(unittest.TestCase):

    def test_base(self):
        pass


class TestTunnelConnect(TestTunnelListen):

    def test_on_config_changed(self):
        tc = tunnels.TunnelConnect(stubs.FactoryStub(), "test_tc")
        self.assertIs(tc.plugs[0].sock, None)
        self.assertEqual(tc.config["host"], "")
        tc.on_config_changed()
        self.assertEqual(tc.config["host"], "")
        tc.config["host"] = "localhost"
        tc.on_config_changed()
        self.assertEqual(tc.config["host"], "localhost:%d" % tc.config["port"])
