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
What the console in the terminal shows as it starts, in the style of
--banner: the line of the version and of help alone, by default; or a
banner, the icon of Virtualbricks or its name in large letters, with the
version, the open project, the workspace, the QEMU emulators, the programs
that are missing and the control sockets listened on.

``plain`` draws the icon in characters, ``colour`` paints them in the 16
colours of the terminal. ``3d`` and ``rainbow`` write the name in letters
of blocks with their shadow, ``pixel`` draws the icon in blocks of colour,
and ``emoji`` goes without a picture: they need a terminal of 24-bit
colour, as most are, and ``emoji`` a font with emoji.

A terminal too narrow for the picture has the text alone.
"""

from __future__ import annotations

import math
import re
import textwrap
from collections.abc import Callable, Sequence
from typing import NamedTuple

import attr

from virtualbricks import __version__, locations
from virtualbricks.brickfactory import BrickFactory
from virtualbricks.cli import BANNERS, Style
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

NONE, PLAIN, COLOUR, THREE_D, RAINBOW, PIXEL, EMOJI = BANNERS

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
# The icon in pixels, two to a character: A the light top of a brick, a
# its dark bottom, m the mortar.
SPRITE = [
    "..................AAAAAAA",
    "..................aaaaaaa",
    "AAAAAAA..................",
    "aaaaaaa..................",
    "...................mmm...",
    "AAA.AAA.........AAA.AAA..",
    "aaa.aaa.........aaa.aaa..",
    ".........................",
    "AAAAAAA.......AAAAAAA....",
    "aaaaaaa.......aaaaaaa....",
    ".........................",
    "AAA.AAA.....AAA.AAA......",
    "aaa.aaa.....aaa.aaa......",
    ".........................",
    "AAAAAAA...AAAAAAA........",
    "aaaaaaa...aaaaaaa........",
    ".........................",
    "AAA.AAA.AAAAAAA..........",
    "aaa.aaa.aaaaaaa..........",
    ".........................",
    "...AAAAAAA...............",
    "...aaaaaaa...............",
]
SPRITE_WIDTH = len(SPRITE[0])
# The letters of the name, after the ANSI Shadow font of figlet: the full
# blocks are their faces, the lines of the boxes their shadow.
LETTERS = {
    "A": (
        " █████╗ ",
        "██╔══██╗",
        "███████║",
        "██╔══██║",
        "██║  ██║",
        "╚═╝  ╚═╝",
    ),
    "B": (
        "██████╗ ",
        "██╔══██╗",
        "██████╔╝",
        "██╔══██╗",
        "██████╔╝",
        "╚═════╝ ",
    ),
    "C": (
        " ██████╗",
        "██╔════╝",
        "██║     ",
        "██║     ",
        "╚██████╗",
        " ╚═════╝",
    ),
    "I": (
        "██╗",
        "██║",
        "██║",
        "██║",
        "██║",
        "╚═╝",
    ),
    "K": (
        "██╗  ██╗",
        "██║ ██╔╝",
        "█████╔╝ ",
        "██╔═██╗ ",
        "██║  ██╗",
        "╚═╝  ╚═╝",
    ),
    "L": (
        "██╗     ",
        "██║     ",
        "██║     ",
        "██║     ",
        "███████╗",
        "╚══════╝",
    ),
    "R": (
        "██████╗ ",
        "██╔══██╗",
        "██████╔╝",
        "██╔══██╗",
        "██║  ██║",
        "╚═╝  ╚═╝",
    ),
    "S": (
        "███████╗",
        "██╔════╝",
        "███████╗",
        "╚════██║",
        "███████║",
        "╚══════╝",
    ),
    "T": (
        "████████╗",
        "╚══██╔══╝",
        "   ██║   ",
        "   ██║   ",
        "   ██║   ",
        "   ╚═╝   ",
    ),
    "U": (
        "██╗   ██╗",
        "██║   ██║",
        "██║   ██║",
        "██║   ██║",
        "╚██████╔╝",
        " ╚═════╝ ",
    ),
    "V": (
        "██╗   ██╗",
        "██║   ██║",
        "██║   ██║",
        "╚██╗ ██╔╝",
        " ╚████╔╝ ",
        "  ╚═══╝  ",
    ),
}
FACE = "█"
# The name on one line, else on two.
NAME: tuple[str, ...] = ("VIRTUALBRICKS",)
NAME_SPLIT: tuple[str, ...] = ("VIRTUAL", "BRICKS")

# The spaces between the picture and the text.
GAP = 4
# The columns the text needs beside the picture; with fewer, it goes alone.
TEXT_WIDTH = 40
# The columns a value wraps at, however narrow the terminal.
VALUE_WIDTH = 20
# The emulators named; those after them are counted.
NAMED = 3
QEMU_PREFIX = "qemu-system-"

# The kinds of the facts.
PROJECT = "project"
WORKSPACE = "workspace"
QEMU = "qemu"
MISSING = "missing"
LISTENING = "listening"
VERSION = "version"
# The emoji of each kind, and of the first and last lines, in the emoji
# style: all of them two columns wide.
EMOJIS = {
    PROJECT: "📂",
    WORKSPACE: "🏠",
    QEMU: "💻",
    MISSING: "🚧",
    LISTENING: "📡",
    VERSION: "🧱",
}
SPARKLES = "✨"
TIP = "💡"

RGB = tuple[int, int, int]
BRICK: RGB = (203, 67, 67)
BRICK_LIGHT: RGB = (226, 98, 98)
BRICK_DARK: RGB = (160, 44, 44)
MORTAR: RGB = (193, 204, 204)
SHADOW: RGB = (96, 96, 104)
AMBER: RGB = (232, 170, 64)
# The colours of the pixels of SPRITE.
PIXELS: dict[str, RGB] = {"A": BRICK_LIGHT, "a": BRICK_DARK, "m": MORTAR}

RESET = "\x1b[0m"
ESCAPE = re.compile(r"\x1b\[[0-9;]*m")


class Fact(NamedTuple):
    """A line of the banner: its kind, its label and its value."""

    kind: str
    label: str
    value: str


@attr.define(frozen=True)
class Banner:
    """The banner that --banner asks for, and the sockets it names."""

    style: Style = NONE
    listening: Sequence[Socket] = ()

    def lines(self, factory: BrickFactory, columns: int = 80) -> list[str]:
        """The lines the console starts with, in a terminal columns wide."""

        return banner(factory, self.style, self.listening, columns)


# The colours


def visible(text: str) -> int:
    """The columns text takes in a terminal, without its colours."""

    return width(ESCAPE.sub("", text))


def paint(text: str, codes: str) -> str:
    """text in the colours of the SGR codes, as 1;31; as it is without."""

    if not codes or not text:
        return text
    return f"\x1b[{codes}m{text}{RESET}"


def fg(colour: RGB) -> str:
    return "38;2;{};{};{}".format(*colour)


def bg(colour: RGB) -> str:
    return "48;2;{};{};{}".format(*colour)


def mix(start: RGB, end: RGB, at: float) -> RGB:
    """The colour at a fraction of the way from start to end."""

    r, g, b = (round(s + (e - s) * at) for s, e in zip(start, end))
    return r, g, b


def rainbow(at: float) -> RGB:
    """The colour at a place of the rainbow, as lolcat paints it."""

    r, g, b = (
        round(math.sin(at + phase) * 127 + 128)
        for phase in (0, 2 * math.pi / 3, 4 * math.pi / 3)
    )
    return r, g, b


def painted(cells: Sequence[tuple[str, str]]) -> str:
    """A line of characters each with its codes, a run of the same once."""

    out = []
    run, codes = "", ""
    for character, code in cells:
        if code != codes:
            out.append(paint(run, codes))
            run, codes = "", code
        run += character
    out.append(paint(run, codes))
    return "".join(out)


@attr.define(frozen=True)
class Palette:
    """The SGR codes of each part of a banner; empty for none."""

    brick: str = ""
    mortar: str = ""
    title: str = ""
    label: str = ""
    warning: str = ""
    key: str = ""
    # the colour of a label by its line, instead of label
    labels: Callable[[int], str] | None = None


PLAIN_PALETTE = Palette()
# the 16 colours of the terminal, whichever they are
COLOUR_PALETTE = Palette(
    brick="31", mortar="90", title="1", label="1;31", warning="33", key="1"
)
# 24-bit colour
TRUE_PALETTE = Palette(
    brick=fg(BRICK),
    mortar=fg(MORTAR),
    title="1",
    label="1;" + fg(BRICK),
    warning=fg(AMBER),
    key="1",
)
RAINBOW_PALETTE = attr.evolve(
    TRUE_PALETTE, labels=lambda line: "1;" + fg(rainbow(line * 0.6))
)


# The facts


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
) -> list[Fact]:
    """
    What the banner says, line by line: a fact with an empty label goes on
    with the one before.
    """

    rows = []
    current = projects.current
    if current is not None:
        rows.append(
            Fact(PROJECT, _("Project"), _project(factory, current.name))
        )
    rows.append(
        Fact(WORKSPACE, _("Workspace"), locations.short_path(projects.path))
    )
    qemu_path = str(get_setting("qemu_path"))
    found = emulators(qemu_path)
    if found:
        rows.append(Fact(QEMU, _("QEMU"), found))
    if get_setting("warn_missing_programs"):
        missing = missing_programs(str(get_setting("vde_path")), qemu_path)
        if missing:
            names = ", ".join(map(str, missing))
            rows.append(Fact(MISSING, _("Missing"), names))
    for number, socket in enumerate(listening):
        label = _("Listening") if number == 0 else ""
        value = _("{protocol} on {socket}").format(
            protocol=socket.protocol, socket=socket.name()
        )
        rows.append(Fact(LISTENING, label, value))
    return rows


# The text


def greeting() -> str:
    return _(
        "Virtualbricks {version}. Type help, or press Tab to complete."
    ).format(version=__version__)


def title() -> str:
    return _("Virtualbricks {version}").format(version=__version__)


def hint(palette: Palette) -> str:
    return _("Type {help}, or press {tab} to complete.").format(
        help=paint("help", palette.key), tab=paint(_("Tab"), palette.key)
    )


def _text(
    rows: Sequence[Fact],
    columns: int,
    palette: Palette,
    heading: str | None = None,
    marks: dict[str, str] | None = None,
) -> list[str]:
    """
    The lines of the text: the heading, the facts with their values wrapped
    to fit columns, and how to get help. With marks, each line starts with
    the mark of its kind, and the heading and help with theirs.
    """

    labels = max(width(row.label) for row in rows) + 2
    mark = 3 if marks is not None else 0
    lines: list[str] = []
    if heading is not None:
        lines += [heading, ""]
    for number, row in enumerate(rows):
        wrapped = textwrap.wrap(
            row.value,
            max(columns - labels - mark, VALUE_WIDTH),
            break_long_words=False,
            break_on_hyphens=False,
        )
        codes = palette.labels(number) if palette.labels else palette.label
        label = paint(row.label, codes) + " " * (labels - width(row.label))
        if row.kind == MISSING:
            wrapped = [paint(line, palette.warning) for line in wrapped]
        start = ""
        if marks is not None:
            start = (marks[row.kind] if row.label else "  ") + " "
        lines.append(start + label + wrapped[0])
        lines += [" " * (mark + labels) + line for line in wrapped[1:]]
    lines += ["", hint(palette)]
    return lines


def _beside(left: Sequence[str], right: Sequence[str]) -> list[str]:
    """The lines of a picture, with the text on its right."""

    indent = max(map(visible, left)) + GAP
    height = max(len(left), len(right))
    left = list(left) + [""] * (height - len(left))
    right = list(right) + [""] * (height - len(right))
    return [
        (picture + " " * (indent - visible(picture)) + text).rstrip()
        for picture, text in zip(left, right)
    ]


# The pictures


def logo(palette: Palette) -> list[str]:
    """LOGO, its bricks and its mortar in their colours."""

    def codes(character: str) -> str:
        return palette.mortar if character in ".-" else palette.brick

    return [painted([(c, codes(c)) for c in line]) for line in LOGO]


def pixels() -> list[str]:
    """
    SPRITE in blocks of 24-bit colour, two pixels to a character: the top
    one in the colour of the character, the bottom one in that of its
    background; nothing is painted where a pixel is empty.
    """

    lines = []
    for top_row, bottom_row in zip(SPRITE[::2], SPRITE[1::2]):
        cells = []
        for top, bottom in zip(top_row, bottom_row):
            up, down = PIXELS.get(top), PIXELS.get(bottom)
            if up is None and down is None:
                cells.append((" ", ""))
            elif down is None:
                assert up is not None, "one of them is a pixel"
                cells.append(("▀", fg(up)))
            elif up is None:
                cells.append(("▄", fg(down)))
            elif up == down:
                cells.append(("█", fg(up)))
            else:
                cells.append(("▀", f"{fg(up)};{bg(down)}"))
        lines.append(painted(cells).rstrip())
    return lines


def big(words: Sequence[str], face: Callable[[int, int], str]) -> list[str]:
    """
    The words in LETTERS, one under the other: the faces in the codes that
    face gives for a column and a line of all of them, the shadows grey.
    """

    lines: list[str] = []
    for word in words:
        for row in range(len(LETTERS["A"])):
            line = "".join(LETTERS[letter][row] for letter in word)
            y = len(lines)
            cells = [
                (
                    c,
                    (
                        face(x, y)
                        if c == FACE
                        else fg(SHADOW) if c != " " else ""
                    ),
                )
                for x, c in enumerate(line)
            ]
            lines.append(painted(cells).rstrip())
    return lines


def big_width(word: str) -> int:
    return sum(len(LETTERS[letter][0]) for letter in word)


def _brick_face(x: int, y: int) -> str:
    # lit from above: each line a little darker
    return fg(mix(BRICK_LIGHT, BRICK_DARK, (y % 6) / 5))


def _rainbow_face(x: int, y: int) -> str:
    return fg(rainbow((x + 2 * y) * 0.07))


# The banners


def banner(
    factory: BrickFactory,
    style: Style = NONE,
    listening: Sequence[Socket] = (),
    columns: int = 80,
) -> list[str]:
    """
    The lines the console starts with in style, for a terminal columns
    wide: the line of the version and help alone for NONE; else the
    picture, with the text beside or below it, or the text alone if the
    picture doesn't fit.
    """

    if style == NONE:
        return [greeting()]
    rows = facts(factory, listening)
    if style == EMOJI:
        heading = paint(title(), TRUE_PALETTE.title)
        heading = f"{EMOJIS[VERSION]} {heading} {SPARKLES}"
        lines = _text(rows, columns, TRUE_PALETTE, heading, EMOJIS)
        lines[-1] = f"{TIP} {lines[-1]}"
        return lines
    if style in (THREE_D, RAINBOW):
        return _letters(rows, style, columns)
    if style == PIXEL:
        picture, palette = pixels(), TRUE_PALETTE
    else:
        palette = COLOUR_PALETTE if style == COLOUR else PLAIN_PALETTE
        picture = logo(palette)
    heading = paint(title(), palette.title)
    indent = max(map(visible, picture)) + GAP
    if columns < indent + TEXT_WIDTH:
        return _text(rows, columns, palette, heading)
    return _beside(picture, _text(rows, columns - indent, palette, heading))


def _letters(rows: list[Fact], style: Style, columns: int) -> list[str]:
    """The name in big letters, the version and the facts below it."""

    if style == RAINBOW:
        palette, face = RAINBOW_PALETTE, _rainbow_face
    else:
        palette, face = TRUE_PALETTE, _brick_face
    if columns >= big_width(NAME[0]):
        words = NAME
    elif columns >= max(map(big_width, NAME_SPLIT)):
        words = NAME_SPLIT
    else:
        return _text(rows, columns, palette, paint(title(), palette.title))
    rows = [Fact(VERSION, _("Version"), __version__)] + rows
    return big(words, face) + [""] + _text(rows, columns, palette)
