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

"""Add an existing image, and a new empty disk."""

import os

from twisted.internet import defer

from virtualbricks.tests.config.test_images import INFO, FakeQemuImg
from virtualbricks.tests.gui import GuiTestCase, has_display, untranslated

if has_display:
    from gi.repository import Gtk

    from virtualbricks.gui.dialogs import addimage
    from virtualbricks.gui.dialogs.addimage import (
        ExistingImageDialog,
        NewDiskDialog,
        check_name,
        name_from_file,
        read_description,
    )


def text(view):
    buffer = view.get_buffer()
    return buffer.get_text(
        buffer.get_start_iter(), buffer.get_end_iter(), False
    )


class AddTestCase(GuiTestCase):

    def setUp(self):
        super().setUp()
        untranslated(self)
        self.qemu_img = FakeQemuImg()
        self.added = []
        # the copy runs at once
        self.copies = []

        def copy(function, *args):
            self.copies.append(args)
            return defer.maybeDeferred(function, *args)

        self.patch(addimage.threads, "deferToThread", copy)

    def file(self, folder, name, data=b"disk", info=None):
        path = os.path.join(self.folder(folder), name)
        with open(path, "wb") as fp:
            fp.write(data)
        self.qemu_img.infos[path] = INFO if info is None else info
        return path

    def track(self, dialog):
        dialog.on_added = self.added.append
        self.addCleanup(dialog.dialog.destroy)
        return dialog


class TestWords(AddTestCase):

    def test_names(self):
        self.assertIsNone(check_name(self.factory, "frr"))
        self.factory.new_image("frr", "/lab/frr.qcow2")
        self.assertEqual(
            check_name(self.factory, "frr"), "The name “frr” is in use"
        )
        self.assertIsNotNone(check_name(self.factory, ""))

    def test_the_name_of_a_file(self):
        self.assertEqual(name_from_file("/lab/frr debian.qcow2"), "frr_debian")
        self.assertEqual(name_from_file("/lab/frr"), "frr")

    def test_the_description_beside_a_file(self):
        path = self.file("lab", "frr.qcow2")
        self.assertEqual(read_description(path), "")
        with open(path + ".md", "w") as fp:
            fp.write("\nFRR on Debian 12.\n")
        self.assertEqual(read_description(path), "FRR on Debian 12.")
        with open(path + ".md", "wb") as fp:
            fp.write(b"\xff\xfe")
        self.assertEqual(read_description(path), "")


class TestExistingImage(AddTestCase):

    def setUp(self):
        super().setUp()
        self.dialog = self.track(
            ExistingImageDialog(self.factory, qemu_img=self.qemu_img)
        )

    def test_waits_for_a_file(self):
        self.assertFalse(self.dialog.add_button.get_sensitive())
        self.assertFalse(self.dialog.copy_radio.get_visible())
        # nothing to say yet
        for label in (
            self.dialog.file_facts,
            self.dialog.name_message,
            self.dialog.error_label,
        ):
            self.assertFalse(label.get_visible())

    def test_a_file(self):
        path = self.file("lab", "frr debian.qcow2")
        with open(path + ".md", "w") as fp:
            fp.write("FRR on Debian 12.")
        self.dialog.choose(path)
        self.assertEqual(self.qemu_img.calls[0][-1], path)
        self.assertEqual(
            self.dialog.file_facts.get_text(),
            "qcow2 · 4.0 GB disk · 1.9 GB on disk",
        )
        self.assertEqual(self.dialog.name_entry.get_text(), "frr_debian")
        self.assertEqual(
            text(self.dialog.description_view), "FRR on Debian 12."
        )
        self.assertTrue(self.dialog.add_button.get_sensitive())

    def test_keeps_what_was_typed(self):
        self.dialog.name_entry.set_text("router")
        self.dialog.description_view.get_buffer().set_text("Mine.")
        path = self.file("lab", "frr.qcow2")
        with open(path + ".md", "w") as fp:
            fp.write("FRR on Debian 12.")
        self.dialog.choose(path)
        self.assertEqual(self.dialog.name_entry.get_text(), "router")
        self.assertEqual(text(self.dialog.description_view), "Mine.")

    def test_not_a_disk_image(self):
        path = self.file("lab", "notes.txt")
        self.qemu_img.failing.add((path,))
        self.dialog.choose(path)
        self.assertEqual(
            self.dialog.file_facts.get_text(),
            "Not a disk image: qemu-img: info failed",
        )
        self.assertFalse(self.dialog.add_button.get_sensitive())

    def test_a_late_answer(self):
        # the answer about the first file comes after the second is chosen
        first = self.file("lab", "a.qcow2")
        second = self.file("lab", "b.qcow2")
        self.dialog.choose(second)
        self.dialog._read(dict(INFO), first)
        self.dialog._not_read(None, first)
        self.assertEqual(self.dialog.info.format, "qcow2")

    def test_a_name_emptied(self):
        self.dialog.choose(self.file("lab", "frr.qcow2"))
        self.dialog.name_entry.set_text("")
        self.assertFalse(self.dialog.name_message.get_visible())
        self.assertFalse(self.dialog.add_button.get_sensitive())

    def test_a_name_in_use(self):
        self.factory.new_image("frr", "/lab/other.qcow2")
        self.dialog.choose(self.file("lab", "frr.qcow2"))
        self.assertTrue(self.dialog.name_message.get_visible())
        self.assertFalse(self.dialog.add_button.get_sensitive())

    def test_outside_the_workspace_it_copies(self):
        path = self.file("lab", "frr.qcow2")
        self.dialog.choose(path)
        self.assertTrue(self.dialog.copy_radio.get_visible())
        self.assertTrue(self.dialog.copy_radio.get_active())
        self.assertTrue(self.dialog.copies())
        self.dialog.dialog.response(Gtk.ResponseType.OK)
        folder = os.path.join(self.manager.path, "vimages")
        copy = os.path.join(folder, "frr.qcow2")
        self.assertEqual(self.copies, [(path, copy)])
        with open(copy, "rb") as fp:
            self.assertEqual(fp.read(), b"disk")
        image = self.factory.get_image("frr")
        self.assertEqual(image.path, copy)
        self.assertEqual(self.added, [image])

    def test_a_copy_beside_another(self):
        folder = self.folder(os.path.join("workspace", "vimages"))
        open(os.path.join(folder, "frr.qcow2"), "w").close()
        self.dialog.choose(self.file("lab", "frr.qcow2"))
        self.dialog.name_entry.set_text("frr2")
        self.dialog.add()
        self.assertEqual(
            self.factory.get_image("frr2").path,
            os.path.join(folder, "frr-2.qcow2"),
        )

    def test_used_where_it_is(self):
        path = self.file("lab", "frr.qcow2")
        self.dialog.choose(path)
        self.dialog.in_place_radio.set_active(True)
        self.successResultOf(self.dialog.add())
        self.assertEqual(self.copies, [])
        self.assertEqual(self.factory.get_image("frr").path, path)

    def test_above_a_backing_file(self):
        path = self.file(
            "lab", "frr.qcow2", info=dict(INFO, **{"backing-filename": "base"})
        )
        self.dialog.choose(path)
        self.assertFalse(self.dialog.copy_radio.get_sensitive())
        self.assertTrue(self.dialog.in_place_radio.get_active())
        self.assertFalse(self.dialog.copies())
        self.assertIn("above base", self.dialog.file_facts.get_text())

    def test_inside_the_workspace(self):
        path = self.file(os.path.join("workspace", "lab"), "frr.qcow2")
        self.dialog.choose(path)
        self.assertFalse(self.dialog.copy_radio.get_visible())
        self.dialog.add()
        self.assertEqual(self.copies, [])
        self.assertEqual(self.factory.get_image("frr").path, path)

    def test_a_copy_that_fails(self):
        def fail(source, target):
            with open(target, "w") as fp:
                fp.write("half")
            raise OSError(28, "No space left on device")

        self.patch(addimage, "copy_sparse", fail)
        self.dialog.choose(self.file("lab", "frr.qcow2"))
        self.dialog.add()
        folder = os.path.join(self.manager.path, "vimages")
        self.assertEqual(os.listdir(folder), [])
        self.assertIsNone(self.factory.get_image("frr"))
        self.assertIn("No space left", self.dialog.error_label.get_text())
        self.assertTrue(self.dialog.add_button.get_sensitive())
        self.assertEqual(self.added, [])

    def test_cancel(self):
        destroyed = []
        self.dialog.dialog.connect("destroy", destroyed.append)
        self.dialog.dialog.response(Gtk.ResponseType.CANCEL)
        self.assertEqual(len(destroyed), 1)

    def test_show(self):
        parent = Gtk.Window()
        self.addCleanup(parent.destroy)
        self.dialog.show(parent)
        self.assertIs(self.dialog.get_root_widget(), self.dialog.dialog)
        self.assertIs(self.dialog.dialog.get_transient_for(), parent)
        self.assertTrue(self.dialog.dialog.get_visible())

    def test_ok_without_a_file(self):
        self.dialog.dialog.response(Gtk.ResponseType.OK)
        self.assertEqual(self.added, [])


class TestNewDisk(AddTestCase):

    def setUp(self):
        super().setUp()
        self.dialog = self.track(
            NewDiskDialog(self.factory, qemu_img=self.qemu_img)
        )
        self.vimages = os.path.join(self.manager.path, "vimages")

    def test_in_the_image_folder(self):
        self.dialog.name_entry.set_text("scratch disk")
        self.assertEqual(
            self.dialog.target(),
            os.path.join(self.vimages, "scratch_disk.qcow2"),
        )
        self.dialog.format_combo.set_active_id("raw")
        self.assertEqual(
            self.dialog.target(),
            os.path.join(self.vimages, "scratch_disk.raw"),
        )

    def test_waits_for_a_name(self):
        self.assertFalse(self.dialog.create_button.get_sensitive())
        self.assertFalse(self.dialog.error_label.get_visible())
        self.dialog.name_entry.set_text("scratch")
        self.assertTrue(self.dialog.create_button.get_sensitive())

    def test_sizes(self):
        self.assertEqual(self.dialog.size(), 10 * 1000**3)
        self.dialog.size_spin.set_value(3)
        self.dialog.unit_combo.set_active_id("MB")
        # a whole number of sectors
        self.assertEqual(self.dialog.size(), 5860 * 512)

    def test_create(self):
        self.dialog.name_entry.set_text("scratch")
        self.dialog.dialog.response(Gtk.ResponseType.OK)
        path = os.path.join(self.vimages, "scratch.qcow2")
        self.assertEqual(
            self.qemu_img.calls,
            [["create", "-q", "-f", "qcow2", path, str(10 * 1000**3)]],
        )
        image = self.factory.get_image("scratch")
        self.assertEqual(image.path, path)
        self.assertEqual(self.added, [image])

    def test_a_file_there_already(self):
        os.makedirs(self.vimages, exist_ok=True)
        open(os.path.join(self.vimages, "scratch.qcow2"), "w").close()
        self.dialog.name_entry.set_text("scratch")
        self.assertIn("is there already", self.dialog.file_label.get_text())
        self.assertFalse(self.dialog.create_button.get_sensitive())
        self.dialog.dialog.response(Gtk.ResponseType.OK)
        self.assertEqual(self.qemu_img.calls, [])

    def test_create_fails(self):
        self.qemu_img.failing.add(("create", "-q"))
        self.dialog.name_entry.set_text("scratch")
        self.dialog.create()
        self.assertIsNone(self.factory.get_image("scratch"))
        self.assertEqual(
            self.dialog.error_label.get_text(), "qemu-img: create failed"
        )
        self.assertTrue(self.dialog.create_button.get_sensitive())

    def test_cancel(self):
        destroyed = []
        self.dialog.dialog.connect("destroy", destroyed.append)
        self.dialog.dialog.response(Gtk.ResponseType.CANCEL)
        self.assertEqual(len(destroyed), 1)
