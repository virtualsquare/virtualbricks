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

"""The commands without a noun."""

from virtualbricks.console.command import Arg, command
from virtualbricks.console.general import help_
from virtualbricks.tests.console import ConsoleTestCase, own_commands


class TestHelp(ConsoleTestCase):

    def setUp(self):
        super().setUp()
        own_commands(self)
        # help itself, and two commands of a noun
        command(
            None,
            "help",
            Arg("TOPIC", many=True, optional=True),
            help="The commands, a noun's verbs, or one command",
        )(help_)
        command(
            "brick",
            "start",
            Arg("NAME", many=True),
            help="Start bricks",
            example="brick start sw1",
        )(lambda context, name: None)
        command("brick", "list", help="The bricks")(lambda context: None)

    def test_overview(self):
        self.assertEqual(
            self.run_line("help"),
            [
                "A command is a noun, a verb, then its arguments: brick start"
                " sw1.",
                "help NOUN lists the verbs of a noun, and help NOUN VERB tells"
                " about one command.",
                "",
                "brick  Make, change, start, stop and delete bricks",
                "help   The commands, a noun's verbs, or one command",
            ],
        )

    def test_a_noun(self):
        self.assertEqual(
            self.run_line("help brick"),
            [
                "Make, change, start, stop and delete bricks",
                "",
                "brick start NAME…  Start bricks",
                "brick list         The bricks",
            ],
        )

    def test_a_command(self):
        self.assertEqual(
            self.run_line("help brick start"),
            ["brick start NAME…", "Start bricks", "Example: brick start sw1"],
        )
        self.assertEqual(
            self.run_line("help brick list"), ["brick list", "The bricks"]
        )
        self.assertEqual(self.run_line("help help")[0], "help [TOPIC…]")

    def test_nothing_of_the_kind(self):
        for line in ("help nope", "help brick stop", "help brick start sw1"):
            self.assertEqual(
                self.fails(line),
                f"No command {line[5:]}; type help for the commands",
            )
