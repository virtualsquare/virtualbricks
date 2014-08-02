import logging

from twisted.trial import unittest
from twisted.python import log as legacylog

from virtualbricks import log


logger = log.Logger()
test_event = log.Event("This is a test event")
test_event_2 = log.Event("This is another test event")


class Observer:

    def __init__(self):
        self.events = []

    def __call__(self, event):
        self.events.append(event)


class EventCmp:

    def __init__(self, event):
        self.event = event

    def __eq__(self, other):
        if isinstance(other, dict):
            return self.event.is_(other)
        return NotImplemented

    def __ne__(self, other):
        return not self.__eq__(other)


def install_observer(test_case):
    observer = Observer()
    logger.publisher.addObserver(observer)
    test_case.addCleanup(logger.publisher.removeObserver, observer)
    return observer


class TestLog(unittest.TestCase):

    def setUp(self):
        self.observer = install_observer(self)

    def test_log(self):
        """Send a simple event."""

        logger.info(test_event)
        self.assertEqual(self.observer.events, [EventCmp(test_event)])

    def test_tap(self):
        """Collect only specific events. Here test_event_2 is not collected."""

        observer = Observer()
        self.addCleanup(test_event.tap(observer, logger.publisher))
        logger.info(test_event)
        logger.info(test_event_2)
        self.assertEqual(observer.events, [EventCmp(test_event)])

    def test_info_event_attrs(self):
        """
        Test the attributes of an event of level LogLevel.INFO.

        The LegacyLogObserver add some extra attributes to the event...
        """

        logger.info(test_event)
        self.assertEqual(self.observer.events, [EventCmp(test_event)])
        self.assertEqual(sorted(self.observer.events[0].keys()),
                         ["format", "logLevel", "log_format", "log_id",
                          "log_legacy", "log_level", "log_logger",
                          "log_namespace", "log_source", "log_time"])

    def test_filter_event(self):
        """Events can be filtered."""

        logger.publisher.levels.setLogLevelForNamespace(
            "virtualbricks.tests.test_log", log.LogLevel.warn)
        self.addCleanup(logger.publisher.levels.clearLogLevels)
        logger.info(test_event)
        self.assertEqual(len(self.observer.events), 0)

    def test_legacy_emitter(self):
        """Test the events logged with the legacy logger are not lost."""

        observer = log.LegacyAdapter()
        legacylog.addObserver(observer)
        self.addCleanup(legacylog.removeObserver, observer)
        legacylog.msg("test")
        legacylog.err(RuntimeError("error"))
        err = self.flushLoggedErrors(RuntimeError)
        self.assertEqual(len(self.observer.events), 2)
        self.assertEqual(len(err), 1)

    def test_legacy_observer(self):
        """
        If a message is emitted by the new logging machinery, a legacy observer
        does not miss it.
        """

        observer = Observer()
        legacylog.addObserver(observer)
        self.addCleanup(legacylog.removeObserver, observer)
        logger.info(test_event)
        self.assertEqual(observer.events, [EventCmp(test_event)])

    def test_legacy_observer_ignore_debug(self):
        """
        By default all debug messages are filtered by the legacy observer.
        """

        observer = Observer()
        legacylog.addObserver(observer)
        self.addCleanup(legacylog.removeObserver, observer)
        logger.debug(test_event)
        self.assertEqual(observer.events, [])


class TestStdLogging(unittest.TestCase):
    """Test the integration with the standard logging module."""

    def setUp(self):
        self.observer = install_observer(self)
        root = logging.getLogger()
        handler = log.StdLoggingAdapter()
        root.addHandler(handler)
        self.addCleanup(root.removeHandler, handler)

    def test_std_logging_adapter(self):
        """Install and handler to the std's root logger."""

        try:
            raise RuntimeError("test")
        except:
            logging.exception("exp")
        self.flushLoggedErrors(RuntimeError)
        self.assertEqual(len(self.observer.events), 1)
        self.assertEqual(self.observer.events[0]["log_format"].split("\n")[0], "exp")

    def test_event_has_log_id(self):
        """
        Test if events logged with the standard logging library have the
        'log_id' attribute.
        """

        logging.warn("test")
        self.assertEqual(len(self.observer.events), 1)
        self.assertIn("log_id", self.observer.events[0])
