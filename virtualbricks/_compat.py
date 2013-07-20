from virtualbricks import log


def enumerate_str(iterable):
    for idx, item in enumerate(iterable):
        yield str(idx), item


class Logger:

    LogLevel = log.LogLevel

    def __init__(self, namespace):
        self.logger = log.Logger(namespace)

    @property
    def publisher(self):
        return self.logger.publisher

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
    return Logger(namespace)
