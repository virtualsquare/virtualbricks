from twisted.trial import unittest
from twisted.internet import defer

from virtualbricks import errors
from virtualbricks.tests import stubs, successResultOf, failureResultOf


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
        self.assertIsNot(event.config, copy.config)
        self.assertEqual(event.get("delay"), copy.get("delay"))
        self.assertEqual(event.get("actions"), copy.get("actions"))
        event.config["actions"] += ["new action"]
        self.assertNotEqual(event.get("actions"), copy.get("actions"))

    def test_dup_brick(self):
        switch = self.factory.new_brick("switch", "switch")
        switch2 = self.factory.dup_brick(switch)
        self.assertIsNot(switch, switch2)
        vm = self.factory.new_brick("vm", "vm")
        vm2 = self.factory.dup_brick(vm)
        self.assertIsNot(vm, vm2)

    def test_del_brick(self):
        """Delete a brick from a factory."""

        brick = self.factory.newbrick("_stub", "test_brick")
        self.assertEqual(list(self.factory.bricks), [brick])
        successResultOf(self, self.factory.del_brick(brick))
        self.assertEqual(list(self.factory.bricks), [])

    def test_del_running_brick(self):
        """If the brick is running, stop it and remove it."""

        brick = self.factory.newbrick("_stub", "test_brick")
        brick.poweron()
        self.assertIsNot(brick.proc, None)
        successResultOf(self, self.factory.del_brick(brick))
        self.assertEqual(list(self.factory.bricks), [])
        self.assertIs(brick.proc, None)

    def test_del_remove_anyway(self):
        """
        If the brick is running and poweroff() raise an exception, remove the
        brick anyway.
        """

        brick = self.factory.newbrick("_stub", "test_brick")
        brick.poweron()
        brick.poweroff = lambda kill=False: defer.fail(RuntimeError())
        successResultOf(self, self.factory.del_brick(brick))
        errors = self.flushLoggedErrors(RuntimeError)
        self.assertEqual(len(errors), 1)
        self.assertEqual(list(self.factory.bricks), [])
        self.assertIsNot(brick.proc, None)

    def test_stop_brick_error(self):
        """
        Report an error if the factory is stopped but a brick raise an error.
        """

        brick = self.factory.newbrick("_stub", "test_brick")
        brick.poweron()
        brick.poweroff = lambda kill=False: defer.fail(RuntimeError())
        successResultOf(self, self.factory.stop())
        errors = self.flushLoggedErrors(RuntimeError)
        self.assertEqual(len(errors), 1)
        self.assertIsNot(brick.proc, None)
