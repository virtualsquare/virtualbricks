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

"""The format of an image and its backing file, from its header."""

import struct

from twisted.trial import unittest

from virtualbricks.qemu.imageformat import (
    MAX_HEADER_LENGTH,
    ImageFormat,
    NotCowFileError,
    get_backing_file,
    image_type,
    image_type_from_file,
)


def qcow(version, backing=b""):
    """A qcow header, and its backing file after it."""

    offset = 72 if backing else 0
    header = b"QFI\xfb" + struct.pack(">IQI", version, offset, len(backing))
    return header.ljust(72, b"\x00") + backing


def cow(backing=b"", version=2):
    return b"OOOM" + struct.pack(">I", version) + backing.ljust(1024, b"\0")


def vdi():
    return b"<<< Oracle VM VirtualBox Disk Image >>>\n".ljust(
        64, b"\x00"
    ) + struct.pack("<I", 0xBEDA107F)


CLOOP = (
    b"#!/bin/sh\n#V2.0 Format\n"
    b"modprobe cloop file=$0 && mount -r -t iso9660 /dev/cloop $1\n"
)


class TestImageType(unittest.TestCase):
    def test_qcow(self):
        self.assertIs(image_type(qcow(1)), ImageFormat.QCOW)
        self.assertIs(image_type(qcow(2)), ImageFormat.QCOW2)
        self.assertIs(image_type(qcow(3)), ImageFormat.QCOW3)
        self.assertIs(image_type(qcow(4)), ImageFormat.UNKNOWN)

    def test_cow(self):
        self.assertIs(image_type(cow()), ImageFormat.COW)
        self.assertIs(image_type(cow(version=1)), ImageFormat.UNKNOWN)

    def test_qed(self):
        header = b"QED\x00" + struct.pack("<II", 65536, 16)
        self.assertIs(image_type(header), ImageFormat.QED)

    def test_vmdk(self):
        vmdk3 = b"COWD" + struct.pack("<I", 1)
        self.assertIs(image_type(vmdk3), ImageFormat.VMDK)
        vmdk4 = b"KDMV" + struct.pack("<I", 3)
        self.assertIs(image_type(vmdk4), ImageFormat.VMDK)

    def test_vdi(self):
        self.assertIs(image_type(vdi()), ImageFormat.VDI)

    def test_vpc(self):
        header = b"conectix" + struct.pack(">II", 2, 0x10000)
        self.assertIs(image_type(header), ImageFormat.VPC)

    def test_cloop(self):
        self.assertIs(image_type(CLOOP + b"\x00" * 16), ImageFormat.CLOOP)

    def test_unknown(self):
        """A raw image has no header: its format is unknown."""

        self.assertIs(image_type(b"\x00" * 512), ImageFormat.UNKNOWN)
        self.assertIs(image_type(b"\xeb\x63\x90" * 30), ImageFormat.UNKNOWN)

    def test_short(self):
        self.assertIs(image_type(b""), ImageFormat.UNKNOWN)
        self.assertIs(image_type(b"QFI"), ImageFormat.UNKNOWN)
        self.assertIs(image_type(b"QFI\xfb"), ImageFormat.UNKNOWN)
        self.assertIs(image_type(vdi()[:66]), ImageFormat.UNKNOWN)

    def test_enough_bytes(self):
        """The file gives the bytes of the longest header."""

        self.assertGreaterEqual(MAX_HEADER_LENGTH, 68)
        self.assertGreaterEqual(MAX_HEADER_LENGTH, len(CLOOP))


class TestFromFile(unittest.TestCase):
    def write(self, data):
        path = self.mktemp()
        with open(path, "wb") as fp:
            fp.write(data)
        return path

    def test_image_type_from_file(self):
        self.assertIs(
            image_type_from_file(self.write(qcow(3) + b"\x00" * 4096)),
            ImageFormat.QCOW3,
        )
        self.assertIs(
            image_type_from_file(self.write(CLOOP + b"\x00" * 4096)),
            ImageFormat.CLOOP,
        )
        self.assertIs(
            image_type_from_file(self.write(b"")), ImageFormat.UNKNOWN
        )

    def test_image_type_no_file(self):
        self.assertRaises(FileNotFoundError, image_type_from_file, "/nope")

    def test_backing_file_qcow(self):
        for version in (1, 2, 3):
            path = self.write(qcow(version, b"/lab/deb.qcow2"))
            self.assertEqual(get_backing_file(path), "/lab/deb.qcow2")

    def test_no_backing_file(self):
        self.assertIsNone(get_backing_file(self.write(qcow(2))))

    def test_backing_file_cow(self):
        path = self.write(cow(b"/lab/deb.img"))
        self.assertEqual(get_backing_file(path), "/lab/deb.img")

    def test_backing_file_undecodable(self):
        """A name the file system encoding can't decode keeps its bytes."""

        path = self.write(qcow(2, b"/lab/d\xe9b.qcow2"))
        self.assertEqual(get_backing_file(path), "/lab/d\udce9b.qcow2")

    def test_not_cow(self):
        for data in (
            b"",
            b"QFI\xfb",
            qcow(2)[:12],
            qcow(4, b"/lab/deb.qcow2"),
            cow(version=1),
            vdi(),
            b"\x00" * 512,
        ):
            with self.subTest(data=data[:16]):
                self.assertRaises(
                    NotCowFileError, get_backing_file, self.write(data)
                )

    def test_backing_no_file(self):
        self.assertRaises(FileNotFoundError, get_backing_file, "/nope")
