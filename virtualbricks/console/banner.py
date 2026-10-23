# -*- test-case-name: virtualbricks.tests.console.test_banner -*-
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
What the console in the terminal shows as it starts: the icon of
Virtualbricks in characters and, beside it, the version, the open project,
the workspace, the QEMU emulators, the programs that are missing and the
control sockets listened on. A terminal too narrow for both has the text
alone.
"""

from __future__ import annotations

import textwrap
from collections.abc import Sequence

from virtualbricks import __version__, locations
from virtualbricks.brickfactory import BrickFactory
from virtualbricks.config.settings import get_setting
from virtualbricks.config.workspace import projects
from virtualbricks.console.output import width
from virtualbricks.i18n import _, ngettext
from virtualbricks.programs import (
    QEMU_OF_A_FOLDER,
    missing_programs,
    qemu_programs,
)
from virtualbricks.sockets import Socket

# The icon: a V of bricks, the last one coming down on its mortar.
LOGO = [
    "                [_____]",
    "[_____]          .--.",
    "[__|__]        [__|__]",
    "[_____]      [_____]",
    "[__|__]    [__|__]",
    "[_____]  [_____]",
    "[__|__][_____]",
    "   [_____]",
]
LOGO_WIDTH = max(map(len, LOGO))
# The spaces between the icon and the text.
GAP = 4
# The columns the text needs beside the icon; with fewer, it goes alone.
TEXT_WIDTH = 40
# The columns a value wraps at, however narrow the terminal.
VALUE_WIDTH = 20
# The emulators named; those after them are counted.
NAMED = 3
QEMU_PREFIX = "qemu-system-"


def emulators(folder: str) -> str:
    """
    The QEMU emulators in folder and in PATH, by what they emulate, that
    of QEMU_OF_A_FOLDER first; the first NAMED, then how many more. Empty
    if there are none.
    """

    names = [name[len(QEMU_PREFIX) :] for name in qemu_programs(folder)]
    first = QEMU_OF_A_FOLDER[len(QEMU_PREFIX) :]
    if first in names:
        names.remove(first)
        names.insert(0, first)
    # "and 1 more" is no shorter than its name
    if len(names) <= NAMED + 1:
        return ", ".join(names)
    return _("{names} and {count} more").format(
        names=", ".join(names[:NAMED]), count=len(names) - NAMED
    )


def _project(factory: BrickFactory, name: str) -> str:
    bricks = len(list(factory.bricks))
    events = len(list(factory.events))
    images = len(list(factory.images))
    counts = [
        ngettext("{count} brick", "{count} bricks", bricks),
        ngettext("{count} event", "{count} events", events),
        ngettext("{count} disk image", "{count} disk images", images),
    ]
    return _("{name}: {bricks}, {events}, {images}").format(
        name=name,
        bricks=counts[0].format(count=bricks),
        events=counts[1].format(count=events),
        images=counts[2].format(count=images),
    )


def facts(
    factory: BrickFactory, listening: Sequence[Socket] = ()
) -> list[tuple[str, str]]:
    """
    What the banner says, by its label: an empty label goes on with the
    row before.
    """

    rows = []
    current = projects.current
    if current is not None:
        rows.append((_("Project"), _project(factory, current.name)))
    rows.append((_("Workspace"), locations.short_path(projects.path)))
    qemu_path = str(get_setting("qemu_path"))
    found = emulators(qemu_path)
    if found:
        rows.append((_("QEMU"), found))
    if get_setting("warn_missing_programs"):
        missing = missing_programs(str(get_setting("vde_path")), qemu_path)
        if missing:
            rows.append((_("Missing"), ", ".join(map(str, missing))))
    for number, socket in enumerate(listening):
        label = _("Listening") if number == 0 else ""
        rows.append(
            (
                label,
                _("{protocol} on {socket}").format(
                    protocol=socket.protocol, socket=socket.name()
                ),
            )
        )
    return rows


def _text(rows: Sequence[tuple[str, str]], columns: int) -> list[str]:
    """The lines of the text, its values wrapped to fit columns."""

    labels = max(width(label) for label, _value in rows) + 2
    lines = [
        _("Virtualbricks {version}").format(version=__version__),
        "",
    ]
    for label, value in rows:
        wrapped = textwrap.wrap(
            value,
            max(columns - labels, VALUE_WIDTH),
            break_long_words=False,
            break_on_hyphens=False,
        )
        pad = " " * (labels - width(label))
        lines.append(label + pad + wrapped[0])
        lines += [" " * labels + line for line in wrapped[1:]]
    lines += ["", _("Type help, or press Tab to complete.")]
    return lines


def banner(
    factory: BrickFactory,
    listening: Sequence[Socket] = (),
    columns: int = 80,
) -> list[str]:
    """
    The lines the console starts with, for a terminal columns wide: the
    icon, with the text beside it; the text alone if they don't fit.
    """

    rows = facts(factory, listening)
    indent = LOGO_WIDTH + GAP
    if columns < indent + TEXT_WIDTH:
        return _text(rows, columns)
    text = _text(rows, columns - indent)
    logo = LOGO + [""] * (len(text) - len(LOGO))
    text += [""] * (len(logo) - len(text))
    return [
        (left.ljust(indent) + right).rstrip()
        for left, right in zip(logo, text)
    ]
