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


"""The library of the disk images."""

from virtualbricks.tests import FakeLogger
from virtualbricks.tests.gui import GuiTestCase, has_display

if has_display:

    from virtualbricks.gui.windows import disklibrary


class TestDiskLibrary(GuiTestCase):

    def setUp(self):
        super().setUp()
        self.logger = FakeLogger()
        self.patch(disklibrary, "logger", self.logger)
        self.window = disklibrary.DisksLibraryWindow(self.factory)
        self.addCleanup(self.window.get_root_widget().destroy)

    def test_rename_updates_the_disks(self):
        image = self.image("deb")
        vm = self.factory.new_brick("qemu", "vm")
        vm.disk("hda").set_image(image)
        self.window._show_edit_screen(image)
        self.window.name_entry.set_text("debian")
        self.window.on_save_button_clicked(None)
        self.assertIs(self.factory.get_image_by_name("debian"), image)
        self.assertIsNone(self.factory.get_image_by_name("deb"))
        self.assertEqual(vm.config.hda, "debian")
        self.assertIsNone(self.window._disk_image)

    def test_invalid_name(self):
        image = self.image("deb")
        self.window._show_edit_screen(image)
        self.window.name_entry.set_text("1 bad")
        self.window.on_save_button_clicked(None)
        self.assertEqual(image.get_name(), "deb")
        self.assertEqual(self.logger.levels(), ["error"])
        # the form stays open to fix the name
        self.assertIs(self.window._disk_image, image)
