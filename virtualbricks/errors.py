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


from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from virtualbricks.i18n import _

if TYPE_CHECKING:  # pragma: no cover
    from virtualbricks.bricks.virtualmachine import Disk, Image


class Error(Exception):
    pass


class InvalidNameError(Error):
    pass


class NameAlreadyInUseError(InvalidNameError):

    def __init__(self, name: str, kind: str | None = None) -> None:
        InvalidNameError.__init__(self, name)
        self.name = name
        # what has the name: "brick", "event" or "image", if known
        self.kind = kind

    def __str__(self) -> str:
        words = {
            "brick": _("{name} is the name of a brick"),
            "event": _("{name} is the name of an event"),
            "image": _("{name} is the name of an image"),
        }
        in_use = _("{name} is in use")
        if self.kind is not None:
            in_use = words.get(self.kind, in_use)
        return in_use.format(name=self.name)


class InvalidTypeError(Error, ValueError):
    pass


class BadConfigError(Error):
    pass


class NotConnectedError(Error):
    pass


class LinkLoopError(Error):
    """The links of a brick lead back to it: the bricks on a loop don't start."""

    def __init__(self, loop: Sequence[str]) -> None:
        Error.__init__(self, tuple(loop))
        # the names of the bricks on the loop, the first again at the end
        self.loop = tuple(loop)

    def __str__(self) -> str:
        return _(
            "Cannot start '{name}': its links make a loop, {loop}"
        ).format(name=self.loop[0], loop=" → ".join(self.loop))


class LockedImageError(Error):

    def __init__(self, image: Image, master: Disk | None) -> None:
        Exception.__init__(self, image, master)
        self.image = image
        self.master = master

    def __repr__(self) -> str:
        return "Image {0} already locked by {1}".format(
            self.image, self.master
        )


class ImageAlreadyInUseError(Error):
    pass


class PrivateCopyInTheWayError(Error):
    """A private copy named after a machine's new name is in its folder."""

    def __init__(self, filename: str, name: str) -> None:
        Error.__init__(self, filename, name)
        self.filename = filename
        self.name = name

    def __str__(self) -> str:
        return _(
            "The project folder has {file} already, a private copy named"
            " after {name}: move it away first"
        ).format(file=self.filename, name=self.name)


# Project specific errors


class ProjectOpenError(Error):
    """The project is open, and the action needs it closed."""


class TrashNotSupportedError(Error):
    """The file system of the path has no trash."""


class BrickRunningError(Error):
    """There is one or more brick that is running."""


class OtherProgramError(Error):
    """The program of a brick is another's: Virtualbricks can't stop it."""


class CommandError(Exception):
    """
    One utility command failed. Ex. qemu-img.
    """

    def __init__(self, exit_code: int, stderr: str) -> None:
        super().__init__(stderr)
        self.exit_code = exit_code
        self.stderr = stderr
