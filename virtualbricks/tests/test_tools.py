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

import os
import os.path
import struct

from virtualbricks import tools
from virtualbricks.tests import unittest


class MockLock(object):

    def __init__(self):
        self.c = 0

    def __enter__(self):
        self.c += 1

    def __exit__(self, exc_type, exc_value, traceback):
        pass


BACKING_FILENAME = '/hello/backingfile'
BACKING_FILENAME_B = os.fsencode(BACKING_FILENAME)
COW_HEADER = b"OOOM\x00\x00\x00\x02" + BACKING_FILENAME_B + b"\x00" * 1006
QCOW_HEADER = b"QFI\xfb\x00\x00\x00\x01" + struct.pack(">Q", 20) + \
        struct.pack(">I", len(BACKING_FILENAME_B)) + BACKING_FILENAME_B
QCOW_HEADER0 = b"QFI\xfb\x00\x00\x00\x01" + b"\x00" * 12
QCOW_HEADER2 = b"QFI\xfb\x00\x00\x00\x02" + struct.pack(">Q", 20) + \
        struct.pack(">I", len(BACKING_FILENAME_B)) + BACKING_FILENAME_B
UNKNOWN_HEADER = b"MOOO\x00\x00\x00\x02"


class TestTools(unittest.TestCase):

    def test_sincronize_with(self):
        lock = MockLock()
        foo_s = tools.synchronize_with(lock)(lambda: None)
        foo_s()
        self.assertEqual(lock.c, 1)
        foo_s()
        self.assertEqual(lock.c, 2)

    def test_tempfile_context(self):
        with tools.Tempfile() as (fd, filename):
            os.close(fd)
            self.assertTrue(os.path.isfile(filename))
        try:
            with tools.Tempfile() as (fd, filename):
                os.close(fd)
                raise RuntimeError
        except RuntimeError:
            self.assertFalse(os.path.isfile(filename))

    def _create_image(self, content):
        filename = self.mktemp()
        with open(filename, 'wb') as fp:
            fp.write(content)
        return filename

    def test_backing_file_cow(self):
        imagefile = self._create_image(COW_HEADER)
        backing_file = tools.get_backing_file(imagefile)
        self.assertEqual(backing_file, BACKING_FILENAME)

    def test_backing_file_qcow_no_filename(self):
        imagefile = self._create_image(QCOW_HEADER0)
        backing_file = tools.get_backing_file(imagefile)
        self.assertEqual(backing_file, None)

    def test_backing_file_qcow(self):
        imagefile = self._create_image(QCOW_HEADER)
        backing_file = tools.get_backing_file(imagefile)
        self.assertEqual(backing_file, BACKING_FILENAME)

    def test_backing_file_unknown_format(self):
        imagefile = self._create_image(UNKNOWN_HEADER)
        with self.assertRaises(tools.NotCowFileError):
            tools.get_backing_file(imagefile)

    def test_fmtsize(self):
        """Basic fmtusage."""

        self.assertEqual("1023 B", tools.fmtsize(1023))
        self.assertEqual("5120 B", tools.fmtsize(5 * 1024))
        self.assertEqual("9216 B", tools.fmtsize(9 * 1024))
        self.assertEqual("123.0 MB", tools.fmtsize(123 * 1024 ** 2))
        self.assertEqual("10.0 GB", tools.fmtsize(10200 * 1024 ** 2))
        self.assertEqual("321.0 GB", tools.fmtsize(321 * 1024 ** 3))
