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

"""A line read as a command and its arguments."""

from twisted.trial import unittest

from virtualbricks.console.command import (
    Arg,
    CommandError,
    Context,
    Flag,
    Number,
    Pair,
    command,
)
from virtualbricks.console.parser import complete, parse, split
from virtualbricks.tests.console import ConsoleTestCase, own_commands


def nothing(context, **values):
    return values


class TestSplit(unittest.TestCase):

    def test_words(self):
        self.assertEqual(split("brick  start sw1"), ["brick", "start", "sw1"])
        self.assertEqual(split(""), [])

    def test_quotes(self):
        self.assertEqual(
            split('brick set vm1 kernel_command_line="console=ttyS0 root=/"'),
            [
                "brick",
                "set",
                "vm1",
                "kernel_command_line=console=ttyS0 root=/",
            ],
        )
        self.assertEqual(split("a 'b c' d\\ e"), ["a", "b c", "d e"])

    def test_comments(self):
        self.assertEqual(split("brick list  # all of them"), ["brick", "list"])
        self.assertEqual(split("# nothing"), [])
        self.assertEqual(split("shell 'echo #1'"), ["shell", "echo #1"])

    def test_a_quote_not_closed(self):
        error = self.assertRaises(CommandError, split, 'brick set vm1 x="a')
        self.assertEqual(str(error), "A quote isn't closed")


class TestParse(unittest.TestCase):

    def setUp(self):
        own_commands(self)
        self.context = Context(factory=None)
        command(
            "brick",
            "set",
            Arg("NAME"),
            Arg("KEY=VALUE", Pair(), many=True),
            help="help",
        )(nothing)
        command(
            "event",
            "action add",
            Arg("NAME"),
            Arg("WHAT"),
            Arg("SUBJECT", optional=True),
            flags=[Flag("at", Arg("N", Number())), Flag("force")],
            help="help",
        )(nothing)
        command("brick", "list", help="help")(nothing)
        command(
            None, "help", Arg("TOPIC", many=True, optional=True), help="h"
        )(nothing)

    def parse(self, line):
        parsed = parse(self.context, line)
        return parsed.command.name, parsed.values

    def error(self, line):
        return str(self.assertRaises(CommandError, parse, self.context, line))

    def test_nothing(self):
        self.assertIsNone(parse(self.context, "   # a comment"))

    def test_many(self):
        self.assertEqual(
            self.parse("brick set sw1 ports=4 hub_mode=true"),
            (
                "brick set",
                {
                    "name": "sw1",
                    "key_value": [("ports", "4"), ("hub_mode", "true")],
                },
            ),
        )

    def test_optional_and_options(self):
        self.assertEqual(
            self.parse("event action add boot start sw1 --at 2"),
            (
                "event action add",
                {
                    "name": "boot",
                    "what": "start",
                    "subject": "sw1",
                    "at": 2,
                    "force": False,
                },
            ),
        )
        # the options anywhere after the verb; without the optional one
        self.assertEqual(
            self.parse("event action add --force boot start"),
            (
                "event action add",
                {
                    "name": "boot",
                    "what": "start",
                    "subject": None,
                    "at": None,
                    "force": True,
                },
            ),
        )
        self.assertEqual(self.parse("help"), ("help", {"topic": []}))

    def test_what_is_wrong(self):
        self.assertEqual(
            self.error("brick set sw1"),
            "brick set NAME KEY=VALUE…: KEY=VALUE is missing",
        )
        self.assertEqual(
            self.error("brick list sw1 sw2"),
            "brick list: too many words: sw1 sw2",
        )
        self.assertEqual(
            self.error("brick list --all"), "brick list has no option --all"
        )
        self.assertEqual(
            self.error("event action add boot start --at"),
            "--at needs N",
        )
        self.assertEqual(
            self.error("event action add boot start --at x"),
            '"x" is not a number',
        )
        self.assertEqual(
            self.error("brick set sw1 ports"), '"ports" is not KEY=VALUE'
        )

    def test_not_a_command(self):
        self.assertEqual(
            self.error("nope"), "No command nope; type help for the commands"
        )
        self.assertEqual(self.error("brick"), "brick needs a verb: set, list")
        self.assertEqual(
            self.error("brick stop sw1"),
            "brick has no stop: its verbs are set, list",
        )
        # a name is never a command
        self.assertEqual(
            self.error("sw1 start"),
            "No command sw1; type help for the commands",
        )


class TestComplete(ConsoleTestCase):
    """What Tab offers, with the commands of the console."""

    def setUp(self):
        super().setUp()
        self.factory.runtime_dir = "/run/vb"
        self.context = Context(self.factory)
        self.factory.new_brick("switch", "sw1")
        self.factory.new_brick("vm", "vm1")
        self.factory.new_event("boot")

    def complete(self, text):
        return complete(self.context, text)

    def test_the_words(self):
        self.assertEqual(
            self.complete(""),
            (
                "",
                [
                    "brick",
                    "event",
                    "help",
                    "image",
                    "project",
                    "quit",
                    "setting",
                    "source",
                    "status",
                ],
            ),
        )
        self.assertEqual(self.complete("bri"), ("bri", ["brick"]))
        self.assertEqual(self.complete("brick st"), ("st", ["start", "stop"]))
        # a verb of two words, a word at a time
        self.assertEqual(self.complete("brick ca"), ("ca", ["card"]))
        self.assertEqual(
            self.complete("brick card "), ("", ["add", "remove", "set"])
        )

    def test_the_arguments(self):
        self.assertEqual(self.complete("brick start "), ("", ["sw1", "vm1"]))
        # every name of a many
        self.assertEqual(self.complete("brick start sw1 v"), ("v", ["vm1"]))
        self.assertEqual(
            self.complete("brick new t"),
            ("t", ["tap", "tunnelclient", "tunnelserver"]),
        )
        self.assertEqual(self.complete("brick card add "), ("", ["vm1"]))
        self.assertEqual(
            self.complete("brick card add vm1 "),
            ("", ["hostonly", "plug", "socket"]),
        )
        self.assertEqual(self.complete("event show "), ("", ["boot"]))
        self.assertEqual(self.complete("brick list "), ("", []))

    def test_keys_and_values(self):
        self.assertEqual(
            self.complete("brick set sw1 "),
            (
                "",
                [
                    "fast_spanning_tree=",
                    "hub_mode=",
                    "icon=",
                    "on_start=",
                    "on_stop=",
                    "ports=",
                ],
            ),
        )
        self.assertEqual(
            self.complete("brick set vm1 cdrom="),
            ("cdrom=", ["cdrom=device", "cdrom=image", "cdrom=none"]),
        )
        self.assertEqual(
            self.complete("brick set sw1 hub_mode=t"),
            ("hub_mode=t", ["hub_mode=true"]),
        )
        self.assertEqual(
            self.complete("brick set sw1 on_start="),
            ("on_start=", ["on_start=boot"]),
        )
        self.assertEqual(
            self.complete("setting set tray"), ("tray", ["tray_icon="])
        )
        self.assertEqual(
            self.complete("brick unset vm1 mem"), ("mem", ["memory"])
        )

    def test_options_and_quotes(self):
        self.assertEqual(
            self.complete("event action add boot start sw1 --"),
            ("--", ["--at"]),
        )
        self.assertEqual(self.complete('brick set vm1 icon="a '), ("", []))
