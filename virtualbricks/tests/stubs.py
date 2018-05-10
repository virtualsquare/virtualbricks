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

from collections import OrderedDict
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
    command_builder = OrderedDict([("-a", "a"), ("# -b", "b"), ("-c", "c"), ("-d", hook)])
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


class Factory(brickfactory.BrickFactory):

    def __init__(self):
        brickfactory.BrickFactory.__init__(self, defer.Deferred())
        self.register_brick_type(BrickStub, "stub")
        self.register_brick_type(StubBrick, "_stub")


FactoryStub = Factory


class StubBrick(bricks.Brick):

    type = "Stub2"
    command_builder = {"-a": "a", "# -b": "b", "-c": "c", "-d": hook}
    config_factory = BrickStubConfig

    def poweron(self):
        if not self.proc:
            self.proc = bricks.FakeProcess(self)
        return defer.succeed(self)

    def poweroff(self, kill=False):
        self.proc = None
        return defer.succeed((self, None))


