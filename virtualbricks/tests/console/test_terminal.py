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

"""The console in the terminal, and on an input that isn't one."""

import os
import subprocess
import sys
import termios

from twisted.conch.insults import helper, insults
from twisted.internet import defer
from twisted.internet.testing import StringTransport
from twisted.trial import unittest

from virtualbricks import __version__
from virtualbricks.console import command as command_module
from virtualbricks.console import terminal
from virtualbricks.console.command import CommandError, command
from virtualbricks.console.lineedit import CTRL_D
from virtualbricks.console.terminal import (
    ConsoleLine,
    PlainConsole,
    RawTerminal,
    Switcher,
    history_file,
)
from virtualbricks.tests import use_workspace
from virtualbricks.tests.console import ConsoleTestCase

UP = helper.TerminalBuffer.UP_ARROW


class TerminalTestCase(ConsoleTestCase):

    def setUp(self):
        super().setUp()
        self.factory.runtime_dir = "/run/vb"
        use_workspace(self)
        self.screen = helper.TerminalBuffer()
        self.screen.connectionMade()

    def connect(self, protocol):
        protocol.makeConnection(self.screen)
        return protocol

    def console(self):
        return self.connect(ConsoleLine(self.factory, None, self.clock()))

    def type(self, protocol, text):
        for character in text.encode():
            protocol.keystrokeReceived(bytes([character]), None)

    def enter(self, protocol, text=""):
        self.type(protocol, text)
        protocol.keystrokeReceived(b"\r", None)

    def lines(self):
        return [
            line.rstrip() for line in bytes(self.screen).decode().splitlines()
        ]

    def shown(self):
        return [line for line in self.lines() if line]


class TestTheLine(TerminalTestCase):

    def test_a_command_and_its_answer(self):
        console = self.console()
        self.assertEqual(
            self.shown(),
            [
                f"Virtualbricks {__version__}. Type help, or press Tab to"
                " complete.",
                "virtualbricks>",
            ],
        )
        self.enter(console, "brick new switch")
        self.enter(console, "nope")
        self.assertEqual(
            self.shown()[1:],
            [
                "virtualbricks> brick new switch",
                "sw1",
                "virtualbricks> nope",
                "Error: No command nope; type help for the commands",
                "virtualbricks>",
            ],
        )

    def test_the_prompt_is_the_project(self):
        workspace = use_workspace(self, os.path.abspath(self.mktemp()))
        os.makedirs(workspace.path)
        workspace.create("lab")
        workspace.open("lab", self.factory)
        self.console()
        self.assertEqual(self.shown()[-1], "lab>")

    def test_history(self):
        console = self.console()
        self.enter(console, "brick new switch")
        self.enter(console, "status")
        with open(history_file()) as fp:
            self.assertEqual(fp.read(), "brick new switch\nstatus\n")
        # a console of another run has it
        self.screen = helper.TerminalBuffer()
        self.screen.connectionMade()
        again = self.console()
        again.keystrokeReceived(UP, None)
        again.keystrokeReceived(UP, None)
        self.assertEqual(self.shown()[-1], "virtualbricks> brick new switch")

    def test_the_history_keeps_its_last_lines(self):
        self.patch(terminal, "HISTORY_SIZE", 2)
        console = self.console()
        for line in ("status", "help", "brick list"):
            self.enter(console, line)
        with open(history_file()) as fp:
            self.assertEqual(fp.read(), "help\nbrick list\n")

    def test_a_long_history_is_read_to_its_end(self):
        self.patch(terminal, "HISTORY_SIZE", 2)
        os.makedirs(os.path.dirname(history_file()))
        with open(history_file(), "w") as fp:
            fp.write("status\nhelp\n\nbrick list\n")
        console = self.console()
        self.assertEqual(console.historyLines, [b"help", b"brick list"])

    def test_ctrl_c_clears_the_line(self):
        console = self.console()
        self.type(console, "brick li")
        console.keystrokeReceived(terminal.CTRL_C, None)
        self.assertEqual(
            self.shown()[-2:], ["virtualbricks> brick li^C", "virtualbricks>"]
        )
        self.assertEqual(console.lineBuffer, [])

    def test_ctrl_d_quits(self):
        console = self.console()
        brick = self.factory.new_brick("switch", "sw1")
        brick.proc = object()
        console.keystrokeReceived(CTRL_D, None)
        self.assertEqual(
            self.shown()[-2:],
            ["Error: sw1 is running: stop it first", "virtualbricks>"],
        )
        brick.proc = None
        # not while something is typed
        self.type(console, "x")
        console.keystrokeReceived(CTRL_D, None)
        self.assertFalse(self.factory.quit_d.called)
        console.keystrokeReceived(terminal.CTRL_C, None)
        console.keystrokeReceived(CTRL_D, None)
        self.assertTrue(self.factory.quit_d.called)


class TestReadlineKeys(TerminalTestCase):
    """The keys of lineedit, as the terminal sends them."""

    def server(self, namespace=None):
        server = insults.ServerProtocol(
            Switcher, self.factory, namespace or {}, self.clock()
        )
        self.transport = StringTransport()
        server.makeConnection(self.transport)
        return server

    def test_alt_keys(self):
        server = self.server()
        # Alt+B, back to "new"; Alt+T, "switch" and "new" change places
        server.dataReceived(b"brick switch new\x1bb\x1bt\r")
        self.assertEqual([b.name for b in self.factory.bricks], ["sw1"])

    def test_ctrl_arrows_and_ctrl_k(self):
        server = self.server()
        server.dataReceived(b"brick new switch sw1 extra\x1b[1;5D\x0b\r")
        self.assertEqual([b.name for b in self.factory.bricks], ["sw1"])

    def test_the_python_shell_has_them(self):
        server = self.server({"answer": 42})
        server.dataReceived(b"python\r")
        # Alt+Backspace deletes 25
        server.dataReceived(b"answer + 1 + 25\x1b\x7f3\r")
        self.assertIn(b"46", self.transport.value())
        # Ctrl+D deletes, and on an empty line goes back
        server.dataReceived(b"x\x01\x04\x04")
        switcher = server.terminalProtocol
        self.assertIs(switcher.current, switcher.console)


class TestCompletion(TerminalTestCase):

    def test_one_word(self):
        console = self.console()
        self.type(console, "bri")
        console.keystrokeReceived(b"\t", None)
        self.assertEqual(b"".join(console.lineBuffer), b"brick ")
        self.type(console, "new sw")
        console.keystrokeReceived(b"\t", None)
        self.assertEqual(b"".join(console.lineBuffer), b"brick new switch")

    def test_several_words(self):
        console = self.console()
        self.type(console, "brick s")
        console.keystrokeReceived(b"\t", None)
        self.assertEqual(
            self.shown()[-2:],
            ["set  show  start  stop  suspend", "virtualbricks> brick s"],
        )

    def test_nothing(self):
        console = self.console()
        self.type(console, "nope ")
        console.keystrokeReceived(b"\t", None)
        self.assertEqual(b"".join(console.lineBuffer), b"nope ")


class TestWaiting(TerminalTestCase):

    def setUp(self):
        super().setUp()
        self.later = defer.Deferred()
        commands = list(command_module.COMMANDS)
        self.patch(command_module, "COMMANDS", commands)
        command(None, "slow", help="h")(lambda context: self.later)

    def test_keys_wait(self):
        console = self.console()
        self.enter(console, "slow")
        # what is typed while it runs is lost
        self.type(console, "status")
        self.assertEqual(console.lineBuffer, [])
        self.later.callback(["done"])
        self.assertEqual(self.shown()[-2:], ["done", "virtualbricks>"])

    def test_ctrl_c_stops_waiting(self):
        console = self.console()
        self.enter(console, "slow")
        console.keystrokeReceived(terminal.CTRL_C, None)
        self.assertIsNone(console.waiting)
        self.type(console, "stat")
        # the answer comes above the line being typed
        self.later.errback(CommandError("too late", ["half"]))
        self.assertEqual(
            self.shown()[-3:],
            ["half", "Error: too late", "virtualbricks> stat"],
        )


class TestSwitcher(TerminalTestCase):

    def test_through_the_terminal(self):
        # the protocol of the terminal sets factory on its own protocol
        server = insults.ServerProtocol(
            Switcher, self.factory, {}, self.clock()
        )
        transport = StringTransport()
        server.makeConnection(transport)
        server.dataReceived(b"brick new switch\r")
        self.assertIn(b"sw1", transport.value())
        self.assertEqual([b.name for b in self.factory.bricks], ["sw1"])

    def test_the_python_shell(self):
        server = insults.ServerProtocol(
            Switcher, self.factory, {"answer": 42}, self.clock()
        )
        transport = StringTransport()
        server.makeConnection(transport)
        server.dataReceived(b"python\r")
        server.dataReceived(b"answer, len(list(factory.bricks))\r")
        self.assertIn(b"(42, 0)", transport.value())
        switcher = server.terminalProtocol
        server.dataReceived(CTRL_D)
        self.assertIs(switcher.current, switcher.console)
        transport.clear()
        server.dataReceived(b"brick new switch\r")
        self.assertIn(b"sw1", transport.value())

    def test_close(self):
        server = insults.ServerProtocol(
            Switcher, self.factory, {}, self.clock()
        )
        transport = StringTransport()
        server.makeConnection(transport)
        switcher = server.terminalProtocol
        transport.clear()
        closed = switcher.close()
        # the prompt goes, then insert mode: the screen stays
        self.assertEqual(transport.value(), b"\r\x1b[K\x1b[4l")
        self.assertTrue(transport.disconnecting)
        # once the terminal has shown it all
        self.assertNoResult(closed)
        server.connectionLost(None)
        self.successResultOf(closed)

    def test_close_without_the_terminal(self):
        server = insults.ServerProtocol(
            Switcher, self.factory, {}, self.clock()
        )
        transport = StringTransport()
        server.makeConnection(transport)
        switcher = server.terminalProtocol
        server.connectionLost(None)
        transport.clear()
        self.successResultOf(switcher.close())
        self.assertEqual(transport.value(), b"")


class TestPlain(ConsoleTestCase):

    def test_a_line_at_a_time(self):
        console = PlainConsole(self.factory, self.clock())
        transport = StringTransport()
        console.makeConnection(transport)
        console.dataReceived(b"brick new switch\nbrick nope x\n")
        self.assertEqual(transport.value().decode().splitlines()[0], "sw1")
        self.assertTrue(
            transport.value()
            .decode()
            .splitlines()[1]
            .startswith("Error: brick has no nope")
        )
        # the end of the input quits
        console.connectionLost(None)
        self.assertTrue(self.factory.quit_d.called)

    def test_one_command_after_the_other(self):
        later = defer.Deferred()
        commands = list(command_module.COMMANDS)
        self.patch(command_module, "COMMANDS", commands)
        command(None, "slow", help="h")(lambda context: later)
        console = PlainConsole(self.factory, self.clock())
        transport = StringTransport()
        console.makeConnection(transport)
        console.dataReceived(b"slow\n")
        self.assertEqual(transport.producerState, "paused")
        # the end comes while it runs: quit waits for it
        console.connectionLost(None)
        self.assertFalse(self.factory.quit_d.called)
        later.callback(["done"])
        self.assertEqual(transport.value(), b"done\n")
        self.assertTrue(self.factory.quit_d.called)


class TestRawTerminal(unittest.TestCase):

    def test_modes(self):
        leader, follower = os.openpty()
        self.addCleanup(os.close, leader)
        self.addCleanup(os.close, follower)
        before = termios.tcgetattr(follower)
        raw = RawTerminal(follower)
        raw.start()
        iflag, oflag, cflag, lflag = termios.tcgetattr(follower)[:4]
        for flag in (termios.ICANON, termios.ECHO, termios.ISIG):
            self.assertFalse(lflag & flag)
        self.assertFalse(iflag & termios.IXON)
        # the output is processed: a new line starts at its column 0
        self.assertEqual(oflag, before[1])
        raw.stop()
        self.assertEqual(termios.tcgetattr(follower), before)
        raw.stop()


class TestWithoutTheDesktop(unittest.TestCase):

    def test_no_graphics_library(self):
        # in a process of its own: the tests of the windows load GTK
        code = (
            "import sys; import virtualbricks.brickfactory,"
            " virtualbricks.console.terminal, virtualbricks.console.dispatch;"
            " print([m for m in sys.modules if m == 'gi'"
            " or m.startswith(('gi.', 'gtk', 'gobject'))])"
        )
        result = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "[]")
