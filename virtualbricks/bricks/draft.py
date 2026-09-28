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
The settings of a brick while its panel shows them.

A panel works on a draft, never on the brick. The draft holds a copy of the
brick's configuration, and each value set in it is checked by the kind of
its field, as in the brick. A value the kind refuses is kept aside, as it was
typed, with the reason: a problem. ``apply()`` gives the brick the settings
that changed in the draft, in one ``set()``: a running brick takes at once
those it can, through its ``cbset_`` methods, and says it changed once.

A draft also says which settings are in use: a setting of ``WITH`` is in use
while the setting it goes with has the value it needs. A brick that checks
its settings against each other, or against the project, has a draft of its
own, in its module, with ``check()``, ``limits()`` and ``note()``.

Nothing here imports GTK.
"""

from __future__ import annotations

from typing import Any, ClassVar

import attr

from virtualbricks.config.schema import field_names, kind_of


@attr.define(frozen=True)
class Problem:
    """What is wrong with a setting. An error blocks OK; a lack only warns."""

    key: str
    text: str
    error: bool = True


class Draft:
    """The settings of a brick as its panel shows them, until OK."""

    # a setting, and the setting and the value that it goes with
    WITH: ClassVar[dict[str, tuple[str, object]]] = {}

    def __init__(self, brick: Any) -> None:
        self.brick = brick
        # the settings as they were, and as the panel has them
        self.original = attr.evolve(brick.config)
        self.settings = attr.evolve(brick.config)
        # the values that their kind refused, as typed, and why
        self.refused: dict[str, tuple[object, str]] = {}

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
        """Whether a setting is in use: what it goes with has its value."""

        seen = set()
        while name in self.WITH and name not in seen:
            seen.add(name)
            other, value = self.WITH[name]
            if self.get(other) != value:
                return False
            name = other
        return True

    def limits(self, name: str) -> tuple[Any, Any]:
        """The lowest and the highest value of a number, None for no limit."""

        kind = kind_of(self.settings, name)
        return getattr(kind, "min", None), getattr(kind, "max", None)

    def note(self, name: str) -> str:
        """What the project adds to the help of a setting, or ""."""

        return ""

    def check(self) -> list[Problem]:
        """What is wrong between the settings, or with the project."""

        return []

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

    def live(self) -> list[str]:
        """The settings a running brick takes at once, in their order."""

        return [
            name
            for name in field_names(self.settings)
            if hasattr(self.brick, f"cbset_{name}")
        ]


def apply(draft: Draft) -> None:
    """
    Give the brick the settings changed in draft, in one set(); a draft with
    errors is refused.
    """

    errors = draft.errors()
    if errors:
        raise ValueError(f"{errors[0].key}: {errors[0].text}")
    changes = draft.changes()
    if changes:
        draft.brick.set(changes)
