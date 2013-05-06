from virtualbricks import bricks
from virtualbricks.tests import unittest, stubs


class TestBricks(unittest.TestCase):

    def test_factory_state(self):
        factory = stubs.FactoryStub()
        brick = bricks.Brick(factory, "test")
        self.assertEqual(len(factory.bricks), 1)
        self.assertEqual(len(factory.bricksmodel), 1)
        brick2 = bricks._Brick(factory, "test")
        self.assertEqual(len(factory.bricksmodel), 1)

    # def test_basic_interface(self):
    #     factory = stubs.FactoryStub()
    #     brick = bricks.Brick(factory, "test")
