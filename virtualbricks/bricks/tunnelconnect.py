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

from virtualbricks.bricks.tunnellisten import TunnelListen, TunnelListenConfig
from virtualbricks.config import Int, Str, define, field
from virtualbricks.i18n import _


@define
class TunnelConnectConfig(TunnelListenConfig):

    host = field(Str(), default="")
    localport = field(Int(1, 65535), default=10771)


class TunnelConnect(TunnelListen):

    type = "TunnelConnect"
    config_factory = TunnelConnectConfig
    command_builder = {
        "-s": None,
        "#password": "password",
        "-p": "localport",
        "-c": None,
        "#port": "port",
    }

    def __init__(self, factory, name):
        TunnelListen.__init__(self, factory, name)
        self.command_builder["-c"] = self.get_host

    def get_host(self):
        if self.config.host:
            return "{0}:{1}".format(self.config.host, self.config.port)
        return ""

    def get_parameters(self):
        if self.plugs[0].sock:
            return (
                _("plugged to")
                + " "
                + self.plugs[0].sock.brick.name
                + _(", connecting to udp://")
                + self.config.host
            )

        return _("disconnected")

    def configured(self):
        return self.plugs[0].sock is not None and self.config.host
