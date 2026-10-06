# -*- test-case-name: virtualbricks.tests.test_vde -*-
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
Finding the VDE programs, in the folder of the ``vde_path`` setting or on
PATH.
"""

from virtualbricks.config.settings import get_setting
from virtualbricks.programs import find_program


def which(program: str) -> str:
    """
    The path of a VDE program: the one in the folder of the ``vde_path``
    setting, else the one on PATH; a path given in full is itself.

    :raises FileNotFoundError: if there's none, where ``shutil.which()``
        returns None.
    """

    path = find_program(program, str(get_setting("vde_path")))
    if path is None:
        raise FileNotFoundError(program)
    return path
