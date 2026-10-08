# -*- test-case-name: virtualbricks.tests.config.test_tomlfile -*-
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
Read and write TOML files.

Reading uses tomllib, or tomli before Python 3.11. Writing uses tomlkit with a
fixed layout: plain values first, then tables. A list of tables is written as
``[[…]]`` blocks, unless its tables are small enough for one line each.
Files are replaced atomically.

A file can start with a header, and a key written on its own line can have a
note: its description on the lines above it, and ``# default`` beside it when
the value is the default. Tables have no notes.
"""

from __future__ import annotations

import datetime
import os
import re
import sys
import tempfile
import textwrap
from collections.abc import Mapping
from typing import NamedTuple, TypeAlias, TypeGuard

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover (Python 3.10)
    import tomli as tomllib

import tomlkit
from tomlkit import items

__all__ = [
    "DecodeError",
    "FORMAT_NOTE",
    "Note",
    "Notes",
    "Table",
    "Value",
    "dump_toml",
    "dumps_toml",
    "load_toml",
    "loads_toml",
]

DecodeError = tomllib.TOMLDecodeError

# The data of a TOML file, as tomllib reads it.
Value: TypeAlias = (
    str
    | int
    | float
    | bool
    | datetime.datetime
    | datetime.date
    | datetime.time
    | list["Value"]
    | dict[str, "Value"]
)
Table: TypeAlias = dict[str, Value]

# A table with up to this many plain values goes on one line in a list.
INLINE_KEYS = 2
# The width of the comments, as that of the man pages.
WIDTH = 79


class Note(NamedTuple):
    """
    The comment of a key: its description, and whether its value is the
    default. The detail, as ``1-128; default 32``, goes in parentheses after
    the text, which never breaks it.
    """

    text: str
    detail: str = ""
    default: bool = False


# The notes of a file, by the path of their key: the keys of the tables, and
# the index of a table in a list of tables.
Notes: TypeAlias = Mapping[tuple[str | int, ...], Note]

FORMAT_NOTE = Note("The version of the layout of this file")


def loads_toml(text: str) -> Table:
    return tomllib.loads(text)


def load_toml(path: str) -> Table:
    with open(path, "rb") as fp:
        return tomllib.load(fp)


def _is_table_list(value: object) -> TypeGuard[list[Table]]:
    return (
        isinstance(value, list)
        and len(value) > 0
        and all(isinstance(item, dict) for item in value)
    )


def _fits_inline(table: Table) -> bool:
    return len(table) <= INLINE_KEYS and not any(
        isinstance(value, (dict, list)) for value in table.values()
    )


def _is_block(value: object) -> bool:
    """Whether the value is written as a table rather than on its line."""

    if isinstance(value, dict):
        return True
    return _is_table_list(value) and not all(map(_fits_inline, value))


def _value(value: Value) -> items.Item:
    if _is_table_list(value):
        array = tomlkit.array()
        for table in value:
            inline = tomlkit.inline_table()
            inline.update(table)
            array.append(inline)
        array.multiline(True)
        return array
    return tomlkit.item(value)


def comment_lines(note: Note) -> list[str]:
    """
    The lines of the comment above a key, without their ``#``: the text
    wrapped, never at a hyphen, and the detail at the end of the last line,
    or on a line of its own when it doesn't fit.
    """

    width = WIDTH - len("# ")
    lines = textwrap.wrap(
        note.text, width, break_on_hyphens=False, break_long_words=False
    )
    if note.detail:
        detail = f"({note.detail})"
        if lines and len(lines[-1]) + len(" ") + len(detail) <= width:
            lines[-1] += " " + detail
        else:
            lines.append(detail)
    return lines


def _add(
    container: tomlkit.TOMLDocument | items.Table,
    key: str,
    value: Value,
    note: Note | None,
) -> None:
    item = _value(value)
    if note is not None:
        for line in comment_lines(note):
            container.add(tomlkit.comment(line))
        if note.default:
            item.comment("default")
            # two spaces before an inline comment, as in Python
            item.trivia.comment_ws = "  "
    container.add(key, item)


def _fill(
    container: tomlkit.TOMLDocument | items.Table,
    data: Table,
    notes: Notes,
    path: tuple[str | int, ...],
) -> None:
    for key, value in data.items():
        if not _is_block(value):
            _add(container, key, value, notes.get(path + (key,)))
    for key, value in data.items():
        if isinstance(value, dict):
            only_tables = bool(value) and all(map(_is_block, value.values()))
            table = tomlkit.table(only_tables)
            _fill(table, value, notes, path + (key,))
            container.add(key, table)
        elif _is_table_list(value) and _is_block(value):
            blocks = tomlkit.aot()
            for index, item in enumerate(value):
                table = tomlkit.table()
                _fill(table, item, notes, path + (key, index))
                blocks.append(table)
            container.add(key, blocks)


_HEADER = re.compile(r"^\[")


def _space_tables(text: str) -> str:
    lines: list[str] = []
    for line in text.splitlines():
        if _HEADER.match(line) and lines and lines[-1] != "":
            lines.append("")
        if line == "" and lines and lines[-1] == "":
            continue
        lines.append(line)
    while lines and lines[0] == "":
        lines.pop(0)
    return "\n".join(lines) + "\n"


def dumps_toml(
    data: Table, notes: Notes | None = None, header: str = ""
) -> str:
    """
    The text of a TOML file: the header, each of its lines as a comment and a
    blank line after them, then the data with the comments of the notes.
    """

    document = tomlkit.document()
    if header:
        for line in header.splitlines():
            document.add(tomlkit.comment(line))
        document.add(tomlkit.nl())
    _fill(document, data, notes or {}, ())
    return _space_tables(tomlkit.dumps(document))


def dump_toml(
    data: Table, path: str, notes: Notes | None = None, header: str = ""
) -> None:
    """Write the data to path, replacing the file only once it's complete."""

    directory = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(
        dir=directory, prefix=f".{os.path.basename(path)}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fp:
            fp.write(dumps_toml(data, notes, header))
            fp.flush()
            os.fsync(fp.fileno())
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise
