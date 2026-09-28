# -*- test-case-name: virtualbricks.tests.gui.mainwindow.bricks.config.vm.test_machine -*-
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

"""
The Machine section of a virtual machine: the QEMU program, the machine
type and the CPU model, chosen of what the program has, KVM, the CPUs, the
memory, and ACPI.
"""

from virtualbricks.config.settings import get_setting
from virtualbricks.gui.mainwindow.bricks.config.picker import Option, Picker
from virtualbricks.i18n import _
from virtualbricks.programs import qemu_programs


def missing(draft) -> str:
    """What a picker says of a choice its QEMU doesn't have."""

    if draft.qemu is None:
        return ""
    return _("not in QEMU {version}").format(version=draft.qemu.version)


def picker(panel, form, name: str) -> Picker:
    """A picker of name, that sets it in the draft."""

    def chose(value):
        panel.draft.set(name, value)
        panel.on_changed()

    made = Picker(panel.draft.get(name), chose, missing(panel.draft))
    form.row(name, made)
    return made


def build(panel, page) -> None:
    form = page.form
    draft = panel.draft
    form.section(_("Machine"))
    names = qemu_programs(get_setting("qemu_path"))
    form.choice(
        "qemu_program",
        [(name, name.removeprefix("qemu-system-")) for name in names],
        menu=True,
        missing=_("{value}, not installed"),
    )
    panel.machine_picker = picker(panel, form, "machine_type")
    panel.cpu_picker = picker(panel, form, "cpu_model")
    form.switch("use_kvm")
    form.spin("cpus")
    form.spin("memory")
    form.switch("use_kvm_shadow_memory")
    form.spin("kvm_shadow_memory")
    form.switch("acpi")

    def fill():
        info = draft.qemu
        machines = [Option("", _("The default"))]
        cpus = [Option("", _("The default"))]
        if info is not None:
            machines = [Option("", _("The default"), info.default_machine)]
            machines += [
                Option(entry.name, entry.name, entry.description)
                for entry in info.machines
            ]
            cpus += [
                Option(entry.name, entry.name, entry.description)
                for entry in info.cpus
            ]
        for made, options in (
            (panel.machine_picker, machines),
            (panel.cpu_picker, cpus),
        ):
            made.missing = missing(draft)
            made.set_options(options)

    panel.fillers.append(fill)
    fill()
