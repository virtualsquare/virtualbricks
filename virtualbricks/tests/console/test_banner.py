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

"""The banner the console starts with, in each style of --banner."""

import os

from virtualbricks import __version__, locations, sockets
from virtualbricks.config import settings
from virtualbricks.console.banner import (
    AMBER,
    BRICK_DARK,
    BRICK_LIGHT,
    COLOUR,
    DROP,
    DROP_DELAY,
    EMOJI,
    GAP,
    HOVER,
    LETTERS,
    LOGO,
    LOGO_WIDTH,
    MORTAR,
    PIXEL,
    PLAIN,
    RAINBOW,
    SHADOW,
    SPRITE,
    SPRITE_WIDTH,
    THREE_D,
    Banner,
    Fact,
    banner,
    bg,
    drop,
    emulators,
    facts,
    fg,
    frames,
    mix,
    paint,
    painted,
    pixels,
    visible,
)
from virtualbricks.sockets import Socket
from virtualbricks.tests import BrickTestCase, use_workspace

# A dark brick over a light one, as pixels() paints them
BRICK_CODES = f"{fg(BRICK_LIGHT)};{bg(BRICK_DARK)}"


def stripped(lines):
    """The lines without their colours."""

    from virtualbricks.console.banner import ESCAPE

    return [ESCAPE.sub("", line) for line in lines]


def big_line(word, row):
    return "".join(LETTERS[letter][row] for letter in word).rstrip()


class BannerTestCase(BrickTestCase):

    def setUp(self):
        super().setUp()
        self.workspace = use_workspace(
            self, os.path.join(locations.home(), "labs")
        )
        os.makedirs(self.workspace.path)
        # the fakes have all but qemu-img
        self.program("qemu-img")

    def program(self, name):
        path = os.path.join(self.bin, name)
        with open(path, "w") as fp:
            fp.write("#!/bin/sh\n")
        os.chmod(path, 0o755)

    def open(self, name):
        self.workspace.create(name)
        self.workspace.open(name, self.factory)

    def facts(self, listening=()):
        return {
            fact.label: fact.value for fact in facts(self.factory, listening)
        }


class TestNone(BannerTestCase):

    def test_the_line_of_before(self):
        line = f"Virtualbricks {__version__}. Type help, or press Tab to complete."
        self.assertEqual(banner(self.factory), [line])
        self.assertEqual(Banner().lines(self.factory), [line])


class TestPlain(BannerTestCase):

    def test_beside_the_icon(self):
        self.open("lab")
        self.factory.new_brick("switch", "sw1")
        self.factory.new_brick("switch", "sw2")
        self.assertEqual(
            Banner(PLAIN).lines(self.factory),
            [
                f"                [_____]    Virtualbricks {__version__}",
                "[_____]          .--.",
                "[__|__]        [__|__]     Project    lab: 2 bricks,"
                " 0 events, 0 disk images",
                "[_____]      [_____]       Workspace  ~/labs",
                "[__|__]    [__|__]         QEMU       x86_64, i386",
                "[_____]  [_____]",
                "[__|__][_____]             Type help, or press Tab to"
                " complete.",
                "   [_____]",
            ],
        )

    def test_alone_in_a_narrow_terminal(self):
        lines = banner(self.factory, PLAIN, columns=66)
        self.assertEqual(
            lines,
            [
                f"Virtualbricks {__version__}",
                "",
                "Workspace  ~/labs",
                "QEMU       x86_64, i386",
                "",
                "Type help, or press Tab to complete.",
            ],
        )
        self.assertEqual(len(banner(self.factory, PLAIN, columns=67)), 8)

    def test_more_lines_than_the_icon(self):
        listening = [Socket(f"/srv/lab{n}.sock") for n in range(5)]
        lines = banner(self.factory, PLAIN, listening)
        self.assertGreater(len(lines), len(LOGO))
        for logo, line in zip(LOGO, lines):
            self.assertTrue(line.startswith(logo), line)
        # below the icon, the text stays in its column
        indent = " " * (LOGO_WIDTH + GAP)
        self.assertEqual(
            lines[len(LOGO) :],
            [
                indent + "           amp on /srv/lab4.sock",
                "",
                indent + "Type help, or press Tab to complete.",
            ],
        )

    def test_a_long_value_wraps_under_its_column(self):
        # PATH is empty: no VDE program anywhere
        settings.set_setting("vde_path", "")
        lines = banner(self.factory, PLAIN, columns=50)
        first = next(
            n for n, line in enumerate(lines) if line.startswith("Missing")
        )
        wrapped = lines[first : lines.index("", first)]
        self.assertGreater(len(wrapped), 1)
        column = len("Missing    ")
        for line in wrapped[1:]:
            self.assertEqual(line[:column].strip(), "")
            self.assertNotEqual(line[column], " ")
        self.assertEqual(
            " ".join(line[column:] for line in wrapped),
            self.facts()["Missing"],
        )
        self.assertLessEqual(max(map(len, lines)), 50)


class TestColour(BannerTestCase):

    def test_the_plain_banner_in_colour(self):
        self.open("lab")
        lines = banner(self.factory, COLOUR)
        self.assertEqual(stripped(lines), banner(self.factory, PLAIN))
        # the bricks red, the mortar grey, the labels bold red
        self.assertEqual(
            lines[2],
            "\x1b[31m[__|__]        [__|__]\x1b[0m"
            "     \x1b[1;31mProject\x1b[0m    lab: 0 bricks,"
            " 0 events, 0 disk images",
        )
        self.assertIn("\x1b[90m.--.\x1b[0m", lines[1])
        self.assertIn(
            "Type \x1b[1mhelp\x1b[0m, or press \x1b[1mTab\x1b[0m", lines[6]
        )

    def test_the_missing_programs_in_yellow(self):
        os.remove(os.path.join(self.bin, "qemu-img"))
        lines = banner(self.factory, COLOUR)
        self.assertIn("\x1b[33mqemu-img (qemu-utils)\x1b[0m", "\n".join(lines))

    def test_alone_in_a_narrow_terminal(self):
        lines = banner(self.factory, COLOUR, columns=66)
        self.assertEqual(
            stripped(lines), banner(self.factory, PLAIN, columns=66)
        )


class TestLetters(BannerTestCase):

    def test_the_name_on_one_line(self):
        lines = stripped(banner(self.factory, THREE_D, columns=97))
        self.assertEqual(
            lines[:6], [big_line("VIRTUALBRICKS", row) for row in range(6)]
        )
        # the version as a fact: the name is above
        self.assertEqual(
            lines[6:],
            [
                "",
                f"Version    {__version__}",
                "Workspace  ~/labs",
                "QEMU       x86_64, i386",
                "",
                "Type help, or press Tab to complete.",
            ],
        )

    def test_the_name_on_two_lines(self):
        lines = stripped(banner(self.factory, THREE_D, columns=96))
        self.assertEqual(
            lines[:12],
            [big_line("VIRTUAL", row) for row in range(6)]
            + [big_line("BRICKS", row) for row in range(6)],
        )
        self.assertEqual(lines[13], f"Version    {__version__}")
        self.assertEqual(len(banner(self.factory, THREE_D, columns=54)), 18)

    def test_alone_in_a_narrow_terminal(self):
        for style in (THREE_D, RAINBOW):
            lines = stripped(banner(self.factory, style, columns=53))
            self.assertEqual(lines[0], f"Virtualbricks {__version__}")

    def test_lit_from_above(self):
        lines = banner(self.factory, THREE_D, columns=97)
        # the faces darker line by line, the shadows grey
        self.assertIn(paint("██", fg(BRICK_LIGHT)), lines[0])
        self.assertIn(
            paint("██", fg(mix(BRICK_LIGHT, BRICK_DARK, 0.6))), lines[3]
        )
        self.assertIn(paint("╗", fg(SHADOW)), lines[0])
        self.assertIn("\x1b[1;" + fg((203, 67, 67)) + "mVersion", lines[7])

    def test_the_rainbow(self):
        lines = banner(self.factory, RAINBOW, columns=97)
        self.assertEqual(
            stripped(lines),
            stripped(banner(self.factory, THREE_D, columns=97)),
        )
        # a colour for each column of a face, and for each label
        faces = {
            code
            for code in lines[0].split("\x1b[")
            if code.startswith("38;2;")
        }
        self.assertGreater(len(faces), 40)
        labels = {line.split("m", 1)[0] for line in lines[7:10]}
        self.assertEqual(len(labels), 3)


class TestPixel(BannerTestCase):

    def test_beside_the_text(self):
        lines = banner(self.factory, PIXEL)
        self.assertEqual(len(lines), 11)
        self.assertEqual(
            lines[0],
            " " * 18
            + paint("▀" * 7, BRICK_CODES)
            + " " * GAP
            + paint(f"Virtualbricks {__version__}", "1"),
        )
        self.assertEqual(
            stripped(lines)[2][SPRITE_WIDTH + GAP :], "Workspace  ~/labs"
        )

    def test_the_pixels(self):
        lines = pixels()
        self.assertEqual(len(lines), 11)
        # the floating brick, light over dark
        self.assertEqual(lines[0], " " * 18 + paint("▀" * 7, BRICK_CODES))
        # the mortar over the light top of a brick and its joint; then
        # the dark bottom of the brick, over an empty row
        self.assertEqual(stripped(lines)[2], "▄▄▄ ▄▄▄" + " " * 9 + "▄▄▄▀▀▀▄")
        self.assertEqual(stripped(lines)[3], "▀▀▀ ▀▀▀" + " " * 9 + "▀▀▀ ▀▀▀")
        self.assertIn(
            paint("▀", fg(MORTAR))
            + paint("▀▀", f"{fg(MORTAR)};{bg(BRICK_LIGHT)}"),
            lines[2],
        )

    def test_alone_in_a_narrow_terminal(self):
        lines = banner(self.factory, PIXEL, columns=SPRITE_WIDTH + GAP + 39)
        self.assertNotIn("▀", "".join(lines))
        lines = banner(self.factory, PIXEL, columns=SPRITE_WIDTH + GAP + 40)
        self.assertIn("▀", "".join(lines))


class TestDrop(BannerTestCase):

    def column(self, frame, x):
        """The rows of pixels of a column of a frame that a brick is on."""

        return [y for y, row in enumerate(frame) if row[x] in "Aa"]

    def test_a_brick_falls_a_pixel_a_frame(self):
        # the bottom brick first, from the top: column 7 is its own
        pixels = drop()
        for frame in range(21):
            self.assertEqual(self.column(pixels[frame], 7), [frame, frame + 1])
        self.assertEqual(self.column(pixels[-1], 7), [20, 21])

    def test_a_row_at_a_time_from_the_bottom_up(self):
        pixels = drop()
        # the next row starts DROP_DELAY frames after
        self.assertEqual(self.column(pixels[DROP_DELAY - 1], 0), [])
        self.assertEqual(self.column(pixels[DROP_DELAY], 0), [0, 1])
        self.assertEqual(self.column(pixels[DROP_DELAY], 11), [0, 1])

    def test_the_last_brick_hovers_then_lands(self):
        pixels = drop()
        # all the others down, it hovers over its mortar, as in the icon
        hover = [n for n, frame in enumerate(pixels) if frame == SPRITE]
        self.assertEqual(len(hover), HOVER + 1)
        # then falls a pixel a frame
        self.assertEqual(
            pixels[hover[-1] + 1][:3],
            [
                "." * 25,
                "." * 18 + "AAAAAAA",
                "AAAAAAA" + "." * 11 + "aaaaaaa",
            ],
        )
        landed = pixels[-1]
        self.assertEqual(len(pixels), hover[-1] + 3)
        self.assertEqual(landed[2], "AAAAAAA" + "." * 11 + "AAAAAAA")
        self.assertEqual(landed[3], "aaaaaaa" + "." * 11 + "aaaaaaa")
        # the mortar under it is gone, the rest as in the icon
        self.assertEqual(landed[:2], ["." * 25] * 2)
        self.assertEqual(landed[4], "." * 25)
        self.assertEqual(landed[5:], SPRITE[5:])

    def test_the_mortar_once_its_brick_is_down(self):
        pixels = drop()
        mortar = [n for n, frame in enumerate(pixels) if "m" in frame[4]]
        # its brick lands on row 5, from the sixth start
        down = 5 * DROP_DELAY + 5
        self.assertEqual(mortar, list(range(down, len(pixels) - 1)))
        self.assertEqual(self.column(pixels[down], 22), [5, 6])
        self.assertEqual(self.column(pixels[down - 1], 22), [4, 5])

    def test_the_frames_of_the_banner(self):
        shown = frames(self.factory, DROP)
        self.assertEqual(len(shown), len(drop()))
        self.assertEqual({len(frame) for frame in shown}, {11})
        # the text beside each, the same
        indent = SPRITE_WIDTH + GAP
        texts = {
            tuple(line[indent:] for line in stripped(frame)) for frame in shown
        }
        self.assertEqual(len(texts), 1)
        # the first, with the bottom brick at the top
        self.assertEqual(
            stripped(shown[0])[0],
            "   "
            + "▀" * 7
            + " " * (indent - 10)
            + f"Virtualbricks {__version__}",
        )
        # the last one is the banner
        self.assertEqual(shown[-1], banner(self.factory, DROP))
        self.assertEqual(Banner(DROP).frames(self.factory), shown)

    def test_alone_in_a_narrow_terminal(self):
        columns = SPRITE_WIDTH + GAP + 39
        self.assertEqual(
            frames(self.factory, DROP, columns=columns),
            [banner(self.factory, PIXEL, columns=columns)],
        )

    def test_the_others_stay(self):
        for style in (PLAIN, PIXEL, RAINBOW):
            self.assertEqual(
                frames(self.factory, style), [banner(self.factory, style)]
            )


class TestEmoji(BannerTestCase):

    def test_a_mark_on_each_line(self):
        self.open("lab")
        os.remove(os.path.join(self.bin, "qemu-img"))
        listening = [Socket("/srv/a.sock"), Socket("/srv/b.sock")]
        lines = stripped(banner(self.factory, EMOJI, listening, columns=200))
        self.assertEqual(
            lines,
            [
                f"🧱 Virtualbricks {__version__} ✨",
                "",
                "📂 Project    lab: 0 bricks, 0 events, 0 disk images",
                "🏠 Workspace  ~/labs",
                "💻 QEMU       x86_64, i386",
                "🚧 Missing    qemu-img (qemu-utils)",
                "📡 Listening  amp on /srv/a.sock",
                "              amp on /srv/b.sock",
                "",
                "💡 Type help, or press Tab to complete.",
            ],
        )

    def test_the_missing_programs_in_amber(self):
        os.remove(os.path.join(self.bin, "qemu-img"))
        lines = banner(self.factory, EMOJI)
        self.assertIn(
            paint("qemu-img (qemu-utils)", fg(AMBER)), "\n".join(lines)
        )


class TestColours(BannerTestCase):

    def test_visible(self):
        self.assertEqual(visible(paint("ab", "1;31") + "🧱"), 4)

    def test_paint(self):
        self.assertEqual(paint("ab", "31"), "\x1b[31mab\x1b[0m")
        self.assertEqual(paint("ab", ""), "ab")
        self.assertEqual(paint("", "31"), "")

    def test_painted_runs(self):
        self.assertEqual(
            painted([("a", "31"), ("b", "31"), (" ", ""), ("c", "33")]),
            "\x1b[31mab\x1b[0m \x1b[33mc\x1b[0m",
        )


class TestFacts(BannerTestCase):

    def test_the_project(self):
        self.open("lab")
        self.factory.new_brick("switch", "sw1")
        self.factory.new_event("ev1")
        self.assertEqual(
            self.facts()["Project"], "lab: 1 brick, 1 event, 0 disk images"
        )

    def test_no_project(self):
        self.assertNotIn("Project", self.facts())

    def test_the_workspace_outside_home(self):
        use_workspace(self, "/srv/labs")
        self.assertEqual(self.facts()["Workspace"], "/srv/labs")

    def test_no_emulator(self):
        for name in ("qemu-system-x86_64", "qemu-system-i386"):
            os.remove(os.path.join(self.bin, name))
        self.assertNotIn("QEMU", self.facts())

    def test_the_missing_programs(self):
        os.remove(os.path.join(self.bin, "vde_switch"))
        os.remove(os.path.join(self.bin, "qemu-img"))
        self.assertEqual(
            self.facts()["Missing"], "vde_switch (vde2), qemu-img (qemu-utils)"
        )

    def test_not_the_missing_programs_if_not_warned(self):
        os.remove(os.path.join(self.bin, "vde_switch"))
        settings.set_setting("warn_missing_programs", False)
        self.assertNotIn("Missing", self.facts())

    def test_the_sockets(self):
        listening = [
            Socket("/srv/lab.sock"),
            Socket(None, sockets.JSON, "tcp", "127.0.0.1", 7000),
        ]
        self.assertEqual(
            facts(self.factory, listening)[-2:],
            [
                Fact("listening", "Listening", "amp on /srv/lab.sock"),
                Fact("listening", "", "json on tcp 127.0.0.1 port 7000"),
            ],
        )


class TestEmulators(BannerTestCase):

    def test_x86_64_first(self):
        self.program("qemu-system-aarch64")
        self.assertEqual(emulators(self.bin), "x86_64, aarch64, i386")

    def test_the_others_counted(self):
        for arch in ("aarch64", "arm", "riscv64", "s390x"):
            self.program(f"qemu-system-{arch}")
        self.assertEqual(
            emulators(self.bin), "x86_64, aarch64, arm and 3 more"
        )

    def test_one_more_is_named(self):
        for arch in ("aarch64", "arm"):
            self.program(f"qemu-system-{arch}")
        self.assertEqual(emulators(self.bin), "x86_64, aarch64, arm, i386")

    def test_without_x86_64(self):
        os.remove(os.path.join(self.bin, "qemu-system-x86_64"))
        self.assertEqual(emulators(self.bin), "i386")
