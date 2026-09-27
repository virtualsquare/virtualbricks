# -*- test-case-name: virtualbricks.tests.gui.mainwindow.test_events -*-
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
The Events tab of the main window: the events of the project.

A toolbar creates an event, starts or stops them all, and configures the
selected one. In the list, the right button opens the menu of an event,
Delete removes it and a double click starts or stops it.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gtk  # noqa: E402

from virtualbricks.gui import widgets  # noqa: E402
from virtualbricks.gui.mainwindow import eventmenu  # noqa: E402
from virtualbricks.gui.mainwindow.tab import (  # noqa: E402
    Tab,
    popup_menu,
    state_add_selection,
)
from virtualbricks.gui.windows.base import StateManager  # noqa: E402
from virtualbricks.gui.windows.newevent import NewEventDialog  # noqa: E402
from virtualbricks.i18n import _  # noqa: E402
from virtualbricks.tools import dispose  # noqa: E402

# The columns: title, and what the cell shows (see
# widgets.CellRendererFormattable), None for the icon.
COLUMNS = (
    (_("Icon"), None),
    (_("Status"), "s"),
    (_("Name"), "n"),
    (_("Parameters"), "p"),
)
DELETE_KEYS = frozenset(("Delete", "BackSpace"))


class EventsBindingList(widgets.AbstractBindingList):
    """The events of the factory, for a widgets.List."""

    def __init__(self, factory):
        widgets.AbstractBindingList.__init__(self, factory)
        factory.connect("event-added", self._on_added)
        factory.connect("event-removed", self._on_removed)
        factory.connect("event-changed", self._on_changed)

    def __dispose__(self):
        self._factory.disconnect("event-added", self._on_added)
        self._factory.disconnect("event-removed", self._on_removed)
        self._factory.disconnect("event-changed", self._on_changed)

    def __iter__(self):
        return self._factory.iter_events()


def _tool_button(label, stock_id, **properties):
    return Gtk.ToolButton(
        visible=True,
        label=label,
        use_underline=True,
        stock_id=stock_id,
        **properties,
    )


class EventsTab(Tab, Gtk.Box):
    """The events of the project, and what can be done with them."""

    title = _("_Events")

    def __init__(self, gui, factory) -> None:
        super().__init__(visible=True, orientation=Gtk.Orientation.VERTICAL)
        self.gui = gui
        self.factory = factory
        # the menu that shows
        self._menu: Gtk.Menu | None = None

        toolbar = Gtk.Toolbar(
            visible=True, toolbar_style=Gtk.ToolbarStyle.BOTH
        )
        self.new_button = _tool_button(_("New Event"), "gtk-new")
        self.start_button = _tool_button(
            _("Start All Events"), "gtk-media-play"
        )
        self.stop_button = _tool_button(_("Stop All Events"), "gtk-media-stop")
        # made insensitive by the state below, which shows why
        self.configure_button = _tool_button(_("Configure"), "gtk-edit")
        for item in (
            self.new_button,
            None,
            self.start_button,
            self.stop_button,
            None,
            self.configure_button,
        ):
            if item is None:
                item = Gtk.SeparatorToolItem(visible=True)
                item.set_homogeneous(False)
            toolbar.insert(item, -1)
        self.pack_start(toolbar, False, False, 0)

        self.store = widgets.List()
        self._events = EventsBindingList(factory)
        self.store.set_data_source(self._events)
        scrolled = Gtk.ScrolledWindow(
            visible=True, shadow_type=Gtk.ShadowType.IN
        )
        self.view = widgets.TreeView(
            visible=True, model=self.store, headers_clickable=False
        )
        for title, format_string in COLUMNS:
            column = Gtk.TreeViewColumn.new()
            column.set_properties(title=title)
            if format_string is None:
                cell = widgets.CellRendererBrickIcon()
            else:
                cell = widgets.CellRendererFormattable(
                    format_string=format_string, formatting_enabled=True
                )
            column.pack_start(cell, False)
            self.view.append_column(column)
        self.view.set_cells_data_func()
        scrolled.add(self.view)
        self.pack_start(scrolled, True, True, 0)

        self._states = StateManager()
        state_add_selection(
            self._states,
            self.view,
            lambda: self.view.get_selected_value() is not None,
            _("No event selected"),
            self.configure_button,
        )
        self.new_button.connect("clicked", self.on_new_clicked)
        self.start_button.connect("clicked", self.on_start_clicked)
        self.stop_button.connect("clicked", self.on_stop_clicked)
        self.configure_button.connect("clicked", self.on_configure_clicked)
        self.view.connect("button-release-event", self.on_button_release)
        self.view.connect("key-release-event", self.on_key_release)
        self.view.connect("row-activated", self.on_row_activated)

    # What the main window tells

    def on_quit(self) -> None:
        dispose(self._events)

    # Signals

    def on_new_clicked(self, button) -> None:
        NewEventDialog(self.gui).show(self.gui.window)

    def on_start_clicked(self, button) -> None:
        for event in self.factory.iter_events():
            event.poweron()

    def on_stop_clicked(self, button) -> None:
        for event in self.factory.iter_events():
            event.poweroff()

    def on_configure_clicked(self, button) -> None:
        event = self.view.get_selected_value()
        if event is not None:
            self.gui.curtain_up(event)

    def open_menu(self, value, event) -> None:
        self._menu = eventmenu.popup(self.view, event, self.gui, value)

    def on_button_release(self, view, event) -> bool | None:
        return popup_menu(view, event, self.open_menu)

    def on_key_release(self, view, key) -> None:
        if Gdk.keyval_name(key.keyval) in DELETE_KEYS:
            event = view.get_selected_value()
            if event is not None:
                self.gui.ask_remove_event(event)

    def on_row_activated(self, view, path, column) -> None:
        model = view.get_model()
        model.get_value(model.get_iter(path), 0).toggle()
