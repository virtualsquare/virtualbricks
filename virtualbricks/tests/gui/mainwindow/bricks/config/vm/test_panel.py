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

"""The panel of a virtual machine: its sections, and its QEMU's answers."""

from twisted.internet import defer

from virtualbricks.bricks.virtualmachine import (
    UsbDevice,
    VirtualMachineDraft,
    hostonly_sock,
)
from virtualbricks.config.settings import set_setting
from virtualbricks.engine import LocalEngine
from virtualbricks.programs import parse_machine_properties
from virtualbricks.tests.gui import GuiTestCase, has_display, untranslated
from virtualbricks.tests.test_programs import load, recorded_info

if has_display:
    from gi.repository import Gtk

    from virtualbricks.gui.mainwindow.bricks.config.vm.panel import (
        VirtualMachinePanel,
    )


class FakePrograms:
    """The answers of the recorded QEMUs, when told."""

    def __init__(self, target="debian-13"):
        self.target = target
        self.asked = []
        self.waiting = []

    def qemu(self, path):
        self.asked.append(path)
        deferred = defer.Deferred()
        self.waiting.append((deferred, recorded_info(self.target)))
        return deferred

    def machine_properties(self, info, machine):
        self.asked.append((info.path, machine))
        out = load(self.target)["qemu"]["machines"]["pc"]["out"]
        return defer.succeed(parse_machine_properties(out))

    def answer(self):
        waiting, self.waiting = self.waiting, []
        for deferred, info in waiting:
            deferred.callback(info)


class PanelGui:
    """The main window, as a panel sees it: its engine."""

    def __init__(self, engine):
        self.engine = engine


class MachinePanelTestCase(GuiTestCase):

    target = "debian-13"
    answer = True

    def setUp(self):
        super().setUp()
        untranslated(self)
        self.programs = FakePrograms(self.target)
        self.found = [
            UsbDevice("046d:c52b", "Logitech, Inc. Unifying Receiver")
        ]
        # QEMU and lsusb, as the engine of the window asks them
        self.gui = PanelGui(
            LocalEngine(
                self.factory,
                programs=self.programs,
                which=self.which,
                usb_devices=lambda: self.lsusb(),
            )
        )
        self.switch = self.factory.new_brick("switch", "sw1")
        self.vm = self.factory.new_brick("qemu", "vm1")
        self.prepare()
        self.panel = VirtualMachinePanel(
            VirtualMachineDraft(self.vm), self.gui
        )
        self.addCleanup(self.panel.widget.destroy)
        self.calls = []
        self.panel.connect_changed(self.calls.append)
        if self.answer:
            self.programs.answer()

    def prepare(self):
        pass

    def which(self, name):
        if name == "qemu-system-aarch64":
            raise FileNotFoundError(name)
        return f"/usr/bin/{name}"

    def lsusb(self):
        return defer.succeed(self.found)

    def page(self, key):
        return self.panel.page(key)


class TestTheSections(MachinePanelTestCase):

    def test_the_sidebar(self):
        rows = self.panel.sidebar.get_children()
        self.assertEqual(
            [row.page.title for row in rows],
            [
                "Machine",
                "Disks",
                "CD-ROM and boot",
                "Network",
                "Display",
                "Sound and USB",
                "Kernel",
                "Advanced",
            ],
        )
        self.assertIs(self.panel.sidebar.get_selected_row(), rows[0])
        self.assertEqual(self.panel.stack.get_visible_child_name(), "machine")
        self.panel.sidebar.select_row(rows[3])
        self.assertEqual(self.panel.stack.get_visible_child_name(), "network")
        self.assertIs(self.page("machine").form, self.panel.form)

    def test_every_setting_has_a_row(self):
        rows = self.panel.rows
        for name in (
            "qemu_program",
            "machine_type",
            "memory",
            "acpi",
            "forget_disk_changes",
            "cdrom_image",
            "boot_order",
            "headless",
            "keyboard_layout",
            "sound_card",
            "use_usb",
            "kernel",
            "gdb_port",
            "serial_socket",
            "icon",
        ):
            self.assertIn(name, rows)

    def test_a_mark_for_a_problem(self):
        rows = {row.page.key: row for row in self.panel.sidebar.get_children()}
        self.assertFalse(any(row.mark.get_visible() for row in rows.values()))
        self.panel.draft.set("use_kernel", True)
        self.panel.on_changed()
        self.assertTrue(rows["kernel"].mark.get_visible())
        self.assertEqual(
            rows["kernel"].mark.get_icon_name()[0], "dialog-error-symbolic"
        )
        self.panel.draft.set("use_kernel", False)
        self.panel.draft.set("cpu_model", "Zen9")
        self.panel.on_changed()
        self.assertFalse(rows["kernel"].mark.get_visible())
        self.assertEqual(
            rows["machine"].mark.get_icon_name()[0], "dialog-warning-symbolic"
        )

    def test_running(self):
        self.assertEqual(
            self.panel.running_words(),
            "vm1 is running: the settings take effect when it starts again.",
        )


class TestItsQemu(MachinePanelTestCase):

    answer = False

    def test_asked(self):
        self.assertEqual(self.programs.asked, ["/usr/bin/qemu-system-i386"])
        self.assertIsNone(self.panel.draft.qemu)
        self.programs.answer()
        info = self.panel.draft.qemu
        self.assertEqual(str(info.version), "10.0.13")
        self.assertEqual(
            self.panel.status_words.get_text(),
            f"QEMU 10.0.13, {info.path}",
        )
        self.assertEqual(
            self.panel.status.get_message_type(), Gtk.MessageType.INFO
        )
        # the default machine, for its properties
        self.assertEqual(self.programs.asked[1:], [(info.path, "")])
        self.assertIn("acpi", self.panel.draft.machine_properties)
        self.assertGreater(len(self.panel.machine_picker.options), 40)

    def test_another_program(self):
        self.programs.answer()
        self.panel.draft.set("qemu_program", "qemu-system-x86_64")
        self.panel.on_changed()
        self.assertEqual(
            self.programs.asked[-1], "/usr/bin/qemu-system-x86_64"
        )
        # an answer too late is dropped
        self.panel.draft.set("qemu_program", "qemu-system-aarch64")
        self.panel.on_changed()
        self.programs.answer()
        self.assertIsNone(self.panel.draft.qemu)
        self.assertEqual(
            self.panel.status_words.get_text(),
            "qemu-system-aarch64 isn't in /usr/bin: the lists show only"
            " vm1's choices",
        )
        self.assertEqual(
            self.panel.status.get_message_type(), Gtk.MessageType.WARNING
        )

    def test_another_machine_type(self):
        self.programs.answer()
        self.panel.draft.set("machine_type", "q35")
        self.panel.on_changed()
        self.programs.answer()
        self.assertEqual(
            self.programs.asked[-1], (self.panel.draft.qemu.path, "q35")
        )

    def test_a_program_not_installed(self):
        self.vm.update_config({"qemu_program": "qemu-system-aarch64"})
        panel = VirtualMachinePanel(VirtualMachineDraft(self.vm), self.gui)
        self.addCleanup(panel.widget.destroy)
        self.assertIsNone(panel.draft.qemu)
        self.assertEqual(
            panel.page("machine")
            .form.rows["qemu_program"]
            .control.get_active_id(),
            "qemu-system-aarch64",
        )


class TestWhatItLacks(MachinePanelTestCase):

    target = "ubuntu-22.04"

    def prepare(self):
        self.vm.update_config(
            {
                "machine_type": "pc-i440fx-jammy",
                "sound_card": "virtio-sound-pci",
            }
        )
        self.vm.add_plug(self.switch.socks[0], "52:54:00:00:00:01", "e1000")
        self.vm.add_plug(hostonly_sock, "52:54:00:00:00:02", "e1000")
        set_setting("audio_driver", "alsa")

    def test_the_words_of_the_start(self):
        rows = self.panel.rows
        self.assertFalse(rows["machine_type"].problem.get_visible())
        self.assertEqual(
            rows["sound_card"].problem.get_text(),
            "QEMU 6.2.0 has no sound card virtio-sound-pci: the machine has none",
        )
        # 6.2 lists no drivers
        self.assertEqual(
            rows["audio_driver"].caption.get_text(),
            "From the settings · QEMU 6.2.0 doesn't list its drivers: this"
            " one is taken on trust",
        )
        self.assertEqual(
            self.panel.cards.lack.get_text(),
            "QEMU 6.2.0 can't join a VDE switch: card 0 unplugged; install a"
            " QEMU built with VDE",
        )
        self.assertTrue(self.panel.cards.lack.get_visible())
