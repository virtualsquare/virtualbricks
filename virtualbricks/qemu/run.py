# -*- test-case-name: virtualbricks.tests.qemu.test_run -*-
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
Finding the QEMU programs, in the folder of the ``qemu_path`` setting or on
PATH, and running ``qemu-img``.
"""

import os
from pathlib import Path

from twisted.internet.utils import getProcessOutputAndValue

from virtualbricks.config.settings import get_setting
from virtualbricks.errors import CommandError
from virtualbricks.spawn import encode_proc_output, find_executable


def which(program: str) -> str:
    """
    The path of a QEMU program: program itself if it is one, else the one in
    the folder of the ``qemu_path`` setting, else the one on PATH.

    :raises FileNotFoundError: if there's none, where ``shutil.which()``
        returns None.
    """

    folder = Path(get_setting("qemu_path"))
    return str(find_executable(Path(program), folder))


def _encode_or_complain(codes):
    stdout, stderr, exit_status = codes
    if exit_status != 0:
        raise CommandError(exit_status, encode_proc_output(stderr))
    return encode_proc_output(stdout)


def _output(program, args):
    """
    Run a QEMU program: its standard output, when it ends; CommandError if it
    fails, FileNotFoundError if there's none.

    :type args: List[str]
    :rtype: twisted.internet.defer.Deferred[str]
    """

    deferred = getProcessOutputAndValue(which(program), args, env=os.environ)
    return deferred.addCallback(_encode_or_complain)


def qemu_img(args):
    """
    Run qemu-img: its standard output, when it ends.

    :type args: List[str]
    :rtype: twisted.internet.defer.Deferred[str]
    """

    return _output("qemu-img", args)
