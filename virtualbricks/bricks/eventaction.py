# -*- test-case-name: virtualbricks.tests.bricks.test_eventaction -*-
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
An action of an event: start or stop a brick or an event, run a command of
the console or of the shell.

In the project file an action is a table: ``{kind = "start", target =
"sw1"}``, ``{kind = "console", command = "brick set vm1 memory=1024"}``. The
target of start and stop is a name, of a brick or of an event, which a rename
follows. Each action has ``perform(factory)``, which returns a Deferred, or a
failure that says why it can't run.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, TypeAlias

import attr
from twisted.internet import defer, utils

from virtualbricks.bricks import Brick
from virtualbricks.config.report import Report
from virtualbricks.config.schema import Kind
from virtualbricks.config.tomlfile import Value
from virtualbricks.i18n import _

if TYPE_CHECKING:  # pragma: no cover
    from virtualbricks.brickfactory import BrickFactory
    from virtualbricks.bricks.event import Event


def _target(factory: BrickFactory, name: str) -> Brick | Event:
    found = factory.get_brick(name) or factory.get_event(name)
    if found is None:
        raise ValueError(_("No brick or event named {name}").format(name=name))
    return found


@attr.frozen
class StartAction:
    """Start a brick, and wait for it; or start an event, which waits."""

    target: str

    def perform(self, factory: BrickFactory) -> defer.Deferred[Any] | None:
        from virtualbricks.bricks.event import is_event

        found = _target(factory, self.target)
        if is_event(found):
            found.start()
            return defer.succeed(None)
        return found.start()


@attr.frozen
class StopAction:
    """Stop a brick, and wait for it; or stop an event that waits."""

    target: str

    def perform(self, factory: BrickFactory) -> defer.Deferred[Any] | None:
        from virtualbricks.bricks.event import is_event

        found = _target(factory, self.target)
        if is_event(found):
            found.stop()
            return defer.succeed(None)
        return found.stop()


@attr.frozen
class ConsoleAction:
    """A command of the console; its answer, or the reason it failed."""

    command: str

    def perform(self, factory: BrickFactory) -> defer.Deferred[list[str]]:
        from virtualbricks.console.dispatch import run

        return run(factory, self.command)


@attr.frozen
class ShellAction:
    """A command of the shell of the host; its exit code."""

    command: str

    def perform(self, factory: BrickFactory) -> defer.Deferred[int]:
        return utils.getProcessValue("sh", ("-c", self.command), os.environ)


# What an event keeps of an action.
StoredAction: TypeAlias = (
    StartAction | StopAction | ConsoleAction | ShellAction
)

# the kinds in the project file, and what each holds
KINDS: dict[str, tuple[type[StoredAction], str]] = {
    "start": (StartAction, "target"),
    "stop": (StopAction, "target"),
    "console": (ConsoleAction, "command"),
    "shell": (ShellAction, "command"),
}


class EventAction(Kind[StoredAction]):
    """An action of an event, as KINDS has them."""

    def check(self, value: object) -> None:
        if not isinstance(value, tuple(cls for cls, _key in KINDS.values())):
            raise ValueError(f"{value!r} is not an event action")

    def to_data(self, value: StoredAction) -> Value:
        for kind, (cls, key) in KINDS.items():
            if isinstance(value, cls):
                return {"kind": kind, key: getattr(value, key)}
        raise ValueError(f"{value!r} is not an event action")

    def from_data(
        self, data: Value, report: Report, where: str
    ) -> StoredAction:
        if not isinstance(data, dict):
            raise ValueError(f"{data!r} is not a table")
        kind = data.get("kind")
        if not isinstance(kind, str) or kind not in KINDS:
            raise ValueError(f"{kind!r} is not start, stop, console or shell")
        cls, key = KINDS[kind]
        value = data.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{key} {value!r} is not a {key}")
        for other in data.keys() - {"kind", key}:
            report.warning("unknown field, dropped", f"{where}.{other}")
        return cls(value)

    def format(self, value: StoredAction) -> str:
        return describe(value)


def describe(action: object) -> str:
    """An action in words of the console: start sw1, console "…"."""

    for kind, (cls, key) in KINDS.items():
        if isinstance(action, cls):
            text = getattr(action, key)
            if key == "command":
                return f'{kind} "{text}"'
            return f"{kind} {text}"
    return repr(action)
