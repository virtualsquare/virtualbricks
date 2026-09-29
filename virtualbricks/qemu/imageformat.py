# -*- test-case-name: virtualbricks.tests.qemu.test_imageformat -*-
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
The format of a disk image and its backing file, from the first bytes of the
file, as QEMU's block drivers probe them.

A raw image has no header: ``image_type()`` tells it from no other file, and
says ``ImageFormat.UNKNOWN``.
"""

import enum
import os
import struct

QCOW_MAGIC = b"QFI\xfb"
COW_MAGIC = b"OOOM"
# QEMU's cow driver: the magic, the version, then the backing file
COW_VERSION = 2
COW_BACKING_FILENAME_SIZE = 1024
QED_MAGIC = b"QED\x00"
VMDK3_MAGIC = b"COWD"
VMDK4_MAGIC = b"KDMV"
VDI_SIGNATURE = struct.pack("<I", 0xBEDA107F)
VDI_SIGNATURE_OFFSET = 64
VPC_CREATOR = b"conectix"
CLOOP_MAGIC = (
    b"#!/bin/sh\n"
    b"#V2.0 Format\n"
    b"modprobe cloop file=$0 && mount -r -t iso9660 /dev/cloop $1\n"
)
MAX_HEADER_LENGTH = max(
    VDI_SIGNATURE_OFFSET + len(VDI_SIGNATURE), len(CLOOP_MAGIC)
)


class ImageFormat(enum.Enum):
    RAW = enum.auto()
    QCOW = enum.auto()
    QCOW2 = enum.auto()
    # qcow2 with the version 3 header, which qemu-img calls qcow2 too
    QCOW3 = enum.auto()
    QED = enum.auto()
    COW = enum.auto()
    VDI = enum.auto()
    VMDK = enum.auto()
    VPC = enum.auto()
    CLOOP = enum.auto()
    UNKNOWN = enum.auto()


QCOW_VERSIONS = {
    1: ImageFormat.QCOW,
    2: ImageFormat.QCOW2,
    3: ImageFormat.QCOW3,
}


class NotCowFileError(ValueError):
    pass


def image_type(data: bytes) -> ImageFormat:
    """The format of an image whose file starts with these bytes."""

    magic = data[:4]
    if magic == QCOW_MAGIC:
        version = int.from_bytes(data[4:8], "big")
        return QCOW_VERSIONS.get(version, ImageFormat.UNKNOWN)
    if magic == COW_MAGIC and int.from_bytes(data[4:8], "big") == COW_VERSION:
        return ImageFormat.COW
    if magic == QED_MAGIC:
        return ImageFormat.QED
    if magic in (VMDK3_MAGIC, VMDK4_MAGIC):
        return ImageFormat.VMDK
    offset = VDI_SIGNATURE_OFFSET
    if data[offset : offset + len(VDI_SIGNATURE)] == VDI_SIGNATURE:
        return ImageFormat.VDI
    if data.startswith(VPC_CREATOR):
        return ImageFormat.VPC
    if data.startswith(CLOOP_MAGIC):
        return ImageFormat.CLOOP
    return ImageFormat.UNKNOWN


def image_type_from_file(filename: str) -> ImageFormat:
    with open(filename, "rb") as fp:
        return image_type(fp.read(MAX_HEADER_LENGTH))


def get_backing_file(imagefile: str) -> str | None:
    """
    The backing file of a cow or qcow image, None if it has none.

    :raises NotCowFileError: if the image is neither cow nor qcow.
    :raises FileNotFoundError: if the file does not exist.
    """

    with open(imagefile, "rb") as fp:
        header = fp.read(8)
        if len(header) < 8:
            raise NotCowFileError()
        magic, version = header[:4], int.from_bytes(header[4:], "big")
        if magic == COW_MAGIC and version == COW_VERSION:
            backing = fp.read(COW_BACKING_FILENAME_SIZE).split(b"\x00")[0]
        elif magic == QCOW_MAGIC and version in QCOW_VERSIONS:
            data = fp.read(12)
            if len(data) < 12:
                raise NotCowFileError()
            offset, size = struct.unpack(">QI", data)
            if size == 0:
                return None
            fp.seek(offset)
            backing = fp.read(size)
        else:
            raise NotCowFileError()
    return os.fsdecode(backing)
