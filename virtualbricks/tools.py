# -*- test-case-name: virtualbricks.tests.test_tools -*-
# Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
# Copyright (C) 2013 Virtualbricks team

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
import errno
import random
import re
import functools
import tempfile
import struct

from virtualbricks import _compat

log = _compat.getLogger(__name__)


def random_mac():
    random.seed()
    return "00:aa:{0:02x}:{1:02x}:{2:02x}:{3:02x}".format(
        random.getrandbits(8), random.getrandbits(8), random.getrandbits(8),
        random.getrandbits(8))

RandMac = random_mac
MAC_RE = re.compile(r"^([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}$")


def mac_is_valid(mac):
    return bool(MAC_RE.match(mac))


def synchronize(func, lock):
    @functools.wraps(func)
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


def check_missing(path, files):
    return [f for f in files if not os.access(os.path.join(path, f), os.X_OK)]


def check_missing_vde(path):
    bins = ["vde_switch", "vde_plug", "vde_cryptcab", "dpipe", "vdeterm",
            "vde_plug2tap", "wirefilter", "vde_router"]
    return check_missing(path, bins)


def check_missing_qemu(path):
    bins = ["qemu", "kvm", "qemu-system-arm", "qemu-system-cris",
            "qemu-system-i386", "qemu-system-m68k", "qemu-system-microblaze",
            "qemu-system-mips", "qemu-system-mips64", "qemu-system-mips64el",
            "qemu-system-mipsel", "qemu-system-ppc", "qemu-system-ppc64",
            "qemu-system-ppcemb", "qemu-system-sh4", "qemu-system-sh4eb",
            "qemu-system-sparc", "qemu-system-sparc64", "qemu-system-x86_64",
            "qemu-img"]
    missing = check_missing(path, bins)
    return missing, sorted(set(bins) - set(missing))


def check_kvm(path):
    if not os.access(os.path.join(path, "kvm"), os.X_OK):
        return False
    if not os.access("/sys/class/misc/kvm", os.X_OK):
        return False
    return True


def check_ksm():
    try:
        with open("/sys/kernel/mm/ksm/run") as fp:
            return int(fp.readline())
    except IOError:
        return False


def enable_ksm(enable, use_sudo):
    if enable ^ check_ksm():
        cmd = "echo %d > %s" % (enable, "/sys/kernel/mm/ksm/run")
        exit = os.system("sudo %s" % cmd) if use_sudo else os.system(cmd)
        if exit:  # exit state != 0
            log.error("Can not change ksm state. (failed command: %s)" % cmd)


class Tempfile:

    def __enter__(self):
        self.fd, self.filename = tempfile.mkstemp()
        return self.fd, self.filename

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            os.remove(self.filename)
        except OSError, e:
            if e.errno != errno.ENOENT:
                raise


HEADER_FMT = r">BBBBI"
COW_MAGIC = "MOOO"[::-1]
COW_SIZE = 1024
QCOW_MAGIC = "QFI\xfb"
QCOW_HEADER_FMT = r">QI"


def get_backing_file_from_cow(fp):
    data = fp.read(COW_SIZE)
    return data.rstrip("\x00")

def get_backing_file_from_qcow(fp):
    offset, size = struct.unpack(QCOW_HEADER_FMT, fp.read(12))
    if size == 0:
        return ""
    else:
        fp.seek(offset)
        return fp.read(size)


class UnknowTypeError(Exception):
    pass


def get_backing_file(fp):
    data = fp.read(8)
    m1, m2, m3, m4, version = struct.unpack(HEADER_FMT, data)
    magic = "".join(map(chr, (m1, m2, m3, m4)))
    if magic == COW_MAGIC:
        return get_backing_file_from_cow(fp)
    elif magic == QCOW_MAGIC and version in (1, 2):
        return get_backing_file_from_qcow(fp)
    raise UnknowTypeError()


def backing_files_for(files):
    for file in files:
        try:
            with open(file) as fp:
                yield get_backing_file(fp)
        except UnknowTypeError:
            pass
