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

from collections import OrderedDict as odict

from virtualbricks import bricks
from virtualbricks.bricks.plug import Plug
from virtualbricks.config import Str, define, field
from virtualbricks.i18n import _
from virtualbricks.spawn import abspath_vde


@define
class CaptureConfig(bricks.BrickConfig):

    iface = field(Str(), default="")


class Capture(bricks.PrivilegedBrick):

    type = "Capture"
    config_factory = CaptureConfig
    connections = "connect"

    def __init__(self, factory, name):
        bricks.Brick.__init__(self, factory, name)
        self.plugs.append(Plug(self))
        self.command_builder = odict(
            (("-s", self.sock_path), ("*iface", "iface"))
        )

    def sock_path(self):
        if self.plugs[0].sock:
            return self.plugs[0].sock.path.rstrip("[]")
        return ""

    def get_parameters(self):
        if self.config.iface == "":
            return _("No interface selected")
        if self.plugs[0].sock:
            return _("Interface %(interface)s plugged to %(socket)s ") % {
                "interface": self.config.iface,
                "socket": self.plugs[0].sock.brick.name,
            }
        return _("Interface %s disconnected") % self.config.iface

    def prog(self):
        return abspath_vde("vde_pcapplug")

    def open_console(self):
        pass

    def configured(self):
        return self.plugs[0].sock and self.config.iface
