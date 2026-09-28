# -*- test-case-name: virtualbricks.tests.bricks.test_switch -*-
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

"""A switch: vde_switch."""

from virtualbricks import bricks
from virtualbricks.bricks.command import Command, vde_program
from virtualbricks.bricks.draft import Draft, Problem
from virtualbricks.config.schema import Bool, Int, define, field
from virtualbricks.i18n import N_, _, ngettext


@define
class SwitchConfig(bricks.BrickConfig):

    ports = field(
        Int(1, 128),
        default=32,
        label=N_("Ports"),
        help=N_("Number of ports"),
    )
    hub_mode = field(
        Bool(),
        default=False,
        label=N_("Hub mode"),
        help=N_("Send every packet to every port, as a hub"),
    )
    fast_spanning_tree = field(
        Bool(),
        default=False,
        label=N_("Fast spanning tree"),
        help=N_("Run the fast spanning tree protocol"),
    )


class SwitchDraft(Draft):
    """The settings of a switch: it needs a port for each plug in it."""

    def plugged(self) -> list:
        """The bricks plugged into the switch, once each, in their order."""

        bricks = []
        for plug in self.brick.socks[0].plugs:
            if plug.brick not in bricks:
                bricks.append(plug.brick)
        return bricks

    def needed(self) -> int:
        return len(self.brick.socks[0].plugs)

    def limits(self, name):
        low, high = super().limits(name)
        if name == "ports":
            low = max(low, self.needed())
        return low, high

    def note(self, name):
        needed = self.needed()
        if name != "ports" or not needed:
            return ""
        names = ", ".join(brick.name for brick in self.plugged())
        return ngettext(
            "at least {count}: {names} plugs into {switch}",
            "at least {count}: {names} plug into {switch}",
            len(self.plugged()),
        ).format(count=needed, names=names, switch=self.brick.name)

    def check(self):
        needed = self.needed()
        if self.settings.ports >= needed:
            return super().check()
        text = _("{switch} needs {count} ports, one for each plug").format(
            switch=self.brick.name, count=needed
        )
        return [Problem("ports", text)] + super().check()


class Switch(bricks.Brick):

    type = "Switch"
    summary = "A VDE switch"
    ports_used = 0
    config_factory = SwitchConfig
    draft_factory = SwitchDraft

    def set_name(self, name):
        self._name = name
        for so in self.socks:
            so.nickname = name + "_port"
            so.path = self.path()
        self.notify_changed()

    name = property(bricks.Brick.get_name, set_name)

    def __init__(self, factory, name):
        bricks.Brick.__init__(self, factory, name)
        sock = factory.new_sock(self, self.name + "_port")
        sock.path = self.path()
        self.socks.append(sock)

    def get_parameters(self):
        fstp = ""
        hub = ""
        if self.config.fast_spanning_tree:
            fstp = ", FSTP"
        if self.config.hub_mode:
            hub = ", HUB"
        return _("Ports: ") + "%d%s%s" % (self.config.ports, fstp, hub)

    def command(self, prepared):
        config = self.config
        cmd = Command(vde_program(prepared.vde, "vde_switch"))
        cmd.flag("-x", config.hub_mode)
        cmd.option("-n", config.ports)
        cmd.flag("-F", config.fast_spanning_tree)
        cmd.option("-s", self.path())
        cmd.option("-M", self.console())
        return cmd

    def configured(self):
        return self.socks[0].has_valid_path()

    # what a running switch takes at once, by the name of the setting
    def cbset_fast_spanning_tree(self, arg=False):
        self.send(b"fstp/setfstp %d\n" % bool(arg))

    def cbset_hub_mode(self, arg=False):
        self.send(b"port/sethub %d\n" % bool(arg))

    def cbset_ports(self, arg=32):
        self.send(b"port/setnumports %d\n" % arg)
