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

"""The Kernel, and the Advanced, sections."""

from virtualbricks.tests.gui.mainwindow.bricks.config.vm.test_panel import (
    MachinePanelTestCase,
)


class TestTheKernelSection(MachinePanelTestCase):

    def test_what_goes_with_the_kernel(self):
        rows = self.panel.rows
        for name in ("kernel", "use_initrd", "initrd", "kernel_command_line"):
            self.assertFalse(rows[name].get_sensitive(), name)
        rows["use_kernel"].control.set_active(True)
        self.assertTrue(rows["kernel"].get_sensitive())
        self.assertFalse(rows["initrd"].get_sensitive())
        self.assertEqual(
            rows["kernel"].problem.get_text(),
            "Choose the kernel, or don't boot one",
        )
        rows["kernel"].title.get_mnemonic_widget().set_text("/boot/vmlinuz")
        self.assertFalse(rows["kernel"].problem.get_visible())
        self.assertFalse(rows["gdb_port"].get_sensitive())
        rows["use_gdb"].control.set_active(True)
        self.assertTrue(rows["gdb_port"].get_sensitive())


class TestTheAdvancedSection(MachinePanelTestCase):

    def test_its_rows(self):
        rows = self.panel.rows
        rows["clock_local_time"].control.set_active(True)
        rows["icon"].title.get_mnemonic_widget().set_text(
            "/usr/share/icons/vm.png"
        )
        self.assertEqual(
            self.panel.draft.changes(),
            {"clock_local_time": True, "icon": "/usr/share/icons/vm.png"},
        )
