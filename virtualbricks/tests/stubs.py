import logging

from twisted.internet import defer

from virtualbricks import brickfactory, bricks


def hook():
    return "d"


class BrickStub(bricks.Brick):

    type = "Stub"
    command_builder = {"-a": "a", "# -b": "b", "-c": "c", "-d": hook}

    class config_factory(bricks.Config):

        parameters = {"a": bricks.String("arg1"),
                      "c": bricks.Boolean(True)}

    def prog(self):
        return "true"


class Console(list):

    send = list.append


class ConfigFileStub:

    def __init__(self, factory, save=None, restore=None):
        self.factory = factory
        self._save = save
        self._restore = restore

    def get_type(self):
        return "Stub"

    def restore(self, arg):
        with self.factory.lock():
            if self._restore:
                self._restore(arg)

    def save(self, arg):
        with self.factory.lock():
            if self._save:
                self._save(arg)


class FactoryStub(brickfactory.BrickFactory):

    def __init__(self):
        brickfactory.BrickFactory.__init__(self, defer.Deferred())
        self.register_brick_type(BrickStub, "stub")


class LoggingObserver:

    def __init__(self):
        self.msgs = []

    def emit(self, event_dict):
        self.msgs.append(event_dict)
