from virtualbricks import tuntaps
from virtualbricks.tests import unittest, stubs


class TestTap(unittest.TestCase):

    def test_base(self):
        tap = tuntaps.Tap(stubs.FactoryStub(), "test_tap")
        self.assertEqual(len(tap.plugs), 1)
        tap.restore_self_plugs()
        self.assertEqual(len(tap.plugs), 2)
        tap.config["sock"] = "boom"
        tap.clear_self_socks()
        self.assertEqual(tap.config["sock"], "")
        self.assertFalse(tap.configured())


class Capture(unittest.TestCase):

    def test_base(self):
        capture = tuntaps.Capture(stubs.FactoryStub(), "test_capture")
        self.assertEqual(len(capture.plugs), 1)
        capture.restore_self_plugs()
        self.assertEqual(len(capture.plugs), 2)
        capture.config["sock"] = "boom"
        capture.clear_self_socks()
        self.assertEqual(capture.config["sock"], "")
        self.assertFalse(capture.configured())
