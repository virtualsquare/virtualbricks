# Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
# Copyright (C) 2018 Virtualbricks team

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

import logging

import twisted
from twisted.trial import unittest
from twisted.python import log as legacylog

from virtualbricks import log
from virtualbricks.tests import skipUnless


logger = log.Logger()
test_event = log.Event("This is a test event")
test_event_2 = log.Event("This is another test event")


class Observer(list):

    def __call__(self, event):
        self.append(event)

    def __hash__(self):
        return object.__hash__(self)


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
        self.assertEqual(self.observer, [test_event])

    def test_tap(self):
        """Collect only specific events. Here test_event_2 is not collected."""

        observer = Observer()
        self.addCleanup(test_event.tap(observer, logger.publisher))
        logger.info(test_event)
        logger.info(test_event_2)
        self.assertEqual(observer, [test_event])

    def test_info_event_attrs(self):
        """
        Test the attributes of an event of level LogLevel.INFO.

        The LegacyLogObserver add some extra attributes to the event...
        """

        logger.info(test_event)
        self.assertEqual(self.observer, [test_event])
        self.assertEqual(sorted(self.observer[0].keys()),
                         ["format", "logLevel", "log_format", "log_id",
                          "log_legacy", "log_level", "log_logger",
                          "log_namespace", "log_source", "log_time"])

    def test_filter_event(self):
        """Events can be filtered."""

        logger.publisher.levels.setLogLevelForNamespace(
            "virtualbricks.tests.test_log", log.LogLevel.warn)
        self.addCleanup(logger.publisher.levels.clearLogLevels)
        logger.info(test_event)
        self.assertEqual(len(self.observer), 0)

    def test_legacy_emitter(self):
        """Test the events logged with the legacy logger are not lost."""

        observer = log.LegacyAdapter()
        legacylog.addObserver(observer)
        self.addCleanup(legacylog.removeObserver, observer)
        legacylog.msg("test")
        legacylog.err(RuntimeError("error"))
        err = self.flushLoggedErrors(RuntimeError)
        self.assertEqual(len(self.observer), 2)
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
        self.assertEqual(observer, [test_event])

    def test_legacy_observer_ignore_debug(self):
        """
        By default all debug messages are filtered by the legacy observer.
        """

        observer = Observer()
        legacylog.addObserver(observer)
        self.addCleanup(legacylog.removeObserver, observer)
        logger.debug(test_event)
        self.assertEqual(observer, [])

    @skipUnless(twisted.__version__ >= "15.2.0",
                "New behavior in twisted 15.2.0")
    def test_legacy_rename_format_key(self):
        """
        If the event has a 'format' key, rename it to '_format'.
        """

        legacy_observer = log.LegacyAdapter()
        legacylog.addObserver(legacy_observer)
        self.addCleanup(legacylog.removeObserver, legacy_observer)
        legacylog.msg("test")
        self.assertEqual(len(self.observer), 1)
        event = self.observer[0]
        self.assertNotIn("format", event)
        self.assertIn("_format", event)

    @skipUnless(twisted.__version__ >= "15.2.0",
                "New behavior in twisted 15.2.0")
    def test_legacy_has_both_format_and__format(self):
        """
        An error is reported if an event has both 'format' and '_format' keys.
        """

        legacy_observer = log.LegacyAdapter()
        legacylog.addObserver(legacy_observer)
        self.addCleanup(legacylog.removeObserver, legacy_observer)
        legacylog.msg("test", _format="%(test)s")
        self.assertEqual(len(self.observer), 2)
        self.assertEqual(self.observer[0], log.double_format_error)


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
        self.assertEqual(len(self.observer), 1)
        self.assertEqual(self.observer[0]["log_format"].split("\n")[0], "exp")

    def test_event_has_log_id(self):
        """
        Test if events logged with the standard logging library have the
        'log_id' attribute.
        """

        logging.warn("test")
        self.assertEqual(len(self.observer), 1)
        self.assertIn("log_id", self.observer[0])
