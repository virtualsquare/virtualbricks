# -*- test-case-name: virtualbricks.tests.gui.mainwindow.bricks.config.test_switchconfig -*-
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
The panel of a switch: its ports, hub mode and fast spanning tree.
"""

from __future__ import annotations

from virtualbricks.gui.form import Form
from virtualbricks.gui.mainwindow.bricks.config.panel import Panel
from virtualbricks.i18n import _


class SwitchPanel(Panel):
    """The settings of a switch."""

    def build(self, form: Form) -> None:
        form.section(_("Ports"))
        form.spin("ports")
        form.switch("hub_mode")
        form.switch("fast_spanning_tree")
