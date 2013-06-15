# -*- test-case-name: virtualbricks.tests.test_tunnels -*-
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

from virtualbricks import bricks, link, _compat


log = _compat.getLogger(__name__)

if False:  # pyflakes
    _ = str


class TunnelListenConfig(bricks.Config):

    parameters = {"name": bricks.String(""),
                  "sock": bricks.String(""),
                  "password": bricks.String(""),
                  "port": bricks.SpinInt(7667, 1, 65535)}


class TunnelListen(bricks.Brick):

    type = "TunnelListen"
    config_factory = TunnelListenConfig
    command_builder = {"-s": 'sock',
                       "#password": "password",
                       "-p": "port"}

    def __init__(self, factory, name):
        bricks.Brick.__init__(self, factory, name)
        self.config["name"] = name
        self.plugs.append(link.Plug(self))

    def restore_self_plugs(self):
        self.plugs.append(link.Plug(self))

    def clear_self_socks(self, sock=None):
        self.config["sock"] = ""

    def get_parameters(self):
        if self.plugs[0].sock:
            return _("plugged to") + " " + self.plugs[0].sock.brick.name + \
                    " " + _("listening to udp:") + " " + self.config.get("port")
        return _("disconnected")

    def prog(self):
        return self.settings.get("vdepath") + "/vde_cryptcab"

    def on_config_changed(self):
        if self.plugs[0].sock is not None:
            self.config["sock"] = self.plugs[0].sock.path.rstrip('[]')
        bricks.Brick.on_config_changed(self)

    def configured(self):
        return (self.plugs[0].sock is not None)

    def args(self):
        pwdgen = "echo %s | sha1sum >/tmp/tunnel_%s.key && sync" % (
            self.config["password"], self.name)
        exitstatus = os.system(pwdgen)
        log.info("Command pwdgen exited with code %d", exitstatus)
        res = []
        res.append(self.prog())
        res.append("-P")
        res.append("/tmp/tunnel_%s.key" % self.name)
        for arg in self.build_cmd_line():
            res.append(arg)
        return res

    #def post_poweroff(self):
    #    os.unlink("/tmp/tunnel_%s.key" % self.name)
    #    pass


class TunnelConnectConfig(TunnelListenConfig):

    parameters = {"host": bricks.String(""),
                  "localport": bricks.SpinInt(10771, 1, 65535)}


class TunnelConnect(TunnelListen):

    type = "TunnelConnect"
    config_factory = TunnelConnectConfig
    command_builder = {"-s": 'sock',
                       "#password": "password",
                       "-p": "localport",
                       "-c": "host",
                       "#port": "port"}

    def get_parameters(self):
        if self.plugs[0].sock:
            return _("plugged to") + " " + self.plugs[0].sock.brick.name +\
                _(", connecting to udp://") + self.config["host"]

        return _("disconnected")

    def on_config_changed(self):
        if self.plugs[0].sock is not None:
            self.config["sock"] = self.plugs[0].sock.path.rstrip('[]')

        h = self.config["host"]
        if h:
            self.config["host"] = "%s:%d" % (h.split(":")[0],
                                             self.config["port"])

        bricks.Brick.on_config_changed(self)

    def configured(self):
        return self.plugs[0].sock is not None and self.config["host"]
