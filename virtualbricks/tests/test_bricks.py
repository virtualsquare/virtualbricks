from virtualbricks import bricks
from virtualbricks.tests import unittest, stubs


class TestBricks(unittest.TestCase):

    def test_get_cbset(self):
        brick = bricks.Brick(stubs.FactoryStub(), "test")
        cbset = brick.get_cbset("supercalifragilistichespiralidoso")
        self.assertIs(cbset, None)

    # def test_basic_interface(self):
    #     factory = stubs.FactoryStub()
    #     brick = bricks.Brick(factory, "test")
