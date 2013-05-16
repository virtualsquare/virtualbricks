import warnings

from virtualbricks import bricks
from virtualbricks.tests import unittest, stubs


class TestBricks(unittest.TestCase):

    def test_get_cbset(self):
        brick = bricks.Brick(stubs.FactoryStub(), "test")
        cbset = brick.get_cbset("supercalifragilistichespiralidoso")
        self.assertIs(cbset, None)

    def test_warnings(self):
        brick = bricks.Brick(stubs.FactoryStub(), "test")
        with warnings.catch_warnings(record=True)as w:
            warnings.simplefilter("always")
            brick.on_config_changed()
            self.assertEqual(len(w), 1)
            self.assertEquals(w[0].category, DeprecationWarning)


    # def test_basic_interface(self):
    #     factory = stubs.FactoryStub()
    #     brick = bricks.Brick(factory, "test")
