# -*- test-case-name: virtualbricks.tests.console.test_wire -*-
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
What the two ends of the control socket share: the messages of its
protocol, and the checks of its path. It loads no Twisted, for the client.

The protocol is JSON Lines: UTF-8, an object on each line. On connecting,
the Virtualbricks that listens greets::

    {"protocol": 1, "version": "2.1.0", "pid": 4200, "project": "lab1"}

Then each request gets an answer, in order::

    {"line": "brick start sw1", "cwd": "/home/alice/labs"}
    {"ok": true, "lines": ["sw1 runs, process 4242"]}
    {"line": "brick start vm9"}
    {"ok": false, "lines": [], "error": "No brick named vm9"}

``cwd``, the folder that the paths of the command are read from, is
optional: without it, they are read from the folder of Virtualbricks.
"""

from __future__ import annotations

import json
import os
import stat
from collections.abc import Sequence

from virtualbricks import locations
from virtualbricks.i18n import _

# The version of the protocol, in the greeting: a client that doesn't know
# it doesn't send anything.
PROTOCOL = 1
# The longest line a request can be; a longer one closes the connection.
MAX_LINE = 64 * 1024


class Unusable(Exception):
    """A socket path that can't be used; str() says why, to the user."""


class BadRequest(Exception):
    """A line that isn't a request; str() says why."""


def encode(message: dict) -> bytes:
    return json.dumps(message, ensure_ascii=False).encode("utf-8") + b"\n"


def decode(line: bytes) -> dict:
    """The message of a line; ValueError if it isn't a JSON object."""

    message = json.loads(line.decode("utf-8"))
    if not isinstance(message, dict):
        raise ValueError("not a JSON object")
    return message


def greeting(version: str, pid: int, project: str | None) -> dict:
    return {
        "protocol": PROTOCOL,
        "version": version,
        "pid": pid,
        "project": project,
    }


def request(line: str, cwd: str | None = None) -> dict:
    message: dict = {"line": line}
    if cwd is not None:
        message["cwd"] = cwd
    return message


def read_request(line: bytes) -> tuple[str, str | None]:
    """The command and the folder of a request; BadRequest if it isn't one."""

    try:
        message = decode(line)
    except ValueError:
        raise BadRequest(
            _("Not a request: a line of JSON, as {example}").format(
                example='{"line": "brick list"}'
            )
        ) from None
    text = message.get("line")
    if not isinstance(text, str):
        raise BadRequest(_('Not a request: "line" is not a text'))
    cwd = message.get("cwd")
    if cwd is not None and not (isinstance(cwd, str) and os.path.isabs(cwd)):
        raise BadRequest(_('Not a request: "cwd" is not an absolute path'))
    return text, cwd


def answer(lines: Sequence[str]) -> dict:
    return {"ok": True, "lines": list(lines)}


def refusal(error: str, lines: Sequence[str] = ()) -> dict:
    """The answer of a command that failed, after what it did first."""

    return {"ok": False, "lines": list(lines), "error": error}


def check_length(path: str) -> None:
    """Raise Unusable if path is too long for a socket."""

    if len(os.fsencode(path)) > locations.SOCKET_PATH_MAX:
        raise Unusable(
            _("The socket's path, {path}, is longer than {size} bytes").format(
                path=path, size=locations.SOCKET_PATH_MAX
            )
        )


def check_path(path: str, default: bool) -> None:
    """
    Raise Unusable if a socket can't be at path.

    The default socket is in the runtime folder, which must be a folder of
    yours that nobody else can write in: in the temporary folder, where it
    is without XDG_RUNTIME_DIR, another user could have made it first. The
    folder of another path must be there.
    """

    check_length(path)
    folder = os.path.dirname(path)
    try:
        # the runtime folder can't be a link; the folder of another path can
        info = os.lstat(folder) if default else os.stat(folder)
    except FileNotFoundError:
        raise Unusable(
            _("The folder {folder} doesn't exist").format(folder=folder)
        ) from None
    if not stat.S_ISDIR(info.st_mode):
        raise Unusable(_("{folder} isn't a folder").format(folder=folder))
    if not default:
        return
    if info.st_uid != os.getuid():
        raise Unusable(
            _("The runtime folder {folder} isn't yours").format(folder=folder)
        )
    if info.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise Unusable(
            _("Others can write in the runtime folder {folder}").format(
                folder=folder
            )
        )


def check_socket(path: str) -> bool:
    """
    Whether there is a socket at path; raise Unusable if what is there
    isn't a socket, or isn't yours.
    """

    try:
        info = os.lstat(path)
    except (FileNotFoundError, NotADirectoryError):
        return False
    if not stat.S_ISSOCK(info.st_mode):
        raise Unusable(_("{path} isn't a socket").format(path=path))
    if info.st_uid != os.getuid():
        raise Unusable(_("{path} isn't yours").format(path=path))
    return True
