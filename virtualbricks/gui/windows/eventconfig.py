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
Configuration panel of an event.
"""

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gtk

from virtualbricks import console
from virtualbricks.gui.windows.base import _, ConfigController, VALIDKEY


class EventControllerMixin:
    """
    Edit the actions of an event. Used by the event configuration panel and by
    ``ShellCommandDialog``, their UI have the same widgets.
    """

    def setup_controller(self, event):
        self.actions_view.get_selection().set_mode(Gtk.SelectionMode.MULTIPLE)
        self.shell_cell.set_activatable(True)
        self.action_cell.set_property("editable", True)
        model = self.actions_store
        for action in event.config.actions:
            model.append((action, isinstance(action, console.ShellCommand)))
        model.append(("", False))

    def on_action_cell_edited(self, cell_renderer, path, new_text):
        model = self.actions_store
        iter = model.get_iter(path)
        if new_text:
            model.set_value(iter, 0, new_text)
            if model.iter_next(iter) is None:
                model.append(("", False))
        elif model.iter_next(iter) is not None:
            model.remove(iter)
        else:
            model.set_value(iter, 0, new_text)

    def on_shell_cell_toggled(self, cell_renderer, path):
        model = self.actions_store
        model.set_value(
            model.get_iter(path), 1, not cell_renderer.get_active()
        )

    def configure_event(self, event, attrs):
        model = self.actions_store
        f = (console.VbShellCommand, console.ShellCommand)
        attrs["actions"] = [f[row[1]](row[0]) for row in model if row[0]]
        event.set(attrs)


class EventConfigController(ConfigController, EventControllerMixin):
    """
    Configuration panel of an event: the delay and the list of actions.
    """

    def build_ui(self) -> None:
        """Create the widgets, formerly in ``eventconfig.ui``."""

        # actions_store (Gtk.ListStore)
        self.actions_store = Gtk.ListStore(str, bool)

        # panel (Gtk.Box)
        self.panel = Gtk.Box(
            visible=True,
            can_focus=False,
            orientation=Gtk.Orientation.VERTICAL,
            spacing=6,
        )
        hbox1 = Gtk.Box(visible=True, can_focus=False)
        label1 = Gtk.Label(
            visible=True,
            can_focus=False,
            xpad=6,
            label=_("Delay (seconds):"),
        )
        hbox1.pack_start(label1, False, True, 0)
        self.delay_entry = Gtk.Entry(
            visible=True,
            can_focus=True,
            primary_icon_activatable=False,
            secondary_icon_activatable=False,
        )
        hbox1.pack_start(self.delay_entry, False, True, 0)
        self.panel.pack_start(hbox1, False, True, 0)
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
        self.panel.pack_start(self.actions_view, True, True, 0)

        # Signals
        self.delay_entry.connect(
            "key-press-event",
            self.on_delay_entry_key_press_event,
        )
        self.actions_view.connect(
            "key-press-event",
            self.on_actions_view_key_press_event,
        )
        self.action_cell.connect(
            "edited",
            self.on_action_cell_edited,
        )
        self.shell_cell.connect(
            "toggled",
            self.on_shell_cell_toggled,
        )

    def get_root_widget(self) -> Gtk.Box:
        return self.panel

    def get_config_view(self, gui):
        self.setup_controller(self.original)
        entry = self.delay_entry
        entry.set_text(str(self.original.config.delay))
        return self.panel

    def configure_brick(self, gui):
        attributes = {}
        text = self.delay_entry.get_text()
        if str(self.original.config.delay) != text:
            if not text:
                text = 0
            attributes["delay"] = int(text)
        self.configure_event(self.original, attributes)

    def on_delay_entry_key_press_event(self, entry, event):
        if Gdk.keyval_name(event.keyval) not in VALIDKEY:
            return True

    def on_actions_view_key_press_event(self, treeview, event):
        if Gdk.keyval_name(event.keyval) == "Delete":
            selection = treeview.get_selection()
            model, selected = selection.get_selected_rows()
            rows = []
            for path in selected:
                rows.append(Gtk.TreeRowReference(model, path))
            for row in rows:
                iter = model.get_iter(row.get_path())
                next = model.iter_next(iter)
                model.remove(iter)
                if next is None:
                    self.model.append(("", False))
