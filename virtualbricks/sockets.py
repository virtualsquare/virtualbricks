# -*- test-case-name: virtualbricks.tests.test_sockets -*-
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
The sockets of ``--listen`` and ``--connect``: their descriptions, as
``unix:~/labs/lab1.sock:protocol=json`` or ``tcp:lab.example:8765``, which
:func:`parse_socket` reads into a :class:`Socket`. They follow the rules of
Twisted's endpoints, with the keywords of virtualbricks(1).

It imports only a little of the standard library: the command line reads
the descriptions before the rest of Virtualbricks is loaded. What a socket
needs to be opened, the checks of its path and its token, is in
:mod:`virtualbricks.console.wire`.
"""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Sequence
from typing import NamedTuple

# The protocols a socket speaks: the lines of JSON of
# virtualbricks.console.wire, and the commands of
# virtualbricks.console.ampwire.
JSON = "json"
AMP = "amp"
PROTOCOLS = (JSON, AMP)
# The types of socket.
TYPES = ("unix", "tcp", "ssl")
# The keywords of a description of each type, after its path or its port:
# of a socket to listen on, and of the one of --connect. Those of
# ssl are Twisted's, but caCertsDir, which only its clients have.
KEYWORDS = {
    "unix": ("address", "protocol"),
    "tcp": ("port", "interface", "protocol", "tokenFile"),
    "ssl": (
        "port",
        "interface",
        "protocol",
        "tokenFile",
        "privateKey",
        "certKey",
        "extraCertChain",
        "caCertsDir",
    ),
}
CLIENT_KEYWORDS = {
    "unix": ("address", "protocol"),
    "tcp": ("host", "port", "protocol", "tokenFile"),
    "ssl": (
        "host",
        "port",
        "protocol",
        "tokenFile",
        "caCertsDir",
        "privateKey",
        "certKey",
    ),
}
# The keywords that name a file, and the fields of Socket they fill.
FILES = {
    "tokenFile": "token_file",
    "privateKey": "private_key",
    "certKey": "cert",
    "extraCertChain": "chain",
    "caCertsDir": "ca_dir",
}
# What a type looks like, as unix, tcp or ssl.
TYPE = re.compile(r"[a-z][a-z0-9]*", re.IGNORECASE)
PORT = re.compile(r"[0-9]+")
# Where a network socket listens without interface=, and where --connect
# looks for it without a host: this machine.
LOOPBACK = "127.0.0.1"


class Socket(NamedTuple):
    """
    A socket to listen on or to talk to: its path, or its host and its port,
    its protocol and, for tcp and ssl, the file of its token; for ssl, the
    files of its certificate and of those it trusts.

    The host of a socket to listen on is the address of its interface; with
    --connect, it is the machine to talk to. The certificate of a socket to
    listen on is that of Virtualbricks, and its clients show one that
    ca_dir trusts; with --connect, the certificate is that of the client,
    which trusts the certificate of Virtualbricks by ca_dir.
    """

    path: str | None
    protocol: str = AMP
    kind: str = "unix"
    host: str | None = None
    port: int | None = None
    # None for the file of locations.token_file()
    token_file: str | None = None
    private_key: str | None = None
    # the file of private_key without it, which holds both
    cert: str | None = None
    chain: str | None = None
    ca_dir: str | None = None

    def uses_token(self) -> bool:
        """Whether a client proves that it knows the token."""

        if self.kind == "ssl":
            return self.ca_dir is None
        return self.kind == "tcp"

    def files(self) -> dict[str, str]:
        """The files of its keywords, by keyword, as tokenFile."""

        return {
            key: getattr(self, field)
            for key, field in FILES.items()
            if getattr(self, field) is not None
        }

    def where(self) -> str:
        """Where it is, for the messages: its path, or its host and port."""

        if self.kind == "unix":
            return str(self.path)
        return f"{self.host} port {self.port}"

    def name(self) -> str:
        """Its name in the log: the path, or the type, host and port."""

        if self.kind == "unix":
            return str(self.path)
        return f"{self.kind} {self.where()}"


def _and(words: Sequence[str]) -> str:
    words = list(words)
    if len(words) < 2:
        return "".join(words)
    return ", ".join(words[:-1]) + " and " + words[-1]


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


def parse_socket(text: str, client: bool = False) -> Socket:
    """
    The socket of a description: its type, its path or its port, and its
    keywords, as ``unix:PATH:protocol=json`` or ``tcp:8765``. The protocol
    is AMP if left out. With client, the description of
    --connect, which names the machine to talk to: ``tcp:HOST:PORT``, or
    ``tcp:PORT`` for this one.

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
                f"{text}: the types are {_and(TYPES)}, as unix:PATH or"
                " tcp:PORT"
            )
        # a path, as the option took before descriptions
        if len(parts) == 1:
            raise ValueError(f"{text} needs its type: unix:{text}")
        raise ValueError(f"{text} needs its type, as unix:PATH")
    allowed = (CLIENT_KEYWORDS if client else KEYWORDS)[kind]
    keywords: dict[str, str] = {}
    for part in parts:
        if len(part) == 1:
            continue
        key, value = part
        if key not in allowed:
            if client and key == "interface":
                raise ValueError(
                    f"{text}: --connect reaches the machine of host=, as"
                    f" {kind}:lab.example:8765; interface= is where"
                    " Virtualbricks listens"
                )
            raise ValueError(
                f"{text}: unknown keyword {key}; the keywords of {kind} are"
                f" {_and(allowed)}"
            )
        if key in keywords:
            raise ValueError(f"{text}: {key} is given twice")
        keywords[key] = value
    protocol = keywords.get("protocol", AMP).lower()
    if protocol not in PROTOCOLS:
        raise ValueError(f"{text}: the protocol is {' or '.join(PROTOCOLS)}")
    if kind == "unix":
        return Socket(_path(text, args[1:], keywords), protocol, kind)
    if client:
        host, port = _host_and_port(text, kind, args[1:], keywords)
    else:
        host, port = _interface_and_port(text, kind, args[1:], keywords)
    files: dict[str, str | None] = {}
    for key, field in FILES.items():
        if keywords.get(key) == "":
            raise ValueError(f"{text}: {key} needs a file")
        files[field] = keywords.get(key)
    if kind == "ssl" and not client and files["private_key"] is None:
        raise ValueError(
            f"{text} needs privateKey=FILE, the key of its certificate"
        )
    return Socket(None, protocol, kind, host, port, **files)


def _path(text: str, args: list[str], keywords: dict[str, str]) -> str:
    paths = list(args)
    if "address" in keywords:
        paths.append(keywords["address"])
    if len(paths) > 1:
        raise ValueError(
            f"{text}: one path, then the keywords" f" {_and(KEYWORDS['unix'])}"
        )
    if not paths or not paths[0]:
        raise ValueError(f"{text} needs a path, as unix:~/labs/lab1.sock")
    return paths[0]


def _port(text: str, kind: str, value: str | None) -> int:
    if not value:
        raise ValueError(f"{text} needs a port, as {kind}:8765")
    if not PORT.fullmatch(value) or not 1 <= int(value) <= 65535:
        raise ValueError(f"{text}: the port is a number from 1 to 65535")
    return int(value)


def _interface_and_port(
    text: str, kind: str, args: list[str], keywords: dict[str, str]
) -> tuple[str, int]:
    """The address and the port of a socket to listen on."""

    if len(args) > 1:
        raise ValueError(
            f"{text}: the address to listen on is interface={args[0]}"
        )
    given = keywords.get("port")
    if args:
        if given is not None:
            raise ValueError(f"{text}: port is given twice")
        given = args[0]
    port = _port(text, kind, given)
    try:
        address = ipaddress.ip_address(keywords.get("interface", LOOPBACK))
    except ValueError:
        raise ValueError(
            f"{text}: the interface is an IP address, as 127.0.0.1 or ::1"
        ) from None
    if kind == "tcp" and not address.is_loopback:
        raise ValueError(
            f"{text}: tcp listens on this machine only, as"
            " interface=127.0.0.1 or ::1; across the network, ssl"
        )
    return str(address), port


def _host_and_port(
    text: str, kind: str, args: list[str], keywords: dict[str, str]
) -> tuple[str, int]:
    """
    The machine and the port that --connect names, as Twisted's clients
    read them: HOST:PORT, host= and port=; PORT alone is this machine.
    """

    host = keywords.get("host")
    port = keywords.get("port")
    if len(args) == 2 and host is None and port is None:
        host, port = args
    elif len(args) == 1 and port is None:
        port = args[0]
    elif len(args) == 1 and host is None:
        host = args[0]
    elif args:
        raise ValueError(f"{text}: one host and one port, as {kind}:HOST:PORT")
    if host == "":
        raise ValueError(f"{text} needs a host, as {kind}:lab.example:8765")
    return host or LOOPBACK, _port(text, kind, port)
