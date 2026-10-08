# -*- test-case-name: virtualbricks.tests.gui.mainwindow.bricks.config.vm.test_system -*-
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

"""
The Kernel, and the Advanced, sections of a virtual machine: a kernel to
boot, its ramdisk, its command line and GDB; the clock, the serial port and
the icon.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from virtualbricks.i18n import _

if TYPE_CHECKING:  # pragma: no cover
    from virtualbricks.gui.mainwindow.bricks.config.vm.panel import (
        Page,
        VirtualMachinePanel,
    )


def build_kernel(panel: VirtualMachinePanel, page: Page) -> None:
    form = page.form
    form.section(_("Kernel"))
    form.switch("use_kernel")
    form.path("kernel", _("The kernel to boot"))
    form.switch("use_initrd")
    form.path("initrd", _("The initial ramdisk"))
    form.entry("kernel_command_line")
    form.section(_("Debugging"))
    form.switch("use_gdb")
    form.spin("gdb_port")


def build_advanced(panel: VirtualMachinePanel, page: Page) -> None:
    form = page.form
    form.section(_("Clock and serial port"))
    form.switch("clock_local_time")
    form.switch("clock_drift_fix")
    form.switch("serial_socket")
    form.section(_("Icon"))
    form.path("icon", _("The icon of the machine"))
