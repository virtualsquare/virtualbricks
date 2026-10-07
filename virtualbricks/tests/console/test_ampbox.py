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

"""The boxes of AMP without Twisted, as Twisted writes and reads them."""

import io

from twisted.protocols import amp
from twisted.trial import unittest

from virtualbricks.console import ampbox


def reader(data):
    return io.BytesIO(data).read


class TestBoxes(unittest.TestCase):

    def test_as_twisted_reads_them(self):
        box = {
            b"_ask": b"1",
            b"_command": b"Run",
            b"line": "brick set vm1 name=è".encode(),
            b"cwd": b"",
        }
        [parsed] = amp.parseString(ampbox.encode(box))
        self.assertEqual(dict(parsed), box)

    def test_as_twisted_writes_them(self):
        lines = amp.ListOf(amp.Unicode()).toString(["sw1 runs", "", "è"])
        data = amp.AmpBox(_answer=b"1", lines=lines).serialize()
        data += amp.AmpBox(
            _error=b"2", _error_code=b"COMMAND_FAILED"
        ).serialize()
        read = reader(data)
        answer = ampbox.read(read)
        self.assertEqual(answer, {b"_answer": b"1", b"lines": lines})
        self.assertEqual(ampbox.texts(answer[b"lines"]), ["sw1 runs", "", "è"])
        self.assertEqual(
            ampbox.read(read),
            {b"_error": b"2", b"_error_code": b"COMMAND_FAILED"},
        )
        self.assertRaises(ampbox.Closed, ampbox.read, read)

    def test_values(self):
        self.assertEqual(ampbox.integer(b"4200"), 4200)
        self.assertEqual(ampbox.text("è".encode()), "è")
        self.assertEqual(ampbox.texts(b""), [])
        self.assertRaises(ampbox.BadBox, ampbox.integer, b"lab1")
        self.assertRaises(ampbox.BadBox, ampbox.text, b"\xff")
        self.assertRaises(ampbox.BadBox, ampbox.texts, b"\x00\x05ab")
        self.assertRaises(ampbox.BadBox, ampbox.texts, b"\x00")

    def test_too_long(self):
        error = self.assertRaises(
            ampbox.TooLong, ampbox.encode, {b"line": b"x" * 65536}
        )
        self.assertEqual(str(error), "line")
        self.assertRaises(ampbox.TooLong, ampbox.encode, {b"k" * 256: b""})
        ampbox.encode({b"line": b"x" * 65535, b"k" * 255: b""})

    def test_not_a_box(self):
        # the greeting of a JSON socket: a key of 31522 bytes
        read = reader(b'{"protocol": 1}\n')
        self.assertRaises(ampbox.BadBox, ampbox.read, read)

    def test_cut_short(self):
        data = amp.AmpBox(_answer=b"1", lines=b"").serialize()
        for end in (1, 3, 9, len(data) - 1):
            error = self.assertRaises(
                ampbox.Closed, ampbox.read, reader(data[:end])
            )
            self.assertEqual(str(error), "in a box")
        error = self.assertRaises(ampbox.Closed, ampbox.read, reader(b""))
        self.assertEqual(str(error), "")

    def test_a_little_at_a_time(self):
        # a socket gives what has come, never more than asked
        chunks = [b"\x00", b"\x04", b"_as", b"k", b"\x00\x01", b"7"]
        chunks += [b"\x00", b"\x00"]

        def read(size):
            chunk = chunks.pop(0)
            self.assertLessEqual(len(chunk), size)
            return chunk

        self.assertEqual(ampbox.read(read), {b"_ask": b"7"})
        self.assertEqual(chunks, [])
