# -*- test-case-name: virtualbricks.tests.bricks.test_switch -*-
# Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
# Copyright (C) 2019 Virtualbricks team

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

"""A switch: vde_switch."""

from collections import OrderedDict

from virtualbricks import bricks
from virtualbricks.config import schema
from virtualbricks.config.schema import Bool, Int
from virtualbricks.i18n import _
from virtualbricks.spawn import abspath_vde


@schema.define
class SwitchConfig(bricks.BrickConfig):

    numports = schema.field(Int(1, 128), default=32)
    hub = schema.field(Bool(), default=False)
    fstp = schema.field(Bool(), default=False)


class Switch(bricks.Brick):

    type = "Switch"
    ports_used = 0
    config_factory = SwitchConfig

    def set_name(self, name):
        self._name = name
        for so in self.socks:
            so.nickname = name + "_port"
            so.path = self.path()

    name = property(bricks.Brick.get_name, set_name)

    def __init__(self, factory, name):
        bricks.Brick.__init__(self, factory, name)
        self.command_builder = OrderedDict(
            [
                ("-x", "hub"),
                ("-n", "numports"),
                ("-F", "fstp"),
                ("--macaddr", "macaddr"),
                ("-m", "mode"),
                ("-g", "group"),
                ("--priority", "priority"),
                ("--mgmtmode", "mgmtmode"),
                ("--mgmtgroup", "mgmtgroup"),
                ("-s", self.path),
                ("-M", self.console),
            ]
        )
        sock = factory.new_sock(self, self.name + "_port")
        sock.path = self.path()
        self.socks.append(sock)

    def get_parameters(self):
        fstp = ""
        hub = ""
        if self.config.fstp:
            fstp = ", FSTP"
        if self.config.hub:
            hub = ", HUB"
        return _("Ports: ") + "%d%s%s" % (self.config.numports, fstp, hub)

    def prog(self):
        return abspath_vde("vde_switch")

    def configured(self):
        return self.socks[0].has_valid_path()

    # live-management callbacks
    def cbset_path(self, path):
        self.socks[0].path = path

    def cbset_fstp(self, arg=False):
        self.send(b"fstp/setfstp %d\n" % bool(arg))

    def cbset_hub(self, arg=False):
        self.send(b"port/sethub %d\n" % bool(arg))

    def cbset_numports(self, arg=32):
        self.send(b"port/setnumports %d\n" % arg)
