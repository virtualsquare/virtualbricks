# -*- test-case-name: virtualbricks.tests.gui.mainwindow.bricks.config.vm.test_media -*-
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
The Disks, and the CD-ROM and boot, sections of a virtual machine.

The disks are the section of :mod:`.disks`, which writes each change into
the draft: the image of each device, by name, and its mode.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from virtualbricks.bricks.virtualmachine import DISK_DEVICES
from virtualbricks.gui.mainwindow.bricks.config.vm.disks import DisksSection
from virtualbricks.i18n import _

if TYPE_CHECKING:  # pragma: no cover
    from virtualbricks.gui.mainwindow.bricks.config.vm.panel import (
        Page,
        VirtualMachinePanel,
    )

# What -boot takes, and its words.
BOOT = (
    ("", _("The default")),
    ("c", _("The first disk")),
    ("d", _("The CD-ROM")),
    ("a", _("The floppy")),
    ("n", _("The network")),
)


def build_disks(panel: VirtualMachinePanel, page: Page) -> None:
    form = page.form
    vm = panel.draft.brick
    # the main window shows the Images tab
    manage = getattr(panel.gui, "show_images", None)

    def changed() -> None:
        section.to_draft(panel.draft)
        panel.on_changed()

    section = DisksSection(vm, panel.engine, manage=manage, changed=changed)
    panel.disks = section
    form.add(section)
    form.section(_("Changes"))
    form.switch("forget_disk_changes")
    form.switch("virtio_disks")
    page.keys.update(
        f"{device}_{what}"
        for device in DISK_DEVICES
        for what in ("image", "private")
    )


def build_cdrom(panel: VirtualMachinePanel, page: Page) -> None:
    form = page.form
    form.section(_("CD-ROM"))
    form.choice(
        "cdrom",
        [
            ("none", _("Nothing")),
            ("image", _("An image")),
            ("device", _("A drive")),
        ],
    )
    form.path("cdrom_image", _("The image of the CD-ROM"))
    form.entry("cdrom_device")
    form.section(_("Boot"))
    form.choice("boot_order", BOOT, menu=True, missing="{value}")
