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
Configuration panel of the TunnelConnect brick.
"""

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

from virtualbricks.gui.windows.base import _
from virtualbricks.gui.windows.tunnellconfig import (
    TunnelListenConfigController,
)


class TunnelClientConfigController(TunnelListenConfigController):
    """
    Configuration panel of the TunnelConnect brick: the sock to connect to, the
    remote host and port, the local port and the password.

    The code is shared with ``TunnelListenConfigController``, the UI is
    different.
    """

    def build_ui(self) -> None:
        """Create the widgets, formerly in ``tunnelcconfig.ui``."""

        # adjustment1 (Gtk.Adjustment)
        adjustment1 = Gtk.Adjustment(
            lower=1,
            upper=65535,
            step_increment=1,
            page_increment=10,
        )

        # adjustment2 (Gtk.Adjustment)
        adjustment2 = Gtk.Adjustment(
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
            label=_("Tunnel server host:"),
            xalign=0,
        )
        self.panel.attach(label2, 0, 1, 1, 1)
        label3 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("Local port:"),
            xalign=0,
        )
        self.panel.attach(label3, 0, 2, 1, 1)
        self.local_port_spin = Gtk.SpinButton(
            visible=True,
            can_focus=True,
            invisible_char=ord("●"),
            primary_icon_activatable=False,
            secondary_icon_activatable=False,
            adjustment=adjustment2,
        )
        self.panel.attach(self.local_port_spin, 1, 2, 1, 1)
        label4 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("Password:"),
            xalign=0,
        )
        self.panel.attach(label4, 0, 3, 1, 1)
        self.password_entry = Gtk.Entry(
            visible=True,
            can_focus=True,
            visibility=False,
            invisible_char=ord("●"),
            primary_icon_activatable=False,
            secondary_icon_activatable=False,
        )
        self.panel.attach(self.password_entry, 1, 3, 1, 1)
        hbox1 = Gtk.Box(visible=True, can_focus=False, spacing=6)
        self.host_entry = Gtk.Entry(
            visible=True,
            can_focus=True,
            invisible_char=ord("●"),
            primary_icon_activatable=False,
            secondary_icon_activatable=False,
        )
        hbox1.pack_start(self.host_entry, True, True, 0)
        label5 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("Port:"),
            xalign=0,
        )
        hbox1.pack_start(label5, True, True, 0)
        self.port_spin = Gtk.SpinButton(
            visible=True,
            can_focus=True,
            invisible_char=ord("●"),
            primary_icon_activatable=False,
            secondary_icon_activatable=False,
            adjustment=adjustment1,
        )
        hbox1.pack_start(self.port_spin, True, True, 0)
        self.panel.attach(hbox1, 1, 1, 1, 1)

    def get_root_widget(self) -> Gtk.Grid:
        return self.panel

    def get_config_view(self, gui):
        host = self.host_entry
        host.set_text(self.original.get("host"))
        localport = self.local_port_spin
        localport.set_value(self.original.get("localport"))
        return TunnelListenConfigController.get_config_view(self, gui)

    def configure_brick(self, gui):
        TunnelListenConfigController.configure_brick(self, gui)
        host = self.host_entry.get_text()
        lport = self.local_port_spin.get_value_as_int()
        self.original.set({"host": host, "localport": lport})
