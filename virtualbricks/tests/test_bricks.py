import os
import errno
import signal
import StringIO

from virtualbricks import bricks, errors
from virtualbricks.tests import unittest, stubs


class TestBricks(unittest.TestCase):

    def setUp(self):
        self.factory = stubs.FactoryStub()
        self.brick = stubs.BrickStub(self.factory, "test")

    def test_get_cbset(self):
        cbset = self.brick.get_cbset("supercalifragilistichespiralidoso")
        self.assertIs(cbset, None)

    def test_poweron(self):
        self.assertRaises(errors.BadConfigError, self.brick.poweron)
        self.brick.configured = lambda: True
        self.brick.poweron()

    def test_args(self):
        self.assertEqual(self.brick.build_cmd_line(), ["-a", "arg1", "-c",
                                                       "-d", "d"])
        self.assertEqual(self.brick.args(), ["true", "-a", "arg1", "-c", "-d",
                                             "d"])


