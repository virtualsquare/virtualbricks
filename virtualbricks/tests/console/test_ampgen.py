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

"""The typed commands of the AMP socket, written from the table."""

import io
import os
import subprocess
import sys

from twisted.protocols import amp
from twisted.trial import unittest

from virtualbricks.console import ampcommands, ampgen, ampwire
from virtualbricks.console.command import (
    COMMANDS,
    Arg,
    Flag,
    Number,
    Pair,
    command,
    keyword,
)
from virtualbricks.tests import DATA
from virtualbricks.tests.console import own_commands


def nothing(context, **values):
    return values


def _parse(line):
    """A line of a record: its name, arguments, answer and errors."""

    words = line.split()
    arrow, bang = words.index("->"), words.index("!")
    arguments = {}
    for word in words[1:arrow]:
        key, _, kind = word.partition(":")
        arguments[key] = (kind.rstrip("?"), kind.endswith("?"))
    answer = {}
    for word in words[arrow + 1 : bang]:
        key, _, kind = word.partition(":")
        answer[key] = (kind.rstrip("?"), kind.endswith("?"))
    return words[0], arguments, answer, set(words[bang + 1 :])


def breaks(old, new):
    """
    What changes from the record old to the record new in a way that isn't
    additive: a program of old would be refused, or misread.
    """

    before = {name: rest for name, *rest in map(_parse, old.splitlines())}
    after = {name: rest for name, *rest in map(_parse, new.splitlines())}
    found = []
    for name, (arguments, answer, errors) in before.items():
        if name not in after:
            found.append(f"{name} is gone")
            continue
        now_arguments, now_answer, now_errors = after[name]
        for key, (kind, optional) in arguments.items():
            if key not in now_arguments:
                found.append(f"{name} takes no {key}")
            elif now_arguments[key][0] != kind:
                found.append(f"{name} takes {key} of another type")
            elif optional and not now_arguments[key][1]:
                found.append(f"{name} needs {key}")
        for key, (kind, optional) in now_arguments.items():
            if key not in arguments and not optional:
                found.append(f"{name} needs {key}, a new argument")
        for key, (kind, optional) in answer.items():
            if key not in now_answer:
                found.append(f"{name} answers no {key}")
            elif now_answer[key][0] != kind:
                found.append(f"{name} answers {key} of another type")
            elif not optional and now_answer[key][1]:
                found.append(f"{name} may leave out {key}")
        for key, (kind, optional) in now_answer.items():
            if key not in answer and not optional:
                found.append(f"{name} answers {key}, always")
        if errors != now_errors:
            found.append(f"{name} has other errors")
    return found


class TestTheFile(unittest.TestCase):

    def test_written_from_the_table(self):
        with open(ampgen.PATH, encoding="utf-8") as fp:
            text = fp.read()
        self.assertEqual(
            text,
            ampgen.source(),
            "ampcommands.py is not the table's: run"
            " python -m virtualbricks.console.ampgen",
        )

    def test_a_command_for_each(self):
        names = [ampgen.name(command) for command in COMMANDS]
        self.assertEqual(len(set(names)), len(COMMANDS))
        for name in ("Hello", "Run", "Challenge", "Authenticate"):
            self.assertNotIn(name, names)
        for found in COMMANDS:
            typed = getattr(ampcommands, ampgen.name(found))
            self.assertTrue(issubclass(typed, amp.Command))
            self.assertEqual(typed.commandName, ampgen.name(found).encode())
            self.assertEqual(
                [key.decode() for key, _ in typed.arguments],
                [keyword(arg) for arg in found.args]
                + [keyword(flag) for flag in found.flags]
                + ["cwd"],
            )
            self.assertIs(typed.errors, ampcommands.ERRORS)
            self.assertIs(typed.response, ampcommands.LINES)
        self.assertEqual(ampgen.name(COMMANDS[0]), "BrickTypes")

    def test_the_types(self):
        def types(name):
            typed = getattr(ampcommands, name)
            return {key.decode(): kind for key, kind in typed.arguments}

        found = types("BrickSet")
        self.assertIsInstance(found["name"], amp.Unicode)
        self.assertFalse(found["name"].optional)
        self.assertIsInstance(found["key_value"], amp.AmpList)
        self.assertIsInstance(found["cwd"], amp.Unicode)
        self.assertTrue(found["cwd"].optional)
        found = types("EventActionRemove")
        self.assertIsInstance(found["n"], amp.ListOf)
        self.assertIsInstance(found["n"].elementType, amp.Integer)
        found = types("EventActionAdd")
        self.assertIsInstance(found["at"], amp.Integer)
        self.assertTrue(found["at"].optional)
        self.assertTrue(found["subject"].optional)
        found = types("ProjectDelete")
        self.assertIsInstance(found["force"], amp.Boolean)
        self.assertTrue(found["force"].optional)
        found = types("Help")
        self.assertIsInstance(found["topic"], amp.ListOf)
        self.assertTrue(found["topic"].optional)
        self.assertEqual(list(types("Status")), ["cwd"])

    def test_the_errors(self):
        # the more precise first: Twisted sends the first that matches
        self.assertEqual(
            list(ampcommands.ERRORS),
            [
                ampcommands.NotFound,
                ampcommands.BadArgument,
                ampcommands.ProtocolNeeded,
                ampwire.CommandFailed,
                ampwire.AnswerTooLong,
                ampwire.TokenNeeded,
            ],
        )
        self.assertTrue(
            issubclass(ampcommands.NotFound, ampwire.CommandFailed)
        )
        self.assertTrue(
            issubclass(ampcommands.BadArgument, ampwire.CommandFailed)
        )
        self.assertFalse(
            issubclass(ampcommands.ProtocolNeeded, ampwire.CommandFailed)
        )
        self.assertEqual(ampcommands.PROTOCOL, ampgen.PROTOCOL)

    def test_what_it_loads(self):
        # a program imports the commands: no reactor, and nothing of
        # Virtualbricks but ampwire
        code = (
            "import sys\n"
            "from virtualbricks.console import ampcommands\n"
            "print('twisted.internet.reactor' in sys.modules)\n"
            "print(sorted(name for name in sys.modules"
            " if name.startswith('virtualbricks')))\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            encoding="utf-8",
            check=True,
        )
        self.assertEqual(
            result.stdout.splitlines(),
            [
                "False",
                "['virtualbricks', 'virtualbricks.console',"
                " 'virtualbricks.console.ampcommands',"
                " 'virtualbricks.console.ampwire']",
            ],
        )


class TestWriting(unittest.TestCase):
    """The file, from a table of the test's own."""

    def setUp(self):
        own_commands(self)

    def test_a_command(self):
        command(
            "event",
            "action remove",
            Arg("NAME"),
            Arg("N", Number(), many=True),
            flags=[Flag("force")],
            help="Remove actions",
        )(nothing)
        self.assertEqual(
            ampgen.source().split("\n\n\n")[-1],
            "class EventActionRemove(amp.Command):\n"
            '    """event action remove NAME N… [--force]: Remove'
            ' actions."""\n'
            "\n"
            "    arguments = [\n"
            '        (b"name", amp.Unicode()),\n'
            '        (b"n", amp.ListOf(amp.Integer())),\n'
            '        (b"force", amp.Boolean(optional=True)),\n'
            "        CWD,\n"
            "    ]\n"
            "    response = LINES\n"
            "    errors = ERRORS\n",
        )
        # then those of the windows of another machine
        self.assertEqual(
            ampgen.record().splitlines()[0],
            "EventActionRemove name:str n:[int] force:bool? cwd:str?"
            " -> lines:[str] ! NOT_FOUND BAD_ARGUMENT PROTOCOL_NEEDED"
            " COMMAND_FAILED ANSWER_TOO_LONG TOKEN_NEEDED",
        )

    def test_a_kind_it_cant_write(self):
        # KEY=VALUE once, not as the last argument that repeats
        command("brick", "odd", Arg("KEY=VALUE", Pair()), help="h")(nothing)
        self.assertRaises(ValueError, ampgen.source)


class TestMain(unittest.TestCase):

    def test_write(self):
        path = self.mktemp()
        self.patch(ampgen, "PATH", path)
        self.assertEqual(ampgen.main([]), 0)
        with open(path, encoding="utf-8") as fp:
            self.assertEqual(fp.read(), ampgen.source())

    def test_record(self):
        out = io.StringIO()
        self.patch(sys, "stdout", out)
        self.assertEqual(ampgen.main(["--record"]), 0)
        self.assertEqual(out.getvalue(), ampgen.record())

    def test_usage(self):
        err = io.StringIO()
        self.patch(sys, "stderr", err)
        self.assertEqual(ampgen.main(["--help"]), 2)
        self.assertEqual(
            err.getvalue(),
            "usage: python -m virtualbricks.console.ampgen [--record]\n",
        )


class TestTheRecord(unittest.TestCase):
    """What a change of the table does to the protocol."""

    def test_a_class(self):
        class Show(amp.Command):
            arguments = [
                (b"name", amp.Unicode()),
                (b"n", amp.ListOf(amp.Integer(), optional=True)),
                (b"key_value", amp.AmpList(ampcommands.PAIR)),
                (b"all", amp.Boolean(optional=True)),
            ]
            response = [(b"text", amp.Unicode(optional=True))]
            errors = {ampwire.CommandFailed: b"COMMAND_FAILED"}

        class Told(amp.Command):
            arguments = [(b"what", amp.Unicode())]
            requiresAnswer = False

        self.assertEqual(
            ampgen.class_record(Show),
            "Show name:str n:[int]? key_value:pairs all:bool? -> text:str?"
            " ! COMMAND_FAILED",
        )
        # a push: no answer
        self.assertEqual(ampgen.class_record(Told), "Told what:str -> !")
        self.assertEqual(
            breaks("Told what:str -> !", "Told what:str -> !"), []
        )

    def test_the_protocol_is_kept(self):
        path = os.path.join(DATA, f"amp-protocol-{ampgen.PROTOCOL}.txt")
        with open(path, encoding="utf-8") as fp:
            recorded = fp.read()
        self.assertEqual(
            breaks(recorded, ampgen.record()),
            [],
            f"the typed commands changed, and protocol {ampgen.PROTOCOL}"
            " with them: raise ampgen.PROTOCOL and ampwire.PROTOCOLS, and"
            " write the record of the new one with"
            " python -m virtualbricks.console.ampgen --record",
        )

    def test_additive(self):
        errors = "! NOT_FOUND COMMAND_FAILED"
        old = f"BrickSet name:str key_value:pairs cwd:str? -> lines:[str] {errors}"
        self.assertEqual(breaks(old, old), [])
        # a command, an optional argument, an optional answer
        new = (
            f"BrickSet name:str key_value:pairs force:bool? cwd:str?"
            f" -> lines:[str] data:str? {errors}\n"
            f"BrickNew kind:str -> lines:[str] {errors}"
        )
        self.assertEqual(breaks(old, new), [])
        # an argument that a program must send no more
        new = f"BrickSet name:str? key_value:pairs -> lines:[str] {errors}"
        self.assertEqual(breaks(old, new), ["BrickSet takes no cwd"])

    def test_not_additive(self):
        errors = "! NOT_FOUND COMMAND_FAILED"
        old = f"BrickSet name:str key_value:pairs cwd:str? -> lines:[str] {errors}"
        cases = {
            f"BrickNew kind:str -> lines:[str] {errors}": ["BrickSet is gone"],
            f"BrickSet name:[str] key_value:pairs cwd:str? -> lines:[str]"
            f" {errors}": ["BrickSet takes name of another type"],
            f"BrickSet name:str key_value:pairs cwd:str -> lines:[str]"
            f" {errors}": ["BrickSet needs cwd"],
            f"BrickSet name:str key_value:pairs at:int cwd:str?"
            f" -> lines:[str] {errors}": ["BrickSet needs at, a new argument"],
            f"BrickSet name:str key_value:pairs cwd:str? -> text:str"
            f" {errors}": [
                "BrickSet answers no lines",
                "BrickSet answers text, always",
            ],
            f"BrickSet name:str key_value:pairs cwd:str? -> lines:[str]?"
            f" {errors}": ["BrickSet may leave out lines"],
            "BrickSet name:str key_value:pairs cwd:str? -> lines:[str]"
            " ! NOT_FOUND BAD_ARGUMENT COMMAND_FAILED": [
                "BrickSet has other errors"
            ],
        }
        for new, found in cases.items():
            self.assertEqual(breaks(old, new), found, new)
