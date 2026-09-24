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
Dialogs that ask for a single value.
"""

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gtk

from virtualbricks.project import manager as project_manager
from virtualbricks.gui.windows.base import _, destroy_on_exit, Window


class SimpleEntryDialog(Window):
    """
    Ask for a single value: the subclasses set the description and implement
    ``do_action()``.
    """

    description = ""

    def __init__(self, gui):
        Window.__init__(self)
        self.gui = gui
        self.description_label.set_text(self.description)

    def build_ui(self) -> None:
        """Create the widgets, formerly in ``simpleentry.ui``."""

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
            spacing=12,
        )
        dialog_action_area1 = self.dialog.get_action_area()
        dialog_action_area1.set_properties(
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
        dialog_action_area1.child_set(
            button2,
            pack_type=Gtk.PackType.START,
            expand=False,
            fill=False,
        )
        button1 = Gtk.Button(
            label="gtk-ok",
            visible=True,
            can_focus=True,
            receives_default=True,
            use_stock=True,
        )
        self.dialog.add_action_widget(
            button1,
            Gtk.ResponseType.OK,
        )
        button1.set_valign(Gtk.Align.FILL)
        dialog_action_area1.child_set(
            button1,
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
        self.description_label = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("Project name"),
        )
        dialog_vbox1.pack_start(self.description_label, False, True, 0)
        self.name_entry = Gtk.Entry(
            visible=True,
            can_focus=True,
            primary_icon_activatable=False,
            secondary_icon_activatable=False,
        )
        dialog_vbox1.pack_start(self.name_entry, False, True, 0)

        # Signals
        self.dialog.connect(
            "response",
            self.on_dialog_response,
        )

    def get_root_widget(self) -> Gtk.Dialog:
        return self.dialog

    @destroy_on_exit
    def on_dialog_response(self, dialog, response_id):
        if response_id == Gtk.ResponseType.OK:
            self.do_action(self.name_entry.get_text())


class NewProjectDialog(SimpleEntryDialog):
    """
    Ask the name of a new project.
    """

    @property
    def description(self):
        return _("Project name")

    def do_action(self, name):
        self.gui.on_new(name)


class RenameProjectDialog(SimpleEntryDialog):
    """
    Ask the new name of the current project.
    """

    @property
    def description(self):
        return _("New project name")

    def do_action(self, name):
        project_manager.current.rename(name)
