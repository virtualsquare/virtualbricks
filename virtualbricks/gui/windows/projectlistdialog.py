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
Dialogs that act on a project chosen from a list.
"""

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gtk

from virtualbricks.project import manager as project_manager
from virtualbricks.gui.windows.base import _, _Dialog
from virtualbricks.gui.windows.confirmdialog import DeleteProjectConfirmDialog


class _ProjectListDialog(_Dialog):
    """
    The list of the projects, except the current one. The subclasses implement
    ``do_action()`` for the chosen project.
    """

    title = None

    def __init__(self, gui):
        self._gui = gui
        self.build_ui()
        tree_selection = self.projects_view.get_selection()
        tree_model, tree_iter = tree_selection.get_selected()
        for project in project_manager:
            if project != project_manager.current:
                tree_model.append([project.name])
        if self.title is not None:
            self.get_root_widget().set_title(self.title)
        tree_selection.unselect_all()

    def build_ui(self) -> None:
        """Create the widgets, formerly in ``projectlistdialog.ui``."""

        # projects_store (Gtk.ListStore)
        self.projects_store = Gtk.ListStore(str)

        # dialog (Gtk.Dialog)
        self.dialog = Gtk.Dialog(
            width_request=300,
            height_request=300,
            can_focus=False,
            modal=True,
            type_hint=Gdk.WindowTypeHint.DIALOG,
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
            margin_top=6,
            margin_bottom=6,
            label=_("Select project"),
        )
        content_area.pack_start(label1, False, True, 0)
        scrolled_window1 = Gtk.ScrolledWindow(visible=True, can_focus=True)
        self.projects_view = Gtk.TreeView(
            visible=True,
            can_focus=True,
            model=self.projects_store,
            headers_visible=False,
            search_column=0,
        )
        projects_selection = self.projects_view.get_selection()
        tree_view_column1 = Gtk.TreeViewColumn.new()
        tree_view_column1.set_properties(title=_("column"))
        cell_renderer_text1 = Gtk.CellRendererText()
        tree_view_column1.pack_start(cell_renderer_text1, False)
        tree_view_column1.add_attribute(cell_renderer_text1, "text", 0)
        self.projects_view.append_column(tree_view_column1)
        scrolled_window1.add(self.projects_view)
        content_area.pack_start(scrolled_window1, True, True, 0)

        # Need the complete widget tree:
        # default and focus widgets.
        cancel_button.grab_focus()
        self.ok_button.grab_default()

        # Signals
        self.dialog.connect(
            "response",
            self.on_dialog_response,
        )
        self.projects_view.connect(
            "row-activated",
            self.on_projects_view_row_activated,
        )
        projects_selection.connect(
            "changed",
            self.on_projects_selection_changed,
        )

    def get_root_widget(self) -> Gtk.Dialog:
        return self.dialog

    def do_action(self, name):
        raise NotImplementedError('_ProjectListDialog.do_action')

    def _do_action_if_selected(self, tree_selection):
        model, tree_iter = tree_selection.get_selected()
        if tree_iter:
            name = model.get_value(tree_iter, 0)
            self.do_action(name)

    def on_projects_selection_changed(self, tree_selection):
        model, tree_iter = tree_selection.get_selected()
        button_is_sensitive = tree_iter is not None
        self.ok_button.set_sensitive(button_is_sensitive)

    def on_projects_view_row_activated(self, treeview, path, column):
        model = treeview.get_model()
        tree_iter = model.get_iter(path)
        if tree_iter:
            name = model.get_value(tree_iter, 0)
            self.do_action(name)
        return True

    def on_dialog_response(self, dialog, response_id):
        if response_id == Gtk.ResponseType.OK:
            tree_selection = self.projects_view.get_selection()
            self._do_action_if_selected(tree_selection)
        dialog.destroy()
        return True


class OpenProjectDialog(_ProjectListDialog):
    """
    Open a project.
    """

    @property
    def title(self):
        return _('Virtualbricks - Open project')

    def do_action(self, name):
        self._gui.on_open(name)
        self._gui.set_title()
        self.get_root_widget().destroy()


class DeleteProjectDialog(_ProjectListDialog):
    """
    Delete a project.
    """

    @property
    def title(self):
        return _('Virtualbricks - Delete project')

    def do_action(self, name):
        tree_model = self.projects_store
        dialog = DeleteProjectConfirmDialog(name, tree_model)
        dialog.show(self.get_root_widget())
