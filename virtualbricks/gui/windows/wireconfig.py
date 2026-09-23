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
Configuration panel of the Wire brick.
"""

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

from virtualbricks.gui.windows.base import _, _PlugMixin, ConfigController


class WireConfigController(_PlugMixin, ConfigController):
    """
    Configuration panel of the Wire brick: the socks connected by the wire.
    """

    def build_ui(self) -> None:
        """Create the widgets, formerly in ``wireconfig.ui``."""

        # panel (Gtk.Box)
        self.panel = Gtk.Box(
            visible=True,
            can_focus=False,
            orientation=Gtk.Orientation.VERTICAL,
        )
        hbox = Gtk.Box(visible=True, can_focus=False, spacing=6)
        self.sock0_combo = Gtk.ComboBox(visible=True, can_focus=False)
        sock0_cellrenderer = Gtk.CellRendererText()
        self.sock0_combo.pack_start(sock0_cellrenderer, False)
        self.sock0_combo.add_attribute(sock0_cellrenderer, "text", 0)
        hbox.pack_start(self.sock0_combo, False, False, 0)
        label1 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("<=== connect ===>"),
        )
        hbox.pack_start(label1, False, True, 0)
        self.sock1_combo = Gtk.ComboBox(visible=True, can_focus=False)
        sock1_cellrenderer = Gtk.CellRendererText()
        self.sock1_combo.pack_start(sock1_cellrenderer, False)
        self.sock1_combo.add_attribute(sock1_cellrenderer, "text", 0)
        hbox.pack_start(self.sock1_combo, False, False, 0)
        self.panel.pack_start(hbox, False, False, 0)

    def get_root_widget(self) -> Gtk.Box:
        return self.panel

    def get_config_view(self, gui):
        for i, wname in enumerate(("sock0_combo", "sock1_combo")):
            combo = getattr(self, wname)
            self.configure_sock_combobox(
                combo,
                gui.brickfactory.socks.filter_new(),
                self.original,
                self.original.plugs[i],
                gui
            )

        return self.panel

    def configure_brick(self, gui):
        for i, wname in enumerate(("sock0_combo", "sock1_combo")):
            self.connect_plug(self.original.plugs[i], getattr(self, wname))
