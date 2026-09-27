# -*- test-case-name: virtualbricks.tests.test_tools -*-
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
import sys
from pathlib import Path
from functools import update_wrapper, wraps
import struct

from twisted.internet import utils
from twisted.logger import Logger
import constantly as constants

from virtualbricks.config.settings import get_setting

logger = Logger()


def synchronize(func, lock):
    @wraps(func)
    def wrapper(*args, **kwds):
        with lock:
            return func(*args, **kwds)

    return wrapper


def synchronize_with(lock):
    def wrap(func):
        return synchronize(func, lock)

    return wrap


def stack_trace():
    out = []
    f = sys._getframe(1)
    while f:
        out.append("{0.f_code.co_filename}:{0.f_lineno}".format(f))
        f = f.f_back
    return "\n".join(out)


def _check_missing(default_paths, files):
    if not default_paths:
        default_paths = os.environ.get("PATH", ".").split(":")
    elif isinstance(default_paths, str):
        default_paths = [default_paths]
    for filename in files:
        for directory in default_paths:
            if os.access(Path(directory, filename), os.X_OK):
                break
        else:
            yield filename


vde_bins = [
    "vde_switch",
    "vde_plug",
    "vde_cryptcab",
    "dpipe",
    "vdeterm",
    "vde_plug2tap",
    "wirefilter",
    "vde_router",
]

qemu_bins = [
    "qemu",
    "qemu-system-arm",
    "qemu-system-cris",
    "qemu-system-i386",
    "qemu-system-m68k",
    "qemu-system-microblaze",
    "qemu-system-mips",
    "qemu-system-mips64",
    "qemu-system-mips64el",
    "qemu-system-mipsel",
    "qemu-system-ppc",
    "qemu-system-ppc64",
    "qemu-system-ppcemb",
    "qemu-system-sh4",
    "qemu-system-sh4eb",
    "qemu-system-sparc",
    "qemu-system-sparc64",
    "qemu-system-x86_64",
    "qemu-img",
]


def check_missing_vde(path=None):
    if path is None:

        path = get_setting("vdepath")
    return list(_check_missing(path, vde_bins))


def check_missing_qemu(path=None):
    if path is None:

        path = get_setting("qemupath")
    missing = list(_check_missing(path, qemu_bins))
    return missing, sorted(set(qemu_bins) - set(missing))


def check_kvm(path=None):
    return os.access("/dev/kvm", os.R_OK & os.W_OK)


GENERIC_HEADER = ">II"
GENERIC_HEADER_LEN = struct.calcsize(GENERIC_HEADER)
COW_MAGIC = 0x4F4F4F4D  # OOOM
COW_BACKING_FILENAME_SIZE = 1024
QCOW_MAGIC = 0x514649FB  # \xfbIFQ, QFI\xfb
QCOW_HEADER = ">QI"
COWD_MAGIC = 0x44574F43  # COWD
VMDK_MAGIC = 0x564D444B  # KDMV
QED_MAGIC = 0x00444551  # \0DEQ
VDI_HEADER = "<64sI"
VDI_HEADER_LEN = struct.calcsize(VDI_HEADER)
VDI_SIGNATURE = 0xBEDA107F
VPC_HEADER = "<8c"
VPC_CREATOR = "conectix"
VPC_HEADER_LEN = struct.calcsize(VPC_HEADER)
CLOOP_MAGIC = """#!/bin/sh
#V2.0 Format
modprobe cloop file=$0 && mount -r -t iso9660 /dev/cloop $1
"""
CLOOP_HEADER = "{0}c".format(len(CLOOP_MAGIC))
CLOOP_HEADER_LEN = struct.calcsize(CLOOP_HEADER)
MAX_HEADER_LENGTH = max(
    GENERIC_HEADER_LEN, VDI_HEADER_LEN, VPC_HEADER_LEN, CLOOP_HEADER_LEN
)


class NotCowFileError(ValueError):
    pass


def get_backing_file(imagefile):
    """
    Extract the backing file from a image file. Return the imagefile as str,
    None if there is not backing file or raise NotCowFileError if the format is
    unknown.

    :type imagefile: str
    :rtype: str
    :raises NotCowFileError: if the file is not recognized.
    :raises FileNotFound: it the file does not exists.
    """

    with open(imagefile, "rb") as fp:
        header = fp.read(8)
        magic, version = struct.unpack(GENERIC_HEADER, header)
        if magic == COW_MAGIC:
            backing_b = fp.read(COW_BACKING_FILENAME_SIZE).rstrip(b"\x00")
        elif magic == QCOW_MAGIC and version in (1, 2, 3):
            offset, size = struct.unpack(QCOW_HEADER, fp.read(12))
            if size == 0:
                return None
            else:
                fp.seek(offset)
                backing_b = fp.read(size)
        else:
            raise NotCowFileError()
    return os.fsdecode(backing_b)


class ImageFormat(constants.Names):

    RAW = constants.NamedConstant()
    QCOW2 = constants.NamedConstant()
    QCOW3 = constants.NamedConstant()
    QED = constants.NamedConstant()
    QCOW = constants.NamedConstant()
    COW = constants.NamedConstant()
    VDI = constants.NamedConstant()
    VMDK = constants.NamedConstant()
    VPC = constants.NamedConstant()
    CLOOP = constants.NamedConstant()
    UNKNOWN = constants.NamedConstant()


_type_map = {
    COW_MAGIC: {1: ImageFormat.COW},
    QCOW_MAGIC: {
        1: ImageFormat.QCOW,
        2: ImageFormat.QCOW2,
        3: ImageFormat.QCOW3,
    },
    COWD_MAGIC: {1: ImageFormat.VMDK},
    VMDK_MAGIC: {1: ImageFormat.VMDK},
}


def image_type(data):
    """
    Guess the image type inspecting the first bytes of the file.
    Return ImageFormat.UNKNOWN if the image type is... unknown.

    :type data: bytes
    :rtype: ImageFormat
    """

    magic, version = struct.unpack(GENERIC_HEADER, data[:GENERIC_HEADER_LEN])
    if magic == QED_MAGIC:
        return ImageFormat.QED
    try:
        return _type_map[magic][version]
    except KeyError:
        pass
    if struct.unpack(VDI_HEADER, data[:VDI_HEADER_LEN])[1] == VDI_SIGNATURE:
        return ImageFormat.VDI
    if struct.unpack(VPC_HEADER, data[:VPC_HEADER_LEN]) == VPC_CREATOR:
        return ImageFormat.VPC
    if struct.unpack(CLOOP_HEADER, data[:CLOOP_HEADER_LEN]) == CLOOP_MAGIC:
        return ImageFormat.CLOOP
    return ImageFormat.UNKNOWN


def image_type_from_file(filename):
    with open(filename, "rb") as fp:
        return image_type(fp.read(MAX_HEADER_LENGTH))


def is_running(brick):
    return brick.__isrunning__()


def sync():
    """
    Run the sync command wrapped in a deferred. Raise RuntimeError if the
    command fails.

    :rtype: twisted.internet.defer.Deferred[None]
    """

    def complain_on_error(command_info):
        stdout, stderr, exit_status = command_info
        if exit_status != 0:
            raise RuntimeError(f"sync failed\n{stderr}")

    deferred = utils.getProcessOutputAndValue("sync", env=os.environ)
    deferred.addCallback(complain_on_error)
    return deferred


def discard_first_arg(func, *args, **kwds):
    """
    Call func with the given parameters but discard the first one. Useful used
    together with Deferred `addCallback()`. Ex.

        deferred = getProcessValue(['echo', 'hello world'])
        deferred.addCallback(discard_first_arg(print 'hello world2'))

    :param Callable func: the function to wrap.
    :param Tuple args: optional parameters to pass to func.
    :param Dict[str, Any] kwds: optional keyword parameters to pass to func.
    :rtype: Callable
    """

    def wrapper(first_arg, *fargs, **fkwds):
        newkwds = {**kwds, **fkwds}
        return func(*args, *fargs, **newkwds)

    update_wrapper(wrapper, func)
    return wrapper
