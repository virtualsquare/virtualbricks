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

"""The panel of a tunnel server."""

from virtualbricks.tests.gui import GuiTestCase, has_display, untranslated

if has_display:
    from virtualbricks.gui.mainwindow.bricks.config import new_panel
    from virtualbricks.gui.mainwindow.bricks.config.tunnellconfig import (
        TunnelListenPanel,
    )


class TestTheTunnelServerPanel(GuiTestCase):

    def test_its_rows(self):
        untranslated(self)
        switch = self.factory.new_brick("switch", "sw1")
        tunnel = self.factory.new_brick("tunnell", "tl1")
        tunnel.plugs[0].connect(switch.socks[0])
        tunnel.set({"password": "s3cret"})
        panel = new_panel(tunnel)
        self.addCleanup(panel.widget.destroy)
        self.assertIsInstance(panel, TunnelListenPanel)
        rows = panel.form.rows
        self.assertEqual(list(rows), ["plug0", "listen_port", "password"])
        self.assertEqual(
            [row.title.get_text() for row in rows.values()],
            ["Plugged into", "Port", "Password"],
        )
        self.assertEqual(rows["plug0"].control.get_active_id(), "0")
        self.assertEqual(rows["listen_port"].control.get_value(), 7667)
        self.assertEqual(rows["listen_port"].control.get_range(), (1, 65535))
        password = rows["password"].control
        self.assertEqual(password.get_text(), "s3cret")
        self.assertFalse(password.get_visibility())
        rows["listen_port"].control.set_value(7000)
        self.assertEqual(panel.draft.changes(), {"listen_port": 7000})
