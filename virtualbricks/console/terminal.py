# -*- test-case-name: virtualbricks.tests.console.test_terminal -*-
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
The console in the terminal that started Virtualbricks.

On a terminal, :class:`ConsoleLine` is a line to type commands in, with
editing, a history kept between runs and Tab completion; the prompt is the
name of the open project. A command runs to its end before the next: Ctrl+C
stops waiting for it, not what it does. ``python`` opens the Python shell,
and Ctrl+D comes back; Ctrl+D on an empty line quits, as ``quit`` does.
Both lines have the keys of readline, :mod:`virtualbricks.console.lineedit`.

When the input is not a terminal, as a pipe, :class:`PlainConsole` reads it
a line at a time, and quits at its end.

The terminal keeps its output processing: the lines it writes end as the
terminal ends them. Only the line mode, the echo and the signals are turned
off while the console reads. Both lines put the terminal in insert mode; when
Virtualbricks quits, the terminal shows what they wrote last, then the prompt
goes and so does that mode: the shell's line, as readline draws it, would be
garbled.
"""

from __future__ import annotations

import os
import sys
import termios

from twisted.conch import manhole, recvline
from twisted.conch.insults import insults
from twisted.internet import defer, stdio
from twisted.logger import Logger
from twisted.protocols import basic

from virtualbricks import __version__, locations
from virtualbricks.config.workspace import projects
from virtualbricks.console.command import CommandError, Context
from virtualbricks.console.dispatch import run
from virtualbricks.console.lineedit import ReadlineKeys
from virtualbricks.console.parser import complete
from virtualbricks.i18n import _

logger = Logger()
history_error = "The history of the console can't be written"

CTRL_C = b"\x03"
CTRL_L = b"\x0c"
# The lines of the history kept between runs.
HISTORY_SIZE = 500


def history_file() -> str:
    return os.path.join(locations.state_dir(), "history")


def greeting() -> str:
    return _(
        "Virtualbricks {version}. Type help, or press Tab to complete."
    ).format(version=__version__)


def prompt() -> str:
    current = projects.current
    return f"{current.name if current is not None else 'virtualbricks'}> "


def answer_lines(lines) -> list[str]:
    return list(lines)


def error_lines(failure) -> list[str]:
    """The lines of a command that failed: what it did, then why."""

    error = failure.value
    lines = list(getattr(error, "lines", []))
    if not failure.check(CommandError):
        logger.failure("The console failed", failure)
    return lines + [_("Error: {message}").format(message=error)]


def _common(words: list[str]) -> str:
    return os.path.commonprefix(words)


class ConsoleLine(ReadlineKeys, recvline.HistoricRecvLine):
    """The line of the console: each command, run to its end."""

    def __init__(self, factory, switcher=None, reactor=None):
        super().__init__()
        self.brickfactory = factory
        self.switcher = switcher
        self.reactor = reactor
        # the Deferred of the command that runs, None if none does
        self.waiting = None
        self.greeted = False

    # the terminal

    def connectionMade(self):
        self.ps = (prompt().encode(),)
        super().connectionMade()
        self.keyHandlers.update(
            {CTRL_C: self.handle_INT, CTRL_L: self.handle_FF}
        )
        self.historyLines = self.read_history()
        self.historyPosition = len(self.historyLines)

    def initializeScreen(self):
        # the screen isn't cleared: what the terminal shows stays
        if not self.greeted:
            self.greeted = True
            self.write_lines([greeting()])
        self.terminal.write(self.ps[self.pn])
        self.setInsertMode()

    def resume(self):
        """Show the prompt again, back from the Python shell."""

        self.ps = (prompt().encode(),)
        self.lineBuffer = []
        self.lineBufferIndex = 0
        self.terminal.nextLine()
        self.terminal.write(self.ps[self.pn])

    def write_lines(self, lines):
        for line in lines:
            self.terminal.write(line.encode("utf-8", "replace"))
            self.terminal.nextLine()

    # the history

    def read_history(self) -> list[bytes]:
        try:
            with open(history_file(), "rb") as fp:
                lines = fp.read().splitlines()
        except OSError:
            return []
        return [line for line in lines if line.strip()][-HISTORY_SIZE:]

    def write_history(self):
        path = history_file()
        try:
            locations.ensure_private_dir(os.path.dirname(path))
            with open(path, "wb") as fp:
                for line in self.historyLines[-HISTORY_SIZE:]:
                    fp.write(line + b"\n")
        except OSError:
            logger.failure(history_error)

    # the keys

    def keystrokeReceived(self, keyID, modifier):
        if self.waiting is not None:
            # a command runs: Ctrl+C stops waiting for it
            if keyID == CTRL_C:
                self.waiting = None
                self.terminal.write(b"^C")
                self.terminal.nextLine()
                self.drawInputLine()
            return
        super().keystrokeReceived(keyID, modifier)

    def handle_INT(self):
        self.lineBuffer = []
        self.lineBufferIndex = 0
        self.terminal.write(b"^C")
        self.terminal.nextLine()
        self.drawInputLine()

    def end_of_input(self):
        # Ctrl+D on an empty line
        self.terminal.nextLine()
        self.execute("quit")

    def handle_FF(self):
        self.terminal.eraseDisplay()
        self.terminal.cursorHome()
        self.drawInputLine()

    def handle_TAB(self):
        before = b"".join(self.lineBuffer[: self.lineBufferIndex]).decode(
            "utf-8", "replace"
        )
        context = Context(self.brickfactory, self.reactor)
        partial, words = complete(context, before)
        if not words:
            self.terminal.write(b"\a")
            return
        common = _common(words)
        if len(words) == 1 and not common.endswith("="):
            common += " "
        if len(common) > len(partial):
            for character in common[len(partial) :].encode():
                self.characterReceived(bytes([character]), False)
            return
        # nothing to add: the words it can become
        self.terminal.nextLine()
        self.write_lines(["  ".join(words)])
        self.drawInputLine()

    # the commands

    def lineReceived(self, line):
        text = line.decode("utf-8", "replace")
        if line.strip():
            self.write_history()
        if text.strip() == "python" and self.switcher is not None:
            self.switcher.python()
            return
        self.execute(text)

    def execute(self, text):
        done = run(self.brickfactory, text, self.reactor, terminal=self)
        if done.called:
            # at once: the prompt comes back after the answer
            done.addCallbacks(self.write_lines, self._failed)
            self._prompt()
            return
        self.waiting = done

        def finished(result, lines):
            if self.waiting is done:
                self.waiting = None
                self.write_lines(lines(result))
                self._prompt()
            else:
                # the prompt came back with Ctrl+C: above the line typed
                self.terminal.write(b"\r")
                self.terminal.eraseToLineEnd()
                self.write_lines(lines(result))
                self.drawInputLine()

        done.addCallbacks(
            finished, finished, (answer_lines,), None, (error_lines,), None
        )

    def _failed(self, failure):
        self.write_lines(error_lines(failure))

    def _prompt(self):
        self.ps = (prompt().encode(),)
        self.pn = 0
        self.terminal.write(self.ps[self.pn])


class PythonShell(ReadlineKeys, manhole.Manhole):
    """The Python shell, with the factory; Ctrl+D goes back to the console."""

    def __init__(self, namespace, back):
        super().__init__(namespace)
        self.back = back

    def initializeScreen(self):
        self.terminal.nextLine()
        self.terminal.write(
            _(
                "The Python shell: factory is the factory of the bricks."
                " Ctrl+D goes back to the console."
            ).encode()
        )
        self.terminal.nextLine()
        self.terminal.write(self.ps[self.pn])
        self.setInsertMode()

    def handle_QUIT(self):
        self.back()

    def end_of_input(self):
        # Ctrl+D on an empty line
        self.back()


class Switcher(insults.TerminalProtocol):
    """What the keys go to: the console, or the Python shell."""

    def __init__(self, factory, namespace, reactor=None):
        # not factory: insults.ServerProtocol sets that of its protocol
        self.brickfactory = factory
        self.namespace = namespace
        self.reactor = reactor
        self.current = None
        self.console = None
        # fires once the terminal is gone
        self.lost = defer.Deferred()

    def connectionMade(self):
        self.console = ConsoleLine(self.brickfactory, self, self.reactor)
        self.current = self.console
        self.console.makeConnection(self.terminal)

    def python(self):
        namespace = dict(self.namespace, factory=self.brickfactory)
        self.current = PythonShell(namespace, self.back)
        self.current.makeConnection(self.terminal)

    def back(self):
        self.current = self.console
        self.console.resume()

    def keystrokeReceived(self, keyID, modifier):
        self.current.keystrokeReceived(keyID, modifier)

    def terminalSize(self, width, height):
        self.current.terminalSize(width, height)

    def unhandledControlSequence(self, seq):
        self.current.unhandledControlSequence(seq)

    def connectionLost(self, reason):
        if self.console is not None:
            self.console.connectionLost(reason)
        self.lost.callback(None)

    def close(self):
        """
        Give the terminal back to the shell: without the line of the prompt
        and out of insert mode, once it shows all that was written to it.
        The Deferred fires then.
        """

        if not self.lost.called:
            self.terminal.write(b"\r")
            self.terminal.eraseToLineEnd()
            self.terminal.resetModes([insults.modes.IRM])
            # not the terminal's loseConnection: it clears the screen
            self.terminal.transport.loseConnection()
        return self.lost


class PlainConsole(basic.LineOnlyReceiver):
    """The console on an input that isn't a terminal: a line at a time."""

    delimiter = b"\n"

    def __init__(self, factory, reactor=None, output=None):
        self.brickfactory = factory
        self.reactor = reactor
        self.output = output
        self.ended = False
        self.busy = False

    def write_lines(self, lines):
        for line in lines:
            self.transport.write(line.encode("utf-8", "replace") + b"\n")

    def lineReceived(self, line):
        self.busy = True
        self.transport.pauseProducing()
        done = run(
            self.brickfactory, line.decode("utf-8", "replace"), self.reactor
        )
        done.addCallbacks(
            self.write_lines, lambda f: self.write_lines(error_lines(f))
        )
        done.addBoth(self._next)

    def _next(self, _):
        self.busy = False
        if self.ended:
            self._quit()
        else:
            self.transport.resumeProducing()

    def connectionLost(self, reason):
        # the end of the input: quit, once the last command is done
        self.ended = True
        if not self.busy:
            self._quit()

    def _quit(self):
        done = run(self.brickfactory, "quit", self.reactor)
        done.addErrback(
            lambda f: sys.stderr.write("\n".join(error_lines(f)) + "\n")
        )


class RawTerminal:
    """The terminal of fd without its line mode, echo and signals."""

    def __init__(self, fd):
        self.fd = fd
        self.saved = None

    def start(self):
        self.saved = termios.tcgetattr(self.fd)
        iflag, oflag, cflag, lflag, ispeed, ospeed, cc = termios.tcgetattr(
            self.fd
        )
        lflag &= ~(
            termios.ICANON | termios.ECHO | termios.ISIG | termios.IEXTEN
        )
        # Ctrl+S and Ctrl+Q are keys too
        iflag &= ~termios.IXON
        cc[termios.VMIN] = 1
        cc[termios.VTIME] = 0
        termios.tcsetattr(
            self.fd,
            termios.TCSANOW,
            [iflag, oflag, cflag, lflag, ispeed, ospeed, cc],
        )

    def stop(self):
        if self.saved is not None:
            termios.tcsetattr(self.fd, termios.TCSANOW, self.saved)
            self.saved = None


def start(factory, namespace, reactor=None):
    """Read the console on the standard input; return what reads it."""

    if reactor is None:
        from twisted.internet import reactor
    stdin = sys.__stdin__.fileno()
    if not os.isatty(stdin):
        return stdio.StandardIO(PlainConsole(factory, reactor))
    raw = RawTerminal(stdin)
    raw.start()
    reactor.addSystemEventTrigger("after", "shutdown", raw.stop)
    protocol = insults.ServerProtocol(Switcher, factory, namespace, reactor)
    try:
        size = os.get_terminal_size(stdin)
    except OSError:
        pass
    else:
        protocol.termSize.x, protocol.termSize.y = size.columns, size.lines
    io = stdio.StandardIO(protocol)
    # before the reactor drops what the terminal has yet to show
    reactor.addSystemEventTrigger(
        "before", "shutdown", protocol.terminalProtocol.close
    )
    return io
