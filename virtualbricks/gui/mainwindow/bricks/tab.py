# -*- test-case-name: virtualbricks.tests.gui.mainwindow.bricks.test_tab -*-
# Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
# Copyright (C) 2026 Virtualbricks team

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
draft of the brick; a router has none. The disks of a virtual machine show
the Images tab with ``show_images``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from gi.repository import Gdk, Gtk
from twisted.internet import defer
from twisted.logger import Logger

from virtualbricks.brickfactory import BrickFactory
from virtualbricks.bricks import Brick, brickinfo, is_running, must_stop
from virtualbricks.bricks.brickinfo import State
from virtualbricks.gui.mainwindow.bricks import brickmenu
from virtualbricks.gui.mainwindow.bricks.bricklist import BrickList
from virtualbricks.gui.mainwindow.bricks.config import new_panel
from virtualbricks.gui.mainwindow.bricks.config.panel import Panel
from virtualbricks.gui.mainwindow.bricks.newbrick import NewBrickPopover
from virtualbricks.gui.mainwindow.rowtab import (
    RowsTab,
    log_failures,
)
from virtualbricks.i18n import _, ngettext
from virtualbricks.observable import Signal

if TYPE_CHECKING:  # pragma: no cover
    from virtualbricks.gui.mainwindow.window import MainWindow

logger = Logger()
not_started = "Brick not started."
not_stopped = "Brick not stopped."


def count(bricks: list[Brick]) -> str:
    """How many bricks run, of how many."""

    total = len(bricks)
    running = sum(1 for brick in bricks if is_running(brick))
    return ngettext(
        "{running} of {total} running", "{running} of {total} running", total
    ).format(running=running, total=total)


class BricksTab(RowsTab[Brick]):
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

    def __init__(
        self,
        gui: MainWindow,
        factory: BrickFactory,
        show_images: Callable[[], object],
    ) -> None:
        self.show_images = show_images
        super().__init__(gui, factory)

    def make_list(self) -> BrickList:
        return BrickList(self.gui, self.factory, self.configure)

    def signals(self) -> tuple[Signal, Signal, Signal]:
        factory = self.factory
        return (
            factory.brick_added,
            factory.brick_removed,
            factory.brick_changed,
        )

    def items(self) -> list[Brick]:
        return list(self.factory.bricks)

    def count_text(self, items: list[Brick]) -> str:
        return count(items)

    def can_start(self, item: Brick) -> bool:
        # not a switch wrapper, whose switch another program starts
        return item.runs_program and brickinfo.state(item) is State.STOPPED

    def can_stop(self, item: Brick) -> bool:
        # not a switch wrapper, whose switch another program runs
        return must_stop(item)

    def start_all(self) -> defer.Deferred[None]:
        """Start the bricks that can start; the failures are logged."""

        engine = self.gui.engine
        deferreds = [
            engine.start(brick)
            for brick in self.items()
            if self.can_start(brick)
        ]
        return log_failures(deferreds, not_started, logger)

    def stop_all(self) -> defer.Deferred[None]:
        """Stop the bricks that can stop; the failures are logged."""

        engine = self.gui.engine
        deferreds = [
            engine.stop(brick)
            for brick in self.items()
            if self.can_stop(brick)
        ]
        return log_failures(deferreds, not_stopped, logger)

    def new_item(self) -> None:
        """Offer the kinds of bricks, under the button."""

        if self.new_popover is None:
            self.new_popover = NewBrickPopover(self.gui.engine, self.on_made)
        self.new_popover.popup_at(self.new_button)

    def on_made(self, brick: Brick) -> None:
        """Select the new brick, and show its settings."""

        row = self.list.row_of(brick)
        assert row is not None, "the list follows the factory"
        self.list.select_row(row)
        row.grab_focus()
        self.configure(brick)

    def popup(
        self, widget: Gtk.Widget, event: Gdk.EventButton | None, item: Brick
    ) -> Gtk.Menu:
        return brickmenu.popup(
            widget, event, self.gui, item, self.configure, True
        )

    def panel_for(self, item: Brick) -> Panel | None:
        return new_panel(item, self.gui, self.show_images)

    def settings_words(self, item: Brick) -> str:
        return _("{kind} settings").format(kind=brickinfo.kind(item))
