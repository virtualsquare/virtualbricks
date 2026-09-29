# -*- test-case-name: virtualbricks.tests.console.test_ampbox -*-
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
The boxes of Twisted's AMP, written and read without Twisted, so that
``virtualbricks --command`` talks to an AMP socket and still loads no
reactor.

A box is a key and a value, then another, each with its length in two
bytes, and a key of no bytes at its end. A request has ``_ask``, its tag,
and ``_command``, its name; its answer has ``_answer`` and the same tag, or
``_error``, ``_error_code`` and ``_error_description``. See
:mod:`twisted.protocols.amp`, and :mod:`virtualbricks.console.ampwire` for
the commands.
"""

from __future__ import annotations

import struct
from collections.abc import Callable

ASK = b"_ask"
ANSWER = b"_answer"
COMMAND = b"_command"
ERROR = b"_error"
ERROR_CODE = b"_error_code"
ERROR_DESCRIPTION = b"_error_description"
# The longest a key and a value can be, in bytes.
MAX_KEY = 0xFF
MAX_VALUE = 0xFFFF
LENGTH = struct.Struct("!H")


class BadBox(ValueError):
    """What was read isn't a box of AMP."""


class Closed(EOFError):
    """The connection ended in the middle of a box, or before it."""


class TooLong(ValueError):
    """A value longer than AMP carries; str() is its key."""


def encode(box: dict[bytes, bytes]) -> bytes:
    """The bytes of box; TooLong if a key or a value doesn't fit."""

    parts = []
    for key, value in box.items():
        if len(key) > MAX_KEY or len(value) > MAX_VALUE:
            raise TooLong(key.decode("ascii", "replace"))
        parts += [LENGTH.pack(len(key)), key, LENGTH.pack(len(value)), value]
    parts.append(LENGTH.pack(0))
    return b"".join(parts)


def read(read: Callable[[int], bytes]) -> dict[bytes, bytes]:
    """
    The next box, from read(n), which gives n bytes, or fewer at the end of
    the connection. Raise Closed at the end, BadBox for what isn't a box.
    """

    box = {}
    while True:
        key = _string(read, MAX_KEY, bool(box))
        if not key:
            return box
        box[key] = _string(read, MAX_VALUE, True)


def _string(read, most, begun):
    size = _exactly(read, LENGTH.size, begun)
    (length,) = LENGTH.unpack(size)
    if length > most:
        raise BadBox(f"a length of {length}, over {most}")
    return _exactly(read, length, True)


def _exactly(read, count, begun):
    data = b""
    while len(data) < count:
        more = read(count - len(data))
        if not more:
            raise Closed("in a box" if begun or data else "")
        data += more
    return data


def text(value: bytes) -> str:
    """A value of amp.Unicode()."""

    try:
        return value.decode("utf-8")
    except UnicodeDecodeError:
        raise BadBox("not UTF-8") from None


def integer(value: bytes) -> int:
    """A value of amp.Integer()."""

    try:
        return int(value)
    except ValueError:
        raise BadBox("not an integer") from None


def texts(value: bytes) -> list[str]:
    """A value of amp.ListOf(amp.Unicode()): each with its length."""

    items = []
    start = 0
    while start < len(value):
        end = start + LENGTH.size
        if end > len(value):
            raise BadBox("a list cut short")
        (length,) = LENGTH.unpack(value[start:end])
        if end + length > len(value):
            raise BadBox("a list cut short")
        items.append(text(value[end : end + length]))
        start = end + length
    return items
