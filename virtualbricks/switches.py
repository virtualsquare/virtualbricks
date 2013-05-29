# -*- test-case-name: virtualbricks.tests.test_switches -*-
# Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
# Copyright (C) 2013 Virtualbricks team

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

import os
import logging

from virtualbricks import settings, bricks, link


log = logging.getLogger(__name__)

if False:  # pyflakes
    _ = str


class Switch(bricks.Brick):

    type = "Switch"
    ports_used = 0
    command_builder = {"-x": "hubmode",
                       "-n": "numports",
                       "-F": "fstp",
                       "--macaddr": "macaddr",
                       "-m": "mode",
                       "-g": "group",
                       "--priority": "priority",
                       "--mgmtmode": "mgmtmode",
                       "--mgmtgroup": "mgmtgroup"}

    class config_factory(bricks.Config):

        parameters = {"numports": bricks.SpinInt(32, 1, 128),
                      "hub": bricks.Boolean(False),
                      "fstp": bricks.Boolean(False)}

    def set_name(self, name):
        self._name = name
        for so in self.socks:
            so.nickname = name + "_port"
            so.path = os.path.join(settings.VIRTUALBRICKS_HOME, name + ".ctl")

    name = property(bricks.Brick.get_name, set_name)

    def __init__(self, factory, name):
        bricks.Brick.__init__(self, factory, name)
        self.command_builder["-s"] = self.path
        self.command_builder["-M"] = self.console
        # self.cfg.numports = "32"
        # self.cfg.hub = ""
        # self.cfg.fstp = ""
        self.socks.append(link.Sock(self, self.name + "_port"))
        # XXX: obiviusly configuration is changed in __init__, check if it is
        # actually used by someone
        self.on_config_changed()

    def get_parameters(self):
        fstp = ""
        hub = ""
        if (self.cfg.get('fstp', False)):
            if self.cfg.fstp == '*':
                fstp = ", FSTP"
        if (self.cfg.get('hub', False)):
            if self.cfg.hub == '*':
                hub = ", HUB"
        return _("Ports:") + "%d%s%s" % ((int(unicode(
            self.cfg.get('numports', '32')))), fstp, hub)

    def prog(self):
        return self.settings.get("vdepath") + "/vde_switch"

    def on_config_changed(self):
        self.socks[0].path = self.path()

        if self.proc is not None:
            self.need_restart_to_apply_changes = True
        bricks.Brick.on_config_changed(self)

    def configured(self):
        return self.socks[0].has_valid_path()

    # live-management callbacks
    def cbset_fstp(self, arg=False):
        log.debug("%s: callback 'fstp' with argument %s", self.name, arg)
        if arg:
            self.send("fstp/setfstp 1\n")
        else:
            self.send("fstp/setfstp 0\n")
        log.debug(self.recv())

    def cbset_hub(self, arg=False):
        log.debug("%s: callback 'hub' with argument %s", self.name, arg)
        if arg:
            self.send("port/sethub 1\n")
        else:
            self.send("port/sethub 0\n")
        log.debug(self.recv())

    def cbset_numports(self, arg="32"):
        log.debug("%s: callback 'numports' with argument %s", self.name, arg)
        self.send("port/setnumports " + str(arg))
        log.debug(self.recv())


class FakeProcess:

    pid = -1
    terminated = False

    def __init__(self, brick):
        self.brick = brick

    def poll(self):
        if self.terminated:
            return 0
        return None

    def send_signal(self, signo):
        self.terminated = False


class SwitchWrapper(bricks.Brick):

    type = "SwitchWrapper"
    pid = -1

    class config_factory(bricks.Config):

        parameters = {"path": bricks.String(""),
                      "numports": bricks.SpinInt(32, 1, 128),
                      "hub": bricks.Boolean(False),
                      "fstp": bricks.Boolean(False)}

    def __init__(self, factory, name):
        bricks.Brick.__init__(self, factory, name)
        self.socks.append(link.Sock(self, self.name + "_port"))
        # XXX: see Switch __init__
        self.on_config_changed()

    def poweron(self):
        if os.path.exists(self.cfg.path):
            self.proc = FakeProcess(self)
        else:
            log.debug("Socket does not exists: %s", self.cfg.path)
            self.proc = None

    def poweroff(self):
        self.proc = None

    def get_parameters(self):
        return ""

    def __set_sock_path(self):
        self.socks[0].path = self.cfg.path

    def on_config_changed(self):
        self.__set_sock_path()
        bricks.Brick.on_config_changed(self)

    def configure(self, attrs):
        bricks.Brick.configure(self, attrs)
        self.__set_sock_path()

    def configured(self):
        return self.socks[0].has_valid_path()

    def path(self):
        return self.cfg.path
