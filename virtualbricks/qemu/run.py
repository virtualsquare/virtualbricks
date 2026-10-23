# -*- test-case-name: virtualbricks.tests.qemu.test_run -*-
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

"""
Finding the QEMU programs, in the folder of the ``qemu_path`` setting or on
PATH, and running ``qemu-img``.
"""

from __future__ import annotations

import os
from collections.abc import Sequence

from twisted.internet import defer
from twisted.internet.utils import getProcessOutputAndValue

from virtualbricks.config.settings import get_setting
from virtualbricks.errors import CommandError
from virtualbricks.programs import decode_output, find_program


def which(program: str) -> str:
    """
    The path of a QEMU program: the one in the folder of the ``qemu_path``
    setting, else the one on PATH; a path given in full is itself.

    :raises FileNotFoundError: if there's none, where ``shutil.which()``
        returns None.
    """

    path = find_program(program, str(get_setting("qemu_path")))
    if path is None:
        raise FileNotFoundError(program)
    return path


def _decode_or_complain(codes: tuple[bytes, bytes, int]) -> str:
    stdout, stderr, exit_status = codes
    if exit_status != 0:
        raise CommandError(exit_status, decode_output(stderr))
    return decode_output(stdout)


def _output(program: str, args: Sequence[str]) -> defer.Deferred[str]:
    """
    Run a QEMU program: its standard output, when it ends; CommandError if it
    fails, FileNotFoundError if there's none.
    """

    deferred = getProcessOutputAndValue(which(program), args, env=os.environ)
    return deferred.addCallback(_decode_or_complain)


def qemu_img(args: Sequence[str]) -> defer.Deferred[str]:
    """Run qemu-img: its standard output, when it ends."""

    return _output("qemu-img", args)
