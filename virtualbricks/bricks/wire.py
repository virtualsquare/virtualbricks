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

"""A wire: dpipe between two vde_plug, from a switch to another."""

from __future__ import annotations

from typing import TYPE_CHECKING

from virtualbricks import bricks
from virtualbricks.bricks.command import (
    Command,
    Prepared,
    socket_path,
    vde_program,
)
from virtualbricks.bricks.plug import Plug

if TYPE_CHECKING:  # pragma: no cover
    from virtualbricks.brickfactory import BrickFactory


class Wire(bricks.Brick):

    type = "Wire"
    summary = "A wire between two sockets"
    # dpipe joins two vde_plug
    programs: tuple[tuple[str, ...], ...] = (("dpipe",), ("vde_plug",))
    connections = "endpoints"

    def __init__(self, factory: BrickFactory, name: str) -> None:
        bricks.Brick.__init__(self, factory, name)
        self.plugs.append(Plug(self))
        self.plugs.append(Plug(self))

    def configured(self) -> bool:
        return len(self.plugs) == 2 and all(p.sock for p in self.plugs)

    def command(self, prepared: Prepared) -> Command:
        # dpipe joins two vde_plug, one in each switch
        plug = vde_program(prepared.vde, "vde_plug")
        cmd = Command(vde_program(prepared.vde, "dpipe"))
        cmd.arg(plug, socket_path(self.plugs[0]))
        cmd.arg("=", plug, socket_path(self.plugs[1]))
        return cmd
