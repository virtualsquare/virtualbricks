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

"""
Configuration panel of the Switch brick.
"""

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

from virtualbricks.gui.windows.base import _, ConfigController


class SwitchConfigController(ConfigController):
    """
    Configuration panel of the Switch brick: number of ports, FSTP and hub
    mode.
    """

    def build_ui(self) -> None:
        """Create the widgets, formerly in ``switchconfig.ui``."""

        # adjustment1 (Gtk.Adjustment)
        adjustment1 = Gtk.Adjustment(
            lower=1,
            upper=128,
            value=32,
            step_increment=1,
            page_increment=32,
        )

        # panel (Gtk.Grid)
        self.panel = Gtk.Grid(
            visible=True,
            can_focus=False,
            row_spacing=2,
            column_spacing=6,
        )
        label2 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("Number of ports:"),
        )
        self.panel.attach(label2, 0, 0, 1, 2)
        self.ports_spin = Gtk.SpinButton(
            visible=True,
            can_focus=True,
            primary_icon_activatable=False,
            secondary_icon_activatable=False,
            adjustment=adjustment1,
        )
        self.panel.attach(self.ports_spin, 1, 0, 1, 2)
        self.fstp_check = Gtk.CheckButton(
            label=_("Use FSTP"),
            visible=True,
            can_focus=True,
            receives_default=False,
            xalign=0.5,
            draw_indicator=True,
        )
        self.panel.attach(self.fstp_check, 2, 0, 1, 1)
        self.hub_check = Gtk.CheckButton(
            label=_("Hub mode"),
            visible=True,
            can_focus=True,
            receives_default=False,
            xalign=0.5,
            draw_indicator=True,
        )
        self.panel.attach(self.hub_check, 2, 1, 1, 1)

    def get_root_widget(self) -> Gtk.Grid:
        return self.panel

    def get_config_view(self, gui):
        self.fstp_check.set_active(self.original.get("fstp"))
        self.hub_check.set_active(self.original.get("hub"))
        minports = len(
            [
                1
                for b in iter(gui.brickfactory.bricks)
                for p in b.plugs
                if b.socks and p.sock.nickname == b.socks[0].nickname
            ]
        )
        spinner = self.ports_spin
        spinner.set_range(max(minports, 1), 128)
        spinner.set_value(self.original.get("numports"))
        return self.panel

    def configure_brick(self, gui):
        cfg = {
            "fstp": self.fstp_check.get_active(),
            "hub": self.hub_check.get_active(),
            "numports": self.ports_spin.get_value_as_int(),
        }
        self.original.set(cfg)
