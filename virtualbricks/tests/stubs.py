from twisted.internet import defer

from virtualbricks import brickfactory, bricks, virtualmachines as vm


class ProcessTransportStub:

    pid = -1

    def signalProcess(self, signal):
        pass


def hook():
    return "d"


class BrickStubMixin(object):

    def __init__(self):
        self.sended = []
        self.receved = []

    def prog(self):
        return "true"

    def send(self, data):
        self.sended.append(data)


class BrickStubConfig(bricks.Config):

    parameters = {"a": bricks.String("arg1"),
                  "c": bricks.Boolean(True)}


class BrickStub(BrickStubMixin, bricks.Brick):

    type = "Stub"
    command_builder = {"-a": "a", "# -b": "b", "-c": "c", "-d": hook}
    config_factory = BrickStubConfig

    def __init__(self, factory, name):
        BrickStubMixin.__init__(self)
        bricks.Brick.__init__(self, factory, name)


class VirtualMachineStub(BrickStubMixin, vm.VirtualMachine):

    def __init__(self, factory, name):
        BrickStubMixin.__init__(self)
        vm.VirtualMachine.__init__(self, factory, name)


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
