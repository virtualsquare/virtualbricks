# -*- test-case-name: virtualbricks.tests.bricks.test_tunnelconnect -*-
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

from __future__ import annotations

from virtualbricks.bricks.command import Command, Prepared
from virtualbricks.bricks.draft import Draft, Problem
from virtualbricks.bricks.tunnellisten import Tunnel, TunnelConfig
from virtualbricks.config.schema import Int, Str, define, field
from virtualbricks.i18n import N_, _


@define
class TunnelConnectConfig(TunnelConfig):

    # the host that runs the server end, and its port
    server_host: str = field(
        Str(),
        default="",
        label=N_("Server"),
        help=N_("The host that runs the server end"),
    )
    server_port: int = field(
        Int(1, 65535),
        default=7667,
        label=N_("Server port"),
        help=N_("The UDP port of the server end"),
    )
    local_port: int = field(
        Int(1, 65535),
        default=10771,
        label=N_("Local port"),
        help=N_("The local UDP port"),
    )


class TunnelConnectDraft(Draft):
    """The settings of a tunnel client, which needs its server."""

    def check(self) -> list[Problem]:
        problems = super().check()
        if not self.settings.server_host.strip():
            text = _("Without a server, {brick} can't start").format(
                brick=self.brick.name
            )
            problems.insert(0, Problem("server_host", text, error=False))
        return problems


class TunnelConnect(Tunnel):

    type = "TunnelConnect"
    summary = "The client end of an encrypted tunnel"
    config_factory = TunnelConnectConfig
    config: TunnelConnectConfig
    draft_factory = TunnelConnectDraft

    def configured(self) -> bool:
        return self.plugs[0].sock is not None and bool(self.config.server_host)

    def command(self, prepared: Prepared) -> Command:
        config = self.config
        cmd = self.cryptcab(prepared)
        cmd.option("-p", config.local_port)
        cmd.option("-c", f"{config.server_host}:{config.server_port}")
        return cmd
