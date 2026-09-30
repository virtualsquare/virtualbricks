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

"""The AMP commands of the windows of another machine, in protocol 2."""

import subprocess
import sys

from twisted.protocols import amp
from twisted.trial import unittest

from virtualbricks.console import ampcommands, ampgen, ampwire
from virtualbricks.console.command import COMMANDS
from virtualbricks.remote import commands


class TestCommands(unittest.TestCase):

    def test_names_of_their_own(self):
        names = [
            command.commandName
            for command in commands.FROM_PROGRAM + commands.PUSHES
        ]
        self.assertEqual(len(set(names)), len(names))
        others = {ampgen.name(command).encode() for command in COMMANDS}
        others |= {
            command.commandName
            for command in (
                ampwire.Hello,
                ampwire.Run,
                ampwire.Challenge,
                ampwire.Authenticate,
            )
        }
        self.assertEqual(set(names) & others, set())

    def test_protocol_2(self):
        self.assertEqual(commands.PROTOCOL, ampcommands.PROTOCOL)
        self.assertIn(commands.PROTOCOL, ampwire.PROTOCOLS)

    def test_the_pushes_need_no_answer(self):
        for push in commands.PUSHES:
            self.assertTrue(issubclass(push, amp.Command))
            self.assertFalse(push.requiresAnswer, push)
            self.assertEqual(push.errors, {}, push)
        for command in commands.FROM_PROGRAM:
            self.assertTrue(command.requiresAnswer)
            self.assertIs(command.errors, ampcommands.ERRORS)

    def test_the_answers_of_qemu(self):
        # a value each: the questions of programs.py, which the commands
        # don't import
        from virtualbricks.programs import QEMU_QUESTIONS

        self.assertEqual(commands.QEMU_ANSWERS, tuple(QEMU_QUESTIONS))

    def test_in_the_record(self):
        lines = ampgen.record().splitlines()
        for command in commands.FROM_PROGRAM + commands.PUSHES:
            self.assertIn(ampgen.class_record(command), lines)

    def test_what_it_loads(self):
        # a program imports the commands: no reactor, and of Virtualbricks
        # only ampwire and ampcommands
        code = (
            "import sys\n"
            "from virtualbricks.remote import commands\n"
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
                " 'virtualbricks.console.ampwire', 'virtualbricks.remote',"
                " 'virtualbricks.remote.commands']",
            ],
        )
