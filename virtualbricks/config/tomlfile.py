# -*- test-case-name: virtualbricks.tests.config.test_tomlfile -*-
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
Read and write TOML files.

Reading uses tomllib, or tomli before Python 3.11. Writing uses tomlkit with a
fixed layout: plain values first, then tables. A list of tables is written as
``[[…]]`` blocks, unless its tables are small enough for one line each.
Files are replaced atomically.
"""

import os
import re
import tempfile

try:
    import tomllib
except ImportError:  # pragma: no cover (Python 3.10)
    import tomli as tomllib

import tomlkit

__all__ = ["DecodeError", "dump", "dumps", "load", "loads"]

DecodeError = tomllib.TOMLDecodeError

# A table with up to this many plain values goes on one line in a list.
INLINE_KEYS = 2


def loads(text):
    return tomllib.loads(text)


def load(path):
    with open(path, "rb") as fp:
        return tomllib.load(fp)


def _is_table_list(value):
    return (
        isinstance(value, list)
        and len(value) > 0
        and all(isinstance(item, dict) for item in value)
    )


def _fits_inline(table):
    return len(table) <= INLINE_KEYS and not any(
        isinstance(value, (dict, list)) for value in table.values()
    )


def _is_block(value):
    """Whether the value is written as a table rather than on its line."""

    if isinstance(value, dict):
        return True
    return _is_table_list(value) and not all(map(_fits_inline, value))


def _value(value):
    if _is_table_list(value):
        array = tomlkit.array()
        for table in value:
            inline = tomlkit.inline_table()
            inline.update(table)
            array.append(inline)
        array.multiline(True)
        return array
    return value


def _fill(container, data):
    for key, value in data.items():
        if not _is_block(value):
            container.add(key, _value(value))
    for key, value in data.items():
        if isinstance(value, dict):
            only_tables = bool(value) and all(map(_is_block, value.values()))
            table = tomlkit.table(only_tables)
            _fill(table, value)
            container.add(key, table)
        elif _is_block(value):
            blocks = tomlkit.aot()
            for item in value:
                table = tomlkit.table()
                _fill(table, item)
                blocks.append(table)
            container.add(key, blocks)


_HEADER = re.compile(r"^\[")


def _space_tables(text):
    lines = []
    for line in text.splitlines():
        if _HEADER.match(line) and lines and lines[-1] != "":
            lines.append("")
        if line == "" and lines and lines[-1] == "":
            continue
        lines.append(line)
    while lines and lines[0] == "":
        lines.pop(0)
    return "\n".join(lines) + "\n"


def dumps(data):
    document = tomlkit.document()
    _fill(document, data)
    return _space_tables(tomlkit.dumps(document))


def dump(data, path):
    """Write the data to path, replacing the file only once it's complete."""

    directory = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(
        dir=directory, prefix=f".{os.path.basename(path)}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fp:
            fp.write(dumps(data))
            fp.flush()
            os.fsync(fp.fileno())
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise
