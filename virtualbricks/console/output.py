# -*- test-case-name: virtualbricks.tests.console.test_output -*-
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

"""The shapes of the answers: tables in columns, and KEY = VALUE lines."""

from __future__ import annotations

import unicodedata
from collections.abc import Sequence


def width(text: str) -> int:
    """The columns text takes in a terminal: two for a wide character."""

    return sum(
        2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text
    )


def table(
    rows: Sequence[Sequence[str]], headers: Sequence[str] | None = None
) -> list[str]:
    """Lines of columns two spaces apart; the last isn't padded."""

    lines = ([list(headers)] if headers else []) + [list(r) for r in rows]
    if not lines:
        return []
    widths = [
        max(width(line[column]) for line in lines)
        for column in range(len(lines[0]))
    ]
    text = []
    for line in lines:
        cells = [
            cell + " " * (widths[column] - width(cell))
            for column, cell in enumerate(line[:-1])
        ]
        text.append("  ".join(cells + [line[-1]]).rstrip())
    return text


def pairs(
    items: Sequence[tuple[str, str]], note: dict | None = None
) -> list[str]:
    """KEY = VALUE lines, with a comment after the keys in note."""

    note = note or {}
    return [
        f"{key} = {value}" + (f"  # {note[key]}" if key in note else "")
        for key, value in items
    ]
