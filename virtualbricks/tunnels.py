# -*- test-case-name: virtualbricks.tests.test_tunnels -*-
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

import os

from virtualbricks import bricks, link, log
from virtualbricks._spawn import abspath_vde


logger = log.Logger()
pwdgen_exit = log.Event("Command pwdgen exited with {code}")

if False:  # pyflakes
    _ = str


class TunnelListenConfig(bricks.Config):

    parameters = {"password": bricks.String(""),
                  "port": bricks.SpinInt(7667, 1, 65535)}


class TunnelListen(bricks.Brick):

    type = "TunnelListen"
    config_factory = TunnelListenConfig
    command_builder = {"-s": None,
                       "#password": "password",
                       "-p": "port"}

    def __init__(self, factory, name):
        bricks.Brick.__init__(self, factory, name)
        self.command_builder["-s"] = self.sock_path
        self.plugs.append(link.Plug(self))

    def sock_path(self):
        if self.configured():
            return self.plugs[0].sock.path.rstrip('[]')
        return ""

    def get_parameters(self):
        if self.plugs[0].sock:
            return _("plugged to") + " " + self.plugs[0].sock.brick.name + \
                    " " + _("listening to udp:") + " " + \
                    self.config.get("port")
        return _("disconnected")

    def prog(self):
        return abspath_vde('vde_cryptcab')

    def configured(self):
        return bool(self.plugs[0].sock)

    def args(self):
        # TODO: port to utils.getProcessOutput
        pwdgen = "echo %s | sha1sum >/tmp/tunnel_%s.key && sync" % (
            self.config["password"], self.name)
        exitstatus = os.system(pwdgen)
        logger.info(pwdgen_exit, code=exitstatus)
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
    command_builder = {"-s": None,
                       "#password": "password",
                       "-p": "localport",
                       "-c": None,
                       "#port": "port"}

    def __init__(self, factory, name):
        TunnelListen.__init__(self, factory, name)
        self.command_builder["-c"] = self.get_host

    def get_host(self):
        if self.config["host"]:
            return "{0}:{1}".format(self.config["host"], self.config["port"])
        return ""

    def get_parameters(self):
        if self.plugs[0].sock:
            return _("plugged to") + " " + self.plugs[0].sock.brick.name +\
                _(", connecting to udp://") + self.config["host"]

        return _("disconnected")

    def configured(self):
        return self.plugs[0].sock is not None and self.config["host"]
