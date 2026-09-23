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
Dialog to choose the USB devices of a virtual machine.
"""

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gtk

from virtualbricks.gui.windows.base import _, _Dialog, destroy_on_exit


class UsbDevDialog(_Dialog):
    """
    Choose the host USB devices passed to a virtual machine.
    """

    @staticmethod
    def set_cell_id(tree_column, cell, tree_model, tree_itr, data):
        usb_dev = tree_model.get_value(tree_itr, 1)
        cell.set_property('text', usb_dev.id)
        return True

    @staticmethod
    def set_cell_description(tree_column, cell, tree_model, tree_itr, data):
        usb_dev = tree_model.get_value(tree_itr, 1)
        cell.set_property('text', usb_dev.description)
        return True

    def __init__(self, usb_devices, selected_devices):
        """
        :type usb_devices: List[virtualbricks.virtualmachines.UsbDevice]
        :type selected_devices: List[virtualbricks.virtualmachines.UsbDevice]
        """

        self._usb_devices = usb_devices
        self._selected_devices = selected_devices
        self.build_ui()
        self._tree_model = tree_model = Gtk.ListStore(bool, object)
        for device in usb_devices:
            selected = device in selected_devices
            tree_model.append((selected, device))
        self.devices_view.set_model(tree_model)
        self.selected_cell.set_radio(False)
        self.id_column.set_cell_data_func(
            self.id_cell, self.set_cell_id)
        self.description_column.set_cell_data_func(
            self.description_cell, self.set_cell_description)

    def build_ui(self) -> None:
        """Create the widgets, formerly in ``usbdev.ui``."""

        # dialog (Gtk.Dialog)
        self.dialog = Gtk.Dialog(
            width_request=320,
            height_request=260,
            can_focus=False,
            type_hint=Gdk.WindowTypeHint.DIALOG,
        )
        # TODO: empty Glade placeholder, nothing to create.
        content_area = self.dialog.get_content_area()
        content_area.set_properties(
            can_focus=False,
            orientation=Gtk.Orientation.VERTICAL,
            spacing=2,
        )
        action_area = self.dialog.get_action_area()
        action_area.set_properties(
            can_focus=False,
            layout_style=Gtk.ButtonBoxStyle.END,
        )
        cancel_button = Gtk.Button(
            label=_("Cancel"),
            visible=True,
            can_focus=True,
            receives_default=True,
        )
        self.dialog.add_action_widget(
            cancel_button,
            Gtk.ResponseType.CANCEL,
        )
        # add_action_widget() packs the button at the end and aligns it to
        # the baseline, restore the Glade packing and alignment.
        cancel_button.set_valign(Gtk.Align.FILL)
        action_area.child_set(
            cancel_button,
            pack_type=Gtk.PackType.START,
            expand=True,
            fill=True,
        )
        ok_button = Gtk.Button(
            label=_("OK"),
            visible=True,
            can_focus=True,
            can_default=True,
            receives_default=True,
        )
        self.dialog.add_action_widget(ok_button, Gtk.ResponseType.OK)
        ok_button.set_valign(Gtk.Align.FILL)
        action_area.child_set(
            ok_button,
            pack_type=Gtk.PackType.START,
            expand=True,
            fill=True,
        )
        content_area.child_set(action_area, expand=False, fill=False)
        box1 = Gtk.Box(
            visible=True,
            can_focus=False,
            orientation=Gtk.Orientation.VERTICAL,
        )
        label1 = Gtk.Label(
            visible=True,
            can_focus=False,
            margin_top=5,
            margin_bottom=5,
            label=_("Select USB devices"),
        )
        box1.pack_start(label1, False, True, 0)
        scrolled_window1 = Gtk.ScrolledWindow(
            visible=True,
            can_focus=True,
            shadow_type=Gtk.ShadowType.IN,
        )
        self.devices_view = Gtk.TreeView(visible=True, can_focus=True)
        selected_tree_view_column = Gtk.TreeViewColumn.new()
        self.selected_cell = Gtk.CellRendererToggle()
        selected_tree_view_column.pack_start(
            self.selected_cell,
            False,
        )
        selected_tree_view_column.add_attribute(
            self.selected_cell,
            "active",
            0,
        )
        self.devices_view.append_column(selected_tree_view_column)
        self.id_column = Gtk.TreeViewColumn.new()
        self.id_column.set_properties(title=_("ID"))
        self.id_cell = Gtk.CellRendererText()
        self.id_column.pack_start(self.id_cell, False)
        self.devices_view.append_column(self.id_column)
        self.description_column = Gtk.TreeViewColumn.new()
        self.description_column.set_properties(title=_("Name"))
        self.description_cell = Gtk.CellRendererText()
        self.description_column.pack_start(
            self.description_cell,
            False,
        )
        self.devices_view.append_column(self.description_column)
        scrolled_window1.add(self.devices_view)
        box1.pack_start(scrolled_window1, True, True, 0)
        content_area.pack_start(box1, True, True, 0)

        # Need the complete widget tree:
        # default and focus widgets.
        ok_button.grab_default()

        # Signals
        self.dialog.connect("response", self.on_dialog_response)
        self.selected_cell.connect(
            "toggled",
            self.on_selected_cell_toggled,
        )

    def get_root_widget(self) -> Gtk.Dialog:
        return self.dialog

    def on_selected_cell_toggled(self, cell_renderer, path):
        """
        :type cell_renderer: Gtk.CellRendererToggle
        :type path: Gtk.TreePath
        """

        tree_iter = self._tree_model.get_iter(path)
        selected = self._tree_model.get_value(tree_iter, 0)
        self._tree_model.set_value(tree_iter, 0, not selected)
        return True

    @destroy_on_exit
    def on_dialog_response(self, dialog, response_id):
        if response_id == Gtk.ResponseType.OK:
            new_selected_devices = [
                device for selected, device in self._tree_model if selected
            ]
            self._selected_devices[:] = new_selected_devices
        return True
