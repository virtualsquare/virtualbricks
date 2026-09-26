# -*- test-case-name: virtualbricks.tests.gui.mainwindow.test_bricks -*-
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
The Bricks tab of the main window: the bricks of the project.

A toolbar creates a brick, starts or stops them all, and configures the
selected one. In the list, the right button opens the menu of a brick,
Delete removes it and a double click starts or stops it; a brick dropped
on another connects the two. The Running tab shows the same store.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gtk  # noqa: E402
from twisted.internet import defer  # noqa: E402
from twisted.logger import Logger  # noqa: E402

from virtualbricks.gui import widgets  # noqa: E402
from virtualbricks.gui.mainwindow.tab import (  # noqa: E402
    Tab,
    popup_menu,
    state_add_selection,
)
from virtualbricks.gui.windows.base import StateManager  # noqa: E402
from virtualbricks.gui.windows.newbrick import NewBrickDialog  # noqa: E402
from virtualbricks.i18n import _  # noqa: E402
from virtualbricks.tools import dispose  # noqa: E402

logger = Logger()
not_started = "Brick not started."
dnd_no_socks = "I don't know what to do, bricks have no socks."
dnd_dest_brick_not_found = "Cannot found dest brick"
dnd_source_brick_not_found = "Cannot find source brick {name}"
dnd_no_dest = "No destination brick"
dnd_same_brick = "Source and destination bricks are the same."

# A brick dragged on another in the same list, to connect them.
BRICK_TARGET_NAME = "brick-connect-target"
BRICK_DRAG_TARGETS = [
    (
        BRICK_TARGET_NAME,
        Gtk.TargetFlags.SAME_WIDGET | Gtk.TargetFlags.SAME_APP,
        0,
    )
]
# The columns: title, and what the cell shows (see
# widgets.CellRendererFormattable), None for the icon.
COLUMNS = (
    (_("Icon"), None),
    (_("Status"), "s"),
    (_("Type"), "t"),
    (_("Name"), "n"),
    (_("Parameters"), "p"),
)
DELETE_KEYS = frozenset(("Delete", "BackSpace"))


class BricksBindingList(widgets.AbstractBindingList):
    """The bricks of the factory, for a widgets.List."""

    def __init__(self, factory):
        widgets.AbstractBindingList.__init__(self, factory)
        factory.connect("brick-added", self._on_added)
        factory.connect("brick-removed", self._on_removed)
        factory.connect("brick-changed", self._on_changed)

    def __dispose__(self):
        self._factory.disconnect("brick-added", self._on_added)
        self._factory.disconnect("brick-removed", self._on_removed)
        self._factory.disconnect("brick-changed", self._on_changed)

    def __iter__(self):
        return iter(self._factory.bricks)


def _tool_button(label, stock_id):
    return Gtk.ToolButton(
        visible=True, label=label, use_underline=True, stock_id=stock_id
    )


class BricksTab(Tab, Gtk.Box):
    """The bricks of the project, and what can be done with them."""

    title = _("_Bricks")

    def __init__(self, gui, factory) -> None:
        super().__init__(visible=True, orientation=Gtk.Orientation.VERTICAL)
        self.gui = gui
        self.factory = factory

        toolbar = Gtk.Toolbar(
            visible=True, toolbar_style=Gtk.ToolbarStyle.BOTH
        )
        self.new_button = _tool_button(_("New Brick"), "gtk-new")
        self.start_button = _tool_button(_("Start All Bricks"), "gtk-yes")
        self.stop_button = _tool_button(_("Stop All Bricks"), "gtk-no")
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

        # the Running tab shows it too
        self.store = widgets.List()
        self._bricks = BricksBindingList(factory)
        self.store.set_data_source(self._bricks)
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
        self.view.enable_model_drag_source(
            Gdk.ModifierType.BUTTON1_MASK,
            BRICK_DRAG_TARGETS,
            Gdk.DragAction.LINK,
        )
        self.view.enable_model_drag_dest(
            BRICK_DRAG_TARGETS, Gdk.DragAction.LINK
        )
        scrolled.add(self.view)
        self.pack_start(scrolled, True, True, 0)

        self._states = StateManager()
        state_add_selection(
            self._states,
            self.view,
            lambda: self.view.get_selected_value() is not None,
            _("No brick selected"),
            self.configure_button,
        )
        self.new_button.connect("clicked", self.on_new_clicked)
        self.start_button.connect("clicked", self.on_start_clicked)
        self.stop_button.connect("clicked", self.on_stop_clicked)
        self.configure_button.connect("clicked", self.on_configure_clicked)
        self.view.connect("button-release-event", self.on_button_release)
        self.view.connect("key-release-event", self.on_key_release)
        self.view.connect("row-activated", self.on_row_activated)
        self.view.connect("drag-data-get", self.on_drag_data_get)
        self.view.connect("drag-data-received", self.on_drag_data_received)

    def start_all(self) -> defer.Deferred:
        """Start every brick; the failures are logged."""

        def started(results):
            for success, value in results:
                if not success:
                    logger.failure(not_started, value)

        deferreds = [brick.poweron() for brick in self.factory.bricks]
        return defer.DeferredList(deferreds, consumeErrors=True).addCallback(
            started
        )

    def connect_bricks(self, source, destination) -> None:
        """Plug a brick into a socket of the other, as a drop does."""

        if destination is source:
            logger.debug(dnd_same_brick)
        elif source.socks:
            destination.connect(source.socks[0])
        elif destination.socks:
            source.connect(destination.socks[0])
        else:
            logger.info(dnd_no_socks)

    # What the main window tells

    def on_quit(self) -> None:
        dispose(self._bricks)

    # Signals

    def on_new_clicked(self, button) -> None:
        NewBrickDialog(self.factory).show(self.gui.window)

    def on_start_clicked(self, button) -> None:
        self.start_all()

    def on_stop_clicked(self, button) -> None:
        for brick in self.factory.bricks:
            brick.poweroff()

    def on_configure_clicked(self, button) -> None:
        brick = self.view.get_selected_value()
        if brick is not None:
            self.gui.curtain_up(brick)

    def on_button_release(self, view, event) -> bool | None:
        return popup_menu(view, event, self.gui)

    def on_key_release(self, view, key) -> None:
        if Gdk.keyval_name(key.keyval) in DELETE_KEYS:
            brick = view.get_selected_value()
            if brick is not None:
                self.gui.ask_remove_brick(brick)

    def on_row_activated(self, view, path, column) -> None:
        model = view.get_model()
        self.gui.startstop_brick(model.get_value(model.get_iter(path), 0))

    def on_drag_data_get(self, view, context, selection, info, time) -> bool:
        brick = view.get_selected_value()
        selection.set(selection.get_target(), 8, brick.get_name().encode())
        return True

    def on_drag_data_received(
        self, view, context, x, y, selection, info, time
    ) -> bool:
        found = view.get_dest_row_at_pos(x, y)
        if found is None:
            logger.debug(dnd_no_dest)
        else:
            path, _position = found
            name = selection.get_data().decode()
            source = self.factory.get_brick_by_name(name)
            if source is None:
                logger.debug(dnd_source_brick_not_found, name=name)
            else:
                model = view.get_model()
                destination = model.get_value(model.get_iter(path), 0)
                if destination is None:
                    logger.debug(dnd_dest_brick_not_found)
                else:
                    self.connect_bricks(source, destination)
        context.finish(True, False, time)
        return True
