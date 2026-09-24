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
Configuration panel of the TunnelListen brick.
"""

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

from virtualbricks.gui.windows.base import _, _PlugMixin, ConfigController


class TunnelListenConfigController(_PlugMixin, ConfigController):
    """
    Configuration panel of the TunnelListen brick: the sock to connect to, the
    port and the password.
    """

    def build_ui(self) -> None:
        """Create the widgets, formerly in ``tunnellconfig.ui``."""

        # adjustment1 (Gtk.Adjustment)
        adjustment1 = Gtk.Adjustment(
            lower=1,
            upper=65535,
            value=7667,
            step_increment=1,
            page_increment=10,
        )

        # panel (Gtk.Grid)
        self.panel = Gtk.Grid(
            visible=True,
            can_focus=False,
            row_spacing=2,
            column_spacing=6,
        )
        label1 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("Connect to:"),
            xalign=0,
        )
        self.panel.attach(label1, 0, 0, 1, 1)
        self.sock_combo = Gtk.ComboBox(visible=True, can_focus=False)
        cellrenderertext1 = Gtk.CellRendererText()
        self.sock_combo.pack_start(cellrenderertext1, False)
        self.panel.attach(self.sock_combo, 1, 0, 1, 1)
        label2 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("Listen port:"),
            xalign=0,
        )
        self.panel.attach(label2, 0, 1, 1, 1)
        self.port_spin = Gtk.SpinButton(
            visible=True,
            can_focus=True,
            invisible_char=ord("●"),
            primary_icon_activatable=False,
            secondary_icon_activatable=False,
            adjustment=adjustment1,
        )
        self.panel.attach(self.port_spin, 1, 1, 1, 1)
        label4 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("Password:"),
            xalign=0,
        )
        self.panel.attach(label4, 0, 2, 1, 1)
        self.password_entry = Gtk.Entry(
            visible=True,
            can_focus=True,
            visibility=False,
            invisible_char=ord("●"),
            primary_icon_activatable=False,
            secondary_icon_activatable=False,
        )
        self.panel.attach(self.password_entry, 1, 2, 1, 1)

    def get_root_widget(self) -> Gtk.Grid:
        return self.panel

    def get_config_view(self, gui):
        combo = self.sock_combo
        self.configure_sock_combobox(
            combo,
            gui.brickfactory.socks.filter_new(),
            self.original,
            self.original.plugs[0],
            gui,
        )
        port = self.port_spin
        port.set_value(self.original.get("port"))
        password = self.password_entry
        password.set_text(self.original.get("password"))
        return self.panel

    def configure_brick(self, gui):
        self.connect_plug(self.original.plugs[0], self.sock_combo)
        port = self.port_spin.get_value_as_int()
        password = self.password_entry.get_text()
        self.original.set({"port": port, "password": password})
