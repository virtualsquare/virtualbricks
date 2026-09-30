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

"""The panel of a tunnel client."""

from virtualbricks.tests.gui import GuiTestCase, has_display, untranslated

if has_display:
    from virtualbricks.gui.mainwindow.bricks.config import new_panel
    from virtualbricks.gui.mainwindow.bricks.config.tunnelcconfig import (
        TunnelConnectPanel,
    )


class TestTheTunnelClientPanel(GuiTestCase):

    def test_its_rows(self):
        untranslated(self)
        tunnel = self.factory.new_brick("tunnelconnect", "tc1")
        panel = new_panel(tunnel)
        self.addCleanup(panel.widget.destroy)
        self.assertIsInstance(panel, TunnelConnectPanel)
        rows = panel.form.rows
        self.assertEqual(
            list(rows),
            ["plug0", "server_host", "server_port", "local_port", "password"],
        )
        self.assertEqual(
            [row.title.get_text() for row in rows.values()],
            [
                "Plugged into",
                "Server",
                "Server port",
                "Local port",
                "Password",
            ],
        )
        self.assertEqual(
            rows["server_host"].problem.get_text(),
            "Without a server, tc1 can't start",
        )
        rows["server_host"].control.set_text("lab.example.org")
        rows["local_port"].control.set_value(10000)
        self.assertEqual(
            panel.draft.changes(),
            {"server_host": "lab.example.org", "local_port": 10000},
        )
        self.assertFalse(rows["server_host"].problem.get_visible())
