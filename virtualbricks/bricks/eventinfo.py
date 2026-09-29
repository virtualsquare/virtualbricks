# -*- test-case-name: virtualbricks.tests.bricks.test_eventinfo -*-
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
What the Events tab and the console say about an event, without widgets.

An event is ready, waiting for its delay, or not configured when it has no
action. Read here, each action has a kind and a subject: start the brick
sw1, stop the event start-vms, a command of the console or of the shell.
Written back, an action is the same, so the project file doesn't change.

The row of an event says in words what it does, after how long, and which
bricks start it: "After 5 s, starts sw1 and sw2 · when sw1 starts".
"""

from __future__ import annotations

import dataclasses
import enum
import math

from virtualbricks.bricks.eventaction import (
    ConsoleAction,
    ShellAction,
    StartAction,
    StopAction,
)
from virtualbricks.i18n import _, ngettext
from virtualbricks.base import is_running

# Between the parts of a row's line.
SEPARATOR = " · "
ON, OFF = "on", "off"


class State(enum.Enum):
    READY = "ready"
    WAITING = "waiting"
    # it has no action, and can't start
    NOT_CONFIGURED = "not-configured"


LABELS = {
    State.READY: _("Ready"),
    State.WAITING: _("Waiting"),
    State.NOT_CONFIGURED: _("Not configured"),
}


class Kind(enum.Enum):
    START_BRICK = "start-brick"
    STOP_BRICK = "stop-brick"
    START_EVENT = "start-event"
    STOP_EVENT = "stop-event"
    CONSOLE = "console"
    SHELL = "shell"


@dataclasses.dataclass(frozen=True)
class Action:
    """What an action does: its kind, and the name or the command it takes."""

    kind: Kind
    subject: str


def state(event) -> State:
    if is_running(event):
        return State.WAITING
    if not event.config.actions:
        return State.NOT_CONFIGURED
    return State.READY


def seconds_left(event, clock) -> int | None:
    """The whole seconds before a waiting event runs its actions."""

    if event.scheduled is None:
        return None
    return max(0, math.ceil(event.scheduled.getTime() - clock.seconds()))


def read(command, factory) -> Action:
    """The action of an action of an event, as the settings show it."""

    if isinstance(command, ShellAction):
        return Action(Kind.SHELL, command.command)
    if isinstance(command, ConsoleAction):
        return Action(Kind.CONSOLE, command.command)
    start = isinstance(command, StartAction)
    if factory.get_event_by_name(command.target) is not None:
        kind = Kind.START_EVENT if start else Kind.STOP_EVENT
    else:
        # a brick, there or gone
        kind = Kind.START_BRICK if start else Kind.STOP_BRICK
    return Action(kind, command.target)


def write(action: Action):
    """The action as the event keeps it."""

    if action.kind is Kind.SHELL:
        return ShellAction(action.subject)
    if action.kind is Kind.CONSOLE:
        return ConsoleAction(action.subject)
    if action.kind in (Kind.START_BRICK, Kind.START_EVENT):
        return StartAction(action.subject)
    return StopAction(action.subject)


def missing(action: Action, factory) -> bool:
    """Whether the brick or the event of an action is not in the project."""

    if action.kind in (Kind.START_BRICK, Kind.STOP_BRICK):
        return factory.get_brick_by_name(action.subject) is None
    if action.kind in (Kind.START_EVENT, Kind.STOP_EVENT):
        return factory.get_event_by_name(action.subject) is None
    return False


def triggers(event, bricks) -> list:
    """(brick, ON or OFF): the bricks that start event when they start or
    stop."""

    found = []
    for brick in bricks:
        if brick.config.on_start == event.get_name():
            found.append((brick, ON))
        if brick.config.on_stop == event.get_name():
            found.append((brick, OFF))
    return found


def names(items) -> str:
    """Names in a sentence: "sw1", "sw1 and sw2", "sw1, sw2 and sw3"."""

    if len(items) == 1:
        return items[0]
    return _("{first} and {last}").format(
        first=", ".join(items[:-1]), last=items[-1]
    )


# The kinds of actions that the row says together.
GROUPED = (
    Kind.START_BRICK,
    Kind.STOP_BRICK,
    Kind.START_EVENT,
    Kind.STOP_EVENT,
)


def _together(kind, count) -> str:
    if kind is Kind.START_BRICK:
        return _("starts {names}")
    if kind is Kind.STOP_BRICK:
        return _("stops {names}")
    if kind is Kind.START_EVENT:
        return ngettext(
            "starts the event {names}", "starts the events {names}", count
        )
    return ngettext(
        "stops the event {names}", "stops the events {names}", count
    )


def what_it_does(actions) -> list:
    """The actions in words: those of a kind together, in their order."""

    parts = []
    grouped: dict[Kind, list] = {}
    for action in actions:
        if action.kind in GROUPED:
            if action.kind not in grouped:
                grouped[action.kind] = []
                parts.append(action.kind)
            grouped[action.kind].append(action.subject)
        else:
            parts.append(action)
    words = []
    for part in parts:
        if isinstance(part, Kind):
            subjects = grouped[part]
            words.append(
                _together(part, len(subjects)).format(names=names(subjects))
            )
        elif part.kind is Kind.SHELL:
            words.append(
                _("runs “{command}” on the host").format(command=part.subject)
            )
        else:
            words.append(_("runs “{command}”").format(command=part.subject))
    return words


def summary(event, factory) -> str:
    """What the row of event says: its actions, its delay, its bricks."""

    actions = [read(command, factory) for command in event.config.actions]
    if not actions:
        line = _("No actions yet")
    else:
        does = ", ".join(what_it_does(actions))
        delay = event.config.delay
        if delay:
            line = _("After {delay} s, {does}").format(delay=delay, does=does)
        else:
            line = _("At once, {does}").format(does=does)
    when = [
        (
            _("when {brick} starts") if what == ON else _("when {brick} stops")
        ).format(brick=brick.get_name())
        for brick, what in triggers(event, factory.bricks)
    ]
    return SEPARATOR.join([line] + when)
