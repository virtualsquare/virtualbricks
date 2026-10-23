# -*- test-case-name: virtualbricks.tests.console.test_terminal -*-
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

"""
The console in the terminal that started Virtualbricks.

On a terminal, :class:`ConsoleLine` is a line to type commands in, with
editing, a history kept between runs and Tab completion; the prompt is the
name of the open project, and it starts with the banner of --banner,
:mod:`virtualbricks.console.banner`; a key ends one that moves at once.
A command runs to its end before the next: Ctrl+C stops waiting for it,
not what it does. ``python`` opens the Python shell, and Ctrl+D comes back;
Ctrl+D on an empty line quits, as ``quit`` does. Both lines have the keys
of readline, :mod:`virtualbricks.console.lineedit`.

When the input is not a terminal, as a pipe, :class:`PlainConsole` reads it
a line at a time, each once the one before is done, and quits at its end.

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
from collections.abc import Callable, Iterable
from typing import Any, cast

from twisted.conch import manhole, recvline
from twisted.conch.insults import insults
from twisted.internet import defer, stdio
from twisted.internet.base import ReactorBase
from twisted.internet.interfaces import (
    IDelayedCall,
    IHalfCloseableProtocol,
    IReactorTime,
)
from twisted.internet.protocol import connectionDone
from twisted.logger import Logger
from twisted.protocols import basic
from twisted.python.failure import Failure
from zope.interface import implementer

from virtualbricks import locations
from virtualbricks.brickfactory import BrickFactory
from virtualbricks.config.workspace import projects
from virtualbricks.console.banner import Banner, Frame
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
# The seconds between two frames of a banner that moves.
FRAME = 0.02


def history_file() -> str:
    return os.path.join(locations.state_dir(), "history")


def prompt() -> str:
    current = projects.current
    return f"{current.name if current is not None else 'virtualbricks'}> "


def prompts() -> tuple[bytes, bytes]:
    """The prompts of the line, as recvline has two: both prompt()."""

    line = prompt().encode()
    return line, line


def answer_lines(lines: Iterable[str]) -> list[str]:
    return list(lines)


def error_lines(failure: Failure) -> list[str]:
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

    def __init__(
        self,
        factory: BrickFactory,
        switcher: Switcher | None = None,
        reactor: IReactorTime | None = None,
        banner: Banner = Banner(),
        width: int = 80,
        height: int = 24,
    ) -> None:
        super().__init__()
        self.brickfactory = factory
        self.switcher = switcher
        self.reactor = reactor
        self.banner = banner
        # the columns and lines of the terminal, as recvline has them
        self.width = width
        self.height = height
        # the Deferred of the command that runs, None if none does
        self.waiting: defer.Deferred[list[str]] | None = None
        self.greeted = False
        # the frames of the banner still to show, and the call of the next
        self.frames: list[Frame] = []
        self.next_frame: IDelayedCall | None = None

    # the terminal

    def connectionMade(self) -> None:
        self.ps = prompts()
        super().connectionMade()
        self.keyHandlers.update(
            {CTRL_C: self.handle_INT, CTRL_L: self.handle_FF}
        )
        self.historyLines = self.read_history()
        self.historyPosition = len(self.historyLines)

    def initializeScreen(self) -> None:
        # the screen isn't cleared: what the terminal shows stays
        if not self.greeted:
            self.greeted = True
            frames = self.banner.frames(self.brickfactory, self.width)
            # each frame goes back up to the first line of the one before:
            # all its lines must be on the screen
            if self.reactor is None or len(frames[0]) >= self.height:
                frames = frames[-1:]
            self.write_lines(frames[0])
            if len(frames) > 1:
                assert self.reactor is not None, "frames need a clock"
                self.frames = frames[1:]
                self.next_frame = self.reactor.callLater(
                    FRAME, self.show_frame
                )
                return
        self.show_prompt()

    def show_prompt(self) -> None:
        self.terminal.write(self.ps[self.pn])
        self.setInsertMode()

    # the banner that moves

    def show_frame(self) -> None:
        """The next frame of the banner; after the last, the prompt."""

        assert self.reactor is not None, "frames need a clock"
        self.draw_frame(self.frames.pop(0))
        if self.frames:
            self.next_frame = self.reactor.callLater(FRAME, self.show_frame)
        else:
            self.next_frame = None
            self.show_prompt()

    def draw_frame(self, frame: Frame) -> None:
        """A frame over the one before, which has as many lines."""

        self.terminal.cursorUp(len(frame))
        for line in frame:
            self.terminal.write(b"\r")
            self.terminal.eraseLine()
            self.write_lines([line])

    def end_banner(self) -> None:
        """The last frame of the banner at once, then the prompt."""

        if self.next_frame is None:
            return
        self.next_frame.cancel()
        self.next_frame = None
        self.draw_frame(self.frames[-1])
        self.frames = []
        self.show_prompt()

    def connectionLost(self, reason: Failure = connectionDone) -> None:
        if self.next_frame is not None:
            self.next_frame.cancel()
            self.next_frame = None
        super().connectionLost(reason)

    def resume(self) -> None:
        """Show the prompt again, back from the Python shell."""

        self.ps = prompts()
        self.lineBuffer = []
        self.lineBufferIndex = 0
        self.terminal.nextLine()
        self.terminal.write(self.ps[self.pn])

    def write_lines(self, lines: Iterable[str]) -> None:
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

    def write_history(self) -> None:
        path = history_file()
        try:
            locations.ensure_private_dir(os.path.dirname(path))
            with open(path, "wb") as fp:
                for line in self.historyLines[-HISTORY_SIZE:]:
                    fp.write(line + b"\n")
        except OSError:
            logger.failure(history_error)

    # the keys

    def keystrokeReceived(self, keyID: bytes, modifier: bytes | None) -> None:
        # a key ends the banner that moves: the prompt is there for it
        self.end_banner()
        if self.waiting is not None:
            # a command runs: Ctrl+C stops waiting for it
            if keyID == CTRL_C:
                self.waiting = None
                self.terminal.write(b"^C")
                self.terminal.nextLine()
                self.drawInputLine()
            return
        super().keystrokeReceived(keyID, modifier)

    def handle_INT(self) -> None:
        self.lineBuffer = []
        self.lineBufferIndex = 0
        self.terminal.write(b"^C")
        self.terminal.nextLine()
        self.drawInputLine()

    def end_of_input(self) -> None:
        # Ctrl+D on an empty line
        self.terminal.nextLine()
        self.execute("quit")

    def handle_FF(self) -> None:
        self.terminal.eraseDisplay()
        self.terminal.cursorHome()
        self.drawInputLine()

    def handle_TAB(self) -> None:
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

    def lineReceived(self, line: bytes) -> None:
        text = line.decode("utf-8", "replace")
        if line.strip():
            self.write_history()
        if text.strip() == "python" and self.switcher is not None:
            self.switcher.python()
            return
        self.execute(text)

    def execute(self, text: str) -> None:
        done = run(self.brickfactory, text, self.reactor, terminal=self)
        if done.called:
            # at once: the prompt comes back after the answer
            done.addCallbacks(self.write_lines, self._failed)
            self._prompt()
            return
        self.waiting = done

        def finished(
            result: object, lines: Callable[[object], list[str]]
        ) -> None:
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
            finished,
            finished,
            callbackArgs=(answer_lines,),
            errbackArgs=(error_lines,),
        )

    def _failed(self, failure: Failure) -> None:
        self.write_lines(error_lines(failure))

    def _prompt(self) -> None:
        self.ps = prompts()
        self.pn = 0
        self.terminal.write(self.ps[self.pn])


class PythonShell(ReadlineKeys, manhole.Manhole):
    """The Python shell, with the factory; Ctrl+D goes back to the console."""

    def __init__(
        self, namespace: dict[str, object], back: Callable[[], None]
    ) -> None:
        super().__init__(namespace)
        self.back = back

    def initializeScreen(self) -> None:
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

    def handle_QUIT(self) -> None:
        self.back()

    def end_of_input(self) -> None:
        # Ctrl+D on an empty line
        self.back()


class Switcher(insults.TerminalProtocol):
    """What the keys go to: the console, or the Python shell."""

    def __init__(
        self,
        factory: BrickFactory,
        namespace: dict[str, object],
        reactor: IReactorTime | None = None,
        banner: Banner = Banner(),
    ) -> None:
        # not factory: insults.ServerProtocol sets that of its protocol
        self.brickfactory = factory
        self.namespace = namespace
        self.reactor = reactor
        self.banner = banner
        self.current: ConsoleLine | PythonShell | None = None
        self.console: ConsoleLine | None = None
        # fires once the terminal is gone
        self.lost: defer.Deferred[None] = defer.Deferred()

    def connectionMade(self) -> None:
        # the size start() read
        size = self.terminal.termSize
        self.console = ConsoleLine(
            self.brickfactory, self, self.reactor, self.banner, size.x, size.y
        )
        self.current = self.console
        self.console.makeConnection(self.terminal)

    def python(self) -> None:
        namespace = dict(self.namespace, factory=self.brickfactory)
        self.current = PythonShell(namespace, self.back)
        self.current.makeConnection(self.terminal)

    def back(self) -> None:
        assert self.console is not None, "the terminal is connected"
        self.current = self.console
        self.console.resume()

    def keystrokeReceived(self, keyID: bytes, modifier: bytes | None) -> None:
        assert self.current is not None, "the terminal is connected"
        self.current.keystrokeReceived(keyID, modifier)

    def terminalSize(self, width: int, height: int) -> None:
        assert self.current is not None, "the terminal is connected"
        self.current.terminalSize(width, height)

    def unhandledControlSequence(self, seq: bytes) -> None:
        assert self.current is not None, "the terminal is connected"
        self.current.unhandledControlSequence(seq)

    def connectionLost(self, reason: Failure = connectionDone) -> None:
        if self.console is not None:
            self.console.connectionLost(reason)
        self.lost.callback(None)

    def close(self) -> defer.Deferred[None]:
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


@implementer(IHalfCloseableProtocol)
class PlainConsole(basic.LineReceiver):
    """
    The console on an input that isn't a terminal: a line at a time, each
    once the one before is done, the last one too without its new line.

    While a command runs, it pauses: the lines after it wait, those of the
    same read too, and so does the input. Its end closes only the input: the
    answers still to come are written, and Virtualbricks quits once the last
    command is done.
    """

    delimiter = b"\n"

    def __init__(
        self, factory: BrickFactory, reactor: IReactorTime | None = None
    ) -> None:
        self.brickfactory = factory
        self.reactor = reactor
        # the input ended: quit once its lines are done
        self.ended = False
        # a command runs
        self.busy = False
        # Virtualbricks quits: nothing more runs
        self.closed = False
        # fires once the output is closed
        self.output_closed: defer.Deferred[None] = defer.Deferred()

    def write_lines(self, lines: Iterable[str]) -> None:
        assert self.transport is not None, "the input is connected"
        for line in lines:
            self.transport.write(line.encode("utf-8", "replace") + b"\n")

    def lineReceived(self, line: bytes) -> None:
        done = run(
            self.brickfactory, line.decode("utf-8", "replace"), self.reactor
        )
        done.addCallbacks(
            self.write_lines, lambda f: self.write_lines(error_lines(f))
        )
        if done.called:
            # at once: the next line follows
            return
        self.busy = True
        self.pauseProducing()
        done.addBoth(self._next)

    def _next(self, _: object) -> None:
        self.busy = False
        if self.closed:
            return
        # the lines that wait run, up to one that takes time
        self.resumeProducing()
        if self.ended and not self.busy:
            self._quit()

    def readConnectionLost(self) -> None:
        self._end()

    def writeConnectionLost(self) -> None:
        # no one reads the answers: the commands go on all the same
        self._output_closed()

    def connectionLost(self, reason: Failure = connectionDone) -> None:
        self._output_closed()
        self._end()

    def _end(self) -> None:
        """The end of the input: its last line runs, then Virtualbricks quits."""

        if self.ended or self.closed:
            return
        self.ended = True
        rest = self.clearLineBuffer()
        if rest and not rest.endswith(self.delimiter):
            # a line, though no new line ends it
            rest += self.delimiter
        self.dataReceived(rest)
        if not self.busy:
            self._quit()

    def _output_closed(self) -> None:
        if not self.output_closed.called:
            self.output_closed.callback(None)

    def close(self) -> defer.Deferred[None]:
        """
        Virtualbricks quits: write the answers left and close the output.
        The Deferred fires then. The lines that wait don't run.
        """

        self.closed = True
        if not self.output_closed.called:
            assert self.transport is not None, "the input is connected"
            self.transport.loseConnection()
        return self.output_closed

    def _quit(self) -> None:
        done = run(self.brickfactory, "quit", self.reactor)
        done.addErrback(
            lambda f: sys.stderr.write("\n".join(error_lines(f)) + "\n")
        )


class RawTerminal:
    """The terminal of fd without its line mode, echo and signals."""

    def __init__(self, fd: int) -> None:
        self.fd = fd
        # as tcgetattr() gives them
        self.saved: list[Any] | None = None

    def start(self) -> None:
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

    def stop(self) -> None:
        if self.saved is not None:
            termios.tcsetattr(self.fd, termios.TCSANOW, self.saved)
            self.saved = None


def start(
    factory: BrickFactory,
    namespace: dict[str, object],
    reactor: ReactorBase | None = None,
    banner: Banner = Banner(),
) -> stdio.StandardIO:
    """
    Read the console on the standard input; return what reads it. On a
    terminal, it starts with banner.
    """

    if reactor is None:
        from twisted.internet import reactor as default

        reactor = cast("ReactorBase", default)
    assert sys.__stdin__ is not None, "Python has a standard input"
    stdin = sys.__stdin__.fileno()
    if not os.isatty(stdin):
        console = PlainConsole(factory, reactor)
        # before the reactor drops the answers it has yet to write
        reactor.addSystemEventTrigger("before", "shutdown", console.close)
        return stdio.StandardIO(console)
    raw = RawTerminal(stdin)
    raw.start()
    reactor.addSystemEventTrigger("after", "shutdown", raw.stop)
    protocol = insults.ServerProtocol(
        Switcher, factory, namespace, reactor, banner
    )
    try:
        size = os.get_terminal_size(stdin)
    except OSError:
        pass
    else:
        protocol.termSize.x, protocol.termSize.y = size.columns, size.lines
    io = stdio.StandardIO(protocol)
    # connected now: protocol made its Switcher
    switcher = cast(Switcher, protocol.terminalProtocol)
    # before the reactor drops what the terminal has yet to show
    reactor.addSystemEventTrigger("before", "shutdown", switcher.close)
    return io
