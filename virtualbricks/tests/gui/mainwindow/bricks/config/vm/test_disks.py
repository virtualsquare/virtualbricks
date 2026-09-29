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

"""The disks of a machine: their rows, their menu, Add Disk, and what OK gives."""

import os

from virtualbricks.bricks.virtualmachine import VirtualMachineDraft
from virtualbricks.config import images
from virtualbricks.config.workspace import OpenProject
from virtualbricks.tests.config.test_images import INFO, FakeQemuImg
from virtualbricks.tests.gui import GuiTestCase, has_display, untranslated

if has_display:
    from gi.repository import GLib

    from virtualbricks.gui.mainwindow.bricks.config.vm import disks
    from virtualbricks.gui.mainwindow.bricks.config.vm.disks import (
        DisksSection,
    )


class DisksTestCase(GuiTestCase):

    def setUp(self):
        super().setUp()
        untranslated(self)
        self.manager.current = OpenProject(self.folder("lab"), None)
        self.qemu_img = FakeQemuImg()
        self.frr = self.image("frr")
        self.pc = self.image("pc")
        for image in (self.frr, self.pc):
            self.qemu_img.infos[image.get_path()] = INFO
        self.r1 = self.factory.new_brick("qemu", "r1")
        self.r1.update_config(
            {
                "hda_image": "frr",
                "hda_private": True,
                "hdc_image": "pc",
                "hdc_private": False,
            }
        )
        self.section = self.make()

    def make(self):
        section = DisksSection(
            self.r1, self.factory, images.InfoCache(self.qemu_img)
        )
        self.addCleanup(section.destroy)
        return section

    def devices(self):
        return [row.device for row in self.sorted_rows()]

    def sorted_rows(self):
        rows = self.section.list.get_children()
        return sorted(rows, key=lambda row: row.get_index())

    def add_items(self):
        menu = self.section.add_menu
        return [
            menu.get_item_attribute_value(i, "label").unpack()
            for i in range(menu.get_n_items())
        ]


class TestTheRows(DisksTestCase):

    def test_the_disks_it_has(self):
        self.assertEqual(self.devices(), ["hda", "hdc"])
        hda, hdc = self.sorted_rows()
        self.assertIs(hda.image, self.frr)
        self.assertTrue(hda.private)
        self.assertEqual(hda.mode_combo.get_active_id(), disks.PRIVATE)
        self.assertIs(hdc.image, self.pc)
        self.assertFalse(hdc.private)
        self.assertEqual(hdc.picker.name_label.get_text(), "pc")

    def test_what_the_mode_does(self):
        hda, hdc = self.sorted_rows()
        self.assertEqual(
            hda.line.get_text(),
            "r1's changes will be kept in r1_hda.cow, made at the next start;"
            " frr stays as it is.",
        )
        self.assertEqual(
            hdc.line.get_text(),
            "r1 writes into pc; while r1 runs, no other machine can use it.",
        )
        hdc.mode_combo.set_active_id(disks.PRIVATE)
        self.assertIn("r1_hdc.cow", hdc.line.get_text())

    def test_a_private_copy_made(self):
        with open(self.r1.disk("hda").get_cow_path(), "wb") as fp:
            fp.write(b"x" * 5000)
        hda = self.section.row("hda")
        hda.update()
        self.assertIn(
            "r1_hda.cow, 8.2 KB, in the project", hda.line.get_text()
        )
        # another image: the copy is set aside at the next start
        hda.picker.choose(self.pc)
        self.assertEqual(
            hda.line.get_text(),
            "r1_hda.cow keeps r1's changes to frr: the next start sets it"
            " aside and begins again from pc.",
        )

    def test_no_disk(self):
        self.r1.update_config({"hda_image": "", "hdc_image": ""})
        self.section = self.make()
        self.assertEqual(self.devices(), [])
        self.assertEqual(len(self.add_items()), 7)


class TestTheMenuOfADisk(DisksTestCase):

    def test_show_in_files(self):
        shown = []
        self.patch(
            disks, "show_in_files", lambda parent, path: shown.append(path)
        )
        hda = self.section.row("hda")
        self.assertTrue(hda.actions.get_action_enabled("show"))
        hda.actions.activate_action("show", None)
        self.assertEqual(shown, [self.frr.get_path()])
        hda.picker.choose(None)
        self.assertFalse(hda.actions.get_action_enabled("show"))

    def test_remove_disk(self):
        self.section.row("hda").actions.activate_action("remove", None)
        self.assertEqual(self.devices(), ["hdc"])
        self.assertIn("hda", self.add_items())
        # nothing changes before OK
        self.assertIs(self.r1.disk("hda").image, self.frr)


class TestAddDisk(DisksTestCase):

    def test_the_free_devices(self):
        self.assertEqual(
            self.add_items(), ["hdb", "hdd", "fda", "fdb", "mtdblock"]
        )

    def test_add(self):
        self.section.add_actions.activate_action(
            "add", GLib.Variant.new_string("hdb")
        )
        self.assertEqual(self.devices(), ["hda", "hdb", "hdc"])
        hdb = self.section.row("hdb")
        self.assertIsNone(hdb.image)
        self.assertTrue(hdb.private)
        self.assertEqual(
            hdb.line.get_text(), "No image: r1 starts without this disk."
        )
        self.assertNotIn("hdb", self.add_items())

    def test_all_the_devices(self):
        for device in self.section.free():
            self.section.add_disk(device)
        self.assertFalse(self.section.add_button.get_sensitive())
        self.section.remove_disk("fda")
        self.assertTrue(self.section.add_button.get_sensitive())
        self.assertEqual(self.add_items(), ["fda"])

    def test_remove_a_disk_it_has_not(self):
        self.section.remove_disk("fdb")
        self.assertEqual(self.devices(), ["hda", "hdc"])


class TestTheDraft(DisksTestCase):

    def test_to_the_draft(self):
        calls = []
        section = DisksSection(
            self.r1,
            self.factory,
            images.InfoCache(self.qemu_img),
            changed=lambda: calls.append("changed"),
        )
        self.addCleanup(section.destroy)
        section.row("hda").picker.choose(self.pc)
        section.row("hdc").mode_combo.set_active_id(disks.PRIVATE)
        section.add_disk("hdb").picker.choose(self.frr)
        section.remove_disk("hdc")
        self.assertEqual(calls, ["changed"] * 5)
        draft = VirtualMachineDraft(self.r1)
        section.to_draft(draft)
        self.assertEqual(
            [
                (draft.get(f"{device}_image"), draft.get(f"{device}_private"))
                for device in ("hda", "hdb", "hdc")
            ],
            # a disk removed keeps its mode, and loses its image
            [("pc", True), ("frr", True), ("", False)],
        )
        # the machine waits for OK
        self.assertIs(self.r1.disk("hda").image, self.frr)

    def test_without_a_callback(self):
        self.section.add_disk("hdb")
        self.assertIsNone(self.section.changed)


class FakeDialog:
    def __init__(self, shown, name, *args):
        self.shown = shown
        self.name = name
        self.args = args
        self.on_done = None
        self.on_saved = None

    def show(self, parent):
        self.shown.append((self.name, self.args, parent))


class TestTheChanges(DisksTestCase):

    def setUp(self):
        super().setUp()
        self.copy = self.r1.disk("hda").get_cow_path()
        with open(self.copy, "wb") as fp:
            fp.write(b"x" * 5000)
        self.hda = self.section.row("hda")
        self.hda.update()
        self.shown = []
        for name in ("SaveImageDialog", "MergeDialog", "StartOverDialog"):
            self.patch(
                disks, name, lambda *a, n=name: FakeDialog(self.shown, n, *a)
            )

    def items(self, row):
        found = []
        for i in range(row.menu.get_n_items()):
            section = row.menu.get_item_link(i, "section")
            for j in range(section.get_n_items()):
                label = section.get_item_attribute_value(j, "label").unpack()
                action = section.get_item_attribute_value(j, "action")
                name = action.unpack().partition(".")[2]
                found.append((label, row.actions.get_action_enabled(name)))
        return found

    def test_the_menu(self):
        self.assertEqual(
            self.items(self.hda),
            [
                ("Save as a New Image…", True),
                ("Merge into frr…", True),
                ("Start Over from frr…", True),
                ("Show in Files", True),
                ("Remove Disk", True),
            ],
        )

    def test_only_as_saved(self):
        # the image chosen isn't the disk's yet
        self.hda.picker.choose(self.pc)
        self.assertEqual(
            [enabled for _label, enabled in self.items(self.hda)][:3],
            [False, False, False],
        )
        self.assertEqual(self.items(self.hda)[1][0], "Merge into pc…")
        self.hda.picker.choose(self.frr)
        self.hda.mode_combo.set_active_id(disks.ITSELF)
        self.assertFalse(self.hda.keeps_changes())

    def test_no_changes_yet(self):
        # hdc writes into its image; a new copy isn't made yet
        self.assertFalse(self.section.row("hdc").keeps_changes())
        self.hda.picker.choose(self.pc)
        self.hda.picker.choose(self.frr)
        self.assertTrue(self.hda.keeps_changes())
        os.remove(self.copy)
        self.hda.update()
        self.assertFalse(self.hda.keeps_changes())

    def test_save(self):
        self.hda.actions.activate_action("save", None)
        ((name, args, parent),) = self.shown
        self.assertEqual(name, "SaveImageDialog")
        self.assertEqual(args, (self.factory, self.r1, "hda"))
        dialog = self.hda.save()
        # the row follows the disk
        dialog.on_saved(self.pc, True)
        self.assertIs(self.hda.image, self.pc)
        dialog.on_saved(self.frr, False)
        self.assertIs(self.hda.image, self.pc)
        self.assertEqual(dialog.on_done, self.hda.update)

    def test_merge(self):
        self.hda.actions.activate_action("merge", None)
        self.assertEqual(
            self.shown[0][:2], ("MergeDialog", (self.factory, self.r1, "hda"))
        )
        dialog = self.hda.merge()
        dialog.on_saved(self.pc, True)
        self.assertIs(self.hda.image, self.pc)

    def test_start_over(self):
        self.hda.actions.activate_action("start-over", None)
        self.assertEqual(
            self.shown[0][:2], ("StartOverDialog", (self.r1, "hda"))
        )
        self.assertEqual(self.hda.start_over().on_done, self.hda.update)
