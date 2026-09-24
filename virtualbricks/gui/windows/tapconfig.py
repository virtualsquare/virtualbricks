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
Configuration panel of the Tap brick.
"""

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

from virtualbricks.gui.windows.base import _, _PlugMixin, ConfigController


class TapConfigController(_PlugMixin, ConfigController):
    """
    Configuration panel of the Tap brick: the sock to connect to and the IP
    configuration (none, DHCP or manual).
    """

    def build_ui(self) -> None:
        """Create the widgets, formerly in ``tapconfig.ui``."""

        # panel (Gtk.Grid)
        self.panel = Gtk.Grid(
            visible=True,
            can_focus=False,
            row_spacing=2,
            column_spacing=6,
        )
        self.nocfg_radio = Gtk.RadioButton(
            label=_("Don't touch interface settings"),
            visible=True,
            can_focus=True,
            receives_default=False,
            xalign=0.5,
            draw_indicator=True,
        )
        self.panel.attach(self.nocfg_radio, 0, 1, 1, 1)
        self.dhcp_radio = Gtk.RadioButton(
            label=_("Use DHCP"),
            visible=True,
            can_focus=True,
            receives_default=False,
            xalign=0.5,
            draw_indicator=True,
        )
        self.panel.attach(self.dhcp_radio, 0, 2, 1, 1)
        self.manual_radio = Gtk.RadioButton(
            label=_("Manual settings"),
            visible=True,
            can_focus=True,
            receives_default=False,
            xalign=0.5,
            active=True,
            draw_indicator=True,
        )
        self.panel.attach(self.manual_radio, 0, 3, 1, 1)
        hbox1 = Gtk.Box(visible=True, can_focus=False, spacing=12)
        label2 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("Connect to:"),
            xalign=0,
        )
        hbox1.pack_start(label2, False, True, 0)
        self.sock_combo = Gtk.ComboBox(visible=True, can_focus=False)
        renderer1 = Gtk.CellRendererText()
        self.sock_combo.pack_start(renderer1, False)
        hbox1.pack_start(self.sock_combo, True, True, 0)
        self.panel.attach(hbox1, 0, 0, 2, 1)
        hbox2 = Gtk.Box(
            visible=True,
            can_focus=False,
            orientation=Gtk.Orientation.VERTICAL,
        )
        self.ipconfig_grid = Gtk.Grid(visible=True, can_focus=False)
        label3 = Gtk.Label(
            visible=True,
            can_focus=False,
            xpad=6,
            label=_("IP Address:"),
            xalign=1,
        )
        self.ipconfig_grid.attach(label3, 0, 0, 1, 1)
        self.ip_entry = Gtk.Entry(
            visible=True,
            can_focus=True,
            max_length=16,
            invisible_char=ord("●"),
            width_chars=16,
            text=_("10.0.0.1"),
            primary_icon_activatable=False,
            secondary_icon_activatable=False,
        )
        self.ipconfig_grid.attach(self.ip_entry, 1, 0, 1, 1)
        label4 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("Netmask:"),
            xalign=1,
        )
        self.ipconfig_grid.attach(label4, 0, 1, 1, 1)
        self.nm_entry = Gtk.Entry(
            visible=True,
            can_focus=True,
            max_length=16,
            invisible_char=ord("●"),
            width_chars=16,
            text=_("255.0.0.0"),
            primary_icon_activatable=False,
            secondary_icon_activatable=False,
        )
        self.ipconfig_grid.attach(self.nm_entry, 1, 1, 1, 1)
        label5 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("Gateway:"),
            xalign=1,
        )
        self.ipconfig_grid.attach(label5, 0, 2, 1, 1)
        self.gw_entry = Gtk.Entry(
            visible=True,
            can_focus=True,
            max_length=16,
            invisible_char=ord("●"),
            width_chars=16,
            primary_icon_activatable=False,
            secondary_icon_activatable=False,
        )
        self.ipconfig_grid.attach(self.gw_entry, 1, 2, 1, 1)
        hbox2.pack_start(self.ipconfig_grid, False, True, 0)
        self.panel.attach(hbox2, 1, 1, 1, 3)

        # Need the complete widget tree:
        # references to objects created later (radio groups).
        self.nocfg_radio.join_group(self.manual_radio)
        self.dhcp_radio.join_group(self.manual_radio)

        # Signals
        self.manual_radio.connect(
            "toggled",
            self.on_manual_radio_toggled,
        )

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

        self.ip_entry.set_text(self.original.get("ip"))
        self.nm_entry.set_text(self.original.get("nm"))
        self.gw_entry.set_text(self.original.get("gw"))
        # default to manual if not valid mode is set
        if self.original.get("mode") == "off":
            self.nocfg_radio.set_active(True)
        elif self.original.get("mode") == "dhcp":
            self.dhcp_radio.set_active(True)
        else:
            self.manual_radio.set_active(True)

        self.ipconfig_grid.set_sensitive(self.original.get("mode") == "manual")

        return self.panel

    def configure_brick(self, gui):
        if self.nocfg_radio.get_active():
            self.original.set({"mode": "off"})
        elif self.dhcp_radio.get_active():
            self.original.set({"mode": "dhcp"})
        else:
            self.original.set(
                {
                    "mode": "manual",
                    "ip": self.ip_entry.get_text(),
                    "nm": self.nm_entry.get_text(),
                    "gw": self.gw_entry.get_text(),
                }
            )
        self.connect_plug(self.original.plugs[0], self.sock_combo)

    def on_manual_radio_toggled(self, radiobtn):
        self.ipconfig_grid.set_sensitive(radiobtn.get_active())
