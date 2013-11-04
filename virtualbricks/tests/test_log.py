from twisted.trial import unittest

from virtualbricks import log


logger = log.Logger()
test_event = log.Event("This is a test event")
test_event_2 = log.Event("This is another test event")


class TestEvent(unittest.TestCase):

    def test_tap(self):
        """Collect only specific events."""

        ev = []
        self.addCleanup(test_event.tap(ev.append, logger.publisher))
        logger.info(test_event)
        logger.info(test_event_2)
        self.assertEqual(len(ev), 1)
        self.assertIn("log_id", ev[0])
        self.assertEqual(ev[0]["log_id"], test_event.log_id)
