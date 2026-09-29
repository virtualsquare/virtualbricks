# -*- test-case-name: virtualbricks.tests.console.test_general -*-
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

"""The commands without a noun: help, status, source and quit."""

from __future__ import annotations

from twisted.internet import defer

from virtualbricks.console.command import (
    NOUN_HELP,
    Arg,
    ArgKind,
    CommandError,
    command,
    find,
    nouns,
    of_noun,
)
from virtualbricks.bricks import brickinfo, eventinfo
from virtualbricks.console.output import table
from virtualbricks.console.projects import refuse_running
from virtualbricks.i18n import N_, _
from virtualbricks.tools import is_running


class Topic(ArgKind):
    """A noun, then one of its verbs; or a command without a noun."""

    def candidates(self, context, done):
        words = done.get("topic") or []
        if not words:
            return nouns() + [c.verb for c in of_noun(None)]
        return [c.verb for c in of_noun(words[0])]


def _overview() -> list[str]:
    lines = [
        _("A command is a noun, a verb, then its arguments: brick start sw1."),
        _(
            "help NOUN lists the verbs of a noun, and help NOUN VERB tells"
            " about one command."
        ),
        "",
    ]
    rows = [(noun, _(NOUN_HELP[noun])) for noun in nouns()]
    rows += [(c.verb, _(c.help)) for c in of_noun(None)]
    return lines + table(rows)


def _command(found) -> list[str]:
    lines = [found.usage(), _(found.help)]
    if found.example:
        lines.append(_("Example: {example}").format(example=found.example))
    return lines


@command(
    None,
    "help",
    Arg("TOPIC", Topic(), many=True, optional=True),
    help=N_("The commands, a noun's verbs, or one command"),
    example="help brick set",
)
def help_(context, topic):
    if not topic:
        return _overview()
    found, used = find(topic)
    if found is not None and used == len(topic):
        return _command(found)
    if len(topic) == 1 and topic[0] in nouns():
        noun = topic[0]
        return [_(NOUN_HELP[noun]), ""] + table(
            [(c.usage(), _(c.help)) for c in of_noun(noun)]
        )
    raise CommandError(
        _("No command {words}; type help for the commands").format(
            words=" ".join(topic)
        )
    )


@command(
    None,
    "status",
    help=N_(
        "What runs: the bricks with their processes, the events that wait"
    ),
)
def status(context):
    factory = context.factory
    bricks = [
        (brick.name, brickinfo.kind(brick), str(brick.pid))
        for brick in factory.bricks
        if is_running(brick)
    ]
    events = [
        (
            event.name,
            _("{seconds} s").format(
                seconds=eventinfo.seconds_left(event, context.reactor)
            ),
        )
        for event in factory.iter_events()
        if is_running(event)
    ]
    if not bricks and not events:
        return [_("Nothing runs")]
    lines = (
        table(bricks, [_("BRICK"), _("KIND"), _("PROCESS")]) if bricks else []
    )
    if events:
        if lines:
            lines.append("")
        lines += table(events, [_("EVENT"), _("RUNS IN")])
    return lines


@command(
    None,
    "quit",
    help=N_("Quit Virtualbricks; refused while bricks run"),
)
def quit_(context):
    refuse_running(context.factory)
    context.factory.quit()


@command(
    None,
    "source",
    Arg("FILE"),
    help=N_("Run the commands of a file, one a line, up to the first error"),
    example="source ~/labs/start.vb",
)
@defer.inlineCallbacks
def source(context, file):
    from virtualbricks.console.dispatch import run

    path = context.path(file)
    try:
        with open(path, encoding="utf-8") as fp:
            text = fp.read()
    except OSError as exc:
        raise CommandError(
            _("{file} can't be read: {error}").format(
                file=file, error=exc.strerror
            )
        ) from None
    lines = []
    for number, line in enumerate(text.splitlines(), start=1):
        try:
            answer = yield run(
                context.factory,
                line,
                context.reactor,
                context.terminal,
                context.cwd,
            )
        except CommandError as exc:
            raise CommandError(
                f"{file}:{number}: {exc}", lines + exc.lines
            ) from None
        lines += answer
    return lines
