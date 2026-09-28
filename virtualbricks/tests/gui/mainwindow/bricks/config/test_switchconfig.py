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

"""The panel of a switch."""

from virtualbricks.bricks.switch import SwitchDraft
from virtualbricks.tests.gui import GuiTestCase, has_display, untranslated

if has_display:
    from virtualbricks.gui.mainwindow.bricks.config.switchconfig import (
        SwitchPanel,
    )


class TestTheSwitchPanel(GuiTestCase):

    def setUp(self):
        super().setUp()
        untranslated(self)
        self.switch = self.factory.new_brick("switch", "sw1")
        for name in ("tap0", "w1"):
            brick = self.factory.new_brick(
                "tap" if name == "tap0" else "wire", name
            )
            brick.plugs[0].connect(self.switch.socks[0])
        self.switch.set({"fast_spanning_tree": True})
        self.panel = SwitchPanel(SwitchDraft(self.switch))
        self.addCleanup(self.panel.widget.destroy)

    def test_its_rows(self):
        title, _frame = self.panel.widget.get_children()
        self.assertEqual(title.get_text(), "Ports")
        rows = self.panel.form.rows
        self.assertEqual(
            list(rows), ["ports", "hub_mode", "fast_spanning_tree"]
        )
        self.assertEqual(
            [
                (row.title.get_text(), row.caption.get_text())
                for row in rows.values()
            ],
            [
                (
                    "Ports",
                    "Number of ports · at least 2: tap0, w1 plug into sw1",
                ),
                ("Hub mode", "Send every packet to every port, as a hub"),
                ("Fast spanning tree", "Run the fast spanning tree protocol"),
            ],
        )
        self.assertEqual(rows["ports"].control.get_range(), (2, 128))
        self.assertEqual(rows["ports"].control.get_value(), 32)
        self.assertFalse(rows["hub_mode"].control.get_active())
        self.assertTrue(rows["fast_spanning_tree"].control.get_active())

    def test_what_it_changes(self):
        rows = self.panel.form.rows
        rows["ports"].control.set_value(8)
        rows["hub_mode"].control.set_active(True)
        rows["fast_spanning_tree"].control.set_active(False)
        self.assertEqual(
            self.panel.draft.changes(),
            {"ports": 8, "hub_mode": True, "fast_spanning_tree": False},
        )
        self.assertEqual(self.switch.config.ports, 32)
