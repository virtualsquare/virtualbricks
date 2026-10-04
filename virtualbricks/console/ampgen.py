# -*- test-case-name: virtualbricks.tests.console.test_ampgen -*-
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
The typed commands of the AMP socket, written from the table of the console
into ampcommands.py, which a program imports without loading Virtualbricks.
When the table changes, ``python -m virtualbricks.console.ampgen`` writes the
file again, and the tests say whether the change keeps the protocol.

A command's name is its words, each with a capital: ``brick card add`` is
``BrickCardAdd``. Its arguments have the keywords of the parser, and their
types follow from their kinds: a Number is an integer, KEY=VALUE a list of
records of key and value, an argument that repeats a list, an option without
a value a boolean; the rest is text. Every command takes ``cwd`` too, and
answers the lines of the console. The record of the protocol has the
commands of the windows of another machine too, those of
:mod:`virtualbricks.remote.commands`, read from their classes.
"""

from __future__ import annotations

import os
import sys
import textwrap

# the modules of the nouns declare their commands
from twisted.protocols import amp

from virtualbricks.console import command as table, dispatch  # noqa: F401
from virtualbricks.console.command import (
    Arg,
    Choice,
    Command,
    Flag,
    Number,
    Pair,
    keyword,
)

# The protocol of the typed commands, in the answer to Hello. It changes when
# a command changes in a way that isn't additive (see the tests).
PROTOCOL = 2

PATH = os.path.join(os.path.dirname(__file__), "ampcommands.py")

# The types of the record of a protocol, and how the file declares them.
TYPES = {
    "str": "amp.Unicode({})",
    "int": "amp.Integer({})",
    "[str]": "amp.ListOf(amp.Unicode(){})",
    "[int]": "amp.ListOf(amp.Integer(){})",
    "pairs": "amp.AmpList(PAIR{})",
    "bool": "amp.Boolean({})",
}

# The errors of every typed command, by their codes, the more precise first:
# Twisted sends the code of the first class that matches.
ERRORS = (
    ("NotFound", "NOT_FOUND"),
    ("BadArgument", "BAD_ARGUMENT"),
    ("ProtocolNeeded", "PROTOCOL_NEEDED"),
    ("CommandFailed", "COMMAND_FAILED"),
    ("AnswerTooLong", "ANSWER_TOO_LONG"),
    ("TokenNeeded", "TOKEN_NEEDED"),
)

HEADER = '''\
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

# Written by virtualbricks/console/ampgen.py from the table of the console:
# don't change it by hand, run python -m virtualbricks.console.ampgen.

"""
The typed commands of the AMP socket, protocol {protocol}: one for each command
of the console, with its arguments. A connection speaks them once Hello has
agreed on {protocol}::

    vb = await endpoints.connectProtocol(endpoint, amp.AMP())
    await vb.callRemote(Hello, protocols=[PROTOCOL])
    answer = await vb.callRemote(BrickStart, name=["sw1", "vm1"])

Each answers the lines of the console. NotFound and BadArgument say that
nothing was done, CommandFailed that the command failed on the way.
Like ampwire, it loads nothing but Twisted's amp and ampwire, so that a
program can import it, or copy it.
"""

from twisted.protocols import amp

from virtualbricks.console.ampwire import (
    AnswerTooLong,
    CommandFailed,
    TokenNeeded,
)

# The protocol of these commands, which Hello agrees on.
PROTOCOL = {protocol}


class NotFound(CommandFailed):
    """A name of the command names nothing of the project."""


class BadArgument(CommandFailed):
    """An argument of the command isn't one it takes."""


class ProtocolNeeded(Exception):
    """The connection hasn't agreed on this protocol with Hello."""


ERRORS = {{
{errors}
}}
LINES = [(b"lines", amp.ListOf(amp.Unicode()))]
PAIR = [(b"key", amp.Unicode()), (b"value", amp.Unicode())]
CWD = (b"cwd", amp.Unicode(optional=True))
'''

CLASS = """

class {name}(amp.Command):
{doc}

    arguments = {arguments}
    response = LINES
    errors = ERRORS
"""


def name(command: Command) -> str:
    """The name of the AMP command of a command of the console."""

    return "".join(word.capitalize() for word in command.words)


def _type(arg: Arg) -> str:
    if isinstance(arg.kind, Pair):
        if not arg.many:
            raise ValueError(f"{arg.name}: KEY=VALUE without many")
        return "pairs"
    base = "int" if isinstance(arg.kind, Number) else "str"
    return f"[{base}]" if arg.many else base


def arguments(command: Command) -> list[tuple[str, str, bool]]:
    """The arguments of a command: keyword, type and whether optional."""

    found = [(keyword(arg), _type(arg), arg.optional) for arg in command.args]
    for flag in command.flags:
        kind = "bool" if flag.value is None else _type(flag.value)
        found.append((keyword(flag), kind, True))
    return found + [("cwd", "str", True)]


def record() -> str:
    """
    The lines of the record of the protocol, a line for each command: its
    arguments, ? after the optional ones, its answer and its errors; then
    those of the windows of another machine, the pushes without an answer.
    """

    from virtualbricks.remote import commands as windows

    lines = []
    for command in table.COMMANDS:
        words = [name(command)]
        words += [
            f"{key}:{kind}{'?' if optional else ''}"
            for key, kind, optional in arguments(command)
        ]
        words += ["->", "lines:[str]", "!"] + [code for _, code in ERRORS]
        lines.append(" ".join(words))
    for command in windows.FROM_PROGRAM + windows.PUSHES:
        lines.append(class_record(command))
    return "\n".join(lines) + "\n"


def _recorded_type(argument) -> str:
    if isinstance(argument, amp.ListOf):
        return f"[{_recorded_type(argument.elementType)}]"
    if isinstance(argument, amp.AmpList):
        return "pairs"
    return {
        amp.Unicode: "str",
        amp.String: "bytes",
        amp.Integer: "int",
        amp.Boolean: "bool",
    }[type(argument)]


def _recorded(pairs) -> list[str]:
    return [
        f"{key.decode()}:{_recorded_type(argument)}"
        f"{'?' if argument.optional else ''}"
        for key, argument in pairs
    ]


def class_record(command: type[amp.Command]) -> str:
    """The line of the record of a command, read from its class."""

    words = [command.commandName.decode()] + _recorded(command.arguments)
    words += ["->"] + _recorded(command.response) + ["!"]
    words += [code.decode() for code in command.errors.values()]
    return " ".join(words)


def _declared(key: str, kind: str, optional: bool) -> str:
    if key == "cwd":
        return "CWD"
    if kind == "bool":
        return f'(b"{key}", amp.Boolean(optional=True))'
    inner = "optional=True" if optional else ""
    if optional and kind in ("[str]", "[int]", "pairs"):
        inner = ", optional=True"
    return f'(b"{key}", {TYPES[kind].format(inner)})'


def _comment(command: Command, key: str) -> str:
    """The words of a choice, after its argument."""

    items: list[Arg | Flag] = [*command.args, *command.flags]
    for item in items:
        arg = item if isinstance(item, Arg) else item.value
        if (
            arg is not None
            and keyword(item) == key
            and isinstance(arg.kind, Choice)
        ):
            words = list(arg.kind.words)
            return "  # " + ", ".join(words[:-1]) + " or " + words[-1]
    return ""


def _doc(command: Command) -> str:
    text = f"{command.usage()}: {command.help}"
    if not text.endswith("."):
        text += "."
    if len(text) <= 69:
        return f'    """{text}"""'
    lines = textwrap.wrap(text, 72)
    body = "\n".join(f"    {line}" for line in lines)
    return f'    """\n{body}\n    """'


def _class(command: Command) -> str:
    found = arguments(command)
    if len(found) == 1:
        declared = "[CWD]"
    else:
        rows = [
            f"        {_declared(*argument)},{_comment(command, argument[0])}"
            for argument in found
        ]
        declared = "[\n" + "\n".join(rows) + "\n    ]"
    return CLASS.format(
        name=name(command), doc=_doc(command), arguments=declared
    )


def source() -> str:
    """The text of ampcommands.py."""

    errors = "\n".join(f'    {error}: b"{code}",' for error, code in ERRORS)
    text = HEADER.format(protocol=PROTOCOL, errors=errors)
    return text + "".join(_class(command) for command in table.COMMANDS)


def main(argv: list[str]) -> int:
    """
    Write ampcommands.py again; with --record, print the record of the
    protocol, for tests/data/amp-protocol-N.txt.
    """

    if argv == ["--record"]:
        sys.stdout.write(record())
        return 0
    if argv:
        sys.stderr.write(
            "usage: python -m virtualbricks.console.ampgen" " [--record]\n"
        )
        return 2
    with open(PATH, "w", encoding="utf-8") as fp:
        fp.write(source())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
