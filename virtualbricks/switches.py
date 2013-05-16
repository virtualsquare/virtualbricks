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

from virtualbricks import base, settings
from virtualbricks.bricks import Brick
from virtualbricks.link import Sock


log = logging.getLogger(__name__)

if False:  # pyflakes
    _ = str


class SwitchConfig(base.NewConfig):

    parameters = [("numports", base.SpinInt(32, 1, 128)),
                  ("hub", base.Boolean(False)),
                  ("fstp", base.Boolean(False))]


class Switch(Brick):
    """
    >>> # bug #730812
    >>> from copy import deepcopy
    >>> factory = BrickFactory()
    >>> sw1 = Switch(factory, 'sw1')
    >>> sw2 = factory.dupbrick(sw1)
    >>> id(sw1) != id(sw2)
    True
    >>> sw1 is not sw2
    True
    >>> sw1.cfg is not sw2.cfg
    True
    >>> sw1.icon is not sw2.icon
    True
    """

    type = "Switch"

    def set_name(self, name):
        self._name = name
        for so in self.socks:
            so.nickname = name + "_port"
            so.path = os.path.join(settings.VIRTUALBRICKS_HOME, name + ".ctl")

    name = property(Brick.get_name, set_name)

    pid = -1
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

    def __init__(self, _factory, _name):
        Brick.__init__(self, _factory, _name)
        self.command_builder["-s"] = self.path
        self.command_builder["-M"] = self.console
        self.cfg.numports = "32"
        self.cfg.hub = ""
        self.cfg.fstp = ""
        self.socks.append(Sock(self, self.name + "_port"))
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
        Brick.on_config_changed(self)

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

        def __init__(self, brick):
            self.brick = brick

        def poll(self):
            return True


class SwitchWrapper(Brick):

    type = "SwitchWrapper"
    pid = -1
    command_builder = {}
    has_console = False
    proc = None

    def __init__(self, _factory, _name):
        Brick.__init__(self, _factory, _name)
        self.cfg.path = ""
        self.socks.append(Sock(self, self.name + "_port"))
        # XXX: see Switch __init__
        self.on_config_changed()
        self.cfg.numports = 32

    def get_parameters(self):
        return ""

    def prog(self):
        return ""

    def on_config_changed(self):
        self.socks[0].path = self.cfg.path
        Brick.on_config_changed(self)

    def configured(self):
        return self.socks[0].has_valid_path()

    def path(self):
        return self.cfg.path

    def pidfile(self):
        return "/tmp/%s.pid" % self.name

    pidfile = property(pidfile)

    def poweron(self):
        if os.path.exists(self.cfg.path):
            self.proc = FakeProcess(self)
        else:
            self.proc = None

    def _poweron(self):
        pass

    def poweroff(self):
        pass
