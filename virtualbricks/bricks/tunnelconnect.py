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

"""A tunnel client: vde_cryptcab, connecting to a tunnel server."""

from virtualbricks.bricks.command import Command, socket_path, vde_program
from virtualbricks import bricks
from virtualbricks.bricks.tunnellisten import TunnelListen
from virtualbricks.config.schema import Int, Str, define, field
from virtualbricks.i18n import _


@define
class TunnelConnectConfig(bricks.BrickConfig):

    password = field(
        Str(), default="", help="The password of the tunnel, in clear text"
    )
    # the host that runs the server end, and its port
    server_host = field(
        Str(), default="", help="The host that runs the server end"
    )
    server_port = field(
        Int(1, 65535), default=7667, help="The UDP port of the server end"
    )
    local_port = field(Int(1, 65535), default=10771, help="The local UDP port")


class TunnelConnect(TunnelListen):

    type = "TunnelConnect"
    summary = "The client end of an encrypted tunnel"
    config_factory = TunnelConnectConfig

    def get_parameters(self):
        if self.plugs[0].sock:
            return (
                _("plugged to")
                + " "
                + self.plugs[0].sock.brick.name
                + _(", connecting to udp://")
                + self.config.server_host
            )

        return _("disconnected")

    def configured(self):
        return self.plugs[0].sock is not None and self.config.server_host

    def command(self, prepared):
        config = self.config
        cmd = Command(vde_program(prepared.vde, "vde_cryptcab"))
        cmd.option("-P", self.key_path())
        cmd.option("-s", socket_path(self.plugs[0]))
        cmd.option("-p", config.local_port)
        cmd.option("-c", f"{config.server_host}:{config.server_port}")
        return cmd
