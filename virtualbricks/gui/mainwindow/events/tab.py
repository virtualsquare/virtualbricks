# -*- test-case-name: virtualbricks.tests.gui.mainwindow.events.test_tab -*-
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
The Events tab of the main window: the events of the project, on the tab of
rows of :mod:`virtualbricks.gui.mainwindow.rowtab`.

A row says in words what an event does, after how long, and which bricks
start it; while the event waits, its state counts the seconds down. An event
without actions can't start, and its row says so. The switch shows all the
events or the waiting ones, and Start All starts the events that can start.
The search finds an event by its name.

New Event asks a name and a delay, in the window of
:mod:`virtualbricks.gui.mainwindow.events.newevent`, then shows the settings of the
new event. The menu of an event is
:mod:`virtualbricks.gui.mainwindow.events.eventmenu`'s, and its settings are
:mod:`virtualbricks.gui.mainwindow.events.eventeditor`'s.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gio, Gtk  # noqa: E402
from twisted.internet import reactor, task  # noqa: E402
from twisted.internet.interfaces import IReactorTime  # noqa: E402

from virtualbricks.brickfactory import BrickFactory  # noqa: E402
from virtualbricks.bricks.draft import Draft  # noqa: E402
from virtualbricks.bricks import eventinfo  # noqa: E402
from virtualbricks.bricks.event import Event  # noqa: E402
from virtualbricks.gui.mainwindow.events import eventmenu  # noqa: E402
from virtualbricks.gui.mainwindow.events.eventeditor import (  # noqa: E402
    EventEditor,
)
from virtualbricks.bricks.eventinfo import (  # noqa: E402
    LABELS,
    SEPARATOR,
    State,
)
from virtualbricks.gui.mainwindow.events.newevent import (  # noqa: E402
    NewEventDialog,
)
from virtualbricks.gui.mainwindow.picture import Icons  # noqa: E402
from virtualbricks.gui.mainwindow.rowtab import (  # noqa: E402
    ICON_SIZE,
    Pictures,
    Row,
    RowList,
    RowsTab,
)
from virtualbricks.gui.mainwindow.tab import brick_signals  # noqa: E402
from virtualbricks.i18n import _, ngettext  # noqa: E402
from virtualbricks.bricks import Brick, is_running  # noqa: E402
from virtualbricks.observable import Signal  # noqa: E402

if TYPE_CHECKING:  # pragma: no cover
    from virtualbricks.gui.mainwindow.window import VBGUI

# How often the countdown moves, in seconds.
TICK = 1


def count(events: list[Event]) -> str:
    """How many events wait, of how many."""

    total = len(events)
    waiting = sum(1 for event in events if is_running(event))
    return ngettext(
        "{waiting} of {total} waiting", "{waiting} of {total} waiting", total
    ).format(waiting=waiting, total=total)


class EventRow(Row[Event]):
    """An event, what it does and when, and what can be done to it."""

    GROUP = eventmenu.GROUP

    def __init__(
        self,
        gui: VBGUI,
        item: Event,
        icons: Pictures[Event],
        sizes: Gtk.SizeGroup,
        clock: IReactorTime,
    ) -> None:
        # the first update() needs it
        self.clock = clock
        super().__init__(gui, item, icons, sizes)

    def make_actions(self) -> eventmenu.EventActions:
        return eventmenu.EventActions(self.gui, self.item)

    def menu_model(self) -> Gio.Menu:
        return eventmenu.menu(self.item)

    def update(self, processes: bool = False) -> None:
        event = self.item
        state = eventinfo.state(event)
        label = LABELS[state]
        if state is State.WAITING:
            left = eventinfo.seconds_left(event, self.clock)
            label = SEPARATOR.join(
                (label, _("{seconds} s").format(seconds=left))
            )
        tooltip = None
        if state is State.NOT_CONFIGURED:
            tooltip = _("Add an action to {name} first").format(
                name=event.name
            )
        self.show_state(
            eventinfo.summary(event, self.gui.brickfactory),
            label,
            state is State.WAITING,
            state is State.NOT_CONFIGURED,
            tooltip,
            dot="waiting",
        )

    def on_startstop_clicked(self, button: Gtk.Button) -> None:
        eventmenu.startstop(self.gui.engine, self.item)


class EventList(RowList[Event]):
    """
    The events of the factory, a row each. The rows follow the bricks too:
    they say which ones start the events.
    """

    NONE = _("No events")
    NO_MATCH = _("No event matches “{text}”")
    NONE_RUNNING = _("No event is waiting")
    NO_RUNNING_MATCH = _("No waiting event matches “{text}”")

    def __init__(
        self,
        gui: VBGUI,
        factory: BrickFactory,
        clock: IReactorTime | None = None,
    ) -> None:
        # the rows need them, from the first
        self.clock = cast("IReactorTime", reactor) if clock is None else clock
        self._countdown = task.LoopingCall(self._tick)
        self._countdown.clock = self.clock
        super().__init__(gui, factory)
        # what the rows of the events say of the bricks
        for signal in brick_signals(factory):
            signal.connect(self.on_brick_changed)

    def signals(self) -> tuple[Signal, Signal, Signal]:
        factory = self.factory
        return (
            factory.event_added,
            factory.event_removed,
            factory.event_changed,
        )

    def items(self) -> list[Event]:
        return list(self.factory.events)

    def make_row(self, item: Event) -> EventRow:
        return EventRow(self.gui, item, self.icons, self._sizes, self.clock)

    def make_icons(self) -> Icons:
        return Icons(ICON_SIZE)

    def running(self, item: Event) -> bool:
        return is_running(item)

    def close(self) -> None:
        super().close()
        for signal in brick_signals(self.factory):
            signal.disconnect(self.on_brick_changed)
        if self._countdown.running:
            self._countdown.stop()

    def update(self) -> None:
        super().update()
        self._follow_waits()

    # The countdown

    def _follow_waits(self) -> None:
        """Count down while an event waits, and only then."""

        waiting = any(map(is_running, self.items()))
        if waiting and not self._countdown.running:
            self._countdown.start(TICK, now=False)
        elif not waiting and self._countdown.running:
            self._countdown.stop()

    def _tick(self) -> None:
        for event in self.items():
            row = self.row_of(event)
            if is_running(event) and row is not None:
                row.update(self.only_running)

    # The factory

    def on_brick_changed(self, brick: Brick) -> None:
        self.update()


class EventsTab(RowsTab[Event]):
    """The events of the project, and what can be done with them."""

    title = _("_Events")
    NEW = _("New Event")
    SEARCH = _("Search events")
    RUNNING = _("Waiting")
    EMPTY_TITLE = _("No Events Yet")
    EMPTY_WORDS = _(
        "An event waits, then starts or stops bricks, or runs commands. "
        "Add one to script the lab."
    )
    EMPTY_ICON = "event.png"

    def __init__(
        self,
        gui: VBGUI,
        factory: BrickFactory,
        clock: IReactorTime | None = None,
    ) -> None:
        # for the list, which the tab makes first
        self.clock = clock
        super().__init__(gui, factory)

    def make_list(self) -> EventList:
        return EventList(self.gui, self.factory, self.clock)

    def signals(self) -> tuple[Signal, Signal, Signal]:
        factory = self.factory
        return (
            factory.event_added,
            factory.event_removed,
            factory.event_changed,
        )

    def items(self) -> list[Event]:
        return list(self.factory.events)

    def count_text(self, items: list[Event]) -> str:
        return count(items)

    def can_start(self, item: Event) -> bool:
        return eventinfo.state(item) is State.READY

    def start_all(self) -> None:
        """Start the events that can start; they wait, then run."""

        for event in self.items():
            if self.can_start(event):
                self.gui.engine.start_event(event)

    def stop_all(self) -> None:
        """Stop the waiting events: their actions don't run."""

        for event in self.items():
            self.gui.engine.stop_event(event)

    def new_item(self) -> None:
        NewEventDialog(self.gui).show(self.gui.window)

    def popup(
        self, widget: Gtk.Widget, event: Gdk.EventButton | None, item: Event
    ) -> Gtk.Menu:
        return eventmenu.popup(widget, event, self.gui, item, True)

    def panel_for(self, item: Event) -> EventEditor:
        return EventEditor(Draft(item))

    def settings_words(self, item: Event) -> str:
        return _("Event settings")
