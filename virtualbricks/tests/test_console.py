from virtualbricks import console
from virtualbricks.tests import unittest, stubs


class TestProtocol(unittest.TestCase):

    def setUp(self):
        self.factory = stubs.FactoryStub()

    def test_new_brick(self):
        console.parse(self.factory, "new stub test")
        self.assertEquals(len(self.factory.bricks), 1)
        self.assertEquals(self.factory.bricks[0].name, "test")
        self.assertEquals(self.factory.bricks[0].get_type(), "Stub")

    def test_new_event(self):
        console.parse(self.factory, "new event test_event")
        self.assertEquals(len(self.factory.events), 1)
        self.assertEquals(self.factory.events[0].name, "test_event")
        self.assertEquals(self.factory.events[0].get_type(), "Event")
