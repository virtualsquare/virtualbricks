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
from virtualbricks.bricks.plug import Plug
from virtualbricks.config.schema import Str, define, field
from virtualbricks.i18n import _


@define
class CaptureConfig(bricks.BrickConfig):

    # the interface of the host to capture
    interface = field(Str(), default="")


class Capture(bricks.PrivilegedBrick):

    type = "Capture"
    config_factory = CaptureConfig
    connections = "connect"

    def __init__(self, factory, name):
        bricks.Brick.__init__(self, factory, name)
        self.plugs.append(Plug(self))

    def get_parameters(self):
        if self.config.interface == "":
            return _("No interface selected")
        if self.plugs[0].sock:
            return _("Interface %(interface)s plugged to %(socket)s ") % {
                "interface": self.config.interface,
                "socket": self.plugs[0].sock.brick.name,
            }
        return _("Interface %s disconnected") % self.config.interface

    def command(self, prepared):
        cmd = Command(vde_program(prepared.vde, "vde_pcapplug"))
        cmd.option("-s", socket_path(self.plugs[0]))
        cmd.arg(self.config.interface)
        return cmd

    def open_console(self):
        pass

    def configured(self):
        return self.plugs[0].sock and self.config.interface
