# -*- test-case-name: virtualbricks.tests.bricks.test_tap -*-
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

"""A tap: vde_plug2tap, a tap interface of the host plugged to a switch."""

from virtualbricks import bricks
from virtualbricks.bricks.command import Command, socket_path, vde_program
from virtualbricks.bricks.draft import Draft
from virtualbricks.bricks.plug import Plug
from virtualbricks.config.schema import Choice, IPv4, define, field
from virtualbricks.i18n import N_, _


@define
class TapConfig(bricks.BrickConfig):

    address_mode = field(
        Choice("off", "dhcp", "manual"),
        default="off",
        label=N_("Address"),
        help=N_("How the interface gets its address"),
    )
    ip_address = field(
        IPv4(),
        default="10.0.0.1",
        label=N_("IP address"),
        help=N_("The address of the interface, when it's set by hand"),
    )
    netmask = field(
        IPv4(),
        default="255.255.255.0",
        label=N_("Netmask"),
        help=N_("The netmask, when the address is set by hand"),
    )
    gateway = field(
        IPv4(optional=True),
        default="",
        label=N_("Gateway"),
        help=N_("The default gateway; empty for none"),
    )


class TapDraft(Draft):
    """The settings of a tap: its addresses, when they are set by hand."""

    WITH = {
        "ip_address": ("address_mode", "manual"),
        "netmask": ("address_mode", "manual"),
        "gateway": ("address_mode", "manual"),
    }

    def note(self, name):
        if name == "address_mode" and self.settings.address_mode != "off":
            # the TODO has it
            return _("Virtualbricks doesn't set it yet")
        return ""


class Tap(bricks.PrivilegedBrick):

    type = "Tap"
    summary = "A tap interface of the host, plugged into a switch"
    config_factory = TapConfig
    draft_factory = TapDraft
    connections = "connect"

    def __init__(self, factory, name):
        bricks.Brick.__init__(self, factory, name)
        self.plugs.append(Plug(self))

    def command(self, prepared):
        cmd = Command(vde_program(prepared.vde, "vde_plug2tap"))
        cmd.option("-s", socket_path(self.plugs[0]))
        # the interface of the host has the name of the brick
        cmd.arg(self.name)
        return cmd

    def open_console(self):
        pass

    def configured(self):
        return bool(self.plugs[0].sock)
