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

"""The panel of a Netemu: its ends, its states, their values and the chances."""

from virtualbricks.tests.gui import GuiTestCase, has_display, untranslated

if has_display:
    from gi.repository import Gtk

    from virtualbricks.gui.mainwindow.bricks.config import new_panel
    from virtualbricks.gui.mainwindow.bricks.config.netemuconfig import (
        NetemuPanel,
        summary,
    )


class NetemuPanelTestCase(GuiTestCase):

    def setUp(self):
        super().setUp()
        untranslated(self)
        self.switch = self.factory.new_brick("switch", "sw1")
        self.netemu = self.factory.new_brick("netemu", "ne1")
        manager = self.netemu.markov_manager
        manager.add(1)
        manager.states[1].name = "congested"
        manager.states[1].delay = 80
        manager.weights[0][1] = 2.0
        self.panel = new_panel(self.netemu)
        self.addCleanup(self.panel.widget.destroy)
        self.rows = self.panel.form.rows
        self.calls = []
        self.panel.connect_changed(self.calls.append)

    def state_rows(self):
        return self.panel.states.get_children()


class TestItsParts(NetemuPanelTestCase):

    def test_its_rows(self):
        self.assertIsInstance(self.panel, NetemuPanel)
        self.assertEqual(
            list(self.rows),
            [
                "plug0",
                "plug1",
                "name",
                "bandwidth",
                "delay",
                "buffer_size",
                "loss",
                "period",
                "transitions",
            ],
        )
        self.assertEqual(
            [self.rows[key].title.get_text() for key in ("plug0", "plug1")],
            ["Left end", "Right end"],
        )
        self.assertEqual(self.rows["period"].control.get_value(), 100)

    def test_the_states(self):
        rows = self.state_rows()
        self.assertEqual(
            [row.name.get_text() for row in rows],
            ["default name", "congested"],
        )
        self.assertEqual(
            rows[1].words.get_text(), "125000 bytes/s · 80 ms · 0 % lost"
        )
        self.assertIs(self.panel.states.get_selected_row(), rows[0])
        self.assertTrue(self.panel.remove_button.get_sensitive())

    def test_a_pair(self):
        row = self.rows["delay"]
        forward = row.title.get_mnemonic_widget()
        backward = row.parts["delay_right_to_left"]
        both = row.parts["delay_symmetric"]
        self.assertTrue(both.get_active())
        self.assertFalse(backward.get_sensitive())
        both.set_active(False)
        self.assertTrue(backward.get_sensitive())
        backward.set_value(20)
        forward.set_value(40)
        draft = self.panel.draft
        self.assertEqual(
            (draft.get("delay"), draft.get("delay_right_to_left")), (40, 20)
        )
        self.assertFalse(draft.get("delay_symmetric"))
        # the list follows
        self.assertEqual(
            self.state_rows()[0].words.get_text(),
            "125000 bytes/s · 40 ms · 0 % lost",
        )

    def test_another_state(self):
        rows = self.state_rows()
        self.panel.states.select_row(rows[1])
        self.assertEqual(self.panel.draft.selected, 1)
        self.assertEqual(self.rows["name"].control.get_text(), "congested")
        delay = self.rows["delay"].title.get_mnemonic_widget()
        self.assertEqual(delay.get_value(), 80)
        # showing it changes nothing
        self.assertEqual(self.panel.draft.states[0].name, "default name")
        self.assertEqual(self.panel.draft.states[1].delay, 80)
        self.assertEqual(self.calls, [self.panel])
        self.rows["name"].control.set_text("busy")
        self.assertEqual(rows[1].name.get_text(), "busy")
        self.assertEqual(self.panel.draft.states[1].name, "busy")

    def test_add_and_remove(self):
        self.panel.add_button.clicked()
        rows = self.state_rows()
        self.assertEqual(
            [row.name.get_text() for row in rows],
            ["default name", "state 3", "congested"],
        )
        self.assertIs(self.panel.states.get_selected_row(), rows[1])
        self.assertEqual(self.rows["name"].control.get_text(), "state 3")
        self.assertEqual(
            self.panel.transitions.names,
            ["default name", "state 3", "congested"],
        )
        self.panel.remove_button.clicked()
        self.panel.remove_button.clicked()
        self.assertEqual(
            [row.name.get_text() for row in self.state_rows()],
            ["default name"],
        )
        self.assertFalse(self.panel.remove_button.get_sensitive())
        self.assertEqual(self.rows["name"].control.get_text(), "default name")

    def test_the_period(self):
        self.rows["period"].control.set_value(250)
        self.assertEqual(self.panel.draft.period, 250)
        self.assertEqual(self.calls, [self.panel])

    def test_running(self):
        self.assertEqual(
            self.panel.running_words(),
            "ne1 is running. The states and the transitions change at once;"
            " the ends when it starts again.",
        )

    def test_summary(self):
        state = self.netemu.markov_manager.states[0]
        state.loss = 1.5
        self.assertEqual(summary(state), "125000 bytes/s · 0 ms · 1.5 % lost")


class TestTheChances(NetemuPanelTestCase):

    def cell(self, row, column):
        return self.panel.transitions.get_child_at(column + 1, row + 1)

    def test_the_grid(self):
        grid = self.panel.transitions
        self.assertEqual(
            [grid.get_child_at(column, 0).get_text() for column in (1, 2)],
            ["default name", "congested"],
        )
        self.assertEqual(self.cell(0, 0).get_text(), "98 % stays")
        self.assertEqual(self.cell(1, 1).get_text(), "100 % stays")
        self.assertIsInstance(self.cell(0, 1), Gtk.SpinButton)
        self.assertEqual(self.cell(0, 1).get_value(), 2.0)
        self.assertEqual(self.cell(0, 1).get_range(), (0, 100))
        self.cell(1, 0).set_value(10)
        self.assertEqual(self.panel.draft.weights[1][0], 10.0)
        self.assertEqual(self.cell(1, 1).get_text(), "90 % stays")
        self.assertEqual(self.calls, [self.panel])

    def test_more_than_all(self):
        self.cell(0, 1).set_value(100)
        self.cell(1, 0).set_value(10)
        self.assertEqual(self.panel.draft.errors(), [])
        self.panel.add_button.clicked()
        self.cell(0, 1).set_value(50)
        self.cell(0, 2).set_value(60)
        row = self.rows["transitions"]
        self.assertEqual(
            row.problem.get_text(),
            "From default name the chances add up to more than 100 %",
        )
        self.assertEqual(self.cell(0, 0).get_text(), "-10 % stays")

    def test_renamed(self):
        self.rows["name"].control.set_text("idle")
        self.assertEqual(
            self.panel.transitions.get_child_at(1, 0).get_text(), "idle"
        )
