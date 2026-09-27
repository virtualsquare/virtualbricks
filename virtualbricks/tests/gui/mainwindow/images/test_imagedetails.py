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

"""The details of an image: its name, description, facts and uses."""

import os

from virtualbricks.config import images
from virtualbricks.config.workspace import OpenProject
from virtualbricks.tests import FakeLogger
from virtualbricks.tests.config.test_images import (
    INFO,
    FakeQemuImg,
    FakeWorkspace,
)
from virtualbricks.tests.gui import GuiTestCase, has_display, untranslated
from virtualbricks.tests.gui.mainwindow.images.test_tab import LaterQemuImg

if has_display:
    from virtualbricks.gui import imageinfo
    from virtualbricks.gui.mainwindow.images import imagedetails
    from virtualbricks.gui.mainwindow.images.imagedetails import ImageDetails


def cells(grid):
    """The texts of a grid, row by row."""

    rows = {}
    for child in grid.get_children():
        row = grid.child_get_property(child, "top-attach")
        column = grid.child_get_property(child, "left-attach")
        rows.setdefault(row, {})[column] = child.get_text()
    return [
        [rows[row][column] for column in sorted(rows[row])]
        for row in sorted(rows)
    ]


class DetailsTestCase(GuiTestCase):

    def setUp(self):
        super().setUp()
        untranslated(self)
        self.qemu_img = FakeQemuImg()
        self.infos = images.InfoCache(self.qemu_img)
        self.lab = self.folder("lab")
        self.manager.current = OpenProject(self.lab, None)
        self.workspace = FakeWorkspace(None)
        self.frr = self.image("frr")
        self.qemu_img.infos[self.frr.get_path()] = dict(
            INFO,
            **{"backing-filename": "/lab/base.qcow2"},
        )

    def details(self, image=None, infos=None):
        details = ImageDetails(
            self.frr if image is None else image,
            self.factory,
            self.infos if infos is None else infos,
            self.workspace,
        )
        self.addCleanup(details.panel.destroy)
        return details

    def vm(self, name, private=True, device="hda"):
        vm = self.factory.new_brick("qemu", name)
        vm.set({device: self.frr.get_name(), "private" + device: private})
        return vm


class TestTheFacts(DetailsTestCase):

    def test_the_facts(self):
        facts = cells(self.details().facts)
        self.assertEqual(
            facts[:4],
            [
                ["File", imageinfo.short_path(self.frr.get_path())],
                ["Format", "qcow2, above /lab/base.qcow2"],
                ["Size", "4.0 GB disk, 1.9 GB on disk"],
                ["Snapshots", "virtualbricks"],
            ],
        )
        self.assertEqual(facts[4][0], "Changed")

    def test_while_qemu_img_reads(self):
        qemu_img = LaterQemuImg()
        qemu_img.infos = self.qemu_img.infos
        details = self.details(infos=images.InfoCache(qemu_img))
        self.assertEqual(cells(details.facts)[1], ["Format", "…"])
        qemu_img.answer()
        self.assertEqual(
            cells(details.facts)[1], ["Format", "qcow2, above /lab/base.qcow2"]
        )

    def test_read_once_by_the_list(self):
        self.successResultOf(self.infos.read(self.frr.get_path()))
        self.details()
        self.assertEqual(len(self.qemu_img.calls), 1)

    def test_a_file_that_qemu_img_cant_read(self):
        self.qemu_img.failing.add((self.frr.get_path(),))
        details = self.details()
        self.assertEqual(cells(details.facts)[1], ["Format", "Unknown"])
        # once
        self.assertEqual(len(self.qemu_img.calls), 1)

    def test_a_missing_file(self):
        image = self.factory.new_disk_image("old", "/gone/old.qcow2")
        self.assertEqual(
            cells(self.details(image).facts),
            [["File", "/gone/old.qcow2"], ["State", "The file isn't there"]],
        )
        self.assertEqual(self.qemu_img.calls, [])


class TestTheUses(DetailsTestCase):

    def test_no_disk(self):
        self.assertEqual(cells(self.details().uses), [["No disk uses it."]])

    def test_the_disks(self):
        r1 = self.vm("r1")
        with open(r1.disk("hda").get_cow_path(), "wb") as fp:
            fp.write(b"x" * 5000)
        r2 = self.vm("r2", device="hdb")
        r2.__isrunning__ = lambda: True
        self.vm("vm", private=False)
        self.assertEqual(
            cells(self.details().uses),
            [
                ["r1", "hda", "private copy r1_hda.cow, 8.2 KB", "Stopped"],
                [
                    "r2",
                    "hdb",
                    "private copy r2_hdb.cow, made at the next start",
                    "Running",
                ],
                ["vm", "hda", "the image itself", "Stopped"],
            ],
        )

    def test_no_other_project(self):
        self.assertFalse(self.details().others.get_visible())

    def test_other_projects(self):
        path = self.frr.get_path()
        self.workspace = FakeWorkspace(
            None, ospf=[("router", path)], bgp=[("pc", path)]
        )
        others = self.details().others
        self.assertTrue(others.get_visible())
        self.assertEqual(
            others.get_text(),
            "The projects ospf, as router and bgp, as pc use the same file.",
        )


class TestSaving(DetailsTestCase):

    def test_the_name_and_the_description(self):
        vm = self.vm("r1")
        details = self.details()
        details.name_entry.set_text("frr-debian")
        details.description_view.get_buffer().set_text("FRR on Debian.")
        details.configure_brick(None)
        self.assertEqual(self.frr.get_name(), "frr-debian")
        self.assertEqual(self.frr.get_description(), "FRR on Debian.")
        # the disks follow
        self.assertEqual(vm.config.hda, "frr-debian")

    def test_a_name_in_use(self):
        logger = FakeLogger()
        self.patch(imagedetails, "logger", logger)
        self.factory.new_disk_image("pc", "/lab/pc.qcow2")
        details = self.details()
        details.name_entry.set_text("pc")
        details.description_view.get_buffer().set_text("FRR on Debian.")
        details.configure_brick(None)
        self.assertEqual(self.frr.get_name(), "frr")
        self.assertEqual(logger.levels(), ["error"])
        # the description is saved all the same
        self.assertEqual(self.frr.get_description(), "FRR on Debian.")
        self.assertTrue(os.path.exists(self.frr.get_path()))
