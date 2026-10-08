# -*- test-case-name: virtualbricks.tests.console.test_dispatch -*-
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
Running a line of the console: its answer, or the reason it failed.

Every command fails with a :class:`CommandError`, whose text is for the
user. The errors of the project, as a brick that runs, keep their message;
anything else is logged with its traceback, being a bug or a program that
failed, and its message is the error.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from twisted.internet import defer
from twisted.internet.interfaces import IReactorTime
from twisted.logger import Logger
from twisted.python.failure import Failure

from virtualbricks import errors

# the modules of the nouns declare their commands
from virtualbricks.brickfactory import BrickFactory
from virtualbricks.console import (  # noqa: F401
    bricks,
    events,
    general,
    images,
    projects,
    settings,
)
from virtualbricks.console.command import Command, CommandError, Context
from virtualbricks.console.parser import Parsed, bind, line_of, parse
from virtualbricks.i18n import _

if TYPE_CHECKING:  # pragma: no cover
    from virtualbricks.console.terminal import ConsoleLine

logger = Logger()
command_failed = "The command {line!r} failed"


def _reason(failure: Failure, line: str) -> Failure:
    if failure.check(CommandError):
        return failure
    if failure.check(errors.Error):
        raise CommandError(failure.getErrorMessage())
    logger.failure(command_failed, failure, line=line)
    assert failure.type is not None, "a Failure has its exception's type"
    message = failure.getErrorMessage() or failure.type.__name__
    raise CommandError(
        _("{error}; the messages have the details").format(error=message)
    )


def run(
    factory: BrickFactory,
    line: str,
    reactor: IReactorTime | None = None,
    terminal: ConsoleLine | None = None,
    cwd: str | None = None,
) -> defer.Deferred[list[str]]:
    """
    Run a line of the console on factory; its paths are read from cwd, the
    folder of Virtualbricks if None.

    Return a Deferred of the lines of the answer, which fails with a
    CommandError.
    """

    if reactor is None:
        reactor = _reactor()
    context = Context(factory, reactor, terminal, cwd)
    try:
        parsed = parse(context, line)
    except CommandError:
        return defer.fail()
    if parsed is None:
        return defer.succeed([])
    return _call(context, parsed, line)


def run_command(
    factory: BrickFactory,
    command: Command,
    given: dict[str, Any],
    reactor: IReactorTime | None = None,
    cwd: str | None = None,
) -> defer.Deferred[list[str]]:
    """
    Run command on factory, with given, its arguments by keyword as a typed
    command of the AMP socket gives them; its paths are read from cwd.

    Raise a CommandError at once if the arguments don't read, a NotFound if
    one names nothing: nothing is done then. Otherwise, return a Deferred of
    the lines of the answer, which fails with a CommandError.
    """

    if reactor is None:
        reactor = _reactor()
    context = Context(factory, reactor, cwd=cwd)
    parsed = bind(context, command, given)
    return _call(context, parsed, line_of(command, given))


def _reactor() -> IReactorTime:
    """The reactor, imported when a command runs: not at import."""

    from twisted.internet import reactor

    return cast("IReactorTime", reactor)


def _call(
    context: Context, parsed: Parsed, line: str
) -> defer.Deferred[list[str]]:
    done = defer.maybeDeferred(
        parsed.command.function, context, **parsed.values
    )
    answer = done.addCallback(lambda lines: list(lines or []))
    return answer.addErrback(_reason, line)


def check(factory: BrickFactory, line: str) -> str | None:
    """Why line isn't a command the parser reads, or None if it is one."""

    try:
        parse(Context(factory), line)
    except CommandError as exc:
        return str(exc)
    return None
