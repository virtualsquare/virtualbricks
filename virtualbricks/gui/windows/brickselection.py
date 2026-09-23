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
Dialog to choose the bricks started or stopped by an event.
"""

import string

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gtk

from virtualbricks import console, log
from virtualbricks.gui import widgets
from virtualbricks.gui.windows.base import _, destroy_on_exit, Window


logger = log.Logger()

event_created = log.Event("Event created successfully")


class BrickSelectionDialog(Window):
    """
    Choose the bricks started (or stopped) by an event: the bricks are moved
    between the "available" and the "added" lists, both filtered from the same
    list of bricks.
    """

    def __init__(self, event, action, bricks):
        Window.__init__(self)
        self._event = event
        self._action = action
        self._added = set()
        self.bricks_store.set_data_source(bricks)
        self.available_filter.set_visible_func(self._is_not_added, self._added)
        self.added_filter.set_visible_func(self._is_added, self._added)
        self.available_name_cell.set_property("formatter", string.Formatter())
        self.added_name_cell.set_property("formatter", string.Formatter())
        widgets.set_cells_data_func(self.available_column)
        widgets.set_cells_data_func(self.added_column)
        self.available_filter.refilter()
        self.added_filter.refilter()

    def build_ui(self) -> None:
        """Create the widgets, formerly in ``brickselection.ui``."""

        # bricks_store (widgets.List)
        # Custom widget from glade-catalog.xml
        self.bricks_store = widgets.List()

        # added_filter (Gtk.TreeModelFilter)
        self.added_filter = Gtk.TreeModelFilter(child_model=self.bricks_store)

        # available_filter (Gtk.TreeModelFilter)
        self.available_filter = Gtk.TreeModelFilter(child_model=self.bricks_store)

        # dialog (Gtk.Dialog)
        self.dialog = Gtk.Dialog(
            width_request=800,
            height_request=400,
            can_focus=False,
            border_width=5,
            title=_("Bricks to add to the event"),
            modal=True,
            window_position=Gtk.WindowPosition.CENTER_ALWAYS,
            type_hint=Gdk.WindowTypeHint.DIALOG,
        )
        dialog_vbox1 = self.dialog.get_content_area()
        dialog_vbox1.set_properties(
            visible=True,
            can_focus=False,
            spacing=2,
        )
        dialog_action_area21 = self.dialog.get_action_area()
        dialog_action_area21.set_properties(
            visible=True,
            can_focus=False,
            layout_style=Gtk.ButtonBoxStyle.END,
        )
        button2 = Gtk.Button(
            label="gtk-cancel",
            visible=True,
            can_focus=True,
            receives_default=True,
            use_stock=True,
        )
        self.dialog.add_action_widget(
            button2,
            Gtk.ResponseType.CANCEL,
        )
        # add_action_widget() packs the button at the end and aligns it to
        # the baseline, restore the Glade packing and alignment.
        button2.set_valign(Gtk.Align.FILL)
        dialog_action_area21.child_set(
            button2,
            pack_type=Gtk.PackType.START,
            expand=False,
            fill=False,
        )
        button1 = Gtk.Button(
            label="gtk-ok",
            visible=True,
            can_focus=True,
            can_default=True,
            receives_default=True,
            use_stock=True,
        )
        self.dialog.add_action_widget(
            button1,
            Gtk.ResponseType.OK,
        )
        button1.set_valign(Gtk.Align.FILL)
        dialog_action_area21.child_set(
            button1,
            pack_type=Gtk.PackType.START,
            expand=False,
            fill=False,
        )
        dialog_vbox1.child_set(
            dialog_action_area21,
            expand=False,
            fill=True,
            pack_type=Gtk.PackType.END,
        )
        hbox1 = Gtk.Box(visible=True, can_focus=False)
        scrolledwindow1 = Gtk.ScrolledWindow(visible=True, can_focus=True)
        # Custom widget from glade-catalog.xml
        self.available_view = widgets.TreeView(
            visible=True,
            can_focus=True,
            model=self.available_filter,
        )
        self.available_column = Gtk.TreeViewColumn.new()
        self.available_column.set_properties(title=_("Availables"))
        # Custom widget from glade-catalog.xml
        cri1 = widgets.CellRendererBrickIcon()
        self.available_column.pack_start(cri1, False)
        # Custom widget from glade-catalog.xml
        self.available_name_cell = widgets.CellRendererFormattable(
            format_string="{0:n} ({0:t})",
            formatting_enabled=True,
        )
        self.available_column.pack_start(self.available_name_cell, False)
        self.available_view.append_column(self.available_column)
        scrolledwindow1.add(self.available_view)
        hbox1.pack_start(scrolledwindow1, True, True, 0)
        vbox1 = Gtk.Box(
            visible=True,
            can_focus=False,
            orientation=Gtk.Orientation.VERTICAL,
            spacing=6,
        )
        add_button = Gtk.Button(
            label="gtk-add",
            visible=True,
            can_focus=True,
            receives_default=True,
            use_stock=True,
        )
        vbox1.pack_start(add_button, True, False, 0)
        label3 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("--->\n<---"),
        )
        vbox1.pack_start(label3, False, True, 0)
        remove_button = Gtk.Button(
            label="gtk-remove",
            visible=True,
            can_focus=True,
            receives_default=True,
            use_stock=True,
        )
        vbox1.pack_start(remove_button, True, False, 0)
        hbox1.pack_start(vbox1, False, True, 0)
        scrolledwindow2 = Gtk.ScrolledWindow(visible=True, can_focus=True)
        # Custom widget from glade-catalog.xml
        self.added_view = widgets.TreeView(
            visible=True,
            can_focus=True,
            model=self.added_filter,
        )
        self.added_column = Gtk.TreeViewColumn.new()
        self.added_column.set_properties(title=_("Added"))
        # Custom widget from glade-catalog.xml
        cri2 = widgets.CellRendererBrickIcon()
        self.added_column.pack_start(cri2, False)
        # Custom widget from glade-catalog.xml
        self.added_name_cell = widgets.CellRendererFormattable(
            format_string="{0:n} ({0:t})",
            formatting_enabled=True,
        )
        self.added_column.pack_start(self.added_name_cell, False)
        self.added_view.append_column(self.added_column)
        scrolledwindow2.add(self.added_view)
        hbox1.pack_start(scrolledwindow2, True, True, 0)
        dialog_vbox1.pack_start(hbox1, True, True, 0)

        # Need the complete widget tree:
        # default and focus widgets.
        button1.grab_default()

        # Signals
        self.dialog.connect(
            "response",
            self.on_dialog_response,
        )
        self.available_view.connect("row-activated", self.on_add)
        add_button.connect("clicked", self.on_add)
        remove_button.connect("clicked", self.on_remove)
        self.added_view.connect("row-activated", self.on_remove)

    def get_root_widget(self) -> Gtk.Dialog:
        return self.dialog

    @staticmethod
    def _is_not_added(model, itr, added):
        brick = model.get_value(itr, 0)
        return brick and brick not in added

    @staticmethod
    def _is_added(model, itr, added):
        brick = model.get_value(itr, 0)
        return brick and brick in added

    def on_add(self, *_):
        for brick in self.available_view.get_selected_values():
            self._added.add(brick)
        self.available_view.get_model().refilter()
        self.added_view.get_model().refilter()
        return True

    def on_remove(self, *_):
        for brick in self.added_view.get_selected_values():
            self._added.remove(brick)
        self.available_view.get_model().refilter()
        self.added_view.get_model().refilter()
        return True

    @destroy_on_exit
    def on_dialog_response(self, dialog, response_id):
        if response_id == Gtk.ResponseType.OK:
            self._event.set({
                'actions': [
                    console.VbShellCommand(f'{brick.name} {self._action}')
                    for brick in self._added
                ]
            })
            logger.info(event_created)
