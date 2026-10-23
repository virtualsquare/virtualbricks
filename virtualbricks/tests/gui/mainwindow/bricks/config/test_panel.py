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

"""A panel on a draft: its rows, what it tells, what it says of a brick running."""

from virtualbricks.bricks.draft import Draft
from virtualbricks.tests.gui import GuiTestCase, has_display, untranslated

if has_display:
    from gi.repository import Gtk

    from virtualbricks.gui.mainwindow.bricks.config import PANELS, new_panel
    from virtualbricks.gui.mainwindow.bricks.config.panel import (
        Panel,
        spin_buttons,
    )
    from virtualbricks.gui.mainwindow.bricks.config.switchconfig import (
        SwitchPanel,
    )

    class TwoRows(Panel):
        def build(self, form):
            form.section("Ports")
            form.spin("ports")
            form.switch("hub_mode")

    class Pages(Panel):
        """A number in a form, and one of its own on a page not shown."""

        def build(self, form):
            form.section("Ports")
            form.spin("ports")
            self.own = Gtk.SpinButton(
                adjustment=Gtk.Adjustment(upper=100, step_increment=1)
            )
            self.own.connect(
                "value-changed",
                lambda spin: self.draft.set("ports", spin.get_value_as_int()),
            )
            stack = Gtk.Stack()
            stack.add_named(form.widget, "form")
            stack.add_named(self.own, "own")
            return stack


class PortsOnly(Draft):
    """A switch that takes only its ports at once."""

    def live(self):
        return ["ports"]


class PanelTestCase(GuiTestCase):

    def setUp(self):
        super().setUp()
        untranslated(self)
        self.switch = self.factory.new_brick("switch", "sw1")

    def make(self, panel, draft):
        made = panel(draft)
        self.addCleanup(made.widget.destroy)
        return made


class TestAPanel(PanelTestCase):

    def test_its_rows(self):
        draft = Draft(self.switch)
        panel = self.make(TwoRows, draft)
        self.assertIs(panel.draft, draft)
        self.assertIs(panel.widget, panel.form.widget)
        self.assertIs(panel.form.draft, draft)
        self.assertEqual(list(panel.form.rows), ["ports", "hub_mode"])

    def test_refreshed_once_made(self):
        draft = Draft(self.switch)
        draft.set("ports", 0)
        panel = self.make(TwoRows, draft)
        self.assertTrue(panel.form.rows["ports"].problem.get_visible())

    def test_a_change(self):
        calls = []
        panel = self.make(TwoRows, Draft(self.switch))
        panel.connect_changed(calls.append)
        panel.connect_changed(lambda panel: calls.append("second"))
        panel.form.rows["ports"].control.set_value(0)
        # refreshed first
        self.assertEqual(calls, [panel, "second"])
        panel.form.rows["ports"].control.set_value(200)
        self.assertEqual(panel.draft.get("ports"), 128)
        self.assertFalse(panel.form.rows["ports"].problem.get_visible())

    def test_build(self):
        self.assertRaises(NotImplementedError, Panel, Draft(self.switch))


class TestCommit(PanelTestCase):

    def test_the_numbers_typed(self):
        panel = self.make(Pages, Draft(self.switch))
        spin = panel.form.rows["ports"].control
        self.assertEqual(list(spin_buttons(panel.widget)), [spin, panel.own])
        spin.set_text("8")
        # not yet taken
        self.assertEqual(panel.draft.get("ports"), 32)
        panel.commit()
        self.assertEqual(panel.draft.get("ports"), 8)
        # the one of its own, on the page not shown
        panel.own.set_text("12")
        panel.commit()
        self.assertEqual(panel.draft.get("ports"), 12)

    def test_nothing_typed(self):
        panel = self.make(TwoRows, Draft(self.switch))
        panel.commit()
        self.assertEqual(panel.draft.changes(), {})


class TestRunning(PanelTestCase):

    def test_whether_it_runs(self):
        panel = self.make(TwoRows, Draft(self.switch))
        self.assertFalse(panel.running())
        self.switch.is_running = lambda: True
        self.assertTrue(panel.running())

    def test_everything_at_once(self):
        panel = self.make(SwitchPanel, Draft(self.switch))
        self.assertEqual(
            panel.running_words(),
            "sw1 is running. These change at once: Ports, Hub mode, Fast"
            " spanning tree.",
        )

    def test_some_at_once(self):
        panel = self.make(TwoRows, PortsOnly(self.switch))
        self.assertEqual(
            panel.running_words(),
            "sw1 is running. These change at once: Ports; the rest when it"
            " starts again.",
        )

    def test_nothing_at_once(self):
        tunnel = self.factory.new_brick("tunnellisten", "tl1")

        class Port(Panel):
            def build(self, form):
                form.section("Tunnel")
                form.spin("listen_port")

        panel = self.make(Port, Draft(tunnel))
        self.assertEqual(
            panel.running_words(),
            "tl1 is running: the settings take effect when it starts again.",
        )


class TestTheTable(PanelTestCase):

    def test_a_switch(self):
        self.assertIs(PANELS["Switch"], SwitchPanel)
        panel = new_panel(self.switch)
        self.addCleanup(panel.widget.destroy)
        self.assertIsInstance(panel, SwitchPanel)
        self.assertIs(panel.draft.brick, self.switch)
        self.assertIsInstance(panel.draft, self.switch.draft_factory)

    def test_not_yet(self):
        self.assertIsNone(new_panel(self.factory.new_brick("router", "r1")))
