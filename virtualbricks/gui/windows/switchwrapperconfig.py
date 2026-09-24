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
Configuration panel of the SwitchWrapper brick.
"""

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

from virtualbricks.gui.windows.base import _, ConfigController


class SwitchWrapperConfigController(ConfigController):
    """
    Configuration panel of the SwitchWrapper brick: the path of the existing
    switch.
    """

    def build_ui(self) -> None:
        """Create the widgets, formerly in ``switchwrapperconfig.ui``."""

        # panel (Gtk.Grid)
        self.panel = Gtk.Grid(visible=True, can_focus=False, column_spacing=6)
        label1 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("Path to switch:"),
            xalign=0,
        )
        self.panel.attach(label1, 0, 0, 1, 1)
        self.path_entry = Gtk.Entry(
            visible=True,
            can_focus=True,
            invisible_char=ord("●"),
            primary_icon_activatable=False,
            secondary_icon_activatable=False,
        )
        self.panel.attach(self.path_entry, 1, 0, 1, 1)

    def get_root_widget(self) -> Gtk.Grid:
        return self.panel

    def get_config_view(self, gui):
        self.path_entry.set_text(self.original.get("path"))
        return self.panel

    def configure_brick(self, gui):
        self.original.set({"path": self.path_entry.get_text()})
