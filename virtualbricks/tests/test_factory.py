from virtualbricks import errors
from virtualbricks.tests import unittest, stubs


class Stub2(object):

    def __init__(self, factory, name):
        self.factory = factory
        self.name = name

class Stub3(Stub2):
    pass


class TestFactory(unittest.TestCase):

    def setUp(self):
        self.factory = stubs.FactoryStub()

    def test_reset_config(self):
        self.factory.reset()
        self.assertEquals(self.factory.bricks, [])
        self.assertEquals(self.factory.events, [])
        self.factory.new_brick("stub", "test_brick")
        self.factory.reset()
        self.assertEquals(self.factory.bricks, [])
        self.assertEquals(self.factory.events, [])

    def test_newbrick(self):
        self.assertRaises(errors.InvalidNameError, self.factory.newbrick,
                          "stub", "")
        self.factory.newbrick("stub", "test_brick")
        self.assertRaises(errors.InvalidNameError, self.factory.newbrick,
                          "stub", "test_brick")

    def test_newevent(self):
        self.assertRaises(errors.InvalidNameError, self.factory.newevent,
                          "event", "")
        self.factory.newevent("event", "test_event")
        self.assertRaises(errors.InvalidNameError, self.factory.newevent,
                          "event", "test_event")
        self.assertTrue(self.factory.newevent("Event", "event1"))
        self.assertFalse(self.factory.newevent("eVeNt", "event2"))

    def test_register_new_type(self):
        self.assertRaises(errors.InvalidTypeError, self.factory.new_brick,
                          "stub2", "test")
        self.factory.register_brick_type(Stub2, "stub2")
        brick = self.factory.new_brick("stub2", "test")
        self.assertIs(type(brick), Stub2)
        # override an existing type
        self.factory.register_brick_type(Stub3, "stub2")
        brick = self.factory.new_brick("stub2", "test2")
        self.assertIs(type(brick), Stub3)

    def test_dup_event(self):
        event = self.factory.new_event("test_event")
        copy = self.factory.dupevent(event)
        self.assertIsNot(copy, event)
        self.assertEqual(copy.name, "copy_of_test_event")
        self.assertEqual(event.get("delay"), copy.get("delay"))
        self.assertEqual(event.get("actions"), copy.get("actions"))
