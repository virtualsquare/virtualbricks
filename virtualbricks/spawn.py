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
from pathlib import Path


def find_executable(executable, folder):
    """
    The executable itself, if it is one, else the one in folder, else the one
    on PATH; FileNotFoundError if there's none.

    :type executable: pathlib.Path
    :type folder: Optional[pathlib.Path]
    :rtype: pathlib.Path
    """

    if os.access(executable, os.X_OK):
        return executable
    if folder is not None:
        abspath = folder.joinpath(executable)
        if os.access(abspath, os.X_OK):
            return abspath
    for path in map(Path, os.environ.get("PATH", ".").split(":")):
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
    return str(output, encoding, "strict")


def abspath_vde(executable):
    from virtualbricks.config.settings import get_setting

    return str(
        find_executable(Path(executable), Path(get_setting("vde_path")))
    )
