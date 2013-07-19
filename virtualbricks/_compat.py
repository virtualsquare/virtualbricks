import logging
import inspect
import urllib
import uuid
from datetime import datetime
import time

from twisted.python import failure, util

from virtualbricks import _log as log


class _Event(object):

    def __init__(self, logger, log_level, log_format, log_id):
        self.logger = logger
        self.log_level = log_level
        self.log_format = log_format
        self.log_id = log_id

    def __call__(self, **kwds):
        self.logger.emit(self.log_level, self.log_format, log_id=self.log_id,
                         **kwds)

    def tap(self, observer, publisher):
        filtered = log.FilteringLogObserver(observer, (self._is,))
        publisher.addObserver(filtered, False)
        return lambda: publisher.removeObserver(filtered)

    def _is(self, event):
        if "log_id" in event and event["log_id"] == self.log_id:
            return log.PredicateResult.yes
        return log.PredicateResult.no


def make_id(log_format):
    module = inspect.currentframe().f_back.f_back.f_globals["__name__"]
    params = urllib.urlencode(dict(format=log_format, module=module))
    uri = "http://virtualbricks.eu/ns/log/?" + params
    return str(uuid.uuid5(uuid.NAMESPACE_URL, uri))


class Logger(log.Logger):

    LogLevel = log.LogLevel

    def declare(self, log_level, log_format, log_id=None):
        if log_id is None:
            log_id = make_id(log_format)
        return _Event(self, log_level, log_format, log_id)


class LoggingToTwistedLogHandler(logging.Handler):

    logger = log.Logger()

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
            return log.LogLevel.debug
        elif levelName == "INFO":
            return log.LogLevel.info
        elif levelName == "WARNING":
            return log.LogLevel.warn
        elif levelName in set(("ERROR", "CRITICAL")):
            return log.LogLevel.error
        else:
            # probabilly NOTSET
            return log.LogLevel.info


def enumerate_str(iterable):
    for idx, item in enumerate(iterable):
        yield str(idx), item


class _Logger:

    LogLevel = log.LogLevel

    def __init__(self, name):
        self.logger = Logger(name)

    @property
    def publisher(self):
        return self.logger.publisher

    def declare(self, log_format, log_level, log_id=None):
        return self.logger.declare(log_level, log_format, log_id)

    def debug(self, msg, *args):
        self.logger.debug(msg, **dict(enumerate_str(args)))

    def info(self, msg, *args):
        self.logger.info(msg, **dict(enumerate_str(args)))

    def warning(self, msg, *args):
        self.logger.warn(msg, **dict(enumerate_str(args)))

    def error(self, msg, *args, **kwds):
        self.logger.error(msg, **dict(enumerate_str(args), **kwds))

    def msg(self, message, **kwds):
        if "logLevel" in kwds:
            level = kwds.pop("logLevel")
            self.logger.emit(level, message, **kwds)
        else:
            self.logger.info(message, **kwds)

    def err(self, failure, _why, **kwds):
        self.logger.failure(_why, failure, **kwds)

    def exception(self, msg, *args):
        self.logger.failure(msg, **dict(enumerate_str(args)))

    warn = warning


def getLogger(namespace="virtualbricks"):
    return _Logger(namespace)


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

    def getTimezoneOffset(self, when):
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
        if self.timeFormat is not None:
            return time.strftime(self.timeFormat, time.localtime(when))

        tzOffset = -self.getTimezoneOffset(when)
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

    def __call__(self, eventDict):
        text = log.formatEvent(eventDict)
        timeStr = self.formatTime(eventDict["log_time"])
        fmtDict = {"system": eventDict["log_namespace"],
                   "text": text.replace("\n", "\n\t"),
                   "log_format": "[{system}] {text}\n"}
        msgStr = log.formatEvent(fmtDict)

        util.untilConcludes(self.write, timeStr + " " + msgStr)
        util.untilConcludes(self.flush)  # Hoorj!
