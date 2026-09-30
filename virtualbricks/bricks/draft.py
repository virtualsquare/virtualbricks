# -*- test-case-name: virtualbricks.tests.bricks.test_draft -*-
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
The settings of a brick while its panel shows them; of an event, and of a disk
image, too.

A panel works on a draft, never on the brick. The draft holds a copy of the
brick's configuration, and each value set in it is checked by the kind of
its field, as in the brick. A value the kind refuses is kept aside, as it was
typed, with the reason: a problem. ``apply()`` gives the brick the settings
that changed in the draft, in one ``update_config()``: a running brick takes
at once those it can, through its ``cbset_`` methods, and says it changed
once. An object without a record of settings, as a disk image, has a draft
that makes one in ``read()`` and gives the changes back in ``give()``.

The links of a draft are the sockets that the plugs of the brick join, None
for a plug in nothing; ``sockets()`` are those a plug can join. ``apply()``
moves the plugs whose socket changed. What a brick has beyond its record, as
the states of a Netemu, its draft gives it in ``apply_extras()``.

A draft also says which settings are in use, as the schema of the settings
declares with ``when``, from the values in the draft. A brick that checks its
settings against each other, or against the project, has a draft of its own,
in its module, with ``check()``, ``limits()`` and ``note()``.

Nothing here imports GTK.
"""

from __future__ import annotations

from typing import Any

import attr

from virtualbricks.config.schema import field_names, kind_of, why_unused
from virtualbricks.config.settings import get_setting
from virtualbricks.i18n import _


def copy(record):
    """A copy of a record of settings, with copies of its lists."""

    lists = {
        name: list(value)
        for name, value in attr.asdict(record, recurse=False).items()
        if isinstance(value, list)
    }
    return attr.evolve(record, **lists)


@attr.define(frozen=True)
class Problem:
    """What is wrong with a setting. An error blocks OK; a lack only warns."""

    key: str
    text: str
    error: bool = True


class Draft:
    """The settings of a brick as its panel shows them, until OK."""

    def __init__(self, brick: Any) -> None:
        # a brick, an event or an image
        self.brick = brick
        # the settings as they were, and as the panel has them
        self.original = copy(self.read())
        self.settings = copy(self.original)
        # the values that their kind refused, as typed, and why
        self.refused: dict[str, tuple[object, str]] = {}
        # the socket that each plug joins, or None; an event has no plugs
        self.original_links = [
            plug.sock for plug in getattr(brick, "plugs", ())
        ]
        self.links = list(self.original_links)

    def read(self):
        """The record of the settings, which the draft copies."""

        return self.brick.config

    def give(self, changes: dict[str, object]) -> None:
        """Give the brick the settings that changed, in one update_config()."""

        self.brick.update_config(changes)

    def get(self, name: str) -> object:
        """The value of a setting, as it was typed if its kind refused it."""

        if name in self.refused:
            return self.refused[name][0]
        return getattr(self.settings, name)

    def set(self, name: str, value: object) -> None:
        """
        Set a setting; a value its kind refuses is kept aside, with the
        reason, and the setting keeps its last good value.
        """

        if name not in field_names(self.settings):
            raise KeyError(name)
        try:
            setattr(self.settings, name, value)
        except ValueError as exc:
            # the schema says which field: the row says it already
            reason = str(exc).removeprefix(f"{name}: ")
            self.refused[name] = (value, reason)
        else:
            self.refused.pop(name, None)

    def uses(self, name: str) -> bool:
        """
        Whether a setting is in use: what it goes with has its value, as
        typed. What isn't a setting, as a plug, is always in use.
        """

        if name not in field_names(self.settings):
            return True
        return why_unused(self.settings, name, self.get) is None

    def limits(self, name: str) -> tuple[Any, Any]:
        """The lowest and the highest value of a number, None for no limit."""

        kind = kind_of(self.settings, name)
        return getattr(kind, "min", None), getattr(kind, "max", None)

    def note(self, name: str) -> str:
        """What the project adds to the help of a setting, or ""."""

        return ""

    def check(self) -> list[Problem]:
        """
        What is wrong between the settings, or with the project: here, a
        plug in nothing, which the brick can't start with.
        """

        return [
            Problem(
                f"plug{index}",
                _("In nothing: {brick} can't start").format(
                    brick=self.brick.name
                ),
                error=False,
            )
            for index, sock in enumerate(self.links)
            if sock is None
        ]

    def problems(self) -> list[Problem]:
        """The values refused, then what check() finds."""

        refused = [
            Problem(name, reason) for name, (_, reason) in self.refused.items()
        ]
        return refused + self.check()

    def errors(self) -> list[Problem]:
        return [problem for problem in self.problems() if problem.error]

    def changes(self) -> dict[str, object]:
        """The settings changed in the draft, by name, in their order."""

        return {
            name: getattr(self.settings, name)
            for name in field_names(self.settings)
            if getattr(self.settings, name) != getattr(self.original, name)
        }

    def sockets(self) -> list:
        """
        The sockets a plug of the brick can join: those of the switches, and
        those of the other bricks where the settings allow female plugs.
        """

        female = get_setting("allow_female_plugs")
        return [
            sock
            for sock in self.brick.factory.socks
            if sock.brick is not self.brick
            and (sock.brick.get_type().startswith("Switch") or female)
        ]

    def link(self, index: int, sock: Any) -> None:
        """Plug the plug of index into sock, or into nothing."""

        self.links[index] = sock

    def moved(self) -> dict[int, Any]:
        """The plugs whose socket changed, by index: their new socket."""

        return {
            index: sock
            for index, (sock, before) in enumerate(
                zip(self.links, self.original_links)
            )
            if sock is not before
        }

    def apply_extras(self) -> bool:
        """Give the brick what it has beyond its record; whether it changed."""

        return False

    def live(self) -> list[str]:
        """The settings a running brick takes at once, in their order."""

        return [
            name
            for name in field_names(self.settings)
            if hasattr(self.brick, f"cbset_{name}")
        ]


def apply(draft: Draft) -> None:
    """
    Give the brick the settings changed in draft, in one update_config(),
    after its plugs moved; it says it changed once. A draft with errors is
    refused.
    """

    errors = draft.errors()
    if errors:
        raise ValueError(f"{errors[0].key}: {errors[0].text}")
    brick = draft.brick
    moved = draft.moved()
    for index, sock in moved.items():
        plug = brick.plugs[index]
        if plug.sock is not None:
            plug.disconnect()
        if sock is not None:
            plug.connect(sock)
    extras = draft.apply_extras()
    changes = draft.changes()
    if changes:
        draft.give(changes)
    elif moved or extras:
        brick.changed.notify(brick)
