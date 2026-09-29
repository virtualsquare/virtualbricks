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

"""The commands, their arguments and how they are found."""

from twisted.trial import unittest

from virtualbricks.console.command import (
    Arg,
    Choice,
    CommandError,
    Context,
    Flag,
    Named,
    Number,
    Pair,
    command,
    find,
    keyword,
    nouns,
    of_noun,
)
from virtualbricks.tests.console import own_commands


def nothing(context, **values):
    return values


class TestDeclaring(unittest.TestCase):

    def setUp(self):
        self.commands = own_commands(self)

    def declare(self, noun, verb, *args, **kwargs):
        command(noun, verb, *args, help="help", **kwargs)(nothing)
        return self.commands[-1]

    def test_usage(self):
        declared = self.declare(
            "brick",
            "card add",
            Arg("VM"),
            Arg("TARGET", optional=True),
            flags=[Flag("force"), Flag("at", Arg("N", Number()))],
        )
        self.assertEqual(declared.words, ("brick", "card", "add"))
        self.assertEqual(declared.name, "brick card add")
        self.assertEqual(
            declared.usage(), "brick card add VM [TARGET] [--force] [--at N]"
        )
        many = self.declare("brick", "start", Arg("NAME", many=True))
        self.assertEqual(many.usage(), "brick start NAME…")
        alone = self.declare(None, "quit")
        self.assertEqual(alone.words, ("quit",))
        self.assertEqual(alone.usage(), "quit")

    def test_keywords(self):
        self.assertEqual(keyword(Arg("NAME")), "name")
        self.assertEqual(keyword(Arg("KEY=VALUE")), "key_value")
        self.assertEqual(keyword(Flag("at")), "at")

    def test_find_the_longest(self):
        start = self.declare("brick", "start")
        card = self.declare("brick", "card")
        card_add = self.declare("brick", "card add")
        self.assertEqual(find(["brick", "start", "sw1"]), (start, 2))
        self.assertEqual(find(["brick", "card", "add", "vm1"]), (card_add, 3))
        self.assertEqual(find(["brick", "card", "vm1"]), (card, 2))
        self.assertEqual(find(["brick"]), (None, 0))
        self.assertEqual(find(["event", "start"]), (None, 0))

    def test_nouns(self):
        self.declare("event", "start")
        self.declare("brick", "start")
        self.declare("brick", "stop")
        self.declare(None, "help")
        self.assertEqual(nouns(), ["brick", "event"])
        self.assertEqual([c.verb for c in of_noun("brick")], ["start", "stop"])
        self.assertEqual([c.verb for c in of_noun(None)], ["help"])


class TestKinds(unittest.TestCase):

    def setUp(self):
        self.context = Context(factory=None)

    def test_number(self):
        self.assertEqual(Number().read(self.context, "12"), 12)
        error = self.assertRaises(
            CommandError, Number().read, self.context, "x"
        )
        self.assertEqual(str(error), '"x" is not a number')

    def test_choice(self):
        choice = Choice("left", "right")
        self.assertEqual(choice.read(self.context, "left"), "left")
        error = self.assertRaises(
            CommandError, choice.read, self.context, "up"
        )
        self.assertEqual(str(error), '"up" is not one of left, right')
        self.assertEqual(
            choice.candidates(self.context, {}), ["left", "right"]
        )

    def test_named(self):
        things = {"b": 2, "a": 1}
        named = Named(
            lambda factory, name: things.get(name),
            lambda factory: list(things),
            "No thing named {name}",
        )
        self.assertEqual(named.read(self.context, "a"), 1)
        error = self.assertRaises(CommandError, named.read, self.context, "c")
        self.assertEqual(str(error), "No thing named c")
        self.assertEqual(named.candidates(self.context, {}), ["a", "b"])

    def test_pair(self):
        pair = Pair()
        self.assertEqual(pair.read(self.context, "ports=16"), ("ports", "16"))
        # the value may be empty, and have its own =
        self.assertEqual(pair.read(self.context, "icon="), ("icon", ""))
        self.assertEqual(
            pair.read(self.context, "kernel_command_line=root=/dev/vda"),
            ("kernel_command_line", "root=/dev/vda"),
        )
        for word in ("ports", "=16"):
            error = self.assertRaises(
                CommandError, pair.read, self.context, word
            )
            self.assertEqual(str(error), f'"{word}" is not KEY=VALUE')
