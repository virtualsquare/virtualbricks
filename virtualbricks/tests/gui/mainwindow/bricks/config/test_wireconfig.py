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

"""The panel of a wire."""

from virtualbricks.tests.gui import GuiTestCase, has_display, untranslated

if has_display:
    from virtualbricks.gui.mainwindow.bricks.config import new_panel
    from virtualbricks.gui.mainwindow.bricks.config.wireconfig import WirePanel


class TestTheWirePanel(GuiTestCase):

    def test_its_ends(self):
        untranslated(self)
        sw1 = self.factory.new_brick("switch", "sw1")
        sw2 = self.factory.new_brick("switch", "sw2")
        wire = self.factory.new_brick("wire", "w1")
        wire.plugs[0].connect(sw1.socks[0])
        panel = new_panel(wire)
        self.addCleanup(panel.widget.destroy)
        self.assertIsInstance(panel, WirePanel)
        rows = panel.form.rows
        self.assertEqual(list(rows), ["plug0", "plug1"])
        self.assertEqual(
            [row.title.get_text() for row in rows.values()],
            ["Left end", "Right end"],
        )
        self.assertEqual(rows["plug0"].control.get_active_id(), "0")
        self.assertEqual(rows["plug1"].control.get_active_id(), "")
        self.assertEqual(
            rows["plug1"].problem.get_text(), "In nothing: w1 can't start"
        )
        rows["plug1"].control.set_active_id("1")
        self.assertEqual(panel.draft.moved(), {1: sw2.socks[0]})
        self.assertFalse(rows["plug1"].problem.get_visible())
