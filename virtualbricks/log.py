# -*- test-case-name: virtualbricks.tests.test_log -*-
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

import time
from datetime import datetime
import inspect
import urllib
import uuid
import functools
import collections


from twisted.python import util, failure

from virtualbricks._log import (InvalidLogLevelError, LogLevel, formatEvent,
    Logger as _Logger, LegacyLogger, ILogObserver, ILegacyLogObserver,
    LogPublisher, PredicateResult, ILogFilterPredicate, FilteringLogObserver,
    LogLevelFilterPredicate, LegacyLogObserver, replaceTwistedLoggers)

import six

if six.PY3:
    def encodingFunc(dictionary):
        return urllib.parse.urlencode(dictionary)
else:
    def encodingFunc(dictionary):
        return urllib.urlencode(dictionary)


__all__ = ["Event", "Logger", "InvalidLogLevelError", "LogLevel",
           "formatEvent", "Logger", "LegacyLogger", "ILogObserver",
           "ILegacyLogObserver", "LogPublisher", "PredicateResult",
           "ILogFilterPredicate", "FilteringLogObserver",
           "LogLevelFilterPredicate", "LegacyLogObserver",
           "replaceTwistedLoggers"]


def make_id(log_format, module=None):
    if module is None:
        module = inspect.currentframe().f_back.f_back.f_globals["__name__"]
    params = encodingFunc(dict(format=log_format, module=module))
    uri = "http://virtualbricks.eu/ns/log/?" + params
    return uuid.uuid5(uuid.NAMESPACE_URL, uri)


class Event(object):

    def __init__(self, log_format, log_id=None, module=None):
        self.log_format = log_format
        if log_id is None:
            log_id = make_id(log_format, module)
        self.log_id = log_id

    def __call__(self, logger, level, **kwds):
        logger.emit(level, self.log_format, log_id=self.log_id, **kwds)

    def tap(self, observer, publisher):
        filtered = FilteringLogObserver(observer, (self.is_,))
        publisher.addObserver(filtered, False)
        return lambda: publisher.removeObserver(filtered)

    def is_(self, event):
        if "log_id" in event and event["log_id"] == self.log_id:
            return PredicateResult.yes
        return PredicateResult.no

    def __hash__(self):
        return int(self.log_id)

    def __eq__(self, other):
        if isinstance(other, Event):
            return self.log_id == other.log_id
        elif isinstance(other, collections.Mapping):
            return "log_id" in other and other["log_id"] == self.log_id
        return NotImplemented

    def __ne__(self, other):
        return not self == other


def expect_event(func):
    @functools.wraps(func)
    def wrapper(self, event, *args, **kwds):
        if isinstance(event, str):
            event = Event(event)
        elif isinstance(event, bytes):
            event = Event(event)
        elif isinstance(event, six.text_type):
            event = Event(event)        
        elif not callable(event):
            raise ValueError("func object was not callable nor str or byte")
        return func(self, event, *args, **kwds)
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

    @expect_event
    def failure(self, event, log_failure=None, **kwargs):
        if log_failure is None:
            log_failure = failure.Failure()
        event(self, LogLevel.error, log_failure=log_failure, **kwargs)

    def failure_eb(self, failure, event, reraise=False, **kwargs):
        self.failure(event, failure, **kwargs)
        if reraise:
            return failure

    def log_failure(self, deferred, event, **kwargs):
        def log(failure):
            self.failure(event, failure, **kwargs)
            return failure
        return deferred.addErrback(log)


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


def format_time(when):
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

    def format_time(self, when):
        if self.timeFormat is not None:
            return time.strftime(self.timeFormat, time.localtime(when))
        return format_time(when)

    def __call__(self, event):
        text = formatEvent(event)
        timeStr = self.format_time(event["log_time"])
        fmtDict = {"system": event["log_namespace"],
                   "text": text.replace("\n", "\n\t"),
                   "log_format": "[{system}] {text}\n"}
        msgStr = formatEvent(fmtDict)
        if "log_failure" in event:
            msgStr += event["log_failure"].getTraceback()

        util.untilConcludes(self.write, timeStr + " " + msgStr)
        util.untilConcludes(self.flush)  # Hoorj!


def format_traceback(event):
    if "log_failure" in event:
        return event["log_failure"].getTraceback()
    return ""


import logging


class StdLoggingAdapter(logging.Handler):

    logger = Logger()
    levels = {
        "DEBUG": LogLevel.debug,
        "INFO": LogLevel.info,
        "WARNING": LogLevel.warn,
        "ERROR": LogLevel.error,
        "CRITICAL": LogLevel.error
    }

    def emit(self, record):
        kw = dict(("rec_" + k, v) for k, v in record.__dict__.items())
        kw["log_record"] = True
        event = Event(self.format(record), module="virtualbricks.log.std")
        if record.exc_info is not None:
            tpe, value, tb = record.exc_info
            self.logger.failure(event, failure.Failure(value, tpe, tb), **kw)
        else:
            try:
                level = self.levels[record.levelname]
            except KeyError:
                if record.levelno < logging.DEBUG:
                    level = LogLevel.debug
                elif record.levelno < logging.INFO:
                    level = LogLevel.info
                elif record.levelno < logging.WARNING:
                    level = LogLevel.warn
                else:
                    level = LogLevel.error
            event(self.logger, level, **kw)


double_format_error = Event("Log event has both 'format' and '_format' keys. "
                            "Discarding '_format' ({ev[_format]})")


class LegacyAdapter:

    logger = Logger()
    levels = {
        "DEBUG": LogLevel.debug,
        "INFO": LogLevel.info,
        "WARNING": LogLevel.warn,
        "ERROR": LogLevel.error,
        "CRITICAL": LogLevel.error
    }

    def __call__(self, event):
        if "log_id" in event:
            # don't play ping pong with the LegacyLogObserver
            return
        if "format" in event:
            if "_format" in event:
                self.logger.error(double_format_error, ev=event)
            event["_format"] = event["format"]
            del event["format"]
        if isinstance(event["message"], six.string_types):
            msg = event["message"]
        else:
            msg = "\n".join(event["message"])
        ev = Event(msg, module="virtualbricks.log.legacy")
        if event["isError"]:
            fail = event.get("failure")
            if fail:
                self.logger.failure(ev, log_failure=fail, **event)
            else:
                self.logger.error(ev, **event)
        else:
            self.logger.info(ev, **event)
