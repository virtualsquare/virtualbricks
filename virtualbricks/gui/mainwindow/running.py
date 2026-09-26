# -*- test-case-name: virtualbricks.tests.gui.mainwindow.test_running -*-
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
The Running tab of the main window: the bricks that run, and their process.

The tab shows the store of the Bricks tab through a filter, checked again
every two seconds. The right button opens the menu of a process.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402
from twisted.internet import reactor, task  # noqa: E402

from virtualbricks.gui import widgets  # noqa: E402
from virtualbricks.gui.interfaces import IJobMenu  # noqa: E402
from virtualbricks.gui.mainwindow.tab import Tab  # noqa: E402
from virtualbricks.i18n import _  # noqa: E402
from virtualbricks.tools import is_running  # noqa: E402

# The seconds between two checks of what runs.
REFRESH = 2
# The columns: title, cell renderer, and what it shows (see
# widgets.CellRendererFormattable).
COLUMNS = (
    (_("Icon"), None),
    (_("Pid"), "d"),
    (_("Type"), "t"),
    (_("Name"), "n"),
)


def running(model, itr, data) -> bool:
    brick = model.get_value(itr, 0)
    return brick is not None and is_running(brick)


class RunningTab(Tab, Gtk.ScrolledWindow):
    """The bricks that run, from the store of all the bricks."""

    title = _("R_unning")

    def __init__(self, gui, bricks, clock=None) -> None:
        super().__init__(visible=True, shadow_type=Gtk.ShadowType.IN)
        self.gui = gui
        self.filter = Gtk.TreeModelFilter(child_model=bricks)
        self.filter.set_visible_func(running)
        self.view = widgets.TreeView(visible=True, model=self.filter)
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
        self.add(self.view)

        self.view.connect("button-release-event", self.on_button_release)
        self.connect("destroy", self.on_destroy)
        self._refresh = task.LoopingCall(self.filter.refilter)
        self._refresh.clock = reactor if clock is None else clock
        self._refresh.start(REFRESH)

    # Signals

    def on_button_release(self, view, event) -> bool | None:
        if event.button != 3:
            return None
        found = view.get_path_at_pos(int(event.x), int(event.y))
        if found is None:
            return None
        path, column, _x, _y = found
        view.grab_focus()
        view.set_cursor(path, column, False)
        model = view.get_model()
        brick = model.get_value(model.get_iter(path), 0)
        IJobMenu(brick).popup(event.button, event.time, self.gui)
        return True

    def on_destroy(self, tab) -> None:
        if self._refresh.running:
            self._refresh.stop()
