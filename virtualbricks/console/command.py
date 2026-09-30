# -*- test-case-name: virtualbricks.tests.console.test_command -*-
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
The commands of the console, and the kinds of their arguments.

A command is a noun, a verb and arguments: ``brick start NAME...``. Each
module of a noun declares its commands with :func:`command`, which records
them in ``COMMANDS``: the parser reads a line with them, ``help`` writes
them, and the terminal completes them.

A command's function takes the :class:`Context` and its arguments by name,
and returns the lines of its answer, or a Deferred of them. A command that
can't be done raises :class:`CommandError`, whose text is the message.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Sequence
from typing import Any

import attr

from virtualbricks.i18n import N_, _


class CommandError(Exception):
    """
    A command that can't be done; str() says why, to the user. lines are
    what it did before, as starting the first of three bricks.
    """

    def __init__(self, message: str, lines: Sequence[str] = ()):
        super().__init__(message)
        self.lines = list(lines)


@attr.define
class Context:
    """What a command works on: the factory of the open project."""

    factory: Any
    # the reactor, or a clock in the tests: what a command waits with
    reactor: Any = None
    # the terminal, when the command was typed there
    terminal: Any = None
    # the folder that the paths of the command are read from, None for the
    # folder of Virtualbricks: that of --command, for a command sent there
    cwd: str | None = None

    def path(self, word: str) -> str:
        """The absolute path that word, a path the user typed, names."""

        folder = self.cwd if self.cwd is not None else os.getcwd()
        return os.path.normpath(os.path.join(folder, os.path.expanduser(word)))


class ArgKind:
    """How a word of a command is read, and what it can be."""

    def read(self, context: Context, word: str) -> object:
        return word

    def candidates(self, context: Context, done: dict) -> list[str]:
        """The words it can be, for the completion; done is what's read."""

        return []


class Text(ArgKind):
    """Any word: a name to give, a command, a path."""


class Number(ArgKind):
    def read(self, context: Context, word: str) -> object:
        try:
            return int(word)
        except ValueError:
            raise CommandError(
                _('"{word}" is not a number').format(word=word)
            ) from None


class Choice(ArgKind):
    def __init__(self, *words: str):
        self.words = words

    def read(self, context: Context, word: str) -> object:
        if word not in self.words:
            raise CommandError(
                _('"{word}" is not one of {words}').format(
                    word=word, words=", ".join(self.words)
                )
            )
        return word

    def candidates(self, context: Context, done: dict) -> list[str]:
        return list(self.words)


class Named(ArgKind):
    """The name of something of the project, read as the thing itself."""

    def __init__(
        self,
        find: Callable[[Any, str], object],
        names: Callable[[Any], Sequence[str]],
        missing: str,
    ):
        self.find = find
        self.names = names
        # the message when there is none of that name, with {name}
        self.missing = missing

    def read(self, context: Context, word: str) -> object:
        found = self.find(context.factory, word)
        if found is None:
            raise CommandError(_(self.missing).format(name=word))
        return found

    def candidates(self, context: Context, done: dict) -> list[str]:
        return sorted(self.names(context.factory))


class Pair(ArgKind):
    """KEY=VALUE, read as the pair; the command checks the key."""

    def read(self, context: Context, word: str) -> object:
        key, sep, value = word.partition("=")
        if not sep or not key:
            raise CommandError(
                _('"{word}" is not KEY=VALUE').format(word=word)
            )
        return key, value


class KeyValues(Pair):
    """
    KEY=VALUE, whose keys the completion knows: keys(context, done) gives
    them, kind(context, done, key) the kind of a key's values, None if none.
    """

    def __init__(
        self,
        keys: Callable[[Context, dict], Sequence[str]],
        kind: Callable[[Context, dict, str], Any],
    ):
        self.keys = keys
        self.kind = kind

    def candidates(self, context: Context, done: dict) -> list[str]:
        return [f"{key}=" for key in self.keys(context, done)]

    def values(self, context: Context, done: dict, key: str) -> list[str]:
        """The values the completion offers for key."""

        kind = self.kind(context, done, key)
        return [] if kind is None else values_of(kind, context.factory)


def values_of(kind: Any, factory: Any) -> list[str]:
    """What a value of a kind of the schema can be, where it's a short list."""

    from virtualbricks.config.schema import Bool, Choice as SchemaChoice, Ref

    if isinstance(kind, Bool):
        return ["true", "false"]
    if isinstance(kind, SchemaChoice):
        return list(kind.choices)
    if isinstance(kind, Ref) and kind.target == "event":
        return [event.name for event in factory.events]
    if isinstance(kind, Ref) and kind.target == "image":
        return [image.name for image in factory.images]
    return []


@attr.frozen
class Arg:
    """An argument: its name in the help, its kind, how many."""

    name: str
    kind: ArgKind = attr.field(factory=Text)
    # one or more: the last argument only
    many: bool = False
    optional: bool = False

    def usage(self) -> str:
        text = self.name + ("…" if self.many else "")
        return f"[{text}]" if self.optional else text


@attr.frozen
class Flag:
    """An option of a command, as --force, or --at N with its value."""

    name: str
    value: Arg | None = None

    def usage(self) -> str:
        if self.value is None:
            return f"[--{self.name}]"
        return f"[--{self.name} {self.value.name}]"


@attr.frozen
class Command:
    """A command: noun and verb, its arguments and options, its help."""

    # no noun for the words of their own: help, status, quit...
    noun: str | None
    # one word, or two for a part of something: "card add"
    verb: str
    args: tuple[Arg, ...]
    flags: tuple[Flag, ...]
    # one line, marked with N_() and translated when shown
    help: str
    function: Callable[..., Any]
    example: str = ""

    @property
    def words(self) -> tuple[str, ...]:
        noun = () if self.noun is None else (self.noun,)
        return noun + tuple(self.verb.split())

    @property
    def name(self) -> str:
        return " ".join(self.words)

    def usage(self) -> str:
        parts = [self.name]
        parts += [arg.usage() for arg in self.args]
        parts += [flag.usage() for flag in self.flags]
        return " ".join(parts)


COMMANDS: list[Command] = []

# The nouns, with what their commands do, for help.
NOUN_HELP = {
    "brick": N_("Make, change, start, stop and delete bricks"),
    "event": N_("Make and change events, and start them"),
    "image": N_("The disk images of the project"),
    "setting": N_("The settings of Virtualbricks and of the project"),
    "project": N_("The projects of the workspace"),
}


def _python_name(name: str) -> str:
    """The keyword of an argument: "KEY=VALUE" is key_value."""

    return re.sub(r"\W+", "_", name.lower()).strip("_")


def keyword(item: Arg | Flag) -> str:
    return _python_name(item.name)


def command(
    noun: str | None,
    verb: str,
    *args: Arg,
    flags: Sequence[Flag] = (),
    help: str,
    example: str = "",
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Declare the function below as the command noun verb."""

    def record(function: Callable[..., Any]) -> Callable[..., Any]:
        COMMANDS.append(
            Command(noun, verb, args, tuple(flags), help, function, example)
        )
        return function

    return record


def nouns() -> list[str]:
    return sorted({c.noun for c in COMMANDS if c.noun is not None})


def of_noun(noun: str | None) -> list[Command]:
    """The commands of noun, in the order of their modules."""

    return [c for c in COMMANDS if c.noun == noun]


def find(words: Sequence[str]) -> tuple[Command | None, int]:
    """The command the words start with, and how many words it takes."""

    best: tuple[Command | None, int] = (None, 0)
    for candidate in COMMANDS:
        size = len(candidate.words)
        if tuple(words[:size]) == candidate.words and size > best[1]:
            best = (candidate, size)
    return best
