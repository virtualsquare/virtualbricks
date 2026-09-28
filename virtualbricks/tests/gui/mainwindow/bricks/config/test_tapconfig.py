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

"""The panel of a tap."""

from virtualbricks.tests.gui import GuiTestCase, has_display, untranslated

if has_display:
    from virtualbricks.gui.mainwindow.bricks.config import new_panel
    from virtualbricks.gui.mainwindow.bricks.config.tapconfig import TapPanel


class TestTheTapPanel(GuiTestCase):

    def setUp(self):
        super().setUp()
        untranslated(self)
        self.switch = self.factory.new_brick("switch", "sw1")
        self.tap = self.factory.new_brick("tap", "tap0")
        self.tap.plugs[0].connect(self.switch.socks[0])
        self.panel = new_panel(self.tap)
        self.addCleanup(self.panel.widget.destroy)
        self.rows = self.panel.form.rows

    def test_its_rows(self):
        self.assertIsInstance(self.panel, TapPanel)
        self.assertEqual(
            list(self.rows),
            ["plug0", "address_mode", "ip_address", "netmask", "gateway"],
        )
        buttons = self.rows["address_mode"].control.get_children()
        self.assertEqual(
            [button.get_label() for button in buttons],
            ["Off", "DHCP", "Manual"],
        )
        self.assertTrue(buttons[0].get_active())
        # the addresses wait for Manual
        for name in ("ip_address", "netmask", "gateway"):
            self.assertFalse(self.rows[name].get_sensitive(), name)
        buttons[2].set_active(True)
        for name in ("ip_address", "netmask", "gateway"):
            self.assertTrue(self.rows[name].get_sensitive(), name)
        self.assertEqual(
            self.rows["address_mode"].caption.get_text(),
            "How the interface gets its address · Virtualbricks doesn't set"
            " it yet",
        )

    def test_an_address_typed(self):
        self.rows["address_mode"].control.get_children()[2].set_active(True)
        netmask = self.rows["netmask"]
        netmask.control.set_text("255.255.0.300")
        self.assertEqual(
            netmask.problem.get_text(),
            '"255.255.0.300" is not an IPv4 address',
        )
        self.assertTrue(netmask.control.get_style_context().has_class("error"))
        self.assertEqual(len(self.panel.draft.errors()), 1)
        netmask.control.set_text("255.255.0.0")
        self.assertFalse(netmask.problem.get_visible())
        self.assertEqual(
            self.panel.draft.changes(),
            {"address_mode": "manual", "netmask": "255.255.0.0"},
        )
