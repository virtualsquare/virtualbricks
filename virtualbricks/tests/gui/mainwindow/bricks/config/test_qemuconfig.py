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

"""The programs, machines and CPU models that a machine's panel offers."""

from virtualbricks.tests.gui import GuiTestCase, has_display, untranslated
from virtualbricks.tests.test_programs import recorded_info

if has_display:
    from virtualbricks.gui import widgets
    from virtualbricks.gui.mainwindow.bricks.config.qemuconfig import (
        _chosen,
        cpu_entries,
        machine_entries,
        program_entries,
    )


def listed(entries):
    return [(entry.value, entry.label) for entry in entries]


class TestEntries(GuiTestCase):

    def setUp(self):
        super().setUp()
        untranslated(self)
        self.info = recorded_info("debian-13")

    def test_programs(self):
        names = ["qemu-system-i386", "qemu-system-x86_64"]
        self.assertEqual(
            listed(program_entries(names, "qemu-system-x86_64")),
            [("qemu-system-i386", "i386"), ("qemu-system-x86_64", "x86_64")],
        )

    def test_program_not_installed(self):
        self.assertEqual(
            listed(program_entries(["qemu-system-x86_64"], "qemu-system-arm")),
            [
                ("qemu-system-x86_64", "x86_64"),
                ("qemu-system-arm", "qemu-system-arm, not installed"),
            ],
        )
        self.assertEqual(listed(program_entries([], "")), [])

    def test_machines(self):
        entries = listed(machine_entries(self.info, "q35"))
        self.assertEqual(entries[0], ("", "The default, pc-i440fx-10.0"))
        self.assertIn(
            (
                "q35",
                "q35 Standard PC (Q35 + ICH9, 2009) (alias of pc-q35-10.0)",
            ),
            entries,
        )
        self.assertEqual(len(entries), len(self.info.machines) + 1)

    def test_machine_not_in_this_qemu(self):
        entries = listed(machine_entries(self.info, "pc-q35-11.1"))
        self.assertEqual(
            entries[-1], ("pc-q35-11.1", "pc-q35-11.1, not in this QEMU")
        )

    def test_machines_without_qemu(self):
        self.assertEqual(
            listed(machine_entries(None, "pc")),
            [("", "The default"), ("pc", "pc, not in this QEMU")],
        )
        self.assertEqual(
            listed(machine_entries(None, "")), [("", "The default")]
        )

    def test_cpus(self):
        entries = listed(cpu_entries(self.info, ""))
        self.assertEqual(entries[0], ("", "The default"))
        self.assertIn(("486-v1", "486-v1"), entries)
        self.assertIn(
            ("486", "486 (alias configured by machine type)"), entries
        )
        self.assertEqual(
            listed(cpu_entries(None, "host")),
            [("", "The default"), ("host", "host, not in this QEMU")],
        )

    def test_chosen(self):
        store = widgets.List()
        store.set_properties(value_member="value")
        combo = widgets.ComboBox(model=store)
        self.assertEqual(_chosen(combo, "q35"), "q35")
        store.set_data_source(machine_entries(self.info, "q35"))
        self.assertEqual(_chosen(combo, "q35"), "")
        combo.set_selected_value("q35")
        self.assertEqual(_chosen(combo, "pc"), "q35")
