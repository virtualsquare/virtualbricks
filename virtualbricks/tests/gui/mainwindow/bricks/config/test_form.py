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
from virtualbricks.bricks.switch import SwitchConfig, SwitchDraft
from virtualbricks.config.schema import Int, define, field, field_values
from virtualbricks.tests.gui import GuiTestCase, has_display, untranslated

if has_display:
    from gi.repository import Gtk, Pango

    from virtualbricks.gui.mainwindow.bricks.config import form
    from virtualbricks.gui.mainwindow.bricks.config.form import Form


@define
class HubSettings(SwitchConfig):

    ports = field(
        Int(1, 128),
        default=32,
        label="Ports",
        help="Number of ports",
        when=("hub_mode", True),
    )


class HubDraft(SwitchDraft):
    """The ports of a switch in use only as a hub; a check of its own."""

    def read(self):
        return HubSettings(**field_values(self.brick.config))

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

    def test_a_section_of_any_widget(self):
        made = self.make(Draft(self.switch))
        content = Gtk.Label(label="a list")
        made.section("States", content)
        title, frame = made.widget.get_children()
        self.assertEqual(title.get_text(), "States")
        self.assertIs(frame.get_child(), content)
        # no rows after it
        self.assertRaises(ValueError, made.switch, "hub_mode")

    def test_a_row_of_any_widget(self):
        made = self.make(Draft(self.switch))
        made.section("Ports")
        widget = Gtk.Label(label="3")
        row = made.row("count", widget, "Count", "How many")
        self.assertIs(made.rows["count"], row)
        self.assertIs(row.control, widget)
        self.assertEqual(
            (row.title.get_text(), row.caption.get_text()),
            ("Count", "How many"),
        )
        made.refresh()
        self.assertTrue(row.get_sensitive())


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


class TestAWarning(FormTestCase):

    def test_not_an_error(self):
        tap = self.factory.new_brick("tap", "tap0")
        draft = Draft(tap)
        made = self.make(draft)
        made.section("Connection")
        made.socket(0, "Plugged into", "The switch")
        made.refresh()
        row = made.rows["plug0"]
        self.assertEqual(
            row.problem.get_text(), "In nothing: tap0 can't start"
        )
        styles = row.problem.get_style_context()
        self.assertTrue(styles.has_class("lack"))
        self.assertFalse(styles.has_class("error"))
        self.assertFalse(row.control.get_style_context().has_class("error"))
        made.rows["plug0"].control.set_active_id("0")
        made.refresh()
        self.assertFalse(row.problem.get_visible())
        self.assertFalse(styles.has_class("lack"))


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
        self.switch.update_config({"ports": 1})
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

    def test_an_entry(self):
        tunnel = self.factory.new_brick("tunnelconnect", "tc1")
        draft = Draft(tunnel)
        draft.set("server_host", "lab.example.org")
        made = self.make(draft)
        made.section("Tunnel")
        host = made.entry("server_host")
        password = made.entry("password", secret=True)
        self.assertEqual(host.get_text(), "lab.example.org")
        self.assertTrue(host.get_visibility())
        self.assertFalse(password.get_visibility())
        self.assertEqual(made.rows["server_host"].title.get_text(), "Server")
        password.set_text("s3cret")
        self.assertEqual(draft.get("password"), "s3cret")
        self.assertEqual(self.changes, 1)

    def test_a_path(self):
        wrapper = self.factory.new_brick("switchwrapper", "sww")
        draft = Draft(wrapper)
        draft.set("socket_path", "/run/vde/sw")
        made = self.make(draft)
        made.section("Switch")
        entry = made.path("socket_path", "The folder", folder=True)
        box = made.rows["socket_path"].control
        self.assertEqual(box.get_children()[0], entry)
        self.assertTrue(box.get_style_context().has_class("linked"))
        self.assertIs(
            made.rows["socket_path"].title.get_mnemonic_widget(), entry
        )
        self.assertEqual(entry.get_text(), "/run/vde/sw")
        entry.set_text("/run/vde/other")
        self.assertEqual(draft.get("socket_path"), "/run/vde/other")

    def test_choosing_a_path(self):
        dialogs = []

        class FakeDialog:
            def __init__(self, **props):
                self.props = props
                self.buttons = []
                self.filename = None
                self.handlers = []
                self.destroyed = False
                dialogs.append(self)

            def add_buttons(self, *buttons):
                self.buttons.extend(buttons)

            def set_filename(self, filename):
                self.filename = filename

            def get_filename(self):
                return "/run/vde/chosen"

            def connect(self, signal, handler):
                self.handlers.append((signal, handler))

            def show(self):
                pass

            def destroy(self):
                self.destroyed = True

        self.patch(form.Gtk, "FileChooserDialog", FakeDialog)
        wrapper = self.factory.new_brick("switchwrapper", "sww")
        draft = Draft(wrapper)
        made = self.make(draft)
        made.section("Switch")
        entry = made.path("socket_path", "The folder", folder=True)
        entry.set_text("/run/vde/sw")
        button = made.rows["socket_path"].control.get_children()[1]
        button.clicked()
        [dialog] = dialogs
        self.assertEqual(dialog.props["title"], "The folder")
        self.assertEqual(
            dialog.props["action"], Gtk.FileChooserAction.SELECT_FOLDER
        )
        self.assertEqual(dialog.filename, "/run/vde/sw")
        [(signal, handler)] = dialog.handlers
        self.assertEqual(signal, "response")
        handler(dialog, Gtk.ResponseType.CANCEL)
        self.assertEqual(entry.get_text(), "/run/vde/sw")
        handler(dialog, Gtk.ResponseType.ACCEPT)
        self.assertEqual(entry.get_text(), "/run/vde/chosen")
        self.assertEqual(draft.get("socket_path"), "/run/vde/chosen")
        self.assertTrue(dialog.destroyed)
        # a file, and nothing typed yet
        dialogs.clear()
        entry.set_text("")
        made.path("icon", "An icon")
        made.rows["icon"].control.get_children()[1].clicked()
        self.assertEqual(
            dialogs[0].props["action"], Gtk.FileChooserAction.OPEN
        )
        self.assertIsNone(dialogs[0].filename)

    def test_buttons_of_a_choice(self):
        tap = self.factory.new_brick("tap", "tap0")
        draft = Draft(tap)
        made = self.make(draft)
        made.section("Address")
        box = made.choice(
            "address_mode",
            [("off", "Off"), ("dhcp", "DHCP"), ("manual", "Manual")],
        )
        self.assertTrue(box.get_style_context().has_class("linked"))
        buttons = box.get_children()
        self.assertEqual(
            [b.get_label() for b in buttons], ["Off", "DHCP", "Manual"]
        )
        self.assertEqual(
            [b.get_active() for b in buttons], [True, False, False]
        )
        self.assertFalse(buttons[0].get_mode())
        buttons[2].set_active(True)
        self.assertEqual(draft.get("address_mode"), "manual")
        # the one left says nothing
        self.assertEqual(self.changes, 1)

    def test_a_menu_of_a_choice(self):
        capture = self.factory.new_brick("capture", "cap")
        draft = Draft(capture)
        draft.set("interface", "eth9")
        made = self.make(draft)
        made.section("Capture")
        combo = made.choice(
            "interface",
            [("", "None"), ("eth0", "eth0")],
            menu=True,
            missing="{value}, not here",
        )
        model = combo.get_model()
        self.assertEqual(
            [tuple(row) for row in model],
            [("None", ""), ("eth0", "eth0"), ("eth9, not here", "eth9")],
        )
        self.assertEqual(combo.get_active_id(), "eth9")
        combo.set_active_id("eth0")
        self.assertEqual(draft.get("interface"), "eth0")
        self.assertEqual(self.changes, 1)

    def test_a_socket(self):
        sw2 = self.factory.new_brick("switch", "sw2")
        vm = self.factory.new_brick("qemu", "vm1")
        vm.add_sock()
        tap = self.factory.new_brick("tap", "tap0")
        tap.plugs[0].connect(sw2.socks[0])
        draft = Draft(tap)
        made = self.make(draft)
        made.section("Connection")
        combo = made.socket(0, "Plugged into", "The switch the tap joins")
        row = made.rows["plug0"]
        self.assertEqual(
            (row.title.get_text(), row.caption.get_text()),
            ("Plugged into", "The switch the tap joins"),
        )
        # the switches, not the female plugs
        self.assertEqual(
            [tuple(item) for item in combo.get_model()],
            [("Nothing", ""), ("sw1", "0"), ("sw2", "1")],
        )
        self.assertEqual(combo.get_active_id(), "1")
        combo.set_active_id("0")
        self.assertIs(draft.links[0], self.switch.socks[0])
        self.assertEqual(self.changes, 1)
        combo.set_active_id("")
        self.assertIsNone(draft.links[0])
        # the brick waits for OK
        self.assertIs(tap.plugs[0].sock, sw2.socks[0])

    def test_a_socket_not_offered(self):
        # a female plug, once allowed
        vm = self.factory.new_brick("qemu", "vm1")
        sock = vm.add_sock()
        tap = self.factory.new_brick("tap", "tap0")
        tap.plugs[0].connect(sock)
        made = self.make(Draft(tap))
        made.section("Connection")
        combo = made.socket(0, "Plugged into", "")
        self.assertEqual(
            [tuple(item) for item in combo.get_model()],
            [("Nothing", ""), ("sw1", "0"), ("vm1_sock_eth0", "1")],
        )
        self.assertEqual(combo.get_active_id(), "1")


class TestReload(FormTestCase):

    def test_the_draft_again(self):
        tap = self.factory.new_brick("tap", "tap0")
        netemu = self.factory.new_brick("netemu", "ne1")
        draft = Draft(tap)
        made = self.make(draft)
        made.section("Tap")
        buttons = made.choice(
            "address_mode", [("off", "Off"), ("manual", "Manual")]
        ).get_children()
        entry = made.entry("ip_address")
        draft.set("address_mode", "manual")
        draft.set("ip_address", "10.0.0.2")
        made.reload()
        self.assertTrue(buttons[1].get_active())
        self.assertEqual(entry.get_text(), "10.0.0.2")
        self.assertEqual(self.changes, 0)
        # and the rows are refreshed
        self.assertTrue(made.rows["ip_address"].get_sensitive())
        # a pair, a switch, a spin button, a menu
        draft = Draft(netemu)
        made = self.make(draft)
        made.section("Values")
        row = made.pair("delay", "delay_right_to_left", "delay_symmetric")
        spin = made.spin("bandwidth")
        switch = made.switch("loss_symmetric")
        draft.set("delay", 5)
        draft.set("delay_right_to_left", 6)
        draft.set("delay_symmetric", False)
        draft.set("bandwidth", 7)
        draft.set("loss_symmetric", False)
        made.reload()
        self.assertEqual(row.title.get_mnemonic_widget().get_value(), 5)
        self.assertEqual(row.parts["delay_right_to_left"].get_value(), 6)
        self.assertFalse(row.parts["delay_symmetric"].get_active())
        self.assertEqual(spin.get_value(), 7)
        self.assertFalse(switch.get_active())
        self.assertEqual(self.changes, 0)
        self.assertEqual(draft.get("delay"), 5)

    def test_a_problem_of_a_part(self):
        netemu = self.factory.new_brick("netemu", "ne1")
        draft = Draft(netemu)
        made = self.make(draft)
        made.section("Values")
        row = made.pair("loss", "loss_right_to_left", "loss_symmetric")
        draft.set("loss_right_to_left", 300.0)
        made.refresh()
        self.assertEqual(row.problem.get_text(), "300.0 is outside 0–100")
