import os
from virtualbricks.tests import unittest, stubs
from virtualbricks.gui import graphics
import virtualbricks.gui


GUI_PATH = os.path.dirname(virtualbricks.gui.__file__)


class TestGraphics(unittest.TestCase):

    def setUp(self):
        self.factory = stubs.FactoryStub()
        self.brick = stubs.BrickStub(self.factory, "Test")

    def test_get_filename(self):
        filename = graphics.get_filename("virtualbricks.gui", "data/test")
        self.assertTrue(filename.endswith("virtualbricks/gui/data/test"))

    def test_brick_icon(self):
        self.assertEqual(graphics.brick_icon(self.brick),
                         GUI_PATH + "/data/stub.png")
