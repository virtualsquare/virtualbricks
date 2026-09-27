# -*- test-case-name: virtualbricks.tests.gui.test_imageinfo -*-
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
What the windows say about a disk image, without widgets: the Images tab,
the picker of a disk and the dialogs.

An image is in use while a running machine reads or writes it, not in use
when only stopped machines use it, used by no disk, or its file is missing.
Its facts come from ``qemu-img info``: "qcow2 · 4.0 GB disk · 1.9 GB on
disk". Its use says which machines use it and how: "r1, r2 and r3, private
copies · vm, the image itself". The sizes are in MB and GB, of 1000.

The picker of a disk says of an image its format, the size of its disk and
the other machines that use it; under a disk, a line says what its mode
does.
"""

from __future__ import annotations

import enum
import os

from virtualbricks.i18n import _, ngettext

# Between the parts of a line.
SEPARATOR = " · "


class State(enum.Enum):
    IN_USE = "in-use"
    NOT_IN_USE = "not-in-use"
    NO_DISK = "no-disk"
    MISSING = "missing"


LABELS = {
    State.IN_USE: _("In use"),
    State.NOT_IN_USE: _("Not in use"),
    State.NO_DISK: _("No disk"),
    State.MISSING: _("File missing"),
}


def human_size(size: float) -> str:
    """A size in bytes, in B, KB, MB or GB of 1000."""

    for unit in ("B", "KB", "MB", "GB"):
        if size < 1000 or unit == "GB":
            if unit == "B":
                return f"{size:.0f} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1000
    return f"{size:.1f} TB"  # pragma: no cover


def names(items: list[str]) -> str:
    """Names in a sentence: "r1", "r1 and r2", "r1, r2 and r3"."""

    if len(items) == 1:
        return items[0]
    return _("{first} and {last}").format(
        first=", ".join(items[:-1]), last=items[-1]
    )


def short_path(path: str) -> str:
    """A path, with ~ for the home folder."""

    home = os.path.expanduser("~")
    if path == home or path.startswith(home + os.sep):
        return "~" + path[len(home) :]
    return path


def state(image, uses) -> State:
    """The state of image, which the disks of uses use."""

    if not os.path.exists(image.get_path()):
        return State.MISSING
    if any(use.running for use in uses):
        return State.IN_USE
    if uses:
        return State.NOT_IN_USE
    return State.NO_DISK


def facts(info) -> str:
    """The format and the sizes of an image: "qcow2 · 4.0 GB disk · …"."""

    return SEPARATOR.join(
        (
            info.format,
            _("{size} disk").format(size=human_size(info.virtual_size)),
            _("{size} on disk").format(size=human_size(info.actual_size)),
        )
    )


def _machines(uses) -> list[str]:
    # each machine once, in its order
    found = []
    for use in uses:
        name = use.vm.get_name()
        if name not in found:
            found.append(name)
    return found


def use_words(uses) -> str:
    """Which machines use an image, and how: "r1 and r2, private copies"."""

    if not uses:
        return _("no disk uses it")
    parts = []
    private = _machines([use for use in uses if use.private])
    if private:
        parts.append(
            ngettext(
                "{names}, private copy",
                "{names}, private copies",
                len(private),
            ).format(names=names(private))
        )
    itself = _machines([use for use in uses if not use.private])
    if itself:
        parts.append(
            _("{names}, the image itself").format(names=names(itself))
        )
    return SEPARATOR.join(parts)


def summary(image, info, uses) -> str:
    """
    What the row of image says: its facts, once read, and who uses it; or
    that its file isn't there.
    """

    if not os.path.exists(image.get_path()):
        first = _("{path} isn't there").format(
            path=short_path(image.get_path())
        )
        return SEPARATOR.join((first, use_words(uses)))
    if info is None:
        return use_words(uses)
    return SEPARATOR.join((facts(info), use_words(uses)))


def tooltip(image, image_state: State, uses) -> str | None:
    """What the state of image says, when pointed at."""

    if image_state is State.MISSING:
        return _("Find the file of {name}").format(name=image.get_name())
    if image_state is State.IN_USE:
        running = _machines([use for use in uses if use.running])
        return ngettext("{names} runs", "{names} run", len(running)).format(
            names=names(running)
        )
    return None


# The picker and the disks of a machine


def short_facts(info) -> str:
    """The format and the size of the disk: "qcow2 · 4.0 GB"."""

    return SEPARATOR.join((info.format, human_size(info.virtual_size)))


def others_words(uses, vm) -> str:
    """
    Which machines other than vm use an image, and how: "r2 and r3 use it ·
    gw writes into it"; empty for none.
    """

    others = [use for use in uses if use.vm is not vm]
    parts = []
    private = _machines([use for use in others if use.private])
    if private:
        parts.append(
            ngettext("{names} uses it", "{names} use it", len(private)).format(
                names=names(private)
            )
        )
    itself = _machines([use for use in others if not use.private])
    if itself:
        parts.append(
            ngettext(
                "{names} writes into it", "{names} write into it", len(itself)
            ).format(names=names(itself))
        )
    return SEPARATOR.join(parts)


def option_words(image, info, uses, vm) -> str:
    """What the picker of a disk of vm says of image, under its name."""

    if not os.path.exists(image.get_path()):
        return _("The file isn't on this computer")
    parts = [short_facts(info)] if info is not None else []
    others = others_words(uses, vm)
    if others:
        parts.append(others)
    return SEPARATOR.join(parts)


def disk_line(vm, image, saved, private, copy, copy_size) -> str:
    """
    What a disk of the machine named vm does with image in its mode: its
    private copy, copy, which takes copy_size or isn't made yet (None), or
    the image itself. saved is the image that the disk has now.
    """

    if image is None:
        return _("No image: {vm} starts without this disk.").format(vm=vm)
    name = image.get_name()
    if not os.path.exists(image.get_path()):
        return _(
            "The file of {image} isn't there: find it in the Images tab, or"
            " choose another image."
        ).format(image=name)
    if not private:
        return _(
            "{vm} writes into {image}; while {vm} runs, no other machine can"
            " use it."
        ).format(vm=vm, image=name)
    copy = os.path.basename(copy)
    if copy_size is None:
        return _(
            "{vm}'s changes will be kept in"
            " {copy}, made at the next start; {image} stays as it is."
        ).format(vm=vm, copy=copy, image=name)
    if saved is not None and saved is not image:
        return _(
            "{copy} keeps {vm}'s changes to"
            " {saved}: the next start sets it aside and begins again from"
            " {image}."
        ).format(copy=copy, vm=vm, saved=saved.get_name(), image=name)
    return _(
        "{vm}'s changes are kept in {copy},"
        " {size}, in the project; {image} stays as it is."
    ).format(vm=vm, copy=copy, size=human_size(copy_size), image=name)
