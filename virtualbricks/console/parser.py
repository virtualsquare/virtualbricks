# -*- test-case-name: virtualbricks.tests.console.test_parser -*-
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
A line of the console, read as a command and its arguments.

The words are split as the shell splits them: quotes keep spaces, a
backslash escapes, ``#`` starts a comment. The first words are the noun and
the verb, the rest the arguments, in their order, and the options, anywhere
after the verb: ``--force``, or ``--at 2`` with its value.
"""

from __future__ import annotations

import shlex
from collections.abc import Sequence

import attr

from virtualbricks.console.command import (
    Command,
    CommandError,
    Context,
    find,
    keyword,
    nouns,
    of_noun,
)
from virtualbricks.i18n import _


@attr.frozen
class Parsed:
    """A command, and its arguments read, by keyword."""

    command: Command
    values: dict


def split(line: str) -> list[str]:
    """The words of line, as the shell splits them."""

    try:
        return shlex.split(line, comments=True)
    except ValueError:
        raise CommandError(_("A quote isn't closed")) from None


def _not_a_command(words: Sequence[str]) -> CommandError:
    first = words[0]
    if first in nouns():
        verbs = ", ".join(c.verb for c in of_noun(first))
        if len(words) == 1:
            return CommandError(
                _("{noun} needs a verb: {verbs}").format(
                    noun=first, verbs=verbs
                )
            )
        return CommandError(
            _("{noun} has no {verb}: its verbs are {verbs}").format(
                noun=first, verb=words[1], verbs=verbs
            )
        )
    return CommandError(
        _("No command {word}; type help for the commands").format(word=first)
    )


def parse(context: Context, line: str) -> Parsed | None:
    """The command of line with its arguments read; None if it has none."""

    words = split(line)
    if not words:
        return None
    command, used = find(words)
    if command is None:
        raise _not_a_command(words)
    values: dict = {}
    positional = []
    rest = list(words[used:])
    while rest:
        word = rest.pop(0)
        if not (word.startswith("--") and len(word) > 2):
            positional.append(word)
            continue
        flag = next((f for f in command.flags if f.name == word[2:]), None)
        if flag is None:
            raise CommandError(
                _("{command} has no option {option}").format(
                    command=command.name, option=word
                )
            )
        if flag.value is None:
            values[keyword(flag)] = True
        elif not rest:
            raise CommandError(
                _("{option} needs {value}").format(
                    option=word, value=flag.value.name
                )
            )
        else:
            values[keyword(flag)] = flag.value.kind.read(context, rest.pop(0))
    for flag in command.flags:
        values.setdefault(keyword(flag), None if flag.value else False)
    for arg in command.args:
        key = keyword(arg)
        if not positional:
            if not arg.optional:
                raise CommandError(
                    _("{usage}: {name} is missing").format(
                        usage=command.usage(), name=arg.name
                    )
                )
            values[key] = [] if arg.many else None
        elif arg.many:
            values[key] = [arg.kind.read(context, w) for w in positional]
            positional = []
        else:
            values[key] = arg.kind.read(context, positional.pop(0))
    if positional:
        raise CommandError(
            _("{usage}: too many words: {words}").format(
                usage=command.usage(), words=" ".join(positional)
            )
        )
    return Parsed(command, values)
