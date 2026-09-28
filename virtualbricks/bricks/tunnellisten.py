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

import hashlib
import os

from virtualbricks import bricks
from virtualbricks.bricks.command import Command, socket_path, vde_program
from virtualbricks.bricks.plug import Plug
from virtualbricks.config.schema import Int, Str, define, field
from virtualbricks.i18n import _


def tunnel_key(password):
    """
    The key of a tunnel, made from its password.

    It's what "echo PASSWORD | sha1sum" writes, as Virtualbricks made it
    before, so that both ends of a tunnel agree even when one of them runs an
    older version: the SHA-1 of the password and a newline, in hex, then two
    spaces, a dash and a newline. That shell command changed some passwords
    before it read them, as one with quotes, backslashes, a dollar or spaces
    in a row: with those, the two ends agree only if both run this version.
    """

    digest = hashlib.sha1(f"{password}\n".encode()).hexdigest()
    return f"{digest}  -\n".encode()


def write_key(path, password):
    """Write the key of a tunnel to path, readable by its owner only."""

    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    # a file that was there keeps its mode through O_CREAT
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "wb") as fp:
        fp.write(tunnel_key(password))


@define
class TunnelListenConfig(bricks.BrickConfig):

    password = field(
        Str(), default="", help="The password of the tunnel, in clear text"
    )
    listen_port = field(
        Int(1, 65535), default=7667, help="The UDP port to listen on"
    )


class TunnelListen(bricks.Brick):

    type = "TunnelListen"
    summary = "The server end of an encrypted tunnel"
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
                + str(self.config.listen_port)
            )
        return _("disconnected")

    def configured(self):
        return bool(self.plugs[0].sock)

    def key_path(self):
        """The key of the tunnel, in the runtime folder."""

        return self.runtime_path(f"{self.name}.key")

    def prepare(self, resume=""):
        """The VDE programs, and the key of the tunnel written."""

        deferred = bricks.Brick.prepare(self, resume)

        def key(prepared):
            write_key(self.key_path(), self.config.password)
            return prepared

        return deferred.addCallback(key)

    def command(self, prepared):
        cmd = Command(vde_program(prepared.vde, "vde_cryptcab"))
        cmd.option("-P", self.key_path())
        cmd.option("-s", socket_path(self.plugs[0]))
        cmd.option("-p", self.config.listen_port)
        return cmd
