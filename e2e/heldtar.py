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
tar or bsdtar, held: a program of the tests in their place, on the PATH of
Virtualbricks.

    python heldtar.py REAL GATE SIZE ARGS...

When it extracts an archive from its input (``-x`` and ``-f -``), it reads
SIZE bytes of it, then waits until the file GATE is there, at most a
minute, and runs REAL with the whole input. The archive process of
Virtualbricks writes the archive into it by chunks, and sends the progress
after each: it sends the first, then waits on the second, and the Import
window shows the same progress each time. Otherwise it is REAL.
"""

import os
import subprocess
import sys
import time

# The longest it waits for GATE: then it goes on, if a scenario failed.
WAIT = 60


def from_input(args):
    """Whether the archive of the arguments is the input: -f -."""

    return any(a == "-f" and b == "-" for a, b in zip(args, args[1:]))


def read(size):
    """size bytes of the input, fewer at its end."""

    data = b""
    while len(data) < size:
        chunk = os.read(0, size - len(data))
        if not chunk:
            break
        data += chunk
    return data


def main(real, gate, size, *args):
    if "-x" not in args or not from_input(args):
        os.execv(real, [real, *args])
    head = read(int(size))
    deadline = time.monotonic() + WAIT
    while not os.path.exists(gate) and time.monotonic() < deadline:
        time.sleep(0.05)
    process = subprocess.Popen([real, *args], stdin=subprocess.PIPE)
    try:
        process.stdin.write(head)
        while chunk := os.read(0, 1 << 16):
            process.stdin.write(chunk)
        process.stdin.close()
    except BrokenPipeError:
        pass
    return process.wait()


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
