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

import locale
import os
from twisted.internet.utils import getProcessOutput, getProcessOutputAndValue


def _abspath_exe(path, executable, return_relative=True):
    if '/' in executable:
        if os.access(executable, os.X_OK) or return_relative:
            return executable
        else:
            return None
    if isinstance(path, str) and path != '':
        abspath = os.path.join(path, executable)
        if os.access(abspath, os.X_OK):
            return abspath
        elif return_relative:
            return executable
        else:
            return None
    paths = os.environ.get('PATH', '.').split(':')
    for path in paths:
        if os.access(os.path.join(path, executable), os.X_OK):
            return os.path.join(path, executable)
    if return_relative:
        # cannot find executable, return the relative filename
        return executable


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


def getQemuOutput(executable, args=(), env={}, path=None, reactor=None,
                  errortoo=0):
    exe = abspath_qemu(executable)
    d = getProcessOutput(exe, args, env, path, reactor, errortoo)
    return d.addCallback(encode_proc_output)


def getQemuOutputAndValue(executable, args=(), env={}, path=None, reactor=None):
    exe = abspath_qemu(executable)
    return getProcessOutputAndValue(exe, args, env, path, reactor)


def getVdeOutput(executable, args=(), env={}, path=None, reactor=None,
                 errortoo=0):
    exe = abspath_vde(executable)
    return getProcessOutput(exe, args, env, path, reactor, errortoo)


def abspath_vde(executable, return_relative=True):
    from virtualbricks import settings

    return _abspath_exe(settings.get('vdepath'), executable, return_relative)


def abspath_qemu(executable, return_relative=True):
    from virtualbricks import settings

    return _abspath_exe(settings.get('qemupath'), executable, return_relative)
