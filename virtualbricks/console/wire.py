# -*- test-case-name: virtualbricks.tests.console.test_wire -*-
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
What the two ends of the control socket share: the messages of its
protocol, its tokens and the checks of the paths of its sockets; their
descriptions are in :mod:`virtualbricks.sockets`. It loads no Twisted, for
the client.

The JSON protocol is JSON Lines: UTF-8, an object on each line. On connecting,
the Virtualbricks that listens greets::

    {"protocol": 1, "version": "2.1.0", "pid": 4200, "project": "lab1"}

Then each request gets an answer, in order::

    {"line": "brick start sw1", "cwd": "/home/alice/labs"}
    {"ok": true, "lines": ["sw1 runs, process 4242"]}
    {"line": "brick start vm9"}
    {"ok": false, "lines": [], "error": "No brick named vm9"}

``cwd``, the folder that the paths of the command are read from, is
optional: without it, they are read from the folder of Virtualbricks.

A tcp socket answers only the clients that know its token, and so does an
ssl socket that doesn't ask them for certificates. Its first line
asks for a proof, with a nonce; the greeting comes once the proof is right,
with the proof of Virtualbricks, and the connection closes if it isn't::

    {"protocol": 1, "auth": "token", "nonce": "3f9a..."}
    {"nonce": "c41d...", "proof": "8e02..."}
    {"protocol": 1, "version": "2.1.0", "pid": 4200, "project": "lab1",
     "proof": "51b7..."}

Neither end sends the token: each proves that it knows it, with the HMAC of
both nonces under the token, see :func:`proof`.
"""

from __future__ import annotations

import hmac
import json
import os
import re
import secrets
import stat
from collections.abc import Sequence

from virtualbricks import locations
from virtualbricks.i18n import _

# The version of the protocol, in the greeting: a client that doesn't know
# it doesn't send anything.
PROTOCOL = 1
# The longest line a request can be; a longer one closes the connection.
MAX_LINE = 64 * 1024


# How a socket asks for the proof of its token, in its first line.
AUTH_TOKEN = "token"
# The fewest characters a token has; Virtualbricks makes tokens of 43.
TOKEN_MIN = 16
# How long a client has to prove that it knows the token, in seconds.
PROOF_TIMEOUT = 10
NONCE = re.compile(r"[0-9a-f]{32,128}")


class Unusable(Exception):
    """A socket path that can't be used; str() says why, to the user."""


class NoToken(Unusable):
    """The file of the token isn't there."""


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


def greeting(
    version: str, pid: int, project: str | None, proof: str | None = None
) -> dict:
    """Who answers; with the proof of the token, on a socket that has one."""

    message = {
        "protocol": PROTOCOL,
        "version": version,
        "pid": pid,
        "project": project,
    }
    if proof is not None:
        message["proof"] = proof
    return message


def new_nonce() -> str:
    return secrets.token_hex(32)


def challenge(nonce: str) -> dict:
    """The first line of a socket with a token: the proof, over nonce."""

    return {"protocol": PROTOCOL, "auth": AUTH_TOKEN, "nonce": nonce}


def proof(token: str, side: str, server_nonce: str, client_nonce: str) -> str:
    """
    The proof that side, "client" or "server", knows token: the HMAC-SHA256
    of both nonces under the token, in hex. Each side proves it over the
    same nonces, with its own name, so that neither proof is the other.
    """

    message = f"virtualbricks {side} {server_nonce} {client_nonce}"
    return hmac.new(token.encode(), message.encode(), "sha256").hexdigest()


def token_proof(nonce: str, proof: str) -> dict:
    """The answer of a client to the first line: its nonce and its proof."""

    return {"nonce": nonce, "proof": proof}


def read_proof(line: bytes) -> tuple[str, str]:
    """The nonce and the proof of a client; BadRequest if it isn't one."""

    try:
        message = decode(line)
    except ValueError:
        message = {}
    nonce = message.get("nonce")
    given = message.get("proof")
    if not (isinstance(nonce, str) and NONCE.fullmatch(nonce)):
        raise BadRequest(_('Not a proof: "nonce" and "proof" come first'))
    if not isinstance(given, str):
        raise BadRequest(_('Not a proof: "nonce" and "proof" come first'))
    return nonce, given


def same_proof(given: object, expected: str) -> bool:
    return isinstance(given, str) and hmac.compare_digest(
        given.encode(), expected.encode()
    )


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


def read_token(path: str) -> str:
    """
    The token of the file at path; raise NoToken if the file isn't there,
    Unusable if it can't be a token's: another user's, one that others can
    read or change, or one with a token too short.
    """

    try:
        with open(path, encoding="utf-8") as file:
            info = os.fstat(file.fileno())
            text = file.read(4096)
    except FileNotFoundError:
        raise NoToken(_("{path} doesn't exist").format(path=path)) from None
    except UnicodeDecodeError:
        raise Unusable(
            _("{path} isn't a token: a line of text").format(path=path)
        ) from None
    except OSError as exc:
        raise Unusable(f"{path}: {exc.strerror}") from None
    if not stat.S_ISREG(info.st_mode):
        raise Unusable(_("{path} isn't a file").format(path=path))
    if info.st_uid != os.getuid():
        raise Unusable(_("{path} isn't yours").format(path=path))
    if info.st_mode & 0o077:
        raise Unusable(
            _("Others can read or change {path}: chmod 600 {path}").format(
                path=path
            )
        )
    token = text.strip()
    if len(token) < TOKEN_MIN:
        raise Unusable(
            _(
                "The token of {path} has {size} characters; a token has at"
                " least {least}"
            ).format(path=path, size=len(token), least=TOKEN_MIN)
        )
    return token


def make_token(path: str) -> str:
    """Write a new token in a new file at path, only yours; return it."""

    token = secrets.token_urlsafe(32)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as file:
        file.write(token + "\n")
    return token


def check_length(path: str) -> None:
    """Raise Unusable if path is too long for a socket."""

    if len(os.fsencode(path)) > locations.SOCKET_PATH_MAX:
        raise Unusable(
            _("The socket's path, {path}, is longer than {size} bytes").format(
                path=path, size=locations.SOCKET_PATH_MAX
            )
        )


def in_runtime_dir(path: str) -> bool:
    """
    Whether path is in the runtime folder, or in the folder of a workspace
    there, as the default socket.
    """

    folder = os.path.dirname(path)
    runtime = locations.runtime_dir()
    return folder == runtime or os.path.dirname(folder) == runtime


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
