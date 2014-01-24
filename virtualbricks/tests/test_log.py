import logging

from twisted.trial import unittest
from twisted.python import log as legacylog

from virtualbricks import log


log.replaceTwistedLoggers()
logger = log.Logger()
test_event = log.Event("This is a test event")
test_event_2 = log.Event("This is another test event")


class TestCase(unittest.TestCase):

    def get_logger(self):
        ev = []
        obs = lambda e: ev.append(e)
        logger.publisher.addObserver(obs, False)
        self.addCleanup(logger.publisher.removeObserver, obs)
        return ev


DEFAULT_ATTRS = [
    "log_format",
    "log_id",
    "log_level",
    "log_logger",
    "log_namespace",
    "log_source",
    "log_time"
]
EXTENDED_ARGS = sorted(DEFAULT_ATTRS + ["format", "logLevel", "log_legacy"])


class TestLog(TestCase):

    def test_tap(self):
        """Collect only specific events."""

        ev = []
        self.addCleanup(test_event.tap(ev.append, logger.publisher))
        logger.info(test_event)
        logger.info(test_event_2)
        self.assertEqual(len(ev), 1)
        self.assertIn("log_id", ev[0])
        self.assertEqual(ev[0]["log_id"], test_event.log_id)

    def _test_event_attrs(self, emit, attrs):
        """Test the attributes of an event."""

        events = self.get_logger()
        emit()
        self.assertEqual(len(events), 1)
        self.assertIs(type(events[0]), dict)
        self.assertEqual(sorted(events[0].keys()), attrs)

    def test_info_event_attrs(self):
        """
        Test the attributes of an event of level LogLevel.INFO.

        The LegacyLogObserver add some extra attributes to the event...
        """

        self._test_event_attrs(lambda: logger.info(test_event), EXTENDED_ARGS)

    def test_debug_event_attrs(self):
        """
        Test the attributes of an event of level LogLevel.DEBUG.

        ...but The LegacyLogObserver is filtered so is not called for the event
        with level LogLevel.DEBUG.
        """

        self._test_event_attrs(lambda: logger.debug(test_event), DEFAULT_ATTRS)

    def test_legacy_observer(self):
        """Test the events logged with the legacy logger are not lost."""

        ev = self.get_logger()
        legacylog.msg("test")
        legacylog.err(RuntimeError("error"))
        self.assertEqual(len(self.flushLoggedErrors(Exception)), 1)
        self.assertEqual(len(ev), 2)

    def test_legacy_observer_event_attrs(self):
        """
        Events logged with the legacy logger does not have the log_id
        attribute.
        """

        attrs = EXTENDED_ARGS[:]
        attrs.remove("log_id")
        self._test_event_attrs(lambda: legacylog.msg("test"), attrs)


class TestStdLogging(TestCase):
    """Test the integration with the standard logging module."""

    def _install_std_logging_observer(self):
        root = logging.getLogger()
        handler = log.LoggingToNewLogginAdapter()
        root.addHandler(handler)
        self.addCleanup(root.removeHandler, handler)

    def test_std_logging_adapter(self):
        """Install and handler to the std's root logger."""

        ev = self.get_logger()
        self._install_std_logging_observer()
        try:
            raise Exception("test")
        except:
            logging.exception("exp")
        errors = self.flushLoggedErrors(Exception)
        self.assertEqual(len(errors), 1)
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]["msg"], "exp")
