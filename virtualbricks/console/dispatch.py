# -*- test-case-name: virtualbricks.tests.console.test_dispatch -*-
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
Running a line of the console: its answer, or the reason it failed.

Every command fails with a :class:`CommandError`, whose text is for the
user. The errors of the project, as a brick that runs, keep their message;
anything else is logged with its traceback, being a bug or a program that
failed, and its message is the error.
"""

from __future__ import annotations

from twisted.internet import defer
from twisted.logger import Logger

from virtualbricks import errors

# the modules of the nouns declare their commands
from virtualbricks.console import bricks, general  # noqa: F401
from virtualbricks.console.command import CommandError, Context
from virtualbricks.console.parser import parse
from virtualbricks.i18n import _

logger = Logger()
command_failed = "The command {line!r} failed"


def _reason(failure, line):
    if failure.check(CommandError):
        return failure
    if failure.check(errors.Error):
        raise CommandError(failure.getErrorMessage())
    logger.failure(command_failed, failure, line=line)
    message = failure.getErrorMessage() or failure.type.__name__
    raise CommandError(
        _("{error}; the messages have the details").format(error=message)
    )


def run(factory, line, reactor=None, terminal=None):
    """
    Run a line of the console on factory.

    Return a Deferred of the lines of the answer, which fails with a
    CommandError.
    """

    if reactor is None:
        from twisted.internet import reactor
    context = Context(factory, reactor, terminal)
    try:
        parsed = parse(context, line)
    except CommandError:
        return defer.fail()
    if parsed is None:
        return defer.succeed([])
    done = defer.maybeDeferred(
        parsed.command.function, context, **parsed.values
    )
    done.addCallback(lambda lines: list(lines or []))
    done.addErrback(_reason, line)
    return done
