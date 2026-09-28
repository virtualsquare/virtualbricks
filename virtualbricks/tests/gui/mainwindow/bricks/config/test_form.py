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

"""The rows of a panel: what they show of a draft, and what they write."""

from virtualbricks.bricks.draft import Draft, Problem
from virtualbricks.bricks.switch import SwitchDraft
from virtualbricks.tests.gui import GuiTestCase, has_display, untranslated

if has_display:
    from gi.repository import Gtk, Pango

    from virtualbricks.gui.mainwindow.bricks.config import form
    from virtualbricks.gui.mainwindow.bricks.config.form import Form


class HubDraft(SwitchDraft):
    """The ports of a switch in use only as a hub; a check of its own."""

    WITH = {"ports": ("hub_mode", True)}

    def check(self):
        problems = super().check()
        if self.settings.fast_spanning_tree and self.settings.hub_mode:
            problems.append(Problem("hub_mode", "not with FSTP"))
        return problems


class FormTestCase(GuiTestCase):

    def setUp(self):
        super().setUp()
        untranslated(self)
        self.switch = self.factory.new_brick("switch", "sw1")
        self.changes = 0

    def changed(self):
        self.changes += 1

    def make(self, draft):
        made = Form(draft, self.changed)
        self.addCleanup(made.widget.destroy)
        return made


class TestSections(FormTestCase):

    def test_a_title_and_a_frame(self):
        made = self.make(Draft(self.switch))
        made.section("Ports")
        ports = made.spin("ports")
        made.switch("hub_mode")
        made.section("More")
        made.switch("fast_spanning_tree")
        title, frame, more, frame2 = made.widget.get_children()
        self.assertEqual(title.get_text(), "Ports")
        self.assertEqual(title.get_margin_top(), 0)
        # the second section keeps its distance
        self.assertEqual(more.get_margin_top(), form.GAP)
        [weight] = title.get_attributes().get_attributes()
        self.assertEqual(weight.as_int().value, Pango.Weight.BOLD)
        rows = frame.get_child().get_children()
        self.assertEqual(rows, [made.rows["ports"], made.rows["hub_mode"]])
        self.assertEqual(
            frame2.get_child().get_children(),
            [made.rows["fast_spanning_tree"]],
        )
        self.assertIs(made.rows["ports"].control, ports)
        for widget in (title, frame, more, frame2, *rows):
            self.assertTrue(widget.get_visible(), widget)

    def test_a_line_between_rows(self):
        made = self.make(Draft(self.switch))
        made.section("Ports")
        made.spin("ports")
        made.switch("hub_mode")
        self.assertIsNone(made.rows["ports"].get_header())
        self.assertIsInstance(
            made.rows["hub_mode"].get_header(), Gtk.Separator
        )

    def test_a_row_needs_a_section(self):
        made = self.make(Draft(self.switch))
        self.assertRaises(ValueError, made.switch, "hub_mode")


class TestARow(FormTestCase):

    def test_its_texts(self):
        made = self.make(Draft(self.switch))
        made.section("Ports")
        spin = made.spin("ports")
        row = made.rows["ports"]
        self.assertEqual(row.key, "ports")
        self.assertEqual(row.title.get_text(), "Ports")
        self.assertIs(row.title.get_mnemonic_widget(), spin)
        self.assertEqual(row.caption.get_text(), "Number of ports")
        self.assertTrue(row.caption.get_style_context().has_class("dim-label"))
        self.assertFalse(row.problem.get_visible())
        self.assertTrue(row.problem.get_style_context().has_class("error"))
        self.assertFalse(row.get_activatable())
        self.assertFalse(row.get_selectable())

    def test_translated(self):
        self.patch(form, "_", lambda message: f"<{message}>")
        made = self.make(Draft(self.switch))
        made.section("Ports")
        made.spin("ports")
        row = made.rows["ports"]
        self.assertEqual(row.title.get_text(), "<Ports>")
        self.assertEqual(row.caption.get_text(), "<Number of ports>")

    def test_refresh(self):
        # a machine in the switch
        vm = self.factory.new_brick("qemu", "vm1")
        vm.add_plug(self.switch.socks[0])
        draft = HubDraft(self.switch)
        made = self.make(draft)
        made.section("Ports")
        spin = made.spin("ports")
        made.switch("hub_mode")
        made.switch("fast_spanning_tree")
        made.refresh()
        ports = made.rows["ports"]
        hub = made.rows["hub_mode"]
        # used only as a hub, with the note of the draft
        self.assertFalse(ports.get_sensitive())
        self.assertTrue(hub.get_sensitive())
        self.assertEqual(
            ports.caption.get_text(),
            "Number of ports · at least 1: vm1 plugs into sw1",
        )
        self.assertEqual(
            hub.caption.get_text(), "Send every packet to every port, as a hub"
        )
        draft.set("hub_mode", True)
        draft.set("fast_spanning_tree", True)
        draft.set("ports", 0)
        made.refresh()
        self.assertTrue(ports.get_sensitive())
        # the first problem of each setting
        self.assertEqual(ports.problem.get_text(), "0 is outside 1–128")
        self.assertTrue(ports.problem.get_visible())
        self.assertTrue(spin.get_style_context().has_class("error"))
        self.assertEqual(hub.problem.get_text(), "not with FSTP")
        draft.set("ports", 8)
        draft.set("fast_spanning_tree", False)
        made.refresh()
        for row in (ports, hub):
            self.assertEqual(row.problem.get_text(), "")
            self.assertFalse(row.problem.get_visible())
            self.assertFalse(
                row.control.get_style_context().has_class("error")
            )


class TestTheWidgets(FormTestCase):

    def test_a_switch(self):
        draft = Draft(self.switch)
        draft.set("hub_mode", True)
        made = self.make(draft)
        made.section("Ports")
        switch = made.switch("hub_mode")
        self.assertIsInstance(switch, Gtk.Switch)
        self.assertTrue(switch.get_active())
        self.assertEqual(switch.get_valign(), Gtk.Align.CENTER)
        self.assertEqual(switch.get_halign(), Gtk.Align.END)
        self.assertEqual(self.changes, 0)
        switch.set_active(False)
        self.assertFalse(draft.get("hub_mode"))
        self.assertEqual(self.changes, 1)
        # the brick waits for OK
        self.assertFalse(self.switch.config.hub_mode)

    def test_a_spin_button(self):
        draft = Draft(self.switch)
        made = self.make(draft)
        made.section("Ports")
        spin = made.spin("ports")
        self.assertEqual(spin.get_range(), (1, 128))
        self.assertEqual(spin.get_value(), 32)
        self.assertEqual(spin.get_digits(), 0)
        self.assertTrue(spin.get_numeric())
        self.assertEqual(self.changes, 0)
        spin.set_value(16)
        self.assertEqual(draft.get("ports"), 16)
        self.assertIsInstance(draft.get("ports"), int)
        self.assertEqual(self.changes, 1)

    def test_the_limits_of_the_draft(self):
        for name in ("vm1", "vm2"):
            vm = self.factory.new_brick("qemu", name)
            vm.add_plug(self.switch.socks[0])
        made = self.make(SwitchDraft(self.switch))
        made.section("Ports")
        self.assertEqual(made.spin("ports").get_range(), (2, 128))

    def test_a_value_below_its_limit(self):
        # it stays, and the draft says what is wrong
        for name in ("vm1", "vm2"):
            vm = self.factory.new_brick("qemu", name)
            vm.add_plug(self.switch.socks[0])
        self.switch.set({"ports": 1})
        draft = SwitchDraft(self.switch)
        made = self.make(draft)
        made.section("Ports")
        spin = made.spin("ports")
        self.assertEqual(spin.get_range(), (1, 128))
        self.assertEqual(spin.get_value(), 1)
        self.assertEqual(draft.changes(), {})

    def test_a_number(self):
        netemu = self.factory.new_brick("netemu", "ne1")
        draft = Draft(netemu)
        made = self.make(draft)
        made.section("Values")
        loss = made.spin("loss")
        self.assertEqual(loss.get_digits(), 2)
        self.assertEqual(loss.get_range(), (0, 100))
        loss.set_value(1.5)
        self.assertEqual(draft.get("loss"), 1.5)
        # no limits
        bandwidth = made.spin("bandwidth")
        self.assertEqual(bandwidth.get_range(), (form.LOWEST, form.HIGHEST))
