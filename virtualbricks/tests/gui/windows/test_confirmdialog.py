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

"""Removing a disk image: what the question says, and what Yes does."""

from virtualbricks.config.workspace import OpenProject
from virtualbricks.tests.gui import GuiTestCase, has_display

if has_display:
    from gi.repository import Gtk

    from virtualbricks.gui.windows.confirmdialog import (
        RemoveImageConfirmDialog,
    )


class TestRemoveImage(GuiTestCase):

    def setUp(self):
        super().setUp()
        self.manager.current = OpenProject(self.folder("lab"), None)
        self.frr = self.image("frr")

    def vm(self, name, device="hda", private=True):
        vm = self.factory.new_brick("qemu", name)
        vm.set({device: "frr", "private" + device: private})
        return vm

    def dialog(self):
        dialog = RemoveImageConfirmDialog(self.factory, self.frr)
        self.addCleanup(dialog.dialog.destroy)
        return dialog

    def words(self, dialog):
        return (
            dialog.primary_label.get_text(),
            dialog.secondary_label.get_text(),
        )

    def test_no_disk(self):
        self.assertEqual(
            self.words(self.dialog()),
            (
                "Remove the image frr?",
                f"No disk uses it.\n\nThe file stays: {self.frr.get_path()}",
            ),
        )

    def test_a_disk(self):
        self.vm("r1")
        self.assertEqual(
            self.words(self.dialog())[1],
            "The disk r1 (hda) will have no image. The private copy stays."
            f"\n\nThe file stays: {self.frr.get_path()}",
        )

    def test_a_disk_that_writes_the_image(self):
        # no private copy to speak of
        self.vm("vm", "hdb", private=False)
        self.assertEqual(
            self.words(self.dialog())[1],
            "The disk vm (hdb) will have no image."
            f"\n\nThe file stays: {self.frr.get_path()}",
        )

    def test_disks(self):
        self.vm("r1")
        self.vm("r2")
        self.vm("vm", "hdb", private=False)
        self.assertEqual(
            self.words(self.dialog())[1],
            "The disks r1 (hda), r2 (hda) and vm (hdb) will have no image."
            " The private copies stay."
            f"\n\nThe file stays: {self.frr.get_path()}",
        )

    def test_yes(self):
        r1 = self.vm("r1")
        vm = self.vm("vm", "hdb", private=False)
        changes = []
        r1.changed.connect(changes.append)
        self.dialog().dialog.response(Gtk.ResponseType.YES)
        self.assertIsNone(self.factory.get_image_by_name("frr"))
        self.assertEqual((r1.config.hda, vm.config.hdb), ("", ""))
        # the machines tell that they changed
        self.assertEqual(changes, [r1])

    def test_no(self):
        r1 = self.vm("r1")
        dialog = self.dialog()
        destroyed = []
        dialog.dialog.connect("destroy", destroyed.append)
        dialog.dialog.response(Gtk.ResponseType.NO)
        self.assertIs(self.factory.get_image_by_name("frr"), self.frr)
        self.assertEqual(r1.config.hda, "frr")
        self.assertEqual(len(destroyed), 1)
