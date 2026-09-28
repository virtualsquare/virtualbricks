# -*- test-case-name: virtualbricks.tests.gui.mainwindow.bricks.config.vm.test_devices -*-
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

"""
The Display, and the Sound and USB, sections of a virtual machine.

The sound cards are those of the machine's QEMU that work on their own,
and the PC speaker. The USB devices are those of the host, as lsusb lists
them when the section is made, and those the machine has that the host
hasn't: a switch each.
"""

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Pango  # noqa: E402
from twisted.logger import Logger  # noqa: E402

from virtualbricks.bricks import virtualmachine  # noqa: E402
from virtualbricks.config.settings import get_setting  # noqa: E402
from virtualbricks.gui.mainwindow.bricks.config.picker import (  # noqa: E402
    Option,
    Picker,
)
from virtualbricks.gui.mainwindow.bricks.config.vm.machine import (  # noqa: E402
    missing,
)
from virtualbricks.gui.pango import pango_attr_list  # noqa: E402
from virtualbricks.i18n import _  # noqa: E402

logger = Logger()
usb_error = "Cannot list the USB devices"
GAP = 8
# The sound devices that need another to make a sound: the HDA controllers
# and codecs, and the ones of other buses.
NOT_ALONE = (
    "hda-",
    "intel-hda",
    "ich9-intel-hda",
    "vhost-user-",
    "virtio-sound-device",
)


def sound_options(info, chosen: str) -> list:
    """The sound cards to choose from; the chosen one by its own name."""

    options = [
        Option("", _("None")),
        Option("pcspk", _("PC speaker"), _("The speaker of the PC")),
    ]
    if info is None:
        return options
    device = info.device(chosen) if chosen else None
    for other in info.devices:
        if other.category != "Sound devices" or other.name.startswith(
            NOT_ALONE
        ):
            continue
        value = chosen if other is device else other.name
        options.append(Option(value, other.name, other.description))
    return options


def build_display(panel, page) -> None:
    form = page.form
    form.section(_("Display"))
    form.switch("headless")
    form.switch("standard_vga")
    form.switch("use_vnc")
    form.spin("vnc_display")
    form.switch("sdl_window")
    form.section(_("Keyboard"))
    form.entry("keyboard_layout")


def build_sound(panel, page) -> None:
    form = page.form
    draft = panel.draft
    form.section(_("Sound"))

    def chose(value):
        draft.set("sound_card", value)
        panel.on_changed()

    made = Picker(draft.get("sound_card"), chose, missing(draft))
    panel.sound_picker = made
    form.row("sound_card", made)
    driver = Gtk.Label(visible=True, label=get_setting("audio_driver"))
    form.row("audio_driver", driver, _("Audio driver"), _("From the settings"))

    def fill():
        made.missing = missing(draft)
        made.set_options(sound_options(draft.qemu, draft.get("sound_card")))

    panel.fillers.append(fill)
    fill()

    form.section(_("USB"))
    form.switch("use_usb")
    devices = UsbDevices(panel)
    panel.usb = devices
    form.section(_("USB devices"), devices)
    page.keys.add("usb_devices")
    panel.refreshers.append(
        lambda: devices.set_sensitive(draft.uses("usb_devices"))
    )


class UsbDevices(Gtk.ListBox):
    """The USB devices of the host, and of the machine: a switch each."""

    def __init__(self, panel) -> None:
        super().__init__(visible=True, selection_mode=Gtk.SelectionMode.NONE)
        self.panel = panel
        self.found = None
        self.set_placeholder(
            Gtk.Label(
                visible=True,
                label=_("Looking for the USB devices of the host…"),
                margin=12,
            )
        )
        deferred = virtualmachine.get_usb_devices()
        deferred.addCallback(self.show_devices)
        deferred.addErrback(self.failed)

    def show_devices(self, found) -> None:
        self.found = list(found)
        self.fill()

    def failed(self, failure) -> None:
        logger.failure(usb_error, failure)
        self.show_devices([])

    def fill(self) -> None:
        for row in self.get_children():
            row.destroy()
        chosen = list(self.panel.draft.get("usb_devices"))
        ids = {device.id for device in self.found}
        devices = self.found + [d for d in chosen if d.id not in ids]
        for device in devices:
            self.add(self._row(device, device in chosen, device.id in ids))
        if not devices:
            self.set_placeholder(
                Gtk.Label(
                    visible=True,
                    label=_("The host has no USB devices"),
                    margin=12,
                )
            )

    def _row(self, device, on: bool, there: bool) -> Gtk.ListBoxRow:
        row = Gtk.ListBoxRow(visible=True, activatable=False, selectable=False)
        box = Gtk.Box(visible=True, spacing=12, margin=GAP, margin_start=12)
        texts = Gtk.Box(visible=True, orientation=Gtk.Orientation.VERTICAL)
        name = Gtk.Label(
            visible=True,
            xalign=0.0,
            label=device.id,
            attributes=pango_attr_list(Pango.attr_family_new("monospace")),
        )
        words = device.description or ""
        if not there:
            words = _("{device}, not on this host").format(
                device=words or device.id
            )
        description = Gtk.Label(
            visible=True, xalign=0.0, label=words, wrap=True
        )
        description.get_style_context().add_class("dim-label")
        texts.pack_start(name, False, False, 0)
        texts.pack_start(description, False, False, 0)
        switch = Gtk.Switch(visible=True, active=on, valign=Gtk.Align.CENTER)
        switch.connect("notify::active", self.on_switched, device)
        box.pack_start(texts, True, True, 0)
        box.pack_start(switch, False, False, 0)
        row.add(box)
        row.switch = switch
        row.device = device
        return row

    def on_switched(self, switch, param, device) -> None:
        draft = self.panel.draft
        chosen = [d for d in draft.get("usb_devices") if d.id != device.id]
        if switch.get_active():
            chosen.append(device)
        draft.set("usb_devices", chosen)
        self.panel.on_changed()
