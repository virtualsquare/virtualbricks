# -*- test-case-name: virtualbricks.tests.bricks.test_capture -*-
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

"""A capture: vde_pcapplug, a host interface plugged to a switch."""

from virtualbricks import bricks
from virtualbricks.bricks.command import Command, socket_path, vde_program
from virtualbricks.bricks.draft import Draft, Problem
from virtualbricks.bricks.plug import Plug
from virtualbricks.config.schema import Str, define, field
from virtualbricks.i18n import N_, _

NET_DEV = "/proc/net/dev"


@define
class CaptureConfig(bricks.BrickConfig):

    # the interface of the host to capture
    interface = field(
        Str(),
        default="",
        label=N_("Interface"),
        help=N_("The interface of the host to capture, as eth0"),
    )


def host_interfaces() -> list[str]:
    """The network interfaces of the host, but the loopback."""

    try:
        with open(NET_DEV) as fp:
            lines = fp.readlines()
    except OSError:
        return []
    # two lines of header, then "  eth0: 1234 ..."
    names = [line.split(":", 1)[0].strip() for line in lines[2:]]
    return [name for name in names if name and name != "lo"]


class CaptureDraft(Draft):
    """The settings of a capture, with the interfaces of the host."""

    def __init__(self, brick):
        super().__init__(brick)
        self.interfaces = host_interfaces()

    def check(self):
        interface = self.settings.interface
        if not interface:
            text = _("Without an interface, {brick} can't start")
        elif interface not in self.interfaces:
            text = _("{interface} isn't an interface of this host")
        else:
            return super().check()
        text = text.format(brick=self.brick.name, interface=interface)
        return [Problem("interface", text, error=False)] + super().check()


class Capture(bricks.PrivilegedBrick):

    type = "Capture"
    summary = "An interface of the host, whose packets go to a switch"
    config_factory = CaptureConfig
    draft_factory = CaptureDraft
    connections = "connect"

    def __init__(self, factory, name):
        bricks.Brick.__init__(self, factory, name)
        self.plugs.append(Plug(self))

    def command(self, prepared):
        cmd = Command(vde_program(prepared.vde, "vde_pcapplug"))
        cmd.option("-s", socket_path(self.plugs[0]))
        cmd.arg(self.config.interface)
        return cmd

    def open_console(self):
        pass

    def configured(self):
        return self.plugs[0].sock and self.config.interface
