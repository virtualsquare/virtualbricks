from twisted.trial import unittest

from virtualbricks.tools import is_running
from virtualbricks.tests import stubs, successResultOf
from virtualbricks.errors import BrickRunningError


class TestFactory(unittest.TestCase):

    def test_reset(self):
        factory = stubs.Factory()
        factory.new_brick("stub", "test_brick")
        factory.reset()
        self.assertEquals(factory.bricks, [])

    def test_new_brick(self):
        factory = stubs.Factory()
        NAME = "test_brick"
        TYPE = "Stub"
        brick = factory.new_brick("stub", NAME)
        self.assertEqual(brick.get_type(), TYPE)
        self.assertEqual(brick.get_name(), NAME)

    def test_new_event(self):
        factory = stubs.Factory()
        NAME = "test_event"
        event = factory.new_event(NAME)
        self.assertEqual(event.get_type(), "Event")
        self.assertEqual(event.get_name(), NAME)

    def test_dup_event(self):
        factory = stubs.Factory()
        event = factory.new_event("test_event")
        copy = factory.dup_event(event)
        self.assertIsNot(copy, event)
        self.assertIsNot(copy.config, event.config)
        self.assertEqual(copy.config, event.config)

    def test_dup_brick(self):
        factory = stubs.Factory()
        switch = factory.new_brick("switch", "switch")
        switch2 = factory.dup_brick(switch)
        self.assertIsNot(switch, switch2)
        self.assertIsNot(switch.config, switch2.config)
        self.assertEqual(switch.config, switch2.config)

    def test_del_brick(self):
        """Delete a brick from a factory."""

        factory = stubs.Factory()
        brick = factory.new_brick("stub", "test_brick")
        self.assertEqual(factory.bricks, [brick])
        factory.del_brick(brick)
        self.assertEqual(factory.bricks, [])

    def test_del_running_brick(self):
        """If the brick is running, it cannot be removed."""

        factory = stubs.Factory()
        brick = factory.new_brick("_stub", "test_brick")
        self.assertEqual(brick, successResultOf(self, brick.poweron()))
        self.assertRaises(BrickRunningError, factory.del_brick, brick)
        self.assertEqual(factory.bricks, [brick])
        self.assertTrue(is_running(brick))
