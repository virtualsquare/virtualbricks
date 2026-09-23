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
Dialog to save the current project with a new name.
"""

from pathlib import Path

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gtk

from virtualbricks import settings
from virtualbricks.project import manager as project_manager
from virtualbricks.gui.windows.base import _, _Dialog


class SaveProjectAsDialog(_Dialog):
    """
    Save the current project with a new name; the list shows the existing
    projects.
    """

    def __init__(self, brickfactory):
        self._brickfactory = brickfactory
        self.build_ui()
        model = self.projects_store
        for project in project_manager:
            model.append([project.name])

    def build_ui(self) -> None:
        """Create the widgets, formerly in ``saveprojectasdialog.ui``."""

        # projects_store (Gtk.ListStore)
        self.projects_store = Gtk.ListStore(str)

        # dialog (Gtk.Dialog)
        self.dialog = Gtk.Dialog(
            can_focus=False,
            modal=True,
            window_position=Gtk.WindowPosition.CENTER_ON_PARENT,
            default_width=350,
            default_height=300,
            destroy_with_parent=True,
            type_hint=Gdk.WindowTypeHint.DIALOG,
            skip_taskbar_hint=True,
            skip_pager_hint=True,
        )
        # TODO: empty Glade placeholder, nothing to create.
        content_area = self.dialog.get_content_area()
        content_area.set_properties(
            visible=True,
            can_focus=False,
            orientation=Gtk.Orientation.VERTICAL,
            spacing=2,
        )
        action_area = self.dialog.get_action_area()
        action_area.set_properties(
            visible=True,
            can_focus=False,
            layout_style=Gtk.ButtonBoxStyle.END,
        )
        cancel_button = Gtk.Button(
            label="Cancel",
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
            expand=False,
            fill=False,
        )
        self.ok_button = Gtk.Button(
            label="OK",
            visible=True,
            sensitive=False,
            can_focus=True,
            can_default=True,
            receives_default=True,
        )
        self.dialog.add_action_widget(
            self.ok_button,
            Gtk.ResponseType.OK,
        )
        self.ok_button.set_valign(Gtk.Align.FILL)
        action_area.child_set(
            self.ok_button,
            pack_type=Gtk.PackType.START,
            expand=False,
            fill=False,
        )
        content_area.child_set(
            action_area,
            expand=False,
            fill=True,
            pack_type=Gtk.PackType.END,
        )
        label1 = Gtk.Label(
            visible=True,
            can_focus=False,
            margin_left=1,
            margin_top=6,
            label=_("Existing projects:"),
            xalign=0,
        )
        content_area.pack_start(label1, False, True, 0)
        scrolled_window1 = Gtk.ScrolledWindow(visible=True, can_focus=True)
        tree_view1 = Gtk.TreeView(
            visible=True,
            can_focus=True,
            model=self.projects_store,
            headers_visible=False,
            headers_clickable=False,
            search_column=0,
        )
        tree_view_column1 = Gtk.TreeViewColumn.new()
        tree_view_column1.set_properties(title=_("column"))
        cell_renderer_text1 = Gtk.CellRendererText()
        tree_view_column1.pack_start(cell_renderer_text1, False)
        tree_view_column1.add_attribute(cell_renderer_text1, "text", 0)
        tree_view1.append_column(tree_view_column1)
        scrolled_window1.add(tree_view1)
        content_area.pack_start(scrolled_window1, True, True, 0)
        box1 = Gtk.Box(visible=True, can_focus=False, spacing=6)
        label2 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("New project name:"),
        )
        box1.pack_start(label2, False, True, 0)
        self.project_name_entry = Gtk.Entry(
            visible=True,
            can_focus=True,
            invisible_char=ord("●"),
            activates_default=True,
            primary_icon_activatable=False,
            secondary_icon_activatable=False,
        )
        box1.pack_start(self.project_name_entry, True, True, 0)
        content_area.pack_start(box1, False, True, 0)

        # Need the complete widget tree:
        # default and focus widgets.
        self.ok_button.grab_default()
        self.project_name_entry.grab_focus()

        # Signals
        self.dialog.connect(
            "response",
            self.on_dialog_response,
        )
        self.project_name_entry.connect(
            "changed",
            self.on_project_name_entry_changed,
        )

    def get_root_widget(self) -> Gtk.Dialog:
        return self.dialog

    def _set_error(self, tooltip):
        """
        :type tooltip: str
        :rtype: None
        """

        style_context = self.project_name_entry.get_style_context()
        style_context.add_class('error')
        self.project_name_entry.set_tooltip_markup(tooltip)
        self.ok_button.set_sensitive(False)

    def _reset_error(self):
        """
        :rtype: None
        """

        style_context = self.project_name_entry.get_style_context()
        style_context.remove_class('error')
        self.project_name_entry.set_tooltip_text(None)
        self.ok_button.set_sensitive(True)

    def on_project_name_entry_changed(self, entry):
        new_project_name = entry.get_text()
        if not new_project_name:
            self._reset_error()
            self.ok_button.set_sensitive(False)
            return
        elif new_project_name == project_manager.current.name:
            self._set_error(_('New project name is the same as previous name'))
            return
        try:
            Path(new_project_name).relative_to(settings.DEFAULT_HOME)
        except ValueError:
            # TODO: explain why name is invalid
            self._set_error(_('Invalid project name'))
        for project in project_manager:
            if new_project_name == project.name:
                tooltip = _('A project with the same name already exists')
                self._set_error(tooltip)
                break
        else:
            self._reset_error()

    def on_dialog_response(self, dialog, response_id):
        if response_id == Gtk.ResponseType.OK:
            # TODO: show progress bar
            project_manager.current.save_as(
                self.project_name_entry.get_text(),
                self._brickfactory
            )
        dialog.destroy()
