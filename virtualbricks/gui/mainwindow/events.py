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
The Events tab of the main window: the events of the project, on the tab of
rows of :mod:`virtualbricks.gui.mainwindow.rowtab`.

A row says in words what an event does, after how long, and which bricks
start it; while the event waits, its state counts the seconds down. An event
without actions can't start, and its row says so. The switch shows all the
events or the waiting ones, and Start All starts the events that can start.
The search finds an event by its name.

New Event asks a name and a delay, in the window of
:mod:`virtualbricks.gui.mainwindow.newevent`, then shows the settings of the
new event. The menu of an event is
:mod:`virtualbricks.gui.mainwindow.eventmenu`'s, and its settings are
:mod:`virtualbricks.gui.mainwindow.eventeditor`'s.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402
from twisted.internet import reactor, task  # noqa: E402

from virtualbricks.gui.mainwindow import eventinfo, eventmenu  # noqa: E402
from virtualbricks.gui.mainwindow.eventeditor import EventEditor  # noqa: E402
from virtualbricks.gui.mainwindow.eventinfo import (  # noqa: E402
    LABELS,
    SEPARATOR,
    State,
)
from virtualbricks.gui.mainwindow.newevent import NewEventDialog  # noqa: E402
from virtualbricks.gui.mainwindow.rowtab import (  # noqa: E402
    Row,
    RowList,
    RowsTab,
)
from virtualbricks.i18n import _, ngettext  # noqa: E402
from virtualbricks.tools import is_running  # noqa: E402

# How often the countdown moves, in seconds.
TICK = 1
# What the rows of the events say of the bricks.
BRICK_SIGNALS = ("brick-added", "brick-removed", "brick-changed")


def count(events) -> str:
    """How many events wait, of how many."""

    total = len(events)
    waiting = sum(1 for event in events if is_running(event))
    return ngettext(
        "{waiting} of {total} waiting", "{waiting} of {total} waiting", total
    ).format(waiting=waiting, total=total)


class EventRow(Row):
    """An event, what it does and when, and what can be done to it."""

    GROUP = eventmenu.GROUP

    def __init__(self, gui, item, icons, sizes, clock) -> None:
        # the first update() needs it
        self.clock = clock
        super().__init__(gui, item, icons, sizes)

    def make_actions(self):
        return eventmenu.EventActions(self.gui, self.item)

    def menu_model(self):
        return eventmenu.menu(self.item)

    def update(self, processes=False) -> None:
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
                name=event.get_name()
            )
        self.show(
            eventinfo.summary(event, self.gui.brickfactory),
            label,
            state is State.WAITING,
            state is State.NOT_CONFIGURED,
            tooltip,
            dot="waiting",
        )

    def on_startstop_clicked(self, button) -> None:
        self.item.toggle()


class EventList(RowList):
    """
    The events of the factory, a row each. The rows follow the bricks too:
    they say which ones start the events.
    """

    ADDED = "event-added"
    REMOVED = "event-removed"
    CHANGED = "event-changed"
    NONE = _("No events")
    NO_MATCH = _("No event matches “{text}”")
    NONE_RUNNING = _("No event is waiting")
    NO_RUNNING_MATCH = _("No waiting event matches “{text}”")

    def __init__(self, gui, factory, clock=None) -> None:
        # the rows need them, from the first
        self.clock = reactor if clock is None else clock
        self._countdown = task.LoopingCall(self._tick)
        self._countdown.clock = self.clock
        super().__init__(gui, factory)
        for signal in BRICK_SIGNALS:
            factory.connect(signal, self.on_brick_changed)

    def items(self) -> list:
        return list(self.factory.iter_events())

    def make_row(self, item) -> EventRow:
        return EventRow(self.gui, item, self.icons, self._sizes, self.clock)

    def close(self) -> None:
        super().close()
        for signal in BRICK_SIGNALS:
            self.factory.disconnect(signal, self.on_brick_changed)
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
            if is_running(event):
                self.row_of(event).update(self.only_running)

    # The factory

    def on_brick_changed(self, brick) -> None:
        self.update()


class EventsTab(RowsTab):
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
    ADDED = "event-added"
    REMOVED = "event-removed"
    CHANGED = "event-changed"

    def __init__(self, gui, factory, clock=None) -> None:
        # for the list, which the tab makes first
        self.clock = clock
        super().__init__(gui, factory)

    def make_list(self) -> EventList:
        return EventList(self.gui, self.factory, self.clock)

    def items(self) -> list:
        return list(self.factory.iter_events())

    def count_text(self, items) -> str:
        return count(items)

    def can_start(self, item) -> bool:
        return eventinfo.state(item) is State.READY

    def start_all(self) -> None:
        """Start the events that can start; they wait, then run."""

        for event in self.items():
            if self.can_start(event):
                event.poweron()

    def stop_all(self) -> None:
        """Stop the waiting events: their actions don't run."""

        for event in self.items():
            event.poweroff()

    def new(self) -> None:
        NewEventDialog(self.gui).show(self.gui.window)

    def remove(self, item) -> None:
        self.gui.ask_remove_event(item)

    def popup(self, widget, event, item) -> Gtk.Menu:
        return eventmenu.popup(widget, event, self.gui, item, True)

    def panel_for(self, item) -> EventEditor:
        return EventEditor(item)

    def settings_words(self, item) -> str:
        return _("Event settings")
