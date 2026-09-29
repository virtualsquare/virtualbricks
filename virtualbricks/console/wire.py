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
protocol, the descriptions of the sockets and the checks of their paths. It
loads no Twisted, for the client.

The text protocol is JSON Lines: UTF-8, an object on each line. On connecting,
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
import re
import stat
from collections.abc import Sequence
from typing import NamedTuple

from virtualbricks import locations
from virtualbricks.i18n import _

# The version of the protocol, in the greeting: a client that doesn't know
# it doesn't send anything.
PROTOCOL = 1
# The longest line a request can be; a longer one closes the connection.
MAX_LINE = 64 * 1024

# The protocols a socket speaks: the lines of JSON of this module.
TEXT = "text"
PROTOCOLS = (TEXT,)
# The types of socket: only unix, for now.
TYPES = ("unix",)
# The keywords of a description, after its type and its path.
KEYWORDS = ("address", "protocol")
# What a type looks like, as unix, tcp or ssl.
TYPE = re.compile(r"[a-z][a-z0-9]*", re.IGNORECASE)


class Unusable(Exception):
    """A socket path that can't be used; str() says why, to the user."""


class BadRequest(Exception):
    """A line that isn't a request; str() says why."""


class Socket(NamedTuple):
    """A socket to listen on or to talk to: its path and its protocol."""

    path: str
    protocol: str = TEXT
    kind: str = "unix"


def _parts(text: str) -> list[list[str]]:
    """
    The parts of a description: [value], or [key, value] for key=value.

    These are the rules of Twisted's endpoints: ":" separates the parts, the
    first "=" of a part separates its key from its value, and a backslash
    makes the next character plain.
    """

    parts = []
    part: list[str] = []
    current = ""
    operators = ":="
    chars = iter(text)
    for char in chars:
        if char in operators:
            part.append(current)
            current = ""
            if char == ":":
                parts.append(part)
                part = []
                operators = ":="
            else:
                operators = ":"
        elif char == "\\":
            try:
                current += next(chars)
            except StopIteration:
                raise ValueError(f"{text} ends with a backslash") from None
        else:
            current += char
    part.append(current)
    parts.append(part)
    return parts


def parse_socket(text: str) -> Socket:
    """
    The socket of a description, as ``unix:PATH:protocol=text``: its type,
    its path, or ``address=PATH``, and its protocol, text if left out.

    Raise ValueError if text isn't one; str() says why, to the user.
    """

    parts = _parts(text)
    args = [part[0] for part in parts if len(part) == 1]
    if not args:
        raise ValueError(
            f"{text} needs its type and its path, as unix:~/labs/lab1.sock"
        )
    kind = args[0].lower()
    if kind not in TYPES:
        if TYPE.fullmatch(kind):
            raise ValueError(
                f"{text}: only unix sockets for now, as unix:PATH"
            )
        # a path, as the option took before descriptions
        if len(parts) == 1:
            raise ValueError(f"{text} needs its type: unix:{text}")
        raise ValueError(f"{text} needs its type, as unix:PATH")
    keywords: dict[str, str] = {}
    for part in parts:
        if len(part) == 1:
            continue
        key, value = part
        if key not in KEYWORDS:
            raise ValueError(
                f"{text}: unknown keyword {key}; the keywords are"
                f" {' and '.join(KEYWORDS)}"
            )
        if key in keywords:
            raise ValueError(f"{text}: {key} is given twice")
        keywords[key] = value
    paths = args[1:]
    if "address" in keywords:
        paths.append(keywords["address"])
    if len(paths) > 1:
        raise ValueError(
            f"{text}: one path, then the keywords" f" {' and '.join(KEYWORDS)}"
        )
    if not paths or not paths[0]:
        raise ValueError(f"{text} needs a path, as unix:~/labs/lab1.sock")
    protocol = keywords.get("protocol", TEXT).lower()
    if protocol not in PROTOCOLS:
        raise ValueError(f"{text}: the protocol is {' or '.join(PROTOCOLS)}")
    return Socket(paths[0], protocol, kind)


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
    check_cwd(cwd)
    return text, cwd


def check_cwd(cwd: object) -> None:
    """Raise BadRequest if cwd, the folder of a request, isn't absolute."""

    if cwd is not None and not (isinstance(cwd, str) and os.path.isabs(cwd)):
        raise BadRequest(_('Not a request: "cwd" is not an absolute path'))


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


def in_runtime_dir(path: str) -> bool:
    """Whether path is in the runtime folder, as the default socket."""

    return os.path.dirname(path) == locations.runtime_dir()


def check_path(path: str, private: bool) -> None:
    """
    Raise Unusable if a socket can't be at path.

    A private folder, the runtime folder, must be a folder of yours that
    nobody else can write in: in the temporary folder, where it is without
    XDG_RUNTIME_DIR, another user could have made it first. Another folder
    must be there.
    """

    check_length(path)
    folder = os.path.dirname(path)
    try:
        # the runtime folder can't be a link; another folder can
        info = os.lstat(folder) if private else os.stat(folder)
    except FileNotFoundError:
        raise Unusable(
            _("The folder {folder} doesn't exist").format(folder=folder)
        ) from None
    if not stat.S_ISDIR(info.st_mode):
        raise Unusable(_("{folder} isn't a folder").format(folder=folder))
    if not private:
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
