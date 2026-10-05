# -*- test-case-name: virtualbricks.tests.gui.mainwindow.bricks.test_tab -*-
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
The Bricks tab of the main window: the bricks of the project, on the tab of
rows of :mod:`virtualbricks.gui.mainwindow.rowtab`.

New Brick opens the popover of the kinds of
:mod:`virtualbricks.gui.mainwindow.bricks.newbrick` under the button; the brick
made is selected and its settings show. The switch shows all the bricks or
the running ones, and Start All starts the bricks that can start.
The menu of a brick is :mod:`virtualbricks.gui.mainwindow.bricks.brickmenu`'s, and
its settings are its panel of :mod:`virtualbricks.gui.mainwindow.bricks.config`, on a
draft of the brick; a router has none.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402
from twisted.internet import defer  # noqa: E402
from twisted.logger import Logger  # noqa: E402

from virtualbricks.bricks import brickinfo  # noqa: E402
from virtualbricks.gui.mainwindow.bricks import brickmenu  # noqa: E402
from virtualbricks.bricks.brickinfo import State  # noqa: E402
from virtualbricks.gui.mainwindow.bricks.bricklist import (  # noqa: E402
    BrickList,
)
from virtualbricks.gui.mainwindow.bricks.config import new_panel  # noqa: E402
from virtualbricks.gui.mainwindow.bricks.newbrick import (  # noqa: E402
    NewBrickPopover,
)
from virtualbricks.gui.mainwindow.rowtab import (  # noqa: E402
    RowsTab,
    log_failures,
)
from virtualbricks.i18n import _, ngettext  # noqa: E402
from virtualbricks.bricks import is_running  # noqa: E402

logger = Logger()
not_started = "Brick not started."
not_stopped = "Brick not stopped."


def count(bricks) -> str:
    """How many bricks run, of how many."""

    total = len(bricks)
    running = sum(1 for brick in bricks if is_running(brick))
    return ngettext(
        "{running} of {total} running", "{running} of {total} running", total
    ).format(running=running, total=total)


class BricksTab(RowsTab):
    """The bricks of the project, and what can be done with them."""

    title = _("_Bricks")
    NEW = _("New Brick")
    SEARCH = _("Search bricks")
    RUNNING = _("Running")
    EMPTY_TITLE = _("No Bricks Yet")
    EMPTY_WORDS = _(
        "A brick is a switch, a virtual machine, a wire or a tap. "
        "Add the first one to start the lab."
    )
    EMPTY_ICON = "switch.png"
    # made at the first New Brick, and kept
    new_popover: NewBrickPopover | None = None

    def make_list(self) -> BrickList:
        return BrickList(self.gui, self.factory)

    def signals(self) -> tuple:
        factory = self.factory
        return (
            factory.brick_added,
            factory.brick_removed,
            factory.brick_changed,
        )

    def items(self) -> list:
        return list(self.factory.bricks)

    def count_text(self, items) -> str:
        return count(items)

    def can_start(self, item) -> bool:
        return brickinfo.state(item) is State.STOPPED

    def start_all(self) -> defer.Deferred:
        """Start the bricks that can start; the failures are logged."""

        engine = self.gui.engine
        deferreds = [
            engine.start(brick)
            for brick in self.items()
            if self.can_start(brick)
        ]
        return log_failures(deferreds, not_started, logger)

    def stop_all(self) -> defer.Deferred:
        """Stop the running bricks; the failures are logged."""

        engine = self.gui.engine
        deferreds = [
            engine.stop(brick) for brick in self.items() if is_running(brick)
        ]
        return log_failures(deferreds, not_stopped, logger)

    def new(self) -> None:
        """Offer the kinds of bricks, under the button."""

        if self.new_popover is None:
            self.new_popover = NewBrickPopover(self.gui.engine, self.on_made)
        self.new_popover.popup_at(self.new_button)

    def on_made(self, brick) -> None:
        """Select the new brick, and show its settings."""

        row = self.list.row_of(brick)
        self.list.select_row(row)
        row.grab_focus()
        self.gui.curtain_up(brick)

    def popup(self, widget, event, item) -> Gtk.Menu:
        return brickmenu.popup(widget, event, self.gui, item, True)

    def panel_for(self, item):
        return new_panel(item, self.gui)

    def settings_words(self, item) -> str:
        return _("{kind} settings").format(kind=brickinfo.kind(item))
