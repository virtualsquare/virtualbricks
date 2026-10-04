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

"""The output of a program, line by line, as a terminal shows it."""

from twisted.trial import unittest

from virtualbricks.terminal import Lines

# What the monitor of QEMU 10.0 writes on its standard output, read by read,
# when "info status" comes on its standard input.
QEMU_INFO_STATUS = [
    b"(qemu) ",
    b"i\x1b[K",
    b"\x1b[Din\x1b[K",
    b"\x1b[D\x1b[Dinf\x1b[K",
    b"\x1b[D\x1b[D\x1b[Dinfo\x1b[K",
    b"\x1b[D\x1b[D\x1b[D\x1b[Dinfo \x1b[K",
    b"\x1b[D\x1b[D\x1b[D\x1b[D\x1b[Dinfo s\x1b[K",
    b"\x1b[D\x1b[D\x1b[D\x1b[D\x1b[D\x1b[Dinfo st\x1b[K",
    b"\x1b[D\x1b[D\x1b[D\x1b[D\x1b[D\x1b[D\x1b[Dinfo sta\x1b[K",
    b"\x1b[D\x1b[D\x1b[D\x1b[D\x1b[D\x1b[D\x1b[D\x1b[Dinfo stat\x1b[K",
    b"\x1b[D\x1b[D\x1b[D\x1b[D\x1b[D\x1b[D\x1b[D\x1b[D\x1b[Dinfo statu\x1b[K",
    b"\x1b[D" * 10 + b"info status\x1b[K",
    b"\r\n",
    b"VM status: paused (prelaunch)\r\n",
    b"(qemu) ",
]


def read(*pieces):
    """The lines of pieces of output, the one not ended too."""

    lines = Lines("utf-8")
    read = []
    for piece in pieces:
        read.extend(lines.feed(piece))
    return read + lines.flush()


class TestLines(unittest.TestCase):

    def test_qemu_monitor(self):
        """
        The echo of a command that QEMU writes again at each key is the
        line with its prompt, once.
        """

        lines = Lines("utf-8")
        read = [lines.feed(piece) for piece in QEMU_INFO_STATUS]
        self.assertEqual(
            read,
            [[]] * 12
            + [["(qemu) info status"], ["VM status: paused (prelaunch)"], []],
        )
        self.assertEqual(lines.flush(), ["(qemu) "])

    def test_line_ends(self):
        lines = Lines("utf-8")
        self.assertEqual(lines.feed(b"one\ntwo\r\n\nthr"), ["one", "two", ""])
        self.assertEqual(lines.feed(b"ee\n"), ["three"])
        self.assertEqual(lines.flush(), [])

    def test_vertical_tab_and_form_feed_end_lines(self):
        self.assertEqual(read(b"one\x0btwo\x0cthree"), ["one", "two", "three"])

    def test_flush(self):
        """
        flush() gives the line not ended, and the next line starts at the
        first column.
        """

        lines = Lines("utf-8")
        self.assertEqual(lines.feed(b"  vde$ "), [])
        self.assertEqual(lines.flush(), ["  vde$ "])
        self.assertEqual(lines.flush(), [])
        self.assertEqual(lines.feed(b"\x1b[Cx\n"), [" x"])

    def test_flush_drops_a_sequence_cut_short(self):
        lines = Lines("utf-8")
        self.assertEqual(lines.feed(b"ab\x1b["), [])
        self.assertEqual(lines.flush(), ["ab"])
        self.assertEqual(lines.feed(b"Dx\n"), ["Dx"])

    def test_carriage_return(self):
        """The line written again over itself, as a progress shows."""

        self.assertEqual(read(b"10%\r20%\r100%\r\n"), ["100%"])
        self.assertEqual(read(b"abcdef\rxy"), ["xycdef"])

    def test_backspace(self):
        self.assertEqual(read(b"ab\bc"), ["ac"])
        self.assertEqual(read(b"\b\bab"), ["ab"])

    def test_tab(self):
        """A tab moves to the next column of eight, over what is there."""

        self.assertEqual(read(b"a\tb"), ["a       b"])
        self.assertEqual(read(b"12345678\tb"), ["12345678        b"])
        self.assertEqual(read(b"abcdefghij\rx\ty"), ["xbcdefghyj"])
        self.assertEqual(read(b"a\t"), ["a"])

    def test_cursor_left_and_right(self):
        self.assertEqual(read(b"abc\x1b[2Dx"), ["axc"])
        self.assertEqual(read(b"abc\x1b[Dx"), ["abx"])
        self.assertEqual(read(b"abc\x1b[9Dx"), ["xbc"])
        self.assertEqual(read(b"a\x1b[3Cb"), ["a   b"])
        self.assertEqual(read(b"abc\x1b[0Dx"), ["abx"])

    def test_cursor_to_column(self):
        self.assertEqual(read(b"abcdef\x1b[3Gx"), ["abxdef"])
        self.assertEqual(read(b"abc\x1b[Gx"), ["xbc"])
        self.assertEqual(read(b"ab\x1b[6`x"), ["ab   x"])

    def test_erase_in_line(self):
        self.assertEqual(read(b"abcdef\x1b[3G\x1b[K"), ["ab"])
        self.assertEqual(read(b"abcdef\x1b[3G\x1b[0K"), ["ab"])
        self.assertEqual(read(b"abcdef\x1b[3G\x1b[1K"), ["   def"])
        self.assertEqual(read(b"abcdef\x1b[3G\x1b[1Kx"), ["  xdef"])
        self.assertEqual(read(b"abc\x1b[9G\x1b[1Kx"), ["        x"])
        self.assertEqual(read(b"abcdef\x1b[3G\x1b[2Kx"), ["  x"])
        # the selective erase
        self.assertEqual(read(b"abcdef\x1b[3G\x1b[?1K"), ["   def"])

    def test_erase_characters(self):
        self.assertEqual(read(b"abcdef\x1b[2G\x1b[2X"), ["a  def"])
        self.assertEqual(read(b"abcdef\x1b[2G\x1b[X"), ["a cdef"])
        self.assertEqual(read(b"abcdef\x1b[5G\x1b[9X"), ["abcd"])

    def test_delete_characters(self):
        self.assertEqual(read(b"abcdef\x1b[2G\x1b[2P"), ["adef"])
        self.assertEqual(read(b"abcdef\x1b[2G\x1b[P"), ["acdef"])

    def test_insert_characters(self):
        self.assertEqual(read(b"abcdef\x1b[2G\x1b[2@xy"), ["axybcdef"])
        self.assertEqual(read(b"ab\x1b[5G\x1b[2@x"), ["ab  x"])

    def test_colours_go(self):
        self.assertEqual(
            read(b"\x1b[1;31merror\x1b[0m: \x1b[38;5;208mdisk\x1b[m"),
            ["error: disk"],
        )

    def test_other_sequences_go(self):
        """
        What doesn't edit the line goes: the title of the window, the
        sequences that move the cursor to another line or clear the screen,
        the modes, the character sets.
        """

        self.assertEqual(read(b"\x1b]0;qemu\x07up"), ["up"])
        self.assertEqual(read(b"\x1b]2;qemu\x1b\\up"), ["up"])
        self.assertEqual(read(b"a\x1b[2J\x1b[H\x1b[3;4Hb\x1b[Ac"), ["abc"])
        self.assertEqual(read(b"\x1b[?25la\x1b[?25h\x1b[?7l"), ["a"])
        self.assertEqual(read(b"\x1b(Ba\x1b7b\x1b8c\x1bc"), ["abc"])
        self.assertEqual(read(b"\x1bP1$r\x1b\\a"), ["a"])

    def test_other_control_characters_go(self):
        self.assertEqual(read(b"a\x07b\x00c\x7fd\x0ee"), ["abcde"])

    def test_escape_that_starts_no_sequence(self):
        """The escape goes, what follows it stays."""

        self.assertEqual(read(b"a\x1b\nb"), ["a", "b"])
        self.assertEqual(read(b"a\x1b[1\nb"), ["a[1", "b"])

    def test_sequence_over_two_reads(self):
        for cut in range(1, 6):
            data = b"abc\x1b[2Dx\x1b[K\n"
            # the cuts fall in ESC [ 2 D
            pieces = (data[: 3 + cut], data[3 + cut :])
            self.assertEqual(read(*pieces), ["ax"], pieces)

    def test_string_over_two_reads(self):
        self.assertEqual(read(b"a\x1b]0;qe", b"mu\x07b"), ["ab"])
        self.assertEqual(read(b"a\x1b]0;qemu\x1b", b"\\b"), ["ab"])

    def test_sequence_cut_short_goes(self):
        self.assertEqual(read(b"ab\x1b["), ["ab"])
        self.assertEqual(read(b"ab\x1b]0;title"), ["ab"])

    def test_character_over_two_reads(self):
        self.assertEqual(read(b"caf\xc3", b"\xa9\n"), ["café"])

    def test_bytes_that_are_not_text(self):
        self.assertEqual(read(b"a\xffb\n"), ["a�b"])
        self.assertEqual(read(b"caf\xc3"), ["caf�"])

    def test_encoding(self):
        lines = Lines("latin-1")
        self.assertEqual(lines.feed(b"caf\xe9\n"), ["café"])
