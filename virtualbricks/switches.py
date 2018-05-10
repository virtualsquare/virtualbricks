# -*- test-case-name: virtualbricks.tests.test_switches -*-
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
import os

from twisted.internet import defer

from virtualbricks import settings, bricks, log, errors
from virtualbricks._spawn import abspath_vde


if False:  # pyflakes
    _ = str

sock_not_exists = log.Event("Socket does not exists: {path}")


class SwitchConfig(bricks.Config):

    parameters = {"numports": bricks.SpinInt(32, 1, 128),
                  "hub": bricks.Boolean(False),
                  "fstp": bricks.Boolean(False)}


class Switch(bricks.Brick):

    type = "Switch"
    ports_used = 0
    config_factory = SwitchConfig

    def set_name(self, name):
        self._name = name
        for so in self.socks:
            so.nickname = name + "_port"
            so.path = os.path.join(settings.VIRTUALBRICKS_HOME, name + ".ctl")

    name = property(bricks.Brick.get_name, set_name)

    def __init__(self, factory, name):
        bricks.Brick.__init__(self, factory, name)
        self.command_builder = OrderedDict([
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
                ("-M", self.console)
        ])
        sock = factory.new_sock(self, self.name + "_port")
        sock.path = self.path()
        self.socks.append(sock)

    def get_parameters(self):
        fstp = ""
        hub = ""
        if self.config["fstp"]:
            fstp = ", FSTP"
        if self.config["hub"]:
            hub = ", HUB"
        return _("Ports: ") + "%d%s%s" % (self.config["numports"], fstp, hub)

    def prog(self):
        return abspath_vde('vde_switch')

    def configured(self):
        return self.socks[0].has_valid_path()

    # live-management callbacks
    def cbset_path(self, path):
        self.socks[0].path = path

    def cbset_fstp(self, arg=False):
        self.send("fstp/setfstp %d\n" % bool(arg))

    def cbset_hub(self, arg=False):
        self.send("port/sethub %d\n" % bool(arg))

    def cbset_numports(self, arg="32"):
        self.send("port/setnumports %s\n" % arg)


class SwitchWrapperConfig(bricks.Config):

    parameters = {"path": bricks.String("")}


class SwitchWrapper(bricks.Brick):

    type = "SwitchWrapper"
    pid = -1
    config_factory = SwitchWrapperConfig

    def __init__(self, factory, name):
        bricks.Brick.__init__(self, factory, name)
        self.socks.append(factory.new_sock(self, self.name + "_port"))

    def poweron(self):
        if self.proc is not None:
            return defer.succeed(self)
        elif os.path.exists(self.config["path"]):
            self.proc = bricks.FakeProcess(self)
            return defer.succeed(self)
        else:
            self.logger.debug(sock_not_exists, path=self.config["path"])
            msg = _("Socket does not exists: %s") % self.config["path"]
            return defer.fail(errors.BadConfigError(msg))

    def poweroff(self, kill=False):
        self.proc = None
        return defer.succeed((self, None))

    def get_parameters(self):
        return self.config["path"]

    def configured(self):
        return self.socks[0].has_valid_path()

    def cbset_path(self, path):
        self.socks[0].path = path
