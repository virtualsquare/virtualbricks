# Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
# Copyright (C) 2013 Virtualbricks team

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

import time
from datetime import datetime
import inspect
import urllib
import uuid
import functools

from twisted.python import failure, util

from virtualbricks._log import (InvalidLogLevelError, LogLevel, formatEvent,
    Logger as _Logger, LegacyLogger, ILogObserver, ILegacyLogObserver,
    LogPublisher, PredicateResult, ILogFilterPredicate, FilteringLogObserver,
    LogLevelFilterPredicate, LegacyLogObserver, replaceTwistedLoggers)

__all__ = ["Event", "Logger", "InvalidLogLevelError", "LogLevel",
           "formatEvent", "Logger", "LegacyLogger", "ILogObserver",
           "ILegacyLogObserver", "LogPublisher", "PredicateResult",
           "ILogFilterPredicate", "FilteringLogObserver",
           "LogLevelFilterPredicate", "LegacyLogObserver",
           "replaceTwistedLoggers"]


def make_id(log_format):
    module = inspect.currentframe().f_back.f_back.f_globals["__name__"]
    params = urllib.urlencode(dict(format=log_format, module=module))
    uri = "http://virtualbricks.eu/ns/log/?" + params
    return str(uuid.uuid5(uuid.NAMESPACE_URL, uri))


class Event(object):

    def __init__(self, log_format, log_id=None):
        self.log_format = log_format
        if log_id is None:
            log_id = make_id(log_format)
        self.log_id = log_id

    def __call__(self, logger, level, **kwds):
        logger.emit(level, self.log_format, log_id=self.log_id, **kwds)

    def tap(self, observer, publisher):
        filtered = FilteringLogObserver(observer, (self._is,))
        publisher.addObserver(filtered, False)
        return lambda: publisher.removeObserver(filtered)

    def _is(self, event):
        if "log_id" in event and event["log_id"] == self.log_id:
            return PredicateResult.yes
        return PredicateResult.no


def expect_event(func):
    @functools.wraps(func)
    def wrapper(self, event, **kwds):
        if isinstance(event, str):
            event = Event(event)
        return func(self, event, **kwds)
    return wrapper


class Logger(_Logger):

    @expect_event
    def debug(self, event, **kwds):
        event(self, LogLevel.debug, **kwds)

    @expect_event
    def info(self, event, **kwds):
        event(self, LogLevel.info, **kwds)

    @expect_event
    def warn(self, event, **kwds):
        event(self, LogLevel.warn, **kwds)

    @expect_event
    def error(self, event, **kwds):
        event(self, LogLevel.error, **kwds)

    @expect_event
    def exception(self, event, **kwds):
        event(self, LogLevel.error, log_failure=failure.Failure(), **kwds)


def getTimezoneOffset(when):
    """
    Return the current local timezone offset from UTC.

    @type when: C{int}
    @param when: POSIX (ie, UTC) timestamp for which to find the offset.

    @rtype: C{int}
    @return: The number of seconds offset from UTC.  West is positive,
    east is negative.
    """
    offset = datetime.utcfromtimestamp(when) - datetime.fromtimestamp(when)
    return offset.days * (60 * 60 * 24) + offset.seconds


def formatTime(self, when):
    """
    Format the given UTC value as a string representing that time in the
    local timezone.

    By default it's formatted as a ISO8601-like string (ISO8601 date and
    ISO8601 time separated by a space). It can be customized using the
    C{timeFormat} attribute, which will be used as input for the underlying
    C{time.strftime} call.

    @type when: C{int}
    @param when: POSIX (ie, UTC) timestamp for which to find the offset.

    @rtype: C{str}
    """

    tzOffset = -getTimezoneOffset(when)
    when = datetime.utcfromtimestamp(when + tzOffset)
    tzHour = abs(int(tzOffset / 60 / 60))
    tzMin = abs(int(tzOffset / 60 % 60))
    if tzOffset < 0:
        tzSign = "-"
    else:
        tzSign = "+"
    return "%d-%02d-%02d %02d:%02d:%02d%s%02d%02d" % (
        when.year, when.month, when.day,
        when.hour, when.minute, when.second,
        tzSign, tzHour, tzMin)


class FileLogObserver:
    """
    Log observer that writes to a file-like object.

    @type timeFormat: C{str} or C{NoneType}
    @ivar timeFormat: If not C{None}, the format string passed to strftime().
    """

    timeFormat = None

    def __init__(self, f):
        self.write = f.write
        self.flush = f.flush

    def formatTime(self, when):
        if self.timeFormat is not None:
            return time.strftime(self.timeFormat, time.localtime(when))
        return formatTime(when)

    def __call__(self, eventDict):
        text = formatEvent(eventDict)
        timeStr = self.formatTime(eventDict["log_time"])
        fmtDict = {"system": eventDict["log_namespace"],
                   "text": text.replace("\n", "\n\t"),
                   "log_format": "[{system}] {text}\n"}
        msgStr = formatEvent(fmtDict)

        util.untilConcludes(self.write, timeStr + " " + msgStr)
        util.untilConcludes(self.flush)  # Hoorj!


import logging


class LoggingToTwistedLogHandler(logging.Handler):

    logger = Logger()

    def emit(self, record):
        try:
            msg = self.format(record)
            if record.exc_info is not None:
                self.logger.failure(msg, failure.Failure(*record.exc_info))
            else:
                level = self._map_levelname_to_LogLevel(record.levelname)
                self.logger.emit(level, msg, **record.__dict__)
        except Exception:
            self.handleError(record)

    def _map_levelname_to_LogLevel(self, levelName):
        if levelName == "DEBUG":
            return LogLevel.debug
        elif levelName == "INFO":
            return LogLevel.info
        elif levelName == "WARNING":
            return LogLevel.warn
        elif levelName in set(("ERROR", "CRITICAL")):
            return LogLevel.error
        else:
            # probabilly NOTSET
            return LogLevel.info
