import logging
# import urllib
# import uuid

from twisted.python import log, failure

FATAL = CRITICAL = logging.CRITICAL
WARN = WARNING = logging.WARNING
ERROR = logging.ERROR
INFO = logging.INFO
DEBUG = logging.DEBUG


class LogInfo:

    # class __metaclass__(type):

    #     def __new__(cls, name, bases, dct):
    #         if "id" not in dct:
    #             format = dct.get("format", "UNKNOWN ERROR")
    #             url = "http://virtualbricks.eu/ns/log/?" + urllib.urlencode(
    #                 dict(format=format))
    #             dct["id"] = uuid.uuid5(uuid.NAMESPACE_URL, url)
    #         return type.__new__(cls, name, bases, dct)

    level = INFO
    format = ""

    def __str__(self):
        return self.format.format(self)


class LoggingToTwistedLogHandler(logging.Handler):

    def emit(self, record):
        try:
            msg = self.format(record)
            if record.exc_info is not None:
                msg = log._safeFormat(record.msg, record.args)
                log.err(failure.Failure(*record.exc_info), msg,
                        system=record.name)
            else:
                log.msg(msg, record=record, system=record.name,
                        isError=record.levelno >= logging.ERROR)
        except Exception:
            self.handleError(record)


class Logger(object):

    def __init__(self, name):
        self.name = name

    def debug(self, msg, *args):
        log.msg(log._safeFormat(msg, args), system=self.name,
                logLevel=logging.DEBUG)

    def info(self, msg, *args):
        log.msg(log._safeFormat(msg, args), system=self.name,
                logLevel=logging.INFO)

    def msg(self, message, **kwds):
        kwds["system"] = self.name
        if isinstance(message, LogInfo):
            kwds["logLevel"] = message.level
        log.msg(message, **kwds)

    def warning(self, msg, *args):
        log.msg(log._safeFormat(msg, args), system=self.name,
                logLevel=logging.WARNING)

    def error(self, msg, *args, **kwds):
        log.msg(log._safeFormat(msg, args), system=self.name, isError=True,
                logLevel=logging.ERROR, **kwds)

    def err(self, *args, **kwds):
        kwds["system"] = self.name
        log.err(*args, **kwds)

    def exception(self, msg, *args):
        log.err(failure.Failure(), log._safeFormat(msg, args),
                system=self.name, logLevel=logging.ERROR)

    def critical(self, msg, *args):
        log.err(failure.Failure(), log._safeFormat(msg, args),
                system=self.name, logLevel=logging.CRITICAL)

    warn = warning
    fatal = critical


def getLogger(name=None):
    if name is None:
        return logging.getLogger()
    return Logger(name)
