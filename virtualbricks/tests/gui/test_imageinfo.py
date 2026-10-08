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
What the windows say about a disk image: its state, facts and uses, in the
picker of a disk, and under a disk.
"""

import os

from virtualbricks.config.images import DiskUse, ImageInfo
from virtualbricks.gui import imageinfo
from virtualbricks.gui.imageinfo import State
from virtualbricks.tests import BrickTestCase
from virtualbricks.tests.gui import untranslated

INFO = ImageInfo("qcow2", 4_300_000_000, 1_234_567, None, ())


class FakeImage:
    def __init__(self, path, name="frr"):
        self.path = path
        self.name = name


class FakeVM:
    def __init__(self, name):
        self.name = name


def use(vm, private=True, running=False, device="hda"):
    vm = FakeVM(vm) if isinstance(vm, str) else vm
    return DiskUse(vm, device, private, None, None, running)


class TestWords(BrickTestCase):

    def setUp(self):
        super().setUp()
        untranslated(self)

    def test_sizes(self):
        self.assertEqual(imageinfo.human_size(999), "999 B")
        self.assertEqual(imageinfo.human_size(200_700), "200.7 KB")
        self.assertEqual(imageinfo.human_size(4_300_000_000), "4.3 GB")
        # no TB: a disk is some thousands of GB at most
        self.assertEqual(imageinfo.human_size(2e12), "2000.0 GB")

    def test_names(self):
        self.assertEqual(imageinfo.names(["r1"]), "r1")
        self.assertEqual(imageinfo.names(["r1", "r2"]), "r1 and r2")
        self.assertEqual(imageinfo.names(["r1", "r2", "r3"]), "r1, r2 and r3")

    def test_facts(self):
        self.assertEqual(
            imageinfo.facts(INFO), "qcow2 · 4.3 GB disk · 1.2 MB on disk"
        )

    def test_use_words(self):
        uses = [
            use("r1"),
            use("r1", device="hdb"),
            use("r2"),
            use("vm", private=False),
        ]
        self.assertEqual(
            imageinfo.use_words(uses),
            "r1 and r2, private copies · vm, the image itself",
        )
        self.assertEqual(imageinfo.use_words([use("r1")]), "r1, private copy")
        self.assertEqual(imageinfo.use_words([]), "no disk uses it")


class TestState(BrickTestCase):

    def setUp(self):
        super().setUp()
        untranslated(self)
        self.path = os.path.abspath(self.mktemp())
        open(self.path, "w").close()
        self.image = FakeImage(self.path)

    def test_states(self):
        self.assertIs(imageinfo.state(self.image, [], True), State.NO_DISK)
        self.assertIs(
            imageinfo.state(self.image, [use("r1")], True), State.NOT_IN_USE
        )
        self.assertIs(
            imageinfo.state(
                self.image, [use("r1"), use("r2", running=True)], True
            ),
            State.IN_USE,
        )

    def test_missing_first(self):
        image = FakeImage("/nowhere/frr.qcow2")
        self.assertIs(
            imageinfo.state(image, [use("r1", running=True)], False),
            State.MISSING,
        )

    def test_summary(self):
        uses = [use("r1")]
        self.assertEqual(
            imageinfo.summary(self.image, INFO, uses, True),
            "qcow2 · 4.3 GB disk · 1.2 MB on disk · r1, private copy",
        )
        # before qemu-img says
        self.assertEqual(
            imageinfo.summary(self.image, None, uses, True),
            "r1, private copy",
        )

    def test_summary_of_a_missing_file(self):
        image = FakeImage("/nowhere/frr.qcow2")
        self.assertEqual(
            imageinfo.summary(image, INFO, [], False),
            "/nowhere/frr.qcow2 isn't there · no disk uses it",
        )

    def test_tooltips(self):
        uses = [use("r1", running=True), use("r2", running=True), use("r3")]
        self.assertEqual(
            imageinfo.tooltip(self.image, State.IN_USE, uses), "r1 and r2 run"
        )
        self.assertEqual(
            imageinfo.tooltip(self.image, State.IN_USE, uses[:1]), "r1 runs"
        )
        self.assertEqual(
            imageinfo.tooltip(self.image, State.MISSING, uses),
            "Find the file of frr",
        )
        self.assertIsNone(imageinfo.tooltip(self.image, State.NO_DISK, []))


class TestThePicker(BrickTestCase):

    def setUp(self):
        super().setUp()
        untranslated(self)
        self.path = os.path.abspath(self.mktemp())
        open(self.path, "w").close()
        self.image = FakeImage(self.path)
        self.r1 = FakeVM("r1")

    def test_short_facts(self):
        self.assertEqual(imageinfo.short_facts(INFO), "qcow2 · 4.3 GB")

    def test_the_other_machines(self):
        uses = [
            use(self.r1),
            use("r2"),
            use("r3"),
            use("gw", private=False),
        ]
        self.assertEqual(
            imageinfo.others_words(uses, self.r1),
            "r2 and r3 use it · gw writes into it",
        )
        self.assertEqual(
            imageinfo.others_words(uses[:2], self.r1), "r2 uses it"
        )
        self.assertEqual(imageinfo.others_words(uses[:1], self.r1), "")

    def test_an_option(self):
        uses = [use(self.r1), use("r2")]
        self.assertEqual(
            imageinfo.option_words(self.image, INFO, uses, self.r1, True),
            "qcow2 · 4.3 GB · r2 uses it",
        )
        # before qemu-img says, and used by none else
        self.assertEqual(
            imageinfo.option_words(self.image, None, uses[:1], self.r1, True),
            "",
        )

    def test_an_option_without_its_file(self):
        image = FakeImage("/nowhere/frr.qcow2")
        self.assertEqual(
            imageinfo.option_words(image, INFO, [], self.r1, False),
            "The file isn't there",
        )


class TestTheLineOfADisk(BrickTestCase):

    def setUp(self):
        super().setUp()
        untranslated(self)
        self.path = os.path.abspath(self.mktemp())
        open(self.path, "w").close()
        self.image = FakeImage(self.path)
        self.copy = "/lab/r1_hda.cow"

    def line(self, image, saved=None, private=True, size=None):
        # the file of the image is there if it's on this machine
        there = image is not None and os.path.exists(image.path)
        return imageinfo.disk_line(
            "r1", image, saved, private, self.copy, size, there
        )

    def test_no_image(self):
        self.assertEqual(
            self.line(None), "No image: r1 starts without this disk."
        )

    def test_a_missing_file(self):
        self.assertEqual(
            self.line(FakeImage("/nowhere/frr.qcow2")),
            "The file of frr isn't there: find it in the Images tab, or"
            " choose another image.",
        )

    def test_the_image_itself(self):
        self.assertEqual(
            self.line(self.image, private=False),
            "r1 writes into frr; while r1 runs, no other machine can use it.",
        )

    def test_a_copy_to_make(self):
        self.assertEqual(
            self.line(self.image, self.image),
            "r1's changes will be kept in r1_hda.cow, made at the next start;"
            " frr stays as it is.",
        )

    def test_a_copy(self):
        self.assertEqual(
            self.line(self.image, self.image, size=18_000_000),
            "r1's changes are kept in r1_hda.cow, 18.0 MB, in the project;"
            " frr stays as it is.",
        )

    def test_a_copy_of_another_image(self):
        saved = FakeImage(self.path, "debian")
        self.assertEqual(
            self.line(self.image, saved, size=18_000_000),
            "r1_hda.cow keeps r1's changes to debian: the next start sets it"
            " aside and begins again from frr.",
        )

    def test_a_copy_of_a_disk_added_again(self):
        # the image it had is not known
        self.assertIn(
            "are kept in r1_hda.cow", self.line(self.image, size=4096)
        )
