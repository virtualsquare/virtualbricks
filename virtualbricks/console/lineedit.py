# -*- test-case-name: virtualbricks.tests.console.test_lineedit -*-
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
The keys of readline, for a line of recvline: the line of the console and
that of the Python shell.

Moving: Ctrl+A and Ctrl+E to the ends of the line, Ctrl+B and Ctrl+F a
character, Alt+B and Alt+F, or Ctrl+Left and Ctrl+Right, a word.

Deleting: Ctrl+D the character under the cursor, or on an empty line the
end of the input; Ctrl+W the word before the cursor, up to a space;
Alt+Backspace and Alt+D the word before and after the cursor; Ctrl+U and
Ctrl+K the line before and after it. Ctrl+Y puts back what was deleted
last, and what was deleted by keys one after the other comes back together.
Ctrl+T and Alt+T swap two characters and two words.

Searching: Ctrl+R and Ctrl+S search the history backwards and forwards as
the text is typed. Ctrl+R or Ctrl+S again finds the next match, Backspace
takes back a character, Ctrl+G gives the line back as it was, and any other
key keeps the line found and does what it does: Enter runs it.

For Alt and the Ctrl arrows a word is letters and digits, so memory=512 is
two words; for Ctrl+W it is anything up to a space.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

from twisted.conch.insults import insults

if TYPE_CHECKING:  # pragma: no cover
    from twisted.conch.recvline import HistoricRecvLine as _Line
else:
    # a mixin: what it works on comes from the line that takes it
    _Line = object

# insults sets it with setattr(), out of the sight of mypy
ALT: bytes = getattr(insults.ServerProtocol, "ALT")
BACKSPACE = insults.ServerProtocol.BACKSPACE
BELL = b"\a"
CTRL_A = b"\x01"
CTRL_B = b"\x02"
CTRL_D = b"\x04"
CTRL_E = b"\x05"
CTRL_F = b"\x06"
CTRL_G = b"\x07"
CTRL_H = b"\x08"
CTRL_K = b"\x0b"
CTRL_R = b"\x12"
CTRL_S = b"\x13"
CTRL_T = b"\x14"
CTRL_U = b"\x15"
CTRL_W = b"\x17"
CTRL_Y = b"\x19"
# What terminals send for Ctrl+Left and Ctrl+Right, as Debian's inputrc
# binds them.
WORD_LEFT = (b"\x1b[1;5D", b"\x1b[5D")
WORD_RIGHT = (b"\x1b[1;5C", b"\x1b[5C")


def _printable(key: bytes) -> bool:
    return len(key) == 1 and 32 <= key[0] < 127


class Step(NamedTuple):
    """Where a search is: its text, and the line and column it found."""

    text: bytes
    number: int
    column: int
    failed: bool


class Search:
    """
    An incremental search of lines, as readline's. A step for each
    character of the text and each next match, so that Backspace goes back
    to where the text was one character shorter.
    """

    def __init__(
        self, lines: list[bytes], number: int, column: int, backward: bool
    ) -> None:
        # the history, and the line being edited among them, at number
        self.lines = lines
        self.backward = backward
        self.steps = [Step(b"", number, column, False)]

    @property
    def step(self) -> Step:
        return self.steps[-1]

    def prompt(self) -> bytes:
        failed = b"failed " if self.step.failed else b""
        way = b"reverse-" if self.backward else b""
        return b"(" + failed + way + b"i-search)`" + self.step.text + b"': "

    def line(self) -> bytes:
        return self.lines[self.step.number]

    def add(self, character: bytes) -> bool:
        """Search for the text and character, from the match on."""

        step = self.step
        return self._push(
            step.text + character, self._find(step.text + character, step)
        )

    def again(self, backward: bool, last: bytes) -> bool:
        """
        The next match, backwards or forwards; with no text yet, that of
        the last search, last.
        """

        self.backward = backward
        step = self.step
        if not step.text:
            return bool(last) and self._push(last, self._find(last, step))
        start = step.column - 1 if backward else step.column + 1
        found = self._find(step.text, step._replace(column=start), True)
        return self._push(step.text, found)

    def back(self) -> bool:
        """Take back the last character of the text; False without one."""

        text = self.step.text
        if not text:
            return False
        while self.step.text == text:
            self.steps.pop()
        return True

    def _push(self, text: bytes, found: tuple[int, int] | None) -> bool:
        step = self.step
        if found is None:
            self.steps.append(Step(text, step.number, step.column, True))
            return False
        self.steps.append(Step(text, *found, False))
        return True

    def _find(
        self, text: bytes, step: Step, skip_same: bool = False
    ) -> tuple[int, int] | None:
        """
        The line and position of the first match of text from the step's
        on, the search's way. With skip_same, the lines equal to the step's
        are passed over, as readline does for the next match.
        """

        number, start = step.number, step.column
        same = self.lines[number]
        first = True
        while 0 <= number < len(self.lines):
            line = self.lines[number]
            if first or not (skip_same and line == same):
                if self.backward:
                    found = line.rfind(text, 0, max(start + len(text), 0))
                    found = found if 0 <= found <= start else -1
                else:
                    found = line.find(text, start)
                if found >= 0:
                    return number, found
            first = False
            number += -1 if self.backward else 1
            if 0 <= number < len(self.lines):
                start = len(self.lines[number]) if self.backward else 0
        return None


class ReadlineKeys(_Line):
    """
    The keys of readline, as the module says, for a line of recvline's
    HistoricRecvLine. The class that takes them has end_of_input(), what
    Ctrl+D does on an empty line.
    """

    # the text of the last deletions, for Ctrl+Y
    killed = b""
    # whether the key before, and this one, deleted text for Ctrl+Y
    after_kill = False
    killing = False
    # the search of Ctrl+R and Ctrl+S, while it runs, and its last text
    search: Search | None = None
    last_search = b""
    # the line, its cursor and the place in the history before the search
    search_origin: tuple[list[bytes], int, int]

    if TYPE_CHECKING:  # pragma: no cover

        def end_of_input(self) -> None: ...

    def connectionMade(self) -> None:
        super().connectionMade()
        self.keyHandlers.update(
            {
                CTRL_A: self.handle_HOME,
                CTRL_B: self.handle_LEFT,
                CTRL_D: self.handle_EOF,
                CTRL_E: self.handle_END,
                CTRL_F: self.handle_RIGHT,
                CTRL_K: self.handle_KILL_LINE,
                CTRL_R: self.handle_SEARCH_BACKWARD,
                CTRL_S: self.handle_SEARCH_FORWARD,
                CTRL_T: self.handle_TRANSPOSE_CHARS,
                CTRL_U: self.handle_LINE_DISCARD,
                CTRL_W: self.handle_WORD_RUBOUT,
                CTRL_Y: self.handle_YANK,
            }
        )
        self.altKeyHandlers = {
            b"b": self.handle_BACKWARD_WORD,
            b"f": self.handle_FORWARD_WORD,
            b"d": self.handle_KILL_WORD,
            b"t": self.handle_TRANSPOSE_WORDS,
            BACKSPACE: self.handle_BACKWARD_KILL_WORD,
            CTRL_H: self.handle_BACKWARD_KILL_WORD,
        }

    def keystrokeReceived(self, keyID: bytes, modifier: bytes | None) -> None:
        self.after_kill, self.killing = self.killing, False
        if self.search is not None and self._search_key(keyID, modifier):
            return
        if modifier == ALT:
            handler = self.altKeyHandlers.get(keyID.lower())
            if handler is None:
                self._bell()
            else:
                handler()
            return
        super().keystrokeReceived(keyID, modifier)

    def unhandledControlSequence(self, seq: bytes) -> None:
        self.after_kill, self.killing = self.killing, False
        if self.search is not None:
            self._end_search(accept=True)
        if seq in WORD_LEFT:
            self.handle_BACKWARD_WORD()
        elif seq in WORD_RIGHT:
            self.handle_FORWARD_WORD()
        else:
            super().unhandledControlSequence(seq)

    def drawInputLine(self) -> None:
        # the cursor goes back where it is in the line
        if self.search is not None:
            prompt, line = self.search.prompt(), self.search.line()
            index = self.search.step.column
        else:
            prompt, line = self.ps[self.pn], b"".join(self.lineBuffer)
            index = self.lineBufferIndex
        self.terminal.write(prompt + line)
        if index < len(line):
            self.terminal.cursorBackward(len(line) - index)

    # moving

    def handle_BACKWARD_WORD(self) -> None:
        self._move(self._word_start(self.lineBufferIndex))

    def handle_FORWARD_WORD(self) -> None:
        self._move(self._word_end(self.lineBufferIndex))

    # deleting

    def handle_EOF(self) -> None:
        if not self.lineBuffer:
            self.end_of_input()
        elif self.lineBufferIndex < len(self.lineBuffer):
            self.handle_DELETE()
        else:
            self._bell()

    def handle_WORD_RUBOUT(self) -> None:
        # a word ends at a space, and the spaces after it go with it
        start = self.lineBufferIndex
        while start and self.lineBuffer[start - 1].isspace():
            start -= 1
        while start and not self.lineBuffer[start - 1].isspace():
            start -= 1
        self._kill(start, self.lineBufferIndex)

    def handle_BACKWARD_KILL_WORD(self) -> None:
        index = self.lineBufferIndex
        self._kill(self._word_start(index), index)

    def handle_KILL_WORD(self) -> None:
        index = self.lineBufferIndex
        self._kill(index, self._word_end(index))

    def handle_LINE_DISCARD(self) -> None:
        self._kill(0, self.lineBufferIndex)

    def handle_KILL_LINE(self) -> None:
        self._kill(self.lineBufferIndex, len(self.lineBuffer))

    def handle_YANK(self) -> None:
        if not self.killed:
            self._bell()
            return
        for character in self.killed:
            self.characterReceived(bytes([character]), False)

    def handle_TRANSPOSE_CHARS(self) -> None:
        # the character before the cursor goes past the one under it; at
        # the end of the line, the last two change places
        line, index = self.lineBuffer, self.lineBufferIndex
        if index == 0 or len(line) < 2:
            self._bell()
            return
        if index == len(line):
            index -= 1
        line[index - 1], line[index] = line[index], line[index - 1]
        self.lineBufferIndex = index + 1
        self._redraw()

    def handle_TRANSPOSE_WORDS(self) -> None:
        # the word before the cursor goes past the one after it, found as
        # readline finds them; at the end of the line, the last two
        second_end = self._word_end(self.lineBufferIndex)
        second = self._word_start(second_end)
        first = self._word_start(second)
        first_end = self._word_end(first)
        if first == second or second < first_end:
            self._bell()
            return
        line = self.lineBuffer
        line[first:second_end] = (
            line[second:second_end]
            + line[first_end:second]
            + line[first:first_end]
        )
        self.lineBufferIndex = second_end
        self._redraw()

    # searching

    def handle_SEARCH_BACKWARD(self) -> None:
        self._start_search(backward=True)

    def handle_SEARCH_FORWARD(self) -> None:
        self._start_search(backward=False)

    def _start_search(self, backward: bool) -> None:
        lines = list(self.historyLines)
        number = self.historyPosition
        current = b"".join(self.lineBuffer)
        if number < len(lines):
            lines[number] = current
        else:
            lines.append(current)
            number = len(lines) - 1
        self.search = Search(lines, number, self.lineBufferIndex, backward)
        self.search_origin = (
            list(self.lineBuffer),
            self.lineBufferIndex,
            self.historyPosition,
        )
        self._redraw()

    def _search_key(self, keyID: bytes, modifier: bytes | None) -> bool:
        """A key while searching; False when it ends the search."""

        search = self.search
        assert search is not None, "a search runs"
        found: bool | None
        if modifier is not None:
            found = None
        elif keyID in (CTRL_R, CTRL_S):
            found = search.again(keyID == CTRL_R, self.last_search)
        elif keyID in (BACKSPACE, CTRL_H):
            found = search.back()
        elif keyID == CTRL_G:
            self._end_search(accept=False)
            return True
        elif _printable(keyID):
            found = search.add(keyID)
        else:
            found = None
        if found is None:
            self._end_search(accept=True)
            return False
        if not found:
            self._bell()
        self._redraw()
        return True

    def _end_search(self, accept: bool) -> None:
        search, self.search = self.search, None
        assert search is not None, "a search runs"
        if search.step.text:
            self.last_search = search.step.text
        if accept:
            # the line found, where Up and Down go on from
            step = search.step
            self.lineBuffer = [bytes([c]) for c in search.lines[step.number]]
            self.lineBufferIndex = step.column
            self.historyPosition = step.number
        else:
            line, index, position = self.search_origin
            self.lineBuffer = line
            self.lineBufferIndex = index
            self.historyPosition = position
        self._redraw()

    # helpers

    def _bell(self) -> None:
        self.terminal.write(BELL)

    def _redraw(self) -> None:
        self.terminal.write(b"\r")
        self.terminal.eraseToLineEnd()
        self.drawInputLine()

    def _move(self, index: int) -> None:
        offset = index - self.lineBufferIndex
        if offset > 0:
            self.terminal.cursorForward(offset)
        elif offset < 0:
            self.terminal.cursorBackward(-offset)
        self.lineBufferIndex = index

    def _word_start(self, index: int) -> int:
        line = self.lineBuffer
        while index and not line[index - 1].isalnum():
            index -= 1
        while index and line[index - 1].isalnum():
            index -= 1
        return index

    def _word_end(self, index: int) -> int:
        line = self.lineBuffer
        while index < len(line) and not line[index].isalnum():
            index += 1
        while index < len(line) and line[index].isalnum():
            index += 1
        return index

    def _kill(self, start: int, end: int) -> None:
        """
        Delete the line from start to end, one of them the cursor, and keep
        it for Ctrl+Y: after another deletion, together with that one's.
        """

        self.killing = True
        if start == end:
            self._bell()
            return
        text = b"".join(self.lineBuffer[start:end])
        if not self.after_kill:
            self.killed = text
        elif end == self.lineBufferIndex:
            # backwards: before the text of the last deletion
            self.killed = text + self.killed
        else:
            self.killed += text
        self._move(start)
        del self.lineBuffer[start:end]
        self.terminal.deleteCharacter(end - start)
