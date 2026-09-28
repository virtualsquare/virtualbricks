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

"""A tunnel server: vde_cryptcab, listening for a tunnel client."""

import os

from twisted.logger import Logger

from virtualbricks import bricks
from virtualbricks.bricks.command import Command, socket_path, vde_program
from virtualbricks.bricks.plug import Plug
from virtualbricks.config.schema import Int, Str, define, field
from virtualbricks.i18n import _

logger = Logger()
pwdgen_exit = "Command pwdgen exited with {code}"


@define
class TunnelListenConfig(bricks.BrickConfig):

    password = field(Str(), default="")
    port = field(Int(1, 65535), default=7667)


class TunnelListen(bricks.Brick):

    type = "TunnelListen"
    config_factory = TunnelListenConfig
    connections = "connect"

    def __init__(self, factory, name):
        bricks.Brick.__init__(self, factory, name)
        self.plugs.append(Plug(self))

    def get_parameters(self):
        if self.plugs[0].sock:
            return (
                _("plugged to")
                + " "
                + self.plugs[0].sock.brick.name
                + " "
                + _("listening to udp:")
                + " "
                + str(self.config.port)
            )
        return _("disconnected")

    def configured(self):
        return bool(self.plugs[0].sock)

    def key_path(self):
        return "/tmp/tunnel_%s.key" % self.name

    def prepare(self):
        deferred = bricks.Brick.prepare(self)

        def write_key(prepared):
            # TODO: port to utils.getProcessOutput
            pwdgen = "echo %s | sha1sum >%s && sync" % (
                self.config.password,
                self.key_path(),
            )
            exitstatus = os.system(pwdgen)
            logger.info(pwdgen_exit, code=exitstatus)
            return prepared

        return deferred.addCallback(write_key)

    def command(self, prepared):
        cmd = Command(vde_program(prepared.vde, "vde_cryptcab"))
        cmd.option("-P", self.key_path())
        cmd.option("-s", socket_path(self.plugs[0]))
        cmd.option("-p", self.config.port)
        return cmd

    # def post_poweroff(self):
    #    os.unlink("/tmp/tunnel_%s.key" % self.name)
    #    pass
