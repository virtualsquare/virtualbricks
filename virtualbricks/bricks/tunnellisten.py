# Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
# Copyright (C) 2026 Virtualbricks team

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

from __future__ import annotations

import hashlib
import os
from typing import TYPE_CHECKING

from twisted.internet import defer

from virtualbricks import bricks
from virtualbricks.bricks.command import (
    Command,
    Prepared,
    socket_path,
    vde_program,
)
from virtualbricks.bricks.plug import Plug
from virtualbricks.config.schema import Int, Str, define, field
from virtualbricks.i18n import N_

if TYPE_CHECKING:  # pragma: no cover
    from virtualbricks.brickfactory import BrickFactory


def tunnel_key(password: str) -> bytes:
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


def write_key(path: str, password: str) -> None:
    """Write the key of a tunnel to path, readable by its owner only."""

    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    # a file that was there keeps its mode through O_CREAT
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "wb") as fp:
        fp.write(tunnel_key(password))


# The configuration of OpenSSL for vde_cryptcab: since OpenSSL 3, Blowfish,
# its cipher, is in the legacy provider, which OpenSSL loads only when told
OPENSSL_CONFIG = """\
openssl_conf = openssl_init

[openssl_init]
providers = providers

[providers]
default = activate
legacy = activate

[activate]
activate = 1
"""


def write_openssl_config(path: str) -> None:
    """Write the configuration of OpenSSL for vde_cryptcab to path."""

    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    with open(path, "w") as fp:
        fp.write(OPENSSL_CONFIG)


@define
class TunnelConfig(bricks.BrickConfig):
    """What both ends of a tunnel have: its password."""

    password: str = field(
        Str(),
        default="",
        label=N_("Password"),
        help=N_("The password of the tunnel, in clear text"),
    )


@define
class TunnelListenConfig(TunnelConfig):

    listen_port: int = field(
        Int(1, 65535),
        default=7667,
        label=N_("Port"),
        help=N_("The UDP port to listen on"),
    )


class Tunnel(bricks.Brick):
    """An end of an encrypted tunnel: vde_cryptcab, plugged into a switch."""

    programs = (("vde_cryptcab",),)
    config: TunnelConfig
    connections = "connect"

    def __init__(self, factory: BrickFactory, name: str) -> None:
        bricks.Brick.__init__(self, factory, name)
        self.plugs.append(Plug(self))

    def key_path(self) -> str:
        """The key of the tunnel, in the runtime folder."""

        return self.runtime_path(f"{self.name}.key")

    def openssl_path(self) -> str:
        """The configuration of OpenSSL of the tunnel, in the runtime folder."""

        return self.runtime_path(f"{self.name}.openssl.cnf")

    def prepare(self, resume: str = "") -> defer.Deferred[Prepared]:
        """
        The VDE programs, and the key of the tunnel and its configuration of
        OpenSSL written.
        """

        deferred = bricks.Brick.prepare(self, resume)

        def written(prepared: Prepared) -> Prepared:
            write_key(self.key_path(), self.config.password)
            write_openssl_config(self.openssl_path())
            return prepared

        return deferred.addCallback(written)

    def cryptcab(self, prepared: Prepared) -> Command:
        """
        The Command of vde_cryptcab, with the key and the switch of the
        tunnel, and its configuration of OpenSSL.
        """

        cmd = Command(vde_program(prepared.vde, "vde_cryptcab"))
        cmd.env["OPENSSL_CONF"] = self.openssl_path()
        cmd.option("-P", self.key_path())
        cmd.option("-s", socket_path(self.plugs[0]))
        return cmd


class TunnelListen(Tunnel):

    type = "TunnelListen"
    summary = "The server end of an encrypted tunnel"
    config_factory = TunnelListenConfig
    config: TunnelListenConfig

    def configured(self) -> bool:
        return bool(self.plugs[0].sock)

    def command(self, prepared: Prepared) -> Command:
        cmd = self.cryptcab(prepared)
        cmd.option("-p", self.config.listen_port)
        return cmd
