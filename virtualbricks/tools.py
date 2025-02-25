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
import errno
from pathlib import Path
import random
import re
from functools import update_wrapper, wraps
import tempfile
import struct

from twisted.internet import defer
from twisted.internet import utils
import constantly as constants

from virtualbricks import log
from virtualbricks import settings
from virtualbricks.errors import NoOptionError

logger = log.Logger()
ksm_error = log.Event("Can not change ksm state. (failed command: {cmd})")


def random_mac():
    random.seed()
    return "00:aa:{0:02x}:{1:02x}:{2:02x}:{3:02x}".format(
        random.getrandbits(8), random.getrandbits(8), random.getrandbits(8),
        random.getrandbits(8))


MAC_RE = re.compile(r"^([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}$")


def mac_is_valid(mac):
    return bool(MAC_RE.match(mac))


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
        default_paths = os.environ.get('PATH', '.').split(':')
    elif isinstance(default_paths, str):
        default_paths = [default_paths]
    for filename in files:
        for directory in default_paths:
            if os.access(Path(directory, filename), os.X_OK):
                break
        else:
            yield filename


vde_bins = ["vde_switch", "vde_plug", "vde_cryptcab", "dpipe", "vdeterm",
    "vde_plug2tap", "wirefilter", "vde_router"]

qemu_bins = ["qemu", "qemu-system-arm", "qemu-system-cris",
    "qemu-system-i386", "qemu-system-m68k", "qemu-system-microblaze",
    "qemu-system-mips", "qemu-system-mips64", "qemu-system-mips64el",
    "qemu-system-mipsel", "qemu-system-ppc", "qemu-system-ppc64",
    "qemu-system-ppcemb", "qemu-system-sh4", "qemu-system-sh4eb",
    "qemu-system-sparc", "qemu-system-sparc64", "qemu-system-x86_64",
    "qemu-img"]


def check_missing_vde(path=None):
    if path is None:
        from virtualbricks import settings
        path = settings.get('vdepath')
    return list(_check_missing(path, vde_bins))


def check_missing_qemu(path=None):
    if path is None:
        from virtualbricks import settings
        path = settings.get('qemupath')
    missing = list(_check_missing(path, qemu_bins))
    return missing, sorted(set(qemu_bins) - set(missing))


def check_kvm(path=None):
    return os.access("/dev/kvm", os.R_OK & os.W_OK)


KSM_PATH = '/sys/kernel/mm/ksm/run'


def check_ksm():
    """
    Check if KSM is enabled in the machine.

    :rtype: bool
    """

    try:
        with open(KSM_PATH) as fp:
            return bool(int(fp.readline()))
    except IOError:
        return False


def _check_set_ksm_cb(exit_code, cmd):
    """
    :type exit_code: bool
    :type cmd: str
    :rtype: bool
    """

    if exit_code:  # exit state != 0
        logger.error(ksm_error, cmd=cmd)
    return check_ksm()


def set_ksm(enable):
    """
    Enable or disable KSM support in the machine.

    :type enable: bool
    :rtype: twisted.internet.defer.Deferred[bool]
    """

    ksm_enabled = check_ksm()
    if enable ^ ksm_enabled:
        enable = 1 if enable else 0
        cmd = f'echo {enable} > {KSM_PATH}'
        try:
            sudo = settings.get('sudo')
            args = ['--', 'su', '-c', cmd]
            d = utils.getProcessValue(sudo, args, env=os.environ)
        except NoOptionError:
            shell_exe = os.environ.get('SHELL', '/bin/sh')
            d = utils.getProcessValue(shell_exe, ['-c', cmd], env=os.environ)
        return d.addCallback(_check_set_ksm_cb, cmd)
    else:
        return defer.succeed(ksm_enabled)


class Tempfile:

    def __enter__(self):
        self.fd, self.filename = tempfile.mkstemp()
        return self.fd, self.filename

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            os.remove(self.filename)
        except OSError as e:
            if e.errno != errno.ENOENT:
                raise


GENERIC_HEADER = '>II'
GENERIC_HEADER_LEN = struct.calcsize(GENERIC_HEADER)
COW_MAGIC = 0x4f4f4f4d  # OOOM
COW_BACKING_FILENAME_SIZE = 1024
QCOW_MAGIC = 0x514649fb  # \xfbIFQ, QFI\xfb
QCOW_HEADER = '>QI'
COWD_MAGIC = 0x44574f43  # COWD
VMDK_MAGIC = 0x564d444b  # KDMV
QED_MAGIC = 0x00444551  # \0DEQ
VDI_HEADER = '<64sI'
VDI_HEADER_LEN = struct.calcsize(VDI_HEADER)
VDI_SIGNATURE = 0xbeda107f
VPC_HEADER = '<8c'
VPC_CREATOR = 'conectix'
VPC_HEADER_LEN = struct.calcsize(VPC_HEADER)
CLOOP_MAGIC = '''#!/bin/sh
#V2.0 Format
modprobe cloop file=$0 && mount -r -t iso9660 /dev/cloop $1
'''
CLOOP_HEADER = '{0}c'.format(len(CLOOP_MAGIC))
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

    with open(imagefile, 'rb') as fp:
        header = fp.read(8)
        magic, version = struct.unpack(GENERIC_HEADER, header)
        if magic == COW_MAGIC:
            backing_b = fp.read(COW_BACKING_FILENAME_SIZE).rstrip(b'\x00')
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


def fmtsize(size):
    if size < 10240:
        return "{0} B".format(size)
    size /= 1024.0
    for unit in "KB", "MB", "GB":
        if size < 1024:
            return "{0:.1f} {1}".format(size, unit)
        size /= 1024.0
    return "{0:.1f} TB".format(size)


def copyTo(self, destination, followLinks=True):
    """
    Copies self to destination.

    If self doesn't exist, an OSError is raised.

    If self is a directory, this method copies its children (but not
    itself) recursively to destination - if destination does not exist as a
    directory, this method creates it.  If destination is a file, an
    IOError will be raised.

    If self is a file, this method copies it to destination.  If
    destination is a file, this method overwrites it.  If destination is a
    directory, an IOError will be raised.

    If self is a link (and followLinks is False), self will be copied
    over as a new symlink with the same target as returned by os.readlink.
    That means that if it is absolute, both the old and new symlink will
    link to the same thing.  If it's relative, then perhaps not (and
    it's also possible that this relative link will be broken).

    File/directory permissions and ownership will NOT be copied over.

    If followLinks is True, symlinks are followed so that they're treated
    as their targets.  In other words, if self is a link, the link's target
    will be copied.  If destination is a link, self will be copied to the
    destination's target (the actual destination will be destination's
    target).  Symlinks under self (if self is a directory) will be
    followed and its target's children be copied recursively.

    If followLinks is False, symlinks will be copied over as symlinks.

    @param destination: the destination (a FilePath) to which self
        should be copied
    @param followLinks: whether symlinks in self should be treated as links
        or as their targets
    """
    if self.islink() and not followLinks:
        os.symlink(os.readlink(self.path), destination.path)
        return
    # XXX TODO: *thorough* audit and documentation of the exact desired
    # semantics of this code.  Right now the behavior of existent
    # destination symlinks is convenient, and quite possibly correct, but
    # its security properties need to be explained.
    if self.isdir():
        if not destination.exists():
            destination.createDirectory()
        for child in self.children():
            destChild = destination.child(child.basename())
            copyTo(child, destChild, followLinks)
    elif self.isfile():
        writefile = destination.open('w')
        try:
            readfile = self.open()
            try:
                while 1:
                    # XXX TODO: optionally use os.open, os.read and O_DIRECT
                    # and use os.fstatvfs to determine chunk sizes and make
                    # *****sure**** copy is page-atomic; the following is
                    # good enough for 99.9% of everybody and won't take a
                    # week to audit though.
                    chunk = readfile.read(self._chunkSize)
                    writefile.write(chunk)
                    if len(chunk) < self._chunkSize:
                        break
            finally:
                readfile.close()
        finally:
            writefile.close()
    elif not self.exists():
        raise OSError(errno.ENOENT, "No such file or directory")


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
        3: ImageFormat.QCOW3
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
    with open(filename, 'rb') as fp:
        return image_type(fp.read(MAX_HEADER_LENGTH))


def dispose(obj):
    obj.__dispose__()


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
            raise RuntimeError(f'sync failed\n{stderr}')

    deferred = utils.getProcessOutputAndValue('sync', env=os.environ)
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
