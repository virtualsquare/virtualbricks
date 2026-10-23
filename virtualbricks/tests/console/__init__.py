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

"""The tests of the console, and what they share."""

from virtualbricks.console import command as command_module
from virtualbricks.console.dispatch import run
from virtualbricks.tests import BrickTestCase


def own_commands(test):
    """Give the test a table of commands of its own, empty."""

    commands = []
    test.patch(command_module, "COMMANDS", commands)
    return commands


class ConsoleTestCase(BrickTestCase):
    """Commands run on a factory of their own, as typed in the console."""

    def run_line(self, line):
        """The lines of the answer; the test fails if the command does."""

        return self.successResultOf(run(self.factory, line, self.clock()))

    def fails(self, line):
        """The message of a command that fails."""

        failure = self.failureResultOf(run(self.factory, line, self.clock()))
        from virtualbricks.console.command import CommandError

        failure.trap(CommandError)
        return failure.getErrorMessage()

    def clock(self):
        from twisted.internet import task

        if not hasattr(self, "_clock"):
            self._clock = task.Clock()
        return self._clock
