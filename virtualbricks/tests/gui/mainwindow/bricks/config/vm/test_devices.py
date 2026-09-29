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

"""The Display, and the Sound and USB, sections."""

from twisted.internet import defer

from virtualbricks.bricks.virtualmachine import UsbDevice
from virtualbricks.gui.mainwindow.bricks.config.vm import devices
from virtualbricks.gui.mainwindow.bricks.config.vm.devices import sound_options
from virtualbricks.tests import FakeLogger
from virtualbricks.tests.gui.mainwindow.bricks.config.vm.test_panel import (
    MachinePanelTestCase,
)
from virtualbricks.tests.test_programs import recorded_info


class TestTheDisplaySection(MachinePanelTestCase):

    def test_no_display_wins(self):
        rows = self.panel.rows
        rows["use_vnc"].control.set_active(True)
        self.assertTrue(rows["vnc_display"].get_sensitive())
        rows["headless"].control.set_active(True)
        for name in ("use_vnc", "vnc_display", "sdl_window"):
            self.assertFalse(rows[name].get_sensitive(), name)
        self.assertTrue(rows["headless"].get_sensitive())

    def test_the_keyboard(self):
        entry = self.panel.rows["keyboard_layout"].control
        entry.set_text("ita")
        self.assertEqual(
            self.panel.rows["keyboard_layout"].problem.get_text(),
            "Two letters, as it or de",
        )


class TestTheSoundCards(MachinePanelTestCase):

    def test_those_that_work_alone(self):
        options = sound_options(recorded_info("debian-13"), "")
        self.assertEqual(
            [option.value for option in options],
            [
                "",
                "pcspk",
                "AC97",
                "adlib",
                "cs4231a",
                "ES1370",
                "gus",
                "sb16",
                "usb-audio",
                "virtio-sound-pci",
            ],
        )
        self.assertEqual(
            [option.value for option in sound_options(None, "sb16")],
            ["", "pcspk"],
        )

    def test_an_alias(self):
        options = sound_options(recorded_info("debian-13"), "ac97")
        self.assertIn("ac97", [option.value for option in options])
        self.assertNotIn("AC97", [option.value for option in options])

    def test_the_picker(self):
        picker = self.panel.sound_picker
        self.assertEqual(picker.name.get_text(), "None")
        picker.choose("sb16")
        self.assertEqual(self.panel.draft.get("sound_card"), "sb16")
        driver = self.panel.rows["audio_driver"]
        self.assertEqual(driver.control.get_text(), "alsa")
        self.assertEqual(driver.caption.get_text(), "From the settings")


class TestTheUsbDevices(MachinePanelTestCase):

    def prepare(self):
        self.vm.update_config(
            {
                "use_usb": True,
                "usb_devices": [UsbDevice("0bda:8153", "Realtek")],
            }
        )

    def test_the_rows(self):
        rows = self.panel.usb.get_children()
        self.assertEqual(
            [row.device.id for row in rows], ["046d:c52b", "0bda:8153"]
        )
        self.assertEqual(
            [row.switch.get_active() for row in rows], [False, True]
        )
        rows[0].switch.set_active(True)
        rows[1].switch.set_active(False)
        self.assertEqual(
            [device.id for device in self.panel.draft.get("usb_devices")],
            ["046d:c52b"],
        )
        self.assertTrue(self.panel.usb.get_sensitive())
        self.panel.rows["use_usb"].control.set_active(False)
        self.assertFalse(self.panel.usb.get_sensitive())

    def test_lsusb_fails(self):
        logger = FakeLogger()
        self.patch(devices, "logger", logger)
        self.patch(
            devices.virtualmachine,
            "get_usb_devices",
            lambda: defer.fail(OSError("no lsusb")),
        )
        listed = devices.UsbDevices(self.panel)
        self.addCleanup(listed.destroy)
        self.assertEqual(
            [row.device.id for row in listed.get_children()], ["0bda:8153"]
        )
        self.assertEqual(len(logger.events), 1)
