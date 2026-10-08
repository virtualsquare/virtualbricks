# -*- test-case-name: virtualbricks.tests.bricks.test_command -*-
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
The command line of a brick.

Each brick builds its command line in its ``command()`` method, in the order
of the line, with a :class:`Command`. What the installed program lacks is left
out, and the Command keeps a warning that says what and why; the brick starts
all the same. ``command()`` reads the configuration, the brick's own paths and
what ``prepare()`` gathered, a :class:`Prepared`: it reads no file and starts
nothing.
"""

from __future__ import annotations

import attr

from virtualbricks.bricks.plug import Plug
from virtualbricks.programs import (
    PACKAGES,
    Missing,
    ProgramError,
    QemuInfo,
    VdeInfo,
)

__all__ = ["Command", "Prepared", "joined", "socket_path", "vde_program"]


class Command:
    """
    A program and its arguments, in the order of the command line, and the
    variables of the environment that it gets besides those of Virtualbricks.
    """

    def __init__(self, program: str) -> None:
        self.argv: list[str] = [program]
        self.env: dict[str, str] = {}
        self.warnings: list[str] = []

    def arg(self, *values: object) -> None:
        """Arguments as they are."""

        self.argv.extend(str(value) for value in values)

    def flag(self, option: str, on: object) -> None:
        """The option alone, when on is true."""

        if on:
            self.argv.append(option)

    def option(self, option: str, value: object) -> None:
        """The option and its value, unless the value is empty or None."""

        if value is not None and value != "":
            self.argv += [option, str(value)]

    def warn(self, text: str) -> None:
        """Say what was left out of the line, and why."""

        self.warnings.append(text)


def joined(*parts: str) -> str:
    """The parts that aren't empty, joined by commas, as QEMU wants them."""

    return ",".join(part for part in parts if part)


def vde_socket(path: str) -> str:
    """
    A socket as the VDE programs and QEMU take it. The socket card of a
    virtual machine, whose path ends with "[]", joins one plug with no switch
    between: vdeplug4 names that ptp://.
    """

    if path.endswith("[]"):
        return f"ptp://{path[:-2]}"
    return path


def socket_path(plug: Plug) -> str:
    """The socket a plug is in, as the VDE programs take it."""

    assert plug.sock is not None, "a brick starts with its plugs in sockets"
    return vde_socket(plug.sock.path)


def vde_program(vde: VdeInfo | None, name: str) -> str:
    """The path of a VDE program; ProgramError if it isn't installed."""

    assert vde is not None, "prepare() gathers the VDE programs"
    path = vde.programs.get(name)
    if path is None:
        raise ProgramError(
            f"{Missing(name, PACKAGES.get(name))} isn't installed"
        )
    return path


@attr.define(frozen=True)
class Prepared:
    """What a command line needs that takes asking or work."""

    # the VDE programs, for the bricks that run one
    vde: VdeInfo | None = None
    # the QEMU program of a virtual machine, and the properties of its machine
    qemu: QemuInfo | None = None
    machine_properties: frozenset[str] = frozenset()
    # the disks of a virtual machine, (device, path), in the order of devices
    disks: tuple[tuple[str, str], ...] = ()
    audio_driver: str = ""
    # the saved state that a virtual machine starts from, if any
    resume: str = ""
