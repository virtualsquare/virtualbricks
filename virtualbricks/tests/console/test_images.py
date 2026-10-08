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

"""The commands of the disk images."""

import os

from virtualbricks.console.dispatch import run
from virtualbricks.tests.console import ConsoleTestCase


class TestImages(ConsoleTestCase):

    def setUp(self):
        super().setUp()
        self.factory.runtime_dir = "/run/vb"
        self.path = os.path.abspath(self.mktemp())
        open(self.path, "w").close()
        self.vm = self.factory.new_brick("qemu", "vm1")

    def test_add_and_list(self):
        self.assertEqual(self.run_line("image list"), ["No images"])
        self.assertEqual(
            self.run_line(
                f"image add deb {self.path} 'description=Debian 13'"
            ),
            ["deb"],
        )
        self.vm.update_config({"hda_image": "deb"})
        self.assertEqual(
            self.run_line("image list"),
            [
                "NAME  FILE" + " " * (len(self.path) - 2) + "USED BY",
                f"deb   {self.path}  vm1 hda",
            ],
        )
        self.assertEqual(
            self.run_line("image show deb"),
            ["deb", self.path, "Debian 13", "used by vm1 hda"],
        )

    def test_add_from_the_folder_of_the_command(self):
        folder, name = os.path.split(self.path)
        answer = run(
            self.factory, f"image add deb {name}", self.clock(), cwd=folder
        )
        self.assertEqual(self.successResultOf(answer), ["deb"])
        image = self.factory.get_image("deb")
        self.assertEqual(image.path, self.path)

    def test_what_is_wrong(self):
        self.assertEqual(
            self.fails("image add deb /nope.qcow2"), "No file /nope.qcow2"
        )
        self.assertEqual(
            self.fails(f"image add vm1 {self.path}"),
            "vm1 is the name of a brick",
        )
        self.assertEqual(
            self.fails(f"image add deb {self.path} size=2"),
            "An image has no key size: only description",
        )
        self.assertEqual(self.fails("image show deb"), "No image named deb")

    def test_change_and_delete(self):
        self.run_line(f"image add deb {self.path}")
        self.vm.update_config({"hda_image": "deb"})
        self.assertEqual(self.run_line("image set deb description=Other"), [])
        image = self.factory.get_image("deb")
        self.assertEqual(image.description, "Other")
        self.assertEqual(self.run_line("image rename deb debian"), [])
        self.assertEqual(self.vm.config.hda_image, "debian")
        self.assertEqual(
            self.run_line("image delete debian"), ["vm1 hda has no image now"]
        )
        self.assertEqual(self.vm.config.hda_image, "")
