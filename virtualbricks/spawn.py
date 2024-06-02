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

import json
import locale
import os
from pathlib import Path

from twisted.internet import defer
from twisted.internet.utils import getProcessOutputAndValue

from virtualbricks import log
from virtualbricks.errors import BadConfigError, CommandError


if False:  # pyflakes
    _ = str


logger = log.Logger()
# qemu_img_failed = log.Event('qemu-image failed\n{stderr}')
qemu_commit_failed = log.Event('Failed to commit image.')
qemu_info_failed = log.Event(
    'Error while getting information about image file.'
)


def _abspath_exe(executable, path):
    """
    :type executable: pathlib.Path
    :type path: Optional[pathlib.Path]
    """

    if os.access(executable, os.X_OK):
        return executable
    if path is not None:
        abspath = path.joinpath(executable)
        if os.access(abspath, os.X_OK):
            return abspath
    for path in map(Path, os.environ.get('PATH', '.').split(':')):
        exe = path.joinpath(executable)
        if os.access(exe, os.X_OK):
            return exe
    raise FileNotFoundError(str(executable))


def encode_proc_output(output):
    """
    Encode process output. Virtualbricks works on Linux systems only so we
    don't care for other platforms.

    :type output: bytes
    :rtype: str
    """

    assert isinstance(output, bytes)
    encoding = locale.getpreferredencoding()
    return str(output, encoding, 'strict')


def _encode_or_complain(codes):
    """
    :type codes: Tuple[bytes, bytes, int]
    :rtype: str
    """

    stdout, stderr, exit_status = codes
    if exit_status != 0:
        raise CommandError(exit_status, encode_proc_output(stderr))
    return encode_proc_output(stdout)


def getQemuOutput(executable, args=()):
    """
    Run qemu executable and return the stdout.

    :type args: List[str]
    :rtype: twisted.internet.defer.Deferred[str]
    """

    exe = abspath_qemu(executable)
    if exe is None:
        return defer.fail(BadConfigError(_('{exe} not found').format(exe=exe)))
    deferred = getProcessOutputAndValue(exe, args, env=os.environ)
    return deferred.addCallback(_encode_or_complain)


def abspath_vde(executable):
    from virtualbricks import settings

    return str(_abspath_exe(Path(executable), Path(settings.get('vdepath'))))


def abspath_qemu(executable):
    from virtualbricks import settings

    return str(_abspath_exe(Path(executable), Path(settings.get('qemupath'))))


def qemu_commit_image(path):
    """
    :type path: Union[str, pathlib.Path]
    :rtype: twisted.internet.defer.Deferred[None]
    """

    deferred = qemu_img(['commit', str(path)])
    deferred.addErrback(logger.failure_eb, qemu_commit_failed, reraise=True)
    return deferred


def qemu_img_info(path):
    """
    Run `qemu-img info` on the given file.

    :type path: Union[str, pathlib.Path]
    :rtype: twisted.internet.defer.Deferred[List[Dict[str, Any]]]
    """

    args = ['info', '--format=json', '--backing-chain', str(path)]
    deferred = qemu_img(args)
    deferred.addCallback(json.loads)
    deferred.addErrback(logger.failure_eb, qemu_info_failed, reraise=True)
    return deferred


def qemu_img(args):
    """
    Run qemu-img and return the stdout.

    :type args: List[str]
    :rtype: twisted.internet.defer.Deferred[str]
    """

    return getQemuOutput('qemu-img', args)
