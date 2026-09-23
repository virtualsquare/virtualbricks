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
Configuration panel of the Capture brick.
"""

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

from virtualbricks.gui.windows.base import _, _PlugMixin, ConfigController


class CaptureConfigController(_PlugMixin, ConfigController):
    """
    Configuration panel of the Capture brick: the sock to connect to and the
    host network interface to capture.
    """

    def build_ui(self) -> None:
        """Create the widgets, formerly in ``captureconfig.ui``."""

        # liststore1 (Gtk.ListStore)
        liststore1 = Gtk.ListStore(str)

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
            label=_("Capture interface:"),
            xalign=0,
        )
        self.panel.attach(label2, 0, 1, 1, 1)
        self.interface_combo = Gtk.ComboBox(
            visible=True,
            can_focus=False,
            model=liststore1,
        )
        cellrenderertext2 = Gtk.CellRendererText()
        self.interface_combo.pack_start(cellrenderertext2, False)
        self.interface_combo.add_attribute(cellrenderertext2, "text", 0)
        self.panel.attach(self.interface_combo, 1, 1, 1, 1)

    def get_root_widget(self) -> Gtk.Grid:
        return self.panel

    def get_config_view(self, gui):
        combo = self.sock_combo
        self.configure_sock_combobox(
            combo,
            gui.brickfactory.socks.filter_new(),
            self.original,
            self.original.plugs[0],
            gui
        )
        combo2 = self.interface_combo
        model = combo2.get_model()
        with open("/proc/net/dev") as fd:
            # skip the header
            next(fd), next(fd)
            for line in fd:
                name = line.strip().split(":")[0]
                if name != "lo":
                    itr = model.append((name, ))
                    if self.original.get("iface") == name:
                        combo2.set_active_iter(itr)

        return self.panel

    def configure_brick(self, gui):
        self.connect_plug(self.original.plugs[0], self.sock_combo)
        combo = self.interface_combo
        itr = combo.get_active_iter()
        if itr is not None:
            model = combo.get_model()
            self.original.set({"iface": model[itr][0]})

    def on_manual_radiobutton_toggled(self, radiobtn):
        self.ipconfig_table.set_sensitive(radiobtn.get_active())
