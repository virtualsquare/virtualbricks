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

"""The picker of the image of a disk: its button, its list, its Add items."""

from virtualbricks.config import images
from virtualbricks.config.workspace import OpenProject
from virtualbricks.tests.config.test_images import INFO, FakeQemuImg
from virtualbricks.tests.gui import GuiTestCase, has_display, untranslated
from virtualbricks.tests.gui.mainwindow.images.test_tab import LaterQemuImg

if has_display:
    from virtualbricks.gui.mainwindow.bricks.config import imagepicker
    from virtualbricks.gui.mainwindow.bricks.config.imagepicker import (
        ImagePicker,
    )


class FakeDialog:
    def __init__(self, shown, name, factory):
        self.shown = shown
        self.name = name
        self.factory = factory
        self.on_added = None

    def show(self, parent):
        self.shown.append((self.name, parent))


class PickerTestCase(GuiTestCase):

    def setUp(self):
        super().setUp()
        untranslated(self)
        self.manager.current = OpenProject(self.folder("lab"), None)
        self.qemu_img = FakeQemuImg()
        self.infos = images.InfoCache(self.qemu_img)
        self.frr = self.image("frr")
        self.pc = self.image("pc")
        self.old = self.factory.new_disk_image("old", "/gone/old.qcow2")
        for image in (self.frr, self.pc):
            self.qemu_img.infos[image.get_path()] = INFO
        self.r1 = self.vm("r1", self.frr)
        self.managed = []
        self.chosen = []

    def vm(self, name, image, private=True):
        vm = self.factory.new_brick("qemu", name)
        vm.set({"hda_image": image.get_name(), "hda_private": private})
        return vm

    def picker(self, image=None, infos=None):
        picker = ImagePicker(
            self.factory,
            self.r1,
            image,
            self.infos if infos is None else infos,
            lambda: self.managed.append(True),
        )
        picker.connect("chosen", lambda p: self.chosen.append(p.image))
        self.addCleanup(picker.destroy)
        return picker

    def listed(self, picker):
        return [
            option.image
            for option in picker.options()
            if picker._visible(option)
        ]


class TestTheButton(PickerTestCase):

    def test_an_image(self):
        picker = self.picker(self.frr)
        self.assertEqual(picker.name_label.get_text(), "frr")
        self.assertEqual(
            picker.facts_label.get_text(),
            "qcow2 · 4.0 GB disk · 1.9 GB on disk",
        )

    def test_while_qemu_img_reads(self):
        qemu_img = LaterQemuImg()
        qemu_img.infos = self.qemu_img.infos
        picker = self.picker(self.frr, images.InfoCache(qemu_img))
        self.assertEqual(picker.facts_label.get_text(), "")
        qemu_img.answer()
        self.assertIn("4.0 GB disk", picker.facts_label.get_text())

    def test_another_chosen_while_qemu_img_reads(self):
        qemu_img = LaterQemuImg()
        qemu_img.infos = self.qemu_img.infos
        picker = self.picker(self.frr, images.InfoCache(qemu_img))
        picker.choose(None)
        qemu_img.answer()
        self.assertEqual(
            picker.facts_label.get_text(), "Choose an image for this disk"
        )

    def test_no_image(self):
        picker = self.picker()
        self.assertEqual(picker.name_label.get_text(), "No image")
        self.assertEqual(
            picker.facts_label.get_text(), "Choose an image for this disk"
        )

    def test_a_missing_file(self):
        picker = self.picker(self.old)
        self.assertEqual(
            picker.facts_label.get_text(), "/gone/old.qcow2 isn't there"
        )


class TestTheList(PickerTestCase):

    def test_the_images_then_no_image(self):
        self.vm("r2", self.frr)
        self.vm("gw", self.pc, private=False)
        picker = self.picker(self.frr)
        picker.fill()
        options = picker.options()
        self.assertEqual(
            [option.image for option in options],
            [self.frr, self.pc, self.old, None],
        )
        words = [option.words.get_text() for option in options]
        self.assertEqual(
            words,
            [
                "qcow2 · 4.0 GB · r2 uses it",
                "qcow2 · 4.0 GB · gw writes into it",
                "The file isn't on this computer",
                "",
            ],
        )
        # the chosen one has its mark; an image without its file can't be
        self.assertEqual(
            [
                option.get_children()[0].get_children()[0].get_opacity()
                for option in options
            ],
            [1.0, 0.0, 0.0, 0.0],
        )
        self.assertEqual(
            [option.get_sensitive() for option in options],
            [True, True, False, True],
        )

    def test_filled_again(self):
        picker = self.picker(self.frr)
        picker.fill()
        picker.search.set_text("pc")
        self.factory.new_disk_image("new", "/lab/new.qcow2")
        picker.fill()
        self.assertEqual(picker.search.get_text(), "")
        self.assertEqual(len(picker.options()), 5)

    def test_while_qemu_img_reads(self):
        qemu_img = LaterQemuImg()
        qemu_img.infos = self.qemu_img.infos
        picker = self.picker(infos=images.InfoCache(qemu_img))
        picker.fill()
        self.vm("r2", self.pc)
        picker.fill()
        option = picker.options()[1]
        self.assertEqual(option.words.get_text(), "r2 uses it")
        qemu_img.answer()
        self.assertEqual(
            option.words.get_text(), "qcow2 · 4.0 GB · r2 uses it"
        )

    def test_the_search(self):
        picker = self.picker()
        picker.fill()
        picker.search.set_text("FR")
        self.assertEqual(self.listed(picker), [self.frr])
        picker.search.set_text("")
        self.assertEqual(
            self.listed(picker), [self.frr, self.pc, self.old, None]
        )

    def test_choose(self):
        picker = self.picker(self.frr)
        picker.fill()
        picker.list.emit("row-activated", picker.options()[1])
        self.assertIs(picker.image, self.pc)
        self.assertEqual(self.chosen, [self.pc])
        self.assertEqual(picker.name_label.get_text(), "pc")
        picker.list.emit("row-activated", picker.options()[3])
        self.assertEqual(self.chosen, [self.pc, None])


class TestTheAddItems(PickerTestCase):

    def setUp(self):
        super().setUp()
        self.shown = []
        for name in ("ExistingImageDialog", "NewDiskDialog"):
            self.patch(
                imagepicker,
                name,
                lambda factory, n=name: FakeDialog(self.shown, n, factory),
            )

    def test_labels(self):
        picker = self.picker()
        labels = [
            button.get_child().get_children()[1].get_text()
            for button in picker.add_buttons
        ]
        self.assertEqual(
            labels,
            ["Add an Existing Image…", "New Empty Disk…", "Manage Images…"],
        )

    def test_an_existing_image_is_chosen(self):
        picker = self.picker()
        picker.add_buttons[0].clicked()
        dialog = picker.add_existing()
        self.assertEqual(self.shown[0], ("ExistingImageDialog", None))
        self.assertIs(dialog.factory, self.factory)
        dialog.on_added(self.pc)
        self.assertIs(picker.image, self.pc)

    def test_a_new_disk_is_chosen(self):
        picker = self.picker()
        picker.add_buttons[1].clicked()
        dialog = picker.add_new()
        self.assertEqual(self.shown[0], ("NewDiskDialog", None))
        dialog.on_added(self.pc)
        self.assertEqual(self.chosen, [self.pc])

    def test_manage_images(self):
        picker = self.picker()
        picker.add_buttons[2].clicked()
        self.assertEqual(self.managed, [True])
        # without the Images tab
        picker.manage = None
        picker.manage_images()
        self.assertEqual(self.managed, [True])

    def test_in_a_window(self):
        from gi.repository import Gtk

        window = Gtk.Window()
        self.addCleanup(window.destroy)
        picker = self.picker()
        window.add(picker)
        picker.add_existing()
        self.assertEqual(self.shown, [("ExistingImageDialog", window)])
