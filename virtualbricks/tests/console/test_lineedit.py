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

"""The keys of readline on a line of recvline, and what the screen shows."""

from twisted.conch import recvline
from twisted.conch.insults import helper
from twisted.trial import unittest

from virtualbricks.console.lineedit import (
    ALT,
    BACKSPACE,
    CTRL_A,
    CTRL_B,
    CTRL_D,
    CTRL_E,
    CTRL_F,
    CTRL_G,
    CTRL_H,
    CTRL_K,
    CTRL_R,
    CTRL_S,
    CTRL_T,
    CTRL_U,
    CTRL_W,
    CTRL_Y,
    ReadlineKeys,
)

LEFT = helper.TerminalBuffer.LEFT_ARROW
RIGHT = helper.TerminalBuffer.RIGHT_ARROW


class Line(ReadlineKeys, recvline.HistoricRecvLine):

    ps = (b"> ",)

    def __init__(self):
        super().__init__()
        self.received = []
        self.ended = 0

    def lineReceived(self, line):
        self.received.append(line)
        self.terminal.write(self.ps[self.pn])

    def end_of_input(self):
        self.ended += 1


class LineTestCase(unittest.TestCase):

    def setUp(self):
        self.screen = helper.TerminalBuffer()
        self.screen.connectionMade()
        self.line = Line()
        self.line.makeConnection(self.screen)

    def type(self, text):
        for character in text.encode():
            self.line.keystrokeReceived(bytes([character]), None)

    def keys(self, *keys):
        for key in keys:
            self.line.keystrokeReceived(key, None)

    def alt(self, *keys):
        for key in keys:
            self.line.keystrokeReceived(key, ALT)

    def bells(self):
        """Count the bells from now on: bells() is how many rang."""

        written = []
        write = self.screen.write

        def record(data):
            written.append(data)
            write(data)

        self.patch(self.screen, "write", record)
        return lambda: written.count(b"\a")

    def assertLine(self, expected):
        """
        The row of the cursor is expected, where | is the cursor; out of a
        search, the line and its cursor are the same.
        """

        cursor = expected.index("|")
        text = expected.replace("|", "")
        x, y = self.screen.reportCursorPosition()
        row = bytes(self.screen).decode().split("\n")[y]
        self.assertEqual((row.rstrip(), x), (text.rstrip(), cursor))
        if self.line.search is None:
            line = b"".join(self.line.lineBuffer).decode()
            self.assertEqual(
                ("> " + line, self.line.lineBufferIndex + 2), (text, cursor)
            )


class TestMoving(LineTestCase):

    def test_characters(self):
        self.type("abc")
        self.keys(CTRL_B, CTRL_B)
        self.assertLine("> a|bc")
        self.keys(CTRL_F)
        self.assertLine("> ab|c")
        self.keys(CTRL_A)
        self.assertLine("> |abc")
        self.keys(CTRL_E)
        self.assertLine("> abc|")

    def test_words(self):
        # a word is letters and digits
        self.type("brick set vm1 memory=512")
        self.alt(b"b")
        self.assertLine("> brick set vm1 memory=|512")
        self.alt(b"b")
        self.assertLine("> brick set vm1 |memory=512")
        self.alt(b"b", b"b", b"b", b"b")
        self.assertLine("> |brick set vm1 memory=512")
        self.alt(b"f")
        self.assertLine("> brick| set vm1 memory=512")
        self.alt(b"F", b"F")
        self.assertLine("> brick set vm1| memory=512")

    def test_ctrl_arrows(self):
        self.type("brick set vm1")
        for sequence in (b"\x1b[1;5D", b"\x1b[5D"):
            self.line.unhandledControlSequence(sequence)
        self.assertLine("> brick |set vm1")
        self.line.unhandledControlSequence(b"\x1b[1;5C")
        self.assertLine("> brick set| vm1")
        self.line.unhandledControlSequence(b"\x1b[5C")
        self.assertLine("> brick set vm1|")

    def test_other_alt_keys(self):
        bells = self.bells()
        self.alt(b"x")
        self.assertEqual(bells(), 1)
        self.assertLine("> |")

    def test_the_cursor_is_drawn_where_it_is(self):
        self.type("abcd")
        self.keys(LEFT, LEFT)
        self.line.terminalSize(80, 24)
        self.assertLine("> ab|cd")


class TestDeleting(LineTestCase):

    def test_ctrl_d_deletes_under_the_cursor(self):
        self.type("abc")
        self.keys(CTRL_A, CTRL_D)
        self.assertLine("> |bc")
        bells = self.bells()
        self.keys(CTRL_E, CTRL_D)
        self.assertEqual(bells(), 1)
        self.assertLine("> bc|")
        self.assertEqual(self.line.ended, 0)

    def test_ctrl_d_on_an_empty_line_ends(self):
        self.keys(CTRL_D)
        self.assertEqual(self.line.ended, 1)

    def test_ctrl_w_kills_the_word_before_the_cursor(self):
        self.type("brick start sw1 ")
        # the spaces after the word go with it
        self.keys(CTRL_W)
        self.assertLine("> brick start |")
        self.keys(CTRL_W)
        self.assertLine("> brick |")

    def test_ctrl_w_in_the_middle(self):
        self.type("brick list sw1")
        self.keys(*[LEFT] * 4, CTRL_W)
        self.assertLine("> brick | sw1")
        self.type("show")
        self.assertLine("> brick show| sw1")

    def test_alt_backspace_kills_letters_and_digits(self):
        self.type("memory=512")
        self.alt(BACKSPACE)
        self.assertLine("> memory=|")
        self.alt(CTRL_H)
        self.assertLine("> |")
        self.assertEqual(self.line.killed, b"memory=512")

    def test_alt_d_kills_the_word_after_the_cursor(self):
        self.type("brick show sw1")
        self.keys(CTRL_A)
        self.alt(b"d")
        self.assertLine("> | show sw1")
        self.alt(b"d")
        self.assertLine("> | sw1")
        self.assertEqual(self.line.killed, b"brick show")

    def test_ctrl_u_and_ctrl_k(self):
        self.type("brick show sw1")
        self.keys(*[LEFT] * 4, CTRL_U)
        self.assertLine("> | sw1")
        self.keys(RIGHT, CTRL_K)
        self.assertLine(">  |")
        self.assertEqual(self.line.killed, b"sw1")

    def test_kills_in_a_row_come_back_together(self):
        self.type("brick show sw1")
        self.keys(CTRL_W, CTRL_W)
        self.assertLine("> brick |")
        self.keys(CTRL_Y)
        self.assertLine("> brick show sw1|")
        # backwards, then forwards
        self.alt(b"b")
        self.keys(CTRL_U, CTRL_K)
        self.assertEqual(self.line.killed, b"brick show sw1")
        self.keys(CTRL_Y)
        self.assertLine("> brick show sw1|")

    def test_a_kill_after_another_key_replaces(self):
        self.type("a b")
        self.keys(CTRL_W)
        self.type("c")
        self.keys(CTRL_W)
        self.assertEqual(self.line.killed, b"c")
        self.keys(CTRL_Y)
        self.assertLine("> a c|")

    def test_what_was_killed_stays_for_the_next_lines(self):
        self.type("brick new switch")
        self.keys(CTRL_U, b"\r", CTRL_Y, b"\r")
        self.assertEqual(self.line.received, [b"", b"brick new switch"])

    def test_nothing_to_kill_or_yank(self):
        bells = self.bells()
        self.keys(CTRL_W, CTRL_U, CTRL_K, CTRL_Y)
        self.alt(b"d", BACKSPACE)
        self.assertEqual(bells(), 6)
        self.assertLine("> |")

    def test_ctrl_t_swaps_characters(self):
        self.type("brikc")
        # at the end, the last two
        self.keys(CTRL_T)
        self.assertLine("> brick|")
        self.keys(CTRL_A, CTRL_F, CTRL_F, CTRL_T)
        self.assertLine("> bir|ck")
        bells = self.bells()
        self.keys(CTRL_A, CTRL_T)
        self.assertEqual(bells(), 1)
        self.assertLine("> |birck")

    def test_alt_t_swaps_words(self):
        self.type("start brick sw1")
        self.keys(CTRL_A)
        self.alt(b"f", b"f", b"b")
        self.alt(b"t")
        self.assertLine("> brick start| sw1")
        # at the end, the last two
        self.keys(CTRL_E)
        self.alt(b"t")
        self.assertLine("> brick sw1 start|")
        bells = self.bells()
        self.keys(CTRL_A)
        self.alt(b"t")
        self.assertEqual(bells(), 1)
        self.assertLine("> |brick sw1 start")


class TestSearch(LineTestCase):

    def setUp(self):
        super().setUp()
        self.line.historyLines = [
            b"brick new switch",
            b"brick start sw1",
            b"status",
            b"brick start sw1",
        ]
        self.line.historyPosition = 4

    def test_ctrl_r_finds_as_it_is_typed(self):
        self.keys(CTRL_R)
        self.assertLine("(reverse-i-search)`': |")
        self.type("st")
        self.assertLine("(reverse-i-search)`st': brick |start sw1")
        self.type("at")
        self.assertLine("(reverse-i-search)`stat': |status")

    def test_ctrl_r_again_finds_the_next(self):
        self.keys(CTRL_R)
        self.type("st")
        # the same line again is passed over
        self.keys(CTRL_R)
        self.assertLine("(reverse-i-search)`st': |status")
        self.keys(CTRL_R)
        self.assertLine("(reverse-i-search)`st': brick |start sw1")
        # none more: the line found stays
        bells = self.bells()
        self.keys(CTRL_R)
        self.assertEqual(bells(), 1)
        self.assertLine("(failed reverse-i-search)`st': brick |start sw1")

    def test_ctrl_s_goes_forward(self):
        self.keys(CTRL_R)
        self.type("sw")
        self.keys(CTRL_R)
        self.assertLine("(reverse-i-search)`sw': brick new |switch")
        self.keys(CTRL_S)
        self.assertLine("(i-search)`sw': brick start |sw1")

    def test_backspace_takes_back_a_character(self):
        self.keys(CTRL_R)
        self.type("st")
        self.keys(CTRL_R, BACKSPACE)
        self.assertLine("(reverse-i-search)`s': brick start |sw1")
        self.keys(BACKSPACE)
        self.assertLine("(reverse-i-search)`': |")
        bells = self.bells()
        self.keys(BACKSPACE)
        self.assertEqual(bells(), 1)

    def test_enter_runs_the_line_found(self):
        self.keys(CTRL_R)
        self.type("new")
        self.keys(b"\r")
        self.assertEqual(self.line.received, [b"brick new switch"])
        self.assertEqual(self.line.historyLines[-1], b"brick new switch")

    def test_another_key_keeps_the_line_found(self):
        self.type("bri")
        self.keys(CTRL_R)
        self.type("atu")
        self.keys(CTRL_E)
        self.assertLine("> status|")
        # Up and Down go on from it
        self.keys(helper.TerminalBuffer.DOWN_ARROW)
        self.assertEqual(b"".join(self.line.lineBuffer), b"brick start sw1")

    def test_alt_keys_and_sequences_end_it_too(self):
        self.keys(CTRL_R)
        self.type("sta")
        self.alt(b"f")
        self.assertLine("> brick start| sw1")
        self.keys(CTRL_R)
        self.type("new")
        self.line.unhandledControlSequence(b"\x1b[1;5C")
        self.assertLine("> brick new| switch")

    def test_ctrl_g_gives_the_line_back(self):
        self.type("bri")
        self.keys(LEFT, CTRL_R)
        self.type("status")
        self.keys(CTRL_G)
        self.assertLine("> br|i")
        self.assertEqual(self.line.historyPosition, 4)

    def test_ctrl_r_twice_searches_the_last_text(self):
        self.keys(CTRL_R)
        self.type("new")
        self.keys(CTRL_G, CTRL_R, CTRL_R)
        self.assertLine("(reverse-i-search)`new': brick |new switch")

    def test_nothing_found(self):
        bells = self.bells()
        self.keys(CTRL_R)
        self.type("x")
        self.assertEqual(bells(), 1)
        self.assertLine("(failed reverse-i-search)`x': |")
