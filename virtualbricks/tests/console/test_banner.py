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

"""The banner the console starts with."""

import os

from virtualbricks import __version__, locations, sockets
from virtualbricks.config import settings
from virtualbricks.console.banner import (
    GAP,
    LOGO,
    LOGO_WIDTH,
    banner,
    emulators,
    facts,
)
from virtualbricks.sockets import Socket
from virtualbricks.tests import BrickTestCase, use_workspace


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
        return dict(facts(self.factory, listening))


class TestBanner(BannerTestCase):

    def test_beside_the_icon(self):
        self.open("lab")
        self.factory.new_brick("switch", "sw1")
        self.factory.new_brick("switch", "sw2")
        self.assertEqual(
            banner(self.factory),
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
        lines = banner(self.factory, columns=60)
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

    def test_more_lines_than_the_icon(self):
        listening = [Socket(f"/srv/lab{n}.sock") for n in range(5)]
        lines = banner(self.factory, listening)
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
        lines = banner(self.factory, columns=50)
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
                ("Listening", "amp on /srv/lab.sock"),
                ("", "json on tcp 127.0.0.1 port 7000"),
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
