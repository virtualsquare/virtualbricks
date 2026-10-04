# -*- test-case-name: virtualbricks.tests.test_terminal -*-
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
The output of a program, line by line, as a terminal shows it.

A program that edits its line as on a terminal mixes control characters and
ANSI escape sequences into its output: the monitor of QEMU echoes each key of
a command, then moves the cursor back with ``ESC [ D`` and writes the line
again, and each of these comes in a read of its own. :class:`Lines` reads the
output as it comes, in pieces that can split a line, a sequence or a
character, and gives back the lines that end, as a terminal shows them.

It follows what edits a line: carriage return, backspace, tab, and the CSI
sequences that move the cursor along the line (``C``, ``D``, ``G`` and its
twin HPA), erase (``K``, ``X``), delete (``P``) and insert (``@``). It drops
the other sequences, the colours of ``m`` too, and the other control
characters: a log has no screen to clear, nor a cursor to move up.
"""

import codecs
import re

TAB = 8

# A whole escape sequence: CSI, a string (OSC, DCS, SOS, PM, APC) up to
# BEL or ST, or another sequence of ESC, its intermediates and its final.
_SEQUENCE = re.compile(
    r"""
    \x1b\[ (?P<params>[0-?]*) [ -/]* (?P<final>[@-~])
    | \x1b[]PX^_] .*? (?:\x07|\x1b\\)
    | \x1b (?: [ -/]+ [0-~] | [0-OQ-WYZ\\`-~] )
    """,
    re.VERBOSE | re.DOTALL,
)
# The start of a sequence that the next piece of output ends.
_UNFINISHED = re.compile(
    r"\x1b (?: \[[0-?]*[ -/]* | []PX^_].* | [ -/]* )? \Z",
    re.VERBOSE | re.DOTALL,
)
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")
# what ends a line: line feed, vertical tab and form feed
_NEWLINES = "\n\x0b\x0c"


class Lines:
    """
    The lines of the output of a program, as a terminal shows them.

    feed() takes the bytes as they come and returns the lines that they
    end; flush(), when the output ends, returns the last line too, the one
    that the program didn't end.
    """

    def __init__(self, encoding):
        self._decoder = codecs.getincrementaldecoder(encoding)("replace")
        # the start of a sequence that the next piece ends
        self._pending = ""
        self._cells = []
        self._column = 0

    def feed(self, data):
        """Read data, bytes, and return the lines that it ends."""

        return self._read(self._decoder.decode(data))

    def flush(self):
        """The lines that the program didn't end, as feed() returns them."""

        lines = self._read(self._decoder.decode(b"", final=True))
        self._decoder.reset()
        # a sequence cut short
        self._pending = ""
        if self._cells:
            lines.append(self._end_line())
        return lines

    def _read(self, text):
        text = self._pending + text
        self._pending = ""
        lines = []
        position = 0
        while position < len(text):
            control = _CONTROL.search(text, position)
            end = len(text) if control is None else control.start()
            if end > position:
                self._write(text[position:end])
                position = end
                continue
            char = text[position]
            if char != "\x1b":
                if char in _NEWLINES:
                    lines.append(self._end_line())
                else:
                    self._control(char)
                position += 1
                continue
            sequence = _SEQUENCE.match(text, position)
            if sequence is not None:
                if sequence["final"] is not None:
                    self._csi(sequence["params"], sequence["final"])
                position = sequence.end()
            elif _UNFINISHED.match(text, position):
                self._pending = text[position:]
                break
            else:
                # an ESC that starts no sequence
                position += 1
        return lines

    def _end_line(self):
        line = "".join(self._cells)
        self._cells = []
        self._column = 0
        return line

    def _write(self, text):
        cells = self._cells
        if self._column > len(cells):
            cells.extend(" " * (self._column - len(cells)))
        cells[self._column : self._column + len(text)] = text
        self._column += len(text)

    def _control(self, char):
        if char == "\r":
            self._column = 0
        elif char == "\b":
            self._column = max(self._column - 1, 0)
        elif char == "\t":
            self._column = (self._column // TAB + 1) * TAB

    def _csi(self, params, final):
        # ? K, a selective erase, erases as K does
        first = params.lstrip("<=>?").split(";")[0]
        number = int(first) if first.isdigit() else 0
        count = max(number, 1)
        cells = self._cells
        column = self._column
        if final == "D":
            self._column = max(column - count, 0)
        elif final == "C":
            self._column = column + count
        elif final in "G`":
            self._column = count - 1
        elif final == "K":
            if number == 0:
                del cells[column:]
            elif number == 1:
                self._blank(0, column + 1)
            elif number == 2:
                cells.clear()
        elif final == "X":
            self._blank(column, column + count)
        elif final == "P":
            del cells[column : column + count]
        elif final == "@":
            if column < len(cells):
                cells[column:column] = " " * count

    def _blank(self, start, end):
        """Erase from start to end: the blanks at the end go."""

        cells = self._cells
        if end >= len(cells):
            del cells[start:]
        else:
            cells[start:end] = " " * (end - start)
