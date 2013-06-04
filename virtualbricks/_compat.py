import logging

from twisted.python import log, failure


class LoggingToTwistedLogHandler(logging.Handler):

    def emit(self, record):
        try:
            msg = self.format(record)
            if record.levelno >= logging.ERROR:
                log.err(msg, record=record)
            else:
                log.msg(msg, record=record)
        except (KeyboardInterrupt, SystemExit):
            raise
        except:
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
        log.msg(message, **kwds)

    def warning(self, msg, *args):
        log.msg(log._safeFormat(msg, args), system=self.name,
                logLevel=logging.WARNING)

    def error(self, msg, *args):
        log.err(log._safeFormat(msg, args), system=self.name,
                logLevel=logging.ERROR)

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


def getLogger(name="root"):
    return Logger(name)
