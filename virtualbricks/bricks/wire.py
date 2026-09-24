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

"""A wire: dpipe between two vde_plug, from a switch to another."""

from virtualbricks import bricks
from virtualbricks.i18n import _
from virtualbricks.spawn import abspath_vde


class Wire(bricks.Brick):

    type = "Wire"
    connections = "endpoints"

    def __init__(self, factory, name):
        bricks.Brick.__init__(self, factory, name)
        self.plugs.append(factory.new_plug(self))
        self.plugs.append(factory.new_plug(self))

    def get_parameters(self):
        p0 = _("disconnected")
        p1 = _("disconnected")
        if len(self.plugs) == 2:
            if self.plugs[0].sock:
                p0 = self.plugs[0].sock.brick.name
            if self.plugs[1].sock:
                p1 = self.plugs[1].sock.brick.name
            if p0 != _("disconnected") and p1 != _("disconnected"):
                return _("Configured to connect {0} to {1}").format(p0, p1)
        elif len(self.plugs) == 1:
            if self.plugs[0].sock:
                p0 = self.plugs[0].sock.brick.name
            return _("Configured to connect {0} to {1}").format(p0, p1)
        return _(
            "Not yet configured. Left plug is {0} and right plug is {1}"
        ).format(p0, p1)

    def configured(self):
        return len(self.plugs) == 2 and all(map(lambda p: p.sock, self.plugs))

    def prog(self):
        return (abspath_vde("dpipe"),)

    def args(self):
        return [
            self.prog(),
            abspath_vde("vde_plug"),
            # XXX: this is awful
            self.plugs[0].sock.path.rstrip("[]"),
            "=",
            abspath_vde("vde_plug"),
            self.plugs[1].sock.path.rstrip("[]"),
        ]
