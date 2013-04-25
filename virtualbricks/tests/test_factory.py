from virtualbricks import brickfactory, bricks
from virtualbricks.tests import unittest


class BrickStub(bricks.Brick):

    def get_type(self):
        return "Stub"


class FactoryStub(brickfactory.BrickFactory):

    restore_configfile_real = False

    def __init__(self):
        brickfactory.BrickFactory.__init__(self)
        self.BRICKTYPES["stub"] = BrickStub

    def restore_configfile(self):
        if self.restore_configfile_real:
            brickfactory.BrickFactory.restore_configfile(self)

    new_brick = brickfactory.BrickFactory.newbrick

class TestFactory(unittest.TestCase):

    def setUp(self):
        self.factory = FactoryStub()

    def test_creation(self):
        defaults = {
            "id": "0",
            "name": "",
            "filename": ""
        }
        self.assertEquals(self.factory.project_parms, defaults)
        self.assertTrue(hasattr(self.factory, "BRICKTYPES"))

    def test_reset_config(self):
        self.factory.reset_config()
        self.assertEquals(self.factory.bricks, [])
        self.assertEquals(self.factory.events, [])
        b = self.factory.new_brick("stub", "test_brick")
        self.factory.reset_config()
        self.assertEquals(self.factory.bricks, [])
        self.assertEquals(self.factory.events, [])
