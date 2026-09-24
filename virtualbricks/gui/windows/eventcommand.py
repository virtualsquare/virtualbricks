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
Dialog to set the actions of a new event.
"""

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gtk

from virtualbricks.gui.windows.base import _, Window
from virtualbricks.gui.windows.eventconfig import EventControllerMixin


class ShellCommandDialog(Window, EventControllerMixin):
    """
    Set the actions of a new event. Each action is a Virtualbricks command or,
    when the "sh" column is checked, a shell command.
    """

    def __init__(self, event):
        Window.__init__(self)
        self.event = event
        self.setup_controller(event)

    def build_ui(self) -> None:
        """Create the widgets, formerly in ``eventcommand.ui``."""

        # actions_store (Gtk.ListStore)
        self.actions_store = Gtk.ListStore(str, bool)

        # dialog (Gtk.Dialog)
        self.dialog = Gtk.Dialog(
            can_focus=False,
            border_width=5,
            type_hint=Gdk.WindowTypeHint.DIALOG,
        )
        dialog_vbox1 = self.dialog.get_content_area()
        dialog_vbox1.set_properties(
            visible=True,
            can_focus=False,
            spacing=6,
        )
        dialog_action_area1 = self.dialog.get_action_area()
        dialog_action_area1.set_properties(
            visible=True,
            can_focus=False,
            layout_style=Gtk.ButtonBoxStyle.END,
        )
        cancel_button = Gtk.Button(
            label="gtk-cancel",
            visible=True,
            can_focus=True,
            receives_default=True,
            use_stock=True,
        )
        self.dialog.add_action_widget(
            cancel_button,
            Gtk.ResponseType.CANCEL,
        )
        # add_action_widget() packs the button at the end and aligns it to
        # the baseline, restore the Glade packing and alignment.
        cancel_button.set_valign(Gtk.Align.FILL)
        dialog_action_area1.child_set(
            cancel_button,
            pack_type=Gtk.PackType.START,
            expand=False,
            fill=False,
        )
        ok_button = Gtk.Button(
            label="gtk-ok",
            visible=True,
            can_focus=True,
            receives_default=True,
            use_stock=True,
        )
        self.dialog.add_action_widget(
            ok_button,
            Gtk.ResponseType.OK,
        )
        ok_button.set_valign(Gtk.Align.FILL)
        dialog_action_area1.child_set(
            ok_button,
            pack_type=Gtk.PackType.START,
            expand=False,
            fill=False,
        )
        dialog_vbox1.child_set(
            dialog_action_area1,
            expand=False,
            fill=True,
            pack_type=Gtk.PackType.END,
        )
        label1 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("Enter command (each line is an action)"),
            xalign=0,
        )
        dialog_vbox1.pack_start(label1, False, True, 0)
        self.actions_view = Gtk.TreeView(
            visible=True,
            can_focus=True,
            model=self.actions_store,
            headers_clickable=False,
            search_column=0,
        )
        action_treeviewcolumn = Gtk.TreeViewColumn.new()
        action_treeviewcolumn.set_properties(
            resizable=True,
            title=_("Action"),
            expand=True,
        )
        self.action_cell = Gtk.CellRendererText()
        action_treeviewcolumn.pack_start(self.action_cell, False)
        action_treeviewcolumn.add_attribute(
            self.action_cell,
            "text",
            0,
        )
        self.actions_view.append_column(action_treeviewcolumn)
        sh_treeviewcolumn = Gtk.TreeViewColumn.new()
        sh_treeviewcolumn.set_properties(
            resizable=True,
            title=_("Host shell command"),
        )
        self.shell_cell = Gtk.CellRendererToggle()
        sh_treeviewcolumn.pack_start(self.shell_cell, False)
        sh_treeviewcolumn.add_attribute(self.shell_cell, "active", 1)
        self.actions_view.append_column(sh_treeviewcolumn)
        dialog_vbox1.pack_start(self.actions_view, True, True, 0)

        # Signals
        self.dialog.connect(
            "response",
            self.on_dialog_response,
        )
        self.action_cell.connect(
            "edited",
            self.on_action_cell_edited,
        )
        self.shell_cell.connect(
            "toggled",
            self.on_shell_cell_toggled,
        )

    def get_root_widget(self) -> Gtk.Dialog:
        return self.dialog

    def on_dialog_response(self, dialog, response_id):
        if response_id == Gtk.ResponseType.OK:
            self.configure_event(self.event, {})
        dialog.destroy()
