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

"""The Disks, and the CD-ROM and boot, sections."""

from virtualbricks.config.workspace import OpenProject
from virtualbricks.tests.gui.mainwindow.bricks.config.vm.test_panel import (
    MachinePanelTestCase,
)


class TestTheDisksSection(MachinePanelTestCase):

    def prepare(self):
        self.manager.current = OpenProject(self.folder("lab"), None)
        self.image = self.factory.new_image("deb", "/i/deb.qcow2")
        self.vm.update_config({"hda_image": "deb", "hda_private": True})

    def test_a_change_goes_to_the_draft(self):
        section = self.panel.disks
        self.assertIsNot(section.row("hda"), None)
        section.row("hda").mode_combo.set_active_id("image")
        self.assertEqual(self.panel.draft.changes(), {"hda_private": False})
        section.add_disk("hdb")
        section.remove_disk("hda")
        self.assertEqual(self.panel.draft.get("hda_image"), "")
        self.assertEqual(self.panel.draft.get("hdb_image"), "")
        self.assertTrue(self.panel.draft.get("hdb_private"))
        self.assertEqual(self.vm.config.hda_image, "deb")
        self.assertIn(self.panel, self.calls)

    def test_the_changes(self):
        rows = self.panel.rows
        rows["forget_disk_changes"].control.set_active(True)
        rows["virtio_disks"].control.set_active(True)
        self.assertEqual(
            self.panel.draft.changes(),
            {"forget_disk_changes": True, "virtio_disks": True},
        )
        self.assertTrue(self.panel.page("disks").has("hdc_image"))


class TestTheCdromSection(MachinePanelTestCase):

    def test_its_rows(self):
        rows = self.panel.rows
        buttons = rows["cdrom"].control.get_children()
        self.assertEqual(
            [button.get_label() for button in buttons],
            ["Nothing", "An image", "A drive"],
        )
        self.assertFalse(rows["cdrom_image"].get_sensitive())
        buttons[1].set_active(True)
        self.assertTrue(rows["cdrom_image"].get_sensitive())
        self.assertFalse(rows["cdrom_device"].get_sensitive())
        self.assertEqual(
            rows["cdrom_image"].problem.get_text(),
            "Choose the image of the CD-ROM",
        )
        boot = rows["boot_order"].control
        self.assertEqual(
            [row[0] for row in boot.get_model()],
            [
                "The default",
                "The first disk",
                "The CD-ROM",
                "The floppy",
                "The network",
            ],
        )
        boot.set_active_id("d")
        self.assertEqual(self.panel.draft.get("boot_order"), "d")

    def test_a_boot_order_of_its_own(self):
        self.vm.update_config({"boot_order": "cdn"})
        panel = self.panel.__class__(
            self.panel.draft.__class__(self.vm), self.gui
        )
        self.addCleanup(panel.widget.destroy)
        boot = panel.rows["boot_order"].control
        self.assertEqual(boot.get_active_id(), "cdn")
        self.assertEqual([row[0] for row in boot.get_model()][-1], "cdn")
