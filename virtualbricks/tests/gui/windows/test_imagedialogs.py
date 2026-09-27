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

"""Remove an image, maybe with its file; find the file of an image."""

import os

from virtualbricks.config.images import DiskUse
from virtualbricks.config.workspace import OpenProject
from virtualbricks.tests import FakeLogger, FakeTrash
from virtualbricks.tests.config.test_images import INFO, FakeQemuImg
from virtualbricks.tests.gui import GuiTestCase, has_display, untranslated

if has_display:
    from gi.repository import Gtk

    from virtualbricks.gui import imageinfo
    from virtualbricks.gui.windows import imagedialogs
    from virtualbricks.gui.windows.imagedialogs import (
        FindFileDialog,
        RemoveImageDialog,
        disks_words,
        show_in_files,
    )


class FakeWorkspace:
    """A workspace, its trash, and the projects other than the open one."""

    def __init__(self, path, trasher=None, others=()):
        self.path = path
        self.trasher = trasher
        self.current = None
        self.others = others

    def summaries(self):
        return self.others


class FakeVM:
    def __init__(self, name):
        self.name = name

    def get_name(self):
        return self.name


def texts(dialog):
    return [
        child.get_text()
        for child in dialog.get_content_area().get_children()
        if isinstance(child, Gtk.Label)
    ]


class DialogTestCase(GuiTestCase):

    def setUp(self):
        super().setUp()
        untranslated(self)
        self.logger = FakeLogger()
        self.patch(imagedialogs, "logger", self.logger)
        self.trash = FakeTrash()
        self.workspace = FakeWorkspace(self.folder("workspace"), self.trash)
        self.vimages = self.folder(os.path.join("workspace", "vimages"))
        # the private copies are in the open project
        self.manager.current = OpenProject(
            self.folder(os.path.join("workspace", "lab")), None
        )

    def file(self, folder, name="frr.qcow2", data=b"disk"):
        path = os.path.join(folder, name)
        with open(path, "wb") as fp:
            fp.write(data)
        return path

    def vm(self, name, image, private=True):
        vm = self.factory.new_brick("qemu", name)
        vm.set({"hda": image.get_name(), "privatehda": private})
        return vm


class TestShowInFiles(DialogTestCase):

    def test_the_folder(self):
        shown = []
        self.patch(
            imagedialogs.Gtk,
            "show_uri_on_window",
            lambda parent, uri, time: shown.append((parent, uri)),
        )
        show_in_files(None, "/lab/images/frr.qcow2")
        self.assertEqual(shown, [(None, "file:///lab/images")])

    def test_no_file_manager(self):
        def fail(parent, uri, time):
            raise RuntimeError("no handler")

        self.patch(imagedialogs.Gtk, "show_uri_on_window", fail)
        show_in_files(None, "/lab/images/frr.qcow2")
        self.assertEqual(
            self.logger.formatted(), ["Cannot show /lab/images: no handler"]
        )


class TestDisksWords(DialogTestCase):

    def test_words(self):
        self.assertEqual(disks_words([]), "No disk uses it.")
        uses = [
            DiskUse(FakeVM("r1"), "hda", True, None, None, False),
            DiskUse(FakeVM("vm"), "hdb", False, None, None, False),
        ]
        self.assertEqual(
            disks_words(uses),
            "The disks r1 (hda) and vm (hdb) will have no image."
            " The private copy stays.",
        )
        self.assertEqual(
            disks_words(uses[1:]), "The disk vm (hdb) will have no image."
        )


class TestRemove(DialogTestCase):

    def dialog(self, image):
        dialog = RemoveImageDialog(self.factory, image, self.workspace)
        self.addCleanup(dialog.dialog.destroy)
        return dialog

    def test_the_disks_lose_the_image(self):
        image = self.factory.new_disk_image("frr", self.file(self.vimages))
        vm = self.vm("r1", image)
        dialog = self.dialog(image)
        self.assertIn(
            "The disk r1 (hda) will have no image. The private copy stays.",
            texts(dialog.dialog),
        )
        dialog.dialog.response(Gtk.ResponseType.OK)
        self.assertIsNone(self.factory.get_image_by_name("frr"))
        self.assertIsNone(vm.disk("hda").image)
        # the file stays unless asked
        self.assertTrue(os.path.exists(image.get_path()))

    def test_the_file_to_the_trash(self):
        image = self.factory.new_disk_image("frr", self.file(self.vimages))
        dialog = self.dialog(image)
        self.assertEqual(
            dialog.file_check.get_label(),
            "Also move the file to the trash (4.1 KB)",
        )
        dialog.file_check.set_active(True)
        dialog.dialog.response(Gtk.ResponseType.OK)
        self.assertEqual(self.trash.trashed, [image.get_path()])

    def test_no_trash(self):
        self.workspace.trasher = None
        image = self.factory.new_disk_image("frr", self.file(self.vimages))
        dialog = self.dialog(image)
        self.assertIn("there is no trash", dialog.file_check.get_label())
        dialog.file_check.set_active(True)
        dialog.remove()
        self.assertFalse(os.path.exists(image.get_path()))

    def test_the_trash_fails(self):
        self.trash.error = OSError(13, "Permission denied")
        image = self.factory.new_disk_image("frr", self.file(self.vimages))
        dialog = self.dialog(image)
        dialog.file_check.set_active(True)
        dialog.remove()
        self.assertIsNone(self.factory.get_image_by_name("frr"))
        self.assertEqual(self.logger.levels(), ["error"])

    def test_a_file_outside_the_image_folder(self):
        path = self.file(self.folder("lab"))
        image = self.factory.new_disk_image("frr", path)
        dialog = self.dialog(image)
        self.assertIsNone(dialog.file_check)
        self.assertIn(
            f"The file stays: {imageinfo.short_path(path)}",
            texts(dialog.dialog),
        )

    def test_a_file_that_other_projects_use(self):
        from virtualbricks.tests.config.test_images import FakeWorkspace

        path = self.file(self.vimages)
        others = FakeWorkspace(
            None, ospf=[("router", path)], bgp=[("a", path), ("b", path)]
        )
        self.workspace.others = others.summaries()
        image = self.factory.new_disk_image("frr", path)
        dialog = self.dialog(image)
        self.assertIsNone(dialog.file_check)
        self.assertIn(
            "The projects bgp and ospf use the file too: it stays.",
            texts(dialog.dialog),
        )

    def test_cancel(self):
        image = self.factory.new_disk_image("frr", self.file(self.vimages))
        dialog = self.dialog(image)
        dialog.dialog.response(Gtk.ResponseType.CANCEL)
        self.assertIs(self.factory.get_image_by_name("frr"), image)


class TestFindFile(DialogTestCase):

    def setUp(self):
        super().setUp()
        self.qemu_img = FakeQemuImg()
        self.image = self.factory.new_disk_image("frr", "/gone/frr.qcow2")

    def dialog(self):
        dialog = FindFileDialog(
            self.factory, self.image, self.workspace, self.qemu_img
        )
        self.addCleanup(dialog.dialog.destroy)
        return dialog

    def test_a_file_to_choose(self):
        dialog = self.dialog()
        self.assertIsNone(dialog.chosen)
        self.assertFalse(dialog.use_button.get_sensitive())
        self.assertFalse(dialog.error_label.get_visible())
        self.assertIn("/gone/frr.qcow2 isn't there.", texts(dialog.dialog))
        dialog.dialog.response(Gtk.ResponseType.OK)
        self.assertEqual(self.qemu_img.calls, [])

    def test_the_file_in_the_image_folder(self):
        path = self.file(self.vimages)
        dialog = self.dialog()
        self.assertEqual(dialog.chosen, path)
        self.assertTrue(dialog.use_button.get_sensitive())
        self.assertIn(
            "The image folder has a file of the same name.",
            texts(dialog.dialog),
        )

    def test_show(self):
        parent = Gtk.Window()
        self.addCleanup(parent.destroy)
        dialog = self.dialog()
        dialog.show(parent)
        self.assertIs(dialog.get_root_widget(), dialog.dialog)
        self.assertIs(dialog.dialog.get_transient_for(), parent)
        self.assertTrue(dialog.dialog.get_visible())

    def test_use_the_file(self):
        path = self.file(self.folder("lab"))
        self.qemu_img.infos[path] = INFO
        dialog = self.dialog()
        dialog.choose(path)
        self.assertTrue(dialog.use_button.get_sensitive())
        dialog.dialog.response(Gtk.ResponseType.OK)
        self.assertEqual(self.image.get_path(), path)

    def test_a_file_that_cant_be_used(self):
        path = self.file(self.folder("lab"))
        self.qemu_img.failing.add((path,))
        dialog = self.dialog()
        dialog.choose(path)
        # the dialog says why
        dialog.use()
        self.assertEqual(self.image.get_path(), "/gone/frr.qcow2")
        self.assertTrue(dialog.error_label.get_visible())
        self.assertTrue(dialog.use_button.get_sensitive())

    def test_cancel(self):
        dialog = self.dialog()
        destroyed = []
        dialog.dialog.connect("destroy", destroyed.append)
        dialog.dialog.response(Gtk.ResponseType.CANCEL)
        self.assertEqual(len(destroyed), 1)
