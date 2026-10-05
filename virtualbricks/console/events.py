# -*- test-case-name: virtualbricks.tests.console.test_events -*-
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
The commands of the events: event list, new, action add, start, and the rest.

An action starts or stops a brick or an event, or runs a command of the
console or of the shell, as in the settings of an event; a console command
is checked as it's added.
"""

from __future__ import annotations

import shlex

from twisted.internet import defer

from virtualbricks.bricks import eventinfo
from virtualbricks.bricks.draft import Draft, apply
from virtualbricks.bricks.eventinfo import LABELS, Action, Kind
from virtualbricks.config.schema import field_names, parse_value
from virtualbricks.console.command import (
    Arg,
    ArgKind,
    Choice,
    CommandError,
    Flag,
    Named,
    Number,
    KeyValues,
    command,
)
from virtualbricks.console.output import table
from virtualbricks.i18n import N_, _
from virtualbricks.bricks import is_running

# the name an event gets, as New Event, when none is given
NEW_EVENT = "new_event"


def _events(factory):
    return [event.name for event in factory.events]


EVENT = Named(
    lambda factory, name: factory.get_event(name),
    _events,
    N_("No event named {name}"),
)


class Subject(ArgKind):
    """What an action does: a brick or an event, or a command."""

    def candidates(self, context, done):
        if done.get("what") in ("start", "stop"):
            factory = context.factory
            return sorted([b.name for b in factory.bricks] + _events(factory))
        return []


def _described(action: Action) -> str:
    if action.kind in (Kind.START_BRICK, Kind.START_EVENT):
        return f"start {action.subject}"
    if action.kind in (Kind.STOP_BRICK, Kind.STOP_EVENT):
        return f"stop {action.subject}"
    word = "shell" if action.kind is Kind.SHELL else "console"
    return f"{word} {shlex.quote(action.subject)}"


def _actions(event):
    factory = event.factory
    return [
        eventinfo.read(command, factory) for command in event.config.actions
    ]


def _state(event, clock):
    state = eventinfo.state(event)
    left = eventinfo.seconds_left(event, clock)
    if left is None:
        return LABELS[state]
    return _("{state}, {seconds} s").format(state=LABELS[state], seconds=left)


def _action(context, what, subject):
    """The action of what and subject, checked."""

    if subject is None:
        raise CommandError(_("{what} needs a subject").format(what=what))
    factory = context.factory
    if what in ("start", "stop"):
        if factory.get_brick(subject) is not None:
            kind = Kind.START_BRICK if what == "start" else Kind.STOP_BRICK
        elif factory.get_event(subject) is not None:
            kind = Kind.START_EVENT if what == "start" else Kind.STOP_EVENT
        else:
            raise CommandError(
                _("No brick or event named {name}").format(name=subject)
            )
        return Action(kind, subject)
    if what == "console":
        # the parser's own checks, the names included
        from virtualbricks.console.parser import parse

        try:
            parse(context, subject)
        except CommandError as exc:
            raise CommandError(
                _("{command}: {error}").format(command=subject, error=exc)
            ) from None
        return Action(Kind.CONSOLE, subject)
    return Action(Kind.SHELL, subject)


def _give_actions(event, actions):
    draft = Draft(event)
    draft.set("actions", [eventinfo.write(action) for action in actions])
    errors = draft.errors()
    if errors:
        raise CommandError(f"{event.name} {errors[0].key}: {errors[0].text}")
    apply(draft)


def _numbered(event):
    return [
        f"{number}  {_described(action)}"
        for number, action in enumerate(_actions(event), start=1)
    ]


def _index(event, number, count):
    if not 1 <= number <= count:
        raise CommandError(
            _("{name} has no action {number}").format(
                name=event.name, number=number
            )
        )
    return number - 1


@command("event", "list", help=N_("The events, their state and actions"))
def list_(context):
    factory = context.factory
    events = list(factory.events)
    if not events:
        return [_("No events")]
    rows = [
        (
            event.name,
            _state(event, context.reactor),
            eventinfo.summary(event, factory),
        )
        for event in events
    ]
    return table(rows, [_("NAME"), _("STATE"), _("WHAT IT DOES")])


@command(
    "event",
    "new",
    Arg("NAME", optional=True),
    help=N_("Make an event; without a name, new_event or the next free one"),
)
def new(context, name):
    factory = context.factory
    if name is None:
        name = factory.unused_name(NEW_EVENT)
    else:
        name = factory.check_name(name)
    return [factory.new_event(name).name]


@command(
    "event",
    "show",
    Arg("NAME", EVENT),
    help=N_("An event's delay, its actions numbered, what starts it"),
)
def show(context, name):
    event = name
    lines = [f"{event.name}  {_state(event, context.reactor)}"]
    lines.append(f"delay = {event.config.delay}")
    lines += _numbered(event)
    for brick, what in eventinfo.triggers(event, context.factory.bricks):
        key = "on_start" if what == eventinfo.ON else "on_stop"
        lines.append(
            _("started by {brick}, its {key}").format(
                brick=brick.name, key=key
            )
        )
    return lines


@command(
    "event",
    "set",
    Arg("NAME", EVENT),
    Arg(
        "KEY=VALUE",
        KeyValues(
            lambda context, done: ["delay", "icon"],
            lambda context, done, key: None,
        ),
        many=True,
    ),
    help=N_("Change an event's delay or icon"),
    example="event set boot delay=10",
)
def set_(context, name, key_value):
    event = name
    draft = Draft(event)
    for key, text in key_value:
        if key == "actions":
            raise CommandError(
                _("event action add, remove and move change the actions")
            )
        if key not in field_names(draft.settings):
            raise CommandError(
                _("{name} has no key {key}").format(name=event.name, key=key)
            )
        try:
            draft.set(key, parse_value(event.config, key, text))
        except ValueError as exc:
            raise CommandError(f"{event.name} {key}: {exc}") from None
    errors = draft.errors()
    if errors:
        raise CommandError(f"{event.name} {errors[0].key}: {errors[0].text}")
    apply(draft)


@command(
    "event",
    "action add",
    Arg("NAME", EVENT),
    Arg("WHAT", Choice("start", "stop", "console", "shell")),
    Arg("SUBJECT", Subject(), optional=True),
    flags=[Flag("at", Arg("N", Number()))],
    help=N_(
        "Add an action: start or stop a brick or an event, or a command of"
        " the console or the shell"
    ),
    example='event action add boot console "brick set vm1 memory=1024"',
)
def action_add(context, name, what, subject, at):
    event = name
    actions = _actions(event)
    action = _action(context, what, subject)
    if at is None:
        actions.append(action)
    else:
        actions.insert(_index(event, at, len(actions) + 1), action)
    _give_actions(event, actions)
    return _numbered(event)


@command(
    "event",
    "action remove",
    Arg("NAME", EVENT),
    Arg("N", Number(), many=True),
    help=N_("Remove actions of an event, by their numbers"),
)
def action_remove(context, name, n):
    event = name
    actions = _actions(event)
    for index in sorted(
        {_index(event, i, len(actions)) for i in n}, reverse=True
    ):
        del actions[index]
    _give_actions(event, actions)
    return _numbered(event)


@command(
    "event",
    "action move",
    Arg("NAME", EVENT),
    Arg("N", Number()),
    Arg("TO", Number()),
    help=N_("Move an action of an event to another place"),
)
def action_move(context, name, n, to):
    event = name
    actions = _actions(event)
    action = actions.pop(_index(event, n, len(actions)))
    actions.insert(_index(event, to, len(actions) + 1), action)
    _give_actions(event, actions)
    return _numbered(event)


@command(
    "event",
    "start",
    Arg("NAME", EVENT, many=True),
    help=N_("Start events: each waits its delay, then runs its actions"),
)
def start(context, name):
    lines = []
    for event in name:
        if not event.configured():
            raise CommandError(
                _("{name} has no action").format(name=event.name), lines
            )
    for event in name:
        if is_running(event):
            lines.append(_("{name} waits already").format(name=event.name))
            continue
        event.start()
        lines.append(
            _("{name} runs its actions in {delay} s").format(
                name=event.name, delay=event.config.delay
            )
        )
    return lines


@command(
    "event",
    "stop",
    Arg("NAME", EVENT, many=True),
    help=N_("Stop events that wait"),
)
def stop(context, name):
    lines = []
    for event in name:
        if not is_running(event):
            lines.append(_("{name} isn't waiting").format(name=event.name))
        event.stop()
    return lines


@command(
    "event",
    "run",
    Arg("NAME", EVENT, many=True),
    help=N_("Run the actions of events now, and wait for them"),
)
@defer.inlineCallbacks
def run(context, name):
    lines = []
    for event in name:
        if not event.configured():
            raise CommandError(
                _("{name} has no action").format(name=event.name), lines
            )
    for event in name:
        yield event.run_actions()
        lines.append(_("{name} ran its actions").format(name=event.name))
    return lines


@command(
    "event",
    "rename",
    Arg("NAME", EVENT),
    Arg("NEW"),
    help=N_("Rename an event, and every brick and action that names it"),
)
def rename(context, name, new):
    factory = context.factory
    factory.rename_item(name, new)
    return [name.name] if name.name != new else []


@command(
    "event",
    "duplicate",
    Arg("NAME", EVENT),
    Arg("NEW", optional=True),
    help=N_(
        "Copy an event; without a new name, its name with the next free"
        " number"
    ),
)
def duplicate(context, name, new):
    factory = context.factory
    if new is not None:
        new = factory.check_name(new)
    copy = factory.duplicate_event(name)
    # the name it has already needs no rename
    if new is not None and new != copy.name:
        factory.rename_item(copy, new)
    return [copy.name]


@command(
    "event",
    "delete",
    Arg("NAME", EVENT, many=True),
    help=N_(
        "Delete events, the actions that start or stop them, and the on_start and on_stop that name them"
    ),
)
def delete(context, name):
    for event in name:
        context.factory.remove_event(event)
