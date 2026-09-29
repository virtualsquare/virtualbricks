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

"""A line run: its answer, or why it failed."""

from twisted.internet import defer

from virtualbricks import errors
from virtualbricks.console import dispatch
from virtualbricks.console.dispatch import check
from virtualbricks.console.command import CommandError, command
from virtualbricks.tests import FakeLogger
from virtualbricks.tests.console import ConsoleTestCase, own_commands


class TestRun(ConsoleTestCase):

    def setUp(self):
        super().setUp()
        own_commands(self)
        self.logger = FakeLogger()
        self.patch(dispatch, "logger", self.logger)
        self.seen = []

        def answer(context):
            self.seen.append(context)
            return ["one", "two"]

        command(None, "answer", help="h")(answer)
        command(None, "quiet", help="h")(lambda context: None)
        command(None, "later", help="h")(
            lambda context: defer.succeed(("three",))
        )

        def raises(error):
            def function(context):
                raise error

            return function

        command(None, "refuse", help="h")(raises(CommandError("No way")))
        command(None, "running", help="h")(
            raises(errors.BrickRunningError("sw1 is running"))
        )
        command(None, "bug", help="h")(raises(KeyError("ports")))

    def test_answers(self):
        self.assertEqual(self.run_line("answer"), ["one", "two"])
        self.assertEqual(self.run_line("quiet"), [])
        self.assertEqual(self.run_line("later"), ["three"])
        self.assertEqual(self.run_line(""), [])
        context = self.seen[0]
        self.assertIs(context.factory, self.factory)
        self.assertIs(context.reactor, self.clock())
        self.assertIsNone(context.terminal)

    def test_errors(self):
        self.assertEqual(self.fails("refuse"), "No way")
        self.assertEqual(
            self.fails("nope"), "No command nope; type help for the commands"
        )
        # an error of the project keeps its message
        self.assertEqual(self.fails("running"), "sw1 is running")
        self.assertEqual(self.logger.formatted(), [])

    def test_a_bug_is_logged(self):
        self.assertEqual(
            self.fails("bug"), "'ports'; the messages have the details"
        )
        self.assertEqual(self.logger.formatted(), ["The command 'bug' failed"])


class TestCheck(ConsoleTestCase):

    def test_check(self):
        self.factory.runtime_dir = "/run/vb"
        self.factory.new_brick("switch", "sw1")
        self.assertIsNone(check(self.factory, "brick set sw1 ports=4"))
        self.assertEqual(
            check(self.factory, "brick set sw2 ports=4"), "No brick named sw2"
        )
        self.assertEqual(
            check(self.factory, "sw1 on"),
            "No command sw1; type help for the commands",
        )
        # nothing runs
        self.assertEqual(
            self.factory.get_brick_by_name("sw1").config.ports, 32
        )
