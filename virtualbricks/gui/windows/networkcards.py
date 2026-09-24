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
Old list of the network cards of a virtual machine.

No class uses ``networkcards.ui``: the network cards are in
``qemuconfig.ui`` (``QemuConfigController``). Only the UI is converted.
"""

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gtk

from virtualbricks.gui.windows.base import _, _Window


class NetworkCards(_Window):
    """
    List of the network cards of a virtual machine with the button to add a new
    one.

    No class used this UI, the signal handlers are stubs.
    """

    def __init__(self):
        self.build_ui()

    def build_ui(self) -> None:
        """Create the widgets, formerly in ``networkcards.ui``."""

        # liststore1 (Gtk.ListStore)
        liststore1 = Gtk.ListStore(object)

        # window (Gtk.Window)
        self.window = Gtk.Window(can_focus=False)
        network_cards_view = Gtk.TreeView(
            visible=True,
            can_focus=True,
            model=liststore1,
        )
        vlan_treeviewcolumn = Gtk.TreeViewColumn.new()
        vlan_treeviewcolumn.set_properties(
            title=_("Eth"),
            reorderable=True,
            sort_column_id=0,
        )
        vlan_cellrenderer = Gtk.CellRendererText()
        vlan_treeviewcolumn.pack_start(vlan_cellrenderer, False)
        network_cards_view.append_column(vlan_treeviewcolumn)
        connection_treeviewcolumn = Gtk.TreeViewColumn.new()
        connection_treeviewcolumn.set_properties(
            title=_("Connection"),
            reorderable=True,
            sort_column_id=1,
        )
        connection_cellrenderer = Gtk.CellRendererText()
        connection_treeviewcolumn.pack_start(
            connection_cellrenderer,
            False,
        )
        network_cards_view.append_column(
            connection_treeviewcolumn,
        )
        model_treeviewcolumn = Gtk.TreeViewColumn.new()
        model_treeviewcolumn.set_properties(
            title=_("Model"),
            reorderable=True,
            sort_column_id=2,
        )
        model_cellrenderer = Gtk.CellRendererText()
        model_treeviewcolumn.pack_start(model_cellrenderer, False)
        network_cards_view.append_column(model_treeviewcolumn)
        mac_treeviewcolumn = Gtk.TreeViewColumn.new()
        mac_treeviewcolumn.set_properties(
            title=_("MAC address"),
            reorderable=True,
            sort_column_id=3,
        )
        mac_cellrenderer = Gtk.CellRendererText()
        mac_treeviewcolumn.pack_start(mac_cellrenderer, False)
        network_cards_view.append_column(mac_treeviewcolumn)
        self.window.add(network_cards_view)

        # Signals
        network_cards_view.connect(
            "button-release-event",
            self.on_network_cards_view_button_release_event,
        )
        network_cards_view.connect(
            "key-press-event",
            self.on_network_cards_view_key_press_event,
        )

    def get_root_widget(self) -> Gtk.Window:
        return self.window

    def on_network_cards_view_button_release_event(
        self,
        tree_view: Gtk.TreeView,
        event: Gdk.Event,
        data=None,
    ) -> bool:
        """
        Handler of the "button-release-event" signal of GtkTreeView.

        TODO: no handler in the original class, Gtk.Builder left this signal
        unconnected.
        """

        return False

    def on_network_cards_view_key_press_event(
        self,
        tree_view: Gtk.TreeView,
        event: Gdk.Event,
        data=None,
    ) -> bool:
        """
        Handler of the "key-press-event" signal of GtkTreeView.

        TODO: no handler in the original class, Gtk.Builder left this signal
        unconnected.
        """

        return False
