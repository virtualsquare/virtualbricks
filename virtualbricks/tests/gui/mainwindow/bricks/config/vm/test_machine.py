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

"""The Machine section: the program, the pickers of its QEMU, the rest."""

import os

from virtualbricks import engine
from virtualbricks.programs import qemu_programs
from virtualbricks.tests.gui.mainwindow.bricks.config.vm.test_panel import (
    MachinePanelTestCase,
)


class TestTheMachineSection(MachinePanelTestCase):

    def prepare(self):
        # the QEMU programs that the engine of the window finds
        self.patch(
            engine,
            "qemu_programs",
            lambda folder, used: ["qemu-system-i386", "qemu-system-x86_64"],
        )
        self.vm.update_config(
            {"machine_type": "pc-i440fx-jammy", "cpu_model": "max"}
        )

    def test_the_programs(self):
        program = self.panel.rows["qemu_program"].control
        self.assertEqual(
            [tuple(row) for row in program.get_model()],
            [("i386", "qemu-system-i386"), ("x86_64", "qemu-system-x86_64")],
        )
        self.assertEqual(program.get_active_id(), "qemu-system-i386")

    def test_the_pickers(self):
        machines = self.panel.machine_picker
        self.assertEqual(machines.name.get_text(), "pc-i440fx-jammy")
        self.assertEqual(machines.words.get_text(), "not in QEMU 10.0.13")
        first = machines.list.get_children()[1].option
        self.assertEqual((first.value, first.name), ("", "The default"))
        self.assertEqual(first.description, "pc-i440fx-10.0")
        cpus = self.panel.cpu_picker
        self.assertEqual(cpus.name.get_text(), "max")
        machines.choose("q35")
        self.assertEqual(self.panel.draft.get("machine_type"), "q35")
        self.assertEqual(self.calls[-1], self.panel)
        self.assertFalse(self.panel.rows["machine_type"].problem.get_visible())

    def test_before_the_answers(self):
        self.panel.draft.qemu = None
        self.panel.fill()
        machines = self.panel.machine_picker
        self.assertEqual(machines.words.get_text(), "")
        self.assertEqual(
            [row.option.name for row in machines.list.get_children()],
            ["pc-i440fx-jammy", "The default"],
        )


class TestALinkToAProgram(MachinePanelTestCase):

    def prepare(self):
        # Debian's qemu-system-amd64, the program of the machine
        folder = os.path.abspath(self.mktemp())
        os.makedirs(folder)
        path = os.path.join(folder, "qemu-system-x86_64")
        with open(path, "w") as fp:
            fp.write("#!/bin/sh\n")
        os.chmod(path, 0o755)
        os.symlink("qemu-system-x86_64", f"{folder}/qemu-system-amd64")
        self.patch(os, "environ", dict(os.environ, PATH=""))
        self.patch(
            engine,
            "qemu_programs",
            lambda _, used: qemu_programs(folder, used),
        )
        self.vm.update_config({"qemu_program": "qemu-system-amd64"})

    def test_it_stays(self):
        program = self.panel.rows["qemu_program"].control
        self.assertEqual(
            [tuple(row) for row in program.get_model()],
            [("amd64", "qemu-system-amd64"), ("x86_64", "qemu-system-x86_64")],
        )
        self.assertEqual(program.get_active_id(), "qemu-system-amd64")
