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

"""The panel of a capture."""

from virtualbricks.bricks import capture
from virtualbricks.tests.gui import GuiTestCase, has_display, untranslated

if has_display:
    from virtualbricks.gui.mainwindow.bricks.config import new_panel
    from virtualbricks.gui.mainwindow.bricks.config.captureconfig import (
        CapturePanel,
    )


class TestTheCapturePanel(GuiTestCase):

    def setUp(self):
        super().setUp()
        untranslated(self)
        self.patch(capture, "host_interfaces", lambda: ["enp3s0", "wlan0"])
        self.switch = self.factory.new_brick("switch", "sw1")
        self.capture = self.factory.new_brick("capture", "cap")

    def make(self):
        panel = new_panel(self.capture)
        self.addCleanup(panel.widget.destroy)
        return panel

    def test_its_rows(self):
        panel = self.make()
        self.assertIsInstance(panel, CapturePanel)
        self.assertEqual(list(panel.form.rows), ["plug0", "interface"])
        interface = panel.form.rows["interface"].control
        self.assertEqual(
            [tuple(row) for row in interface.get_model()],
            [("None", ""), ("enp3s0", "enp3s0"), ("wlan0", "wlan0")],
        )
        self.assertEqual(interface.get_active_id(), "")
        # it can't start yet: said, not refused
        self.assertEqual(
            panel.form.rows["interface"].problem.get_text(),
            "Without an interface, cap can't start",
        )
        self.assertEqual(panel.draft.errors(), [])
        interface.set_active_id("wlan0")
        panel.form.rows["plug0"].control.set_active_id("0")
        self.assertEqual(panel.draft.changes(), {"interface": "wlan0"})
        self.assertEqual(panel.draft.moved(), {0: self.switch.socks[0]})
        self.assertFalse(panel.form.rows["interface"].problem.get_visible())

    def test_an_interface_gone(self):
        self.capture.update_config({"interface": "eth0"})
        interface = self.make().form.rows["interface"].control
        self.assertEqual(
            [tuple(row) for row in interface.get_model()][-1],
            ("eth0, not on this host", "eth0"),
        )
        self.assertEqual(interface.get_active_id(), "eth0")
