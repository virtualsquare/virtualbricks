# -*- test-case-name: virtualbricks.tests.gui.mainwindow.bricks.config.test_tunnelcconfig -*-
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
The panel of a tunnel client: the switch at its end, the server it connects
to, its ports and its password.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from virtualbricks.gui.mainwindow.bricks.config.panel import Panel
from virtualbricks.i18n import _

if TYPE_CHECKING:  # pragma: no cover
    from virtualbricks.gui.form import Form


class TunnelConnectPanel(Panel):
    """The settings of the client end of a tunnel."""

    def build(self, form: Form) -> None:
        form.section(_("Connection"))
        form.socket(
            0, _("Plugged into"), _("The switch at this end of the tunnel")
        )
        form.section(_("Tunnel"))
        form.entry("server_host")
        form.spin("server_port")
        form.spin("local_port")
        form.entry("password", secret=True)
