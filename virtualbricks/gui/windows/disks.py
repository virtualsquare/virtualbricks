# -*- test-case-name: virtualbricks.tests.gui.windows.test_disks -*-
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
The disks of a machine, in its Drives tab: a row for each disk it has, with
its device, the picker of its image, its mode and its menu, and a line that
says what the mode does. Add Disk offers the free devices, hda to mtdblock.

The mode is Private copy, the machine's changes kept in a file of the
project, or The image itself, which the machine writes into; the project
file keeps it as the private<device> setting. The menu of a disk with a
private copy saves it as a new image, merges it into its image or starts it
over, in the dialogs of ``imagedialogs``.

Nothing changes until OK: the rows keep what is chosen, and ``apply()``
gives the images to the machine and returns the modes as its settings.
"""

import os

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gio, GLib, Gtk, Pango

from virtualbricks.bricks.virtualmachine import DISK_DEVICES
from virtualbricks.config import images
from virtualbricks.gui import imageinfo
from virtualbricks.gui.windows.base import pango_attr_list
from virtualbricks.gui.windows.imagedialogs import (
    MergeDialog,
    SaveImageDialog,
    StartOverDialog,
    show_in_files,
)
from virtualbricks.gui.windows.imagepicker import ImagePicker
from virtualbricks.i18n import _

# The modes of a disk: whether it has a private copy.
PRIVATE = "private"
ITSELF = "image"
MODES = ((PRIVATE, _("Private copy")), (ITSELF, _("The image itself")))


def _label(text="", dim=False, bold=False, **props):
    label = Gtk.Label(visible=True, label=text, xalign=0.0, **props)
    if dim:
        label.get_style_context().add_class("dim-label")
    if bold:
        label.set_attributes(
            pango_attr_list(Pango.attr_weight_new(Pango.Weight.BOLD))
        )
    return label


class DiskRow(Gtk.ListBoxRow):
    """A disk: its device, its image, its mode and what the mode does."""

    def __init__(self, section, device, image, private) -> None:
        super().__init__(visible=True, activatable=False, selectable=False)
        self.section = section
        self.device = device
        vm = section.vm
        grid = Gtk.Grid(
            visible=True, column_spacing=12, row_spacing=4, margin=10
        )
        device_label = _label(device, dim=True, width_chars=8)
        device_label.get_style_context().add_class("monospace")
        grid.attach(device_label, 0, 0, 1, 1)
        self.picker = ImagePicker(
            section.factory, vm, image, section.infos, section.manage
        )
        self.picker.connect("chosen", lambda picker: self.update())
        grid.attach(self.picker, 1, 0, 1, 1)
        self.mode_combo = Gtk.ComboBoxText(
            visible=True, valign=Gtk.Align.CENTER
        )
        for mode, label in MODES:
            self.mode_combo.append(mode, label)
        self.mode_combo.set_active_id(PRIVATE if private else ITSELF)
        self.mode_combo.connect("changed", lambda combo: self.update())
        grid.attach(self.mode_combo, 2, 0, 1, 1)

        self.actions = Gio.SimpleActionGroup()
        for name, callback in (
            ("save", self.save),
            ("merge", self.merge),
            ("start-over", self.start_over),
            ("show", self.show_in_files),
            ("remove", self.remove),
        ):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", lambda a, p, call=callback: call())
            self.actions.add_action(action)
        self.insert_action_group("disk", self.actions)
        # its items name the image: update() makes them
        self.menu = Gio.Menu()
        self.menu_button = Gtk.MenuButton(
            visible=True,
            relief=Gtk.ReliefStyle.NONE,
            valign=Gtk.Align.CENTER,
            menu_model=self.menu,
            tooltip_text=_("More for {device}").format(device=device),
        )
        self.menu_button.add(
            Gtk.Image(visible=True, icon_name="view-more-symbolic")
        )
        grid.attach(self.menu_button, 3, 0, 1, 1)

        self.line = _label(dim=True, wrap=True, max_width_chars=60)
        grid.attach(self.line, 1, 1, 2, 1)
        self.add(grid)
        self.update()

    @property
    def image(self):
        return self.picker.image

    @property
    def private(self) -> bool:
        return self.mode_combo.get_active_id() == PRIVATE

    def update(self) -> None:
        """Say what the disk does, as chosen now."""

        vm = self.section.vm
        disk = vm.disk(self.device)
        copy = disk.get_cow_path()
        self.line.set_text(
            imageinfo.disk_line(
                vm.get_name(),
                self.image,
                disk.image,
                self.private,
                copy,
                images.space_taken(copy),
            )
        )
        there = self.image is not None and os.path.exists(
            self.image.get_path()
        )
        self.actions.lookup_action("show").set_enabled(there)
        changes = self.keeps_changes()
        for name in ("save", "merge", "start-over"):
            self.actions.lookup_action(name).set_enabled(changes)
        self._make_menu()

    def _make_menu(self) -> None:
        image = "" if self.image is None else self.image.get_name()
        changes = Gio.Menu()
        changes.append(_("Save as a New Image…"), "disk.save")
        changes.append(
            _("Merge into {image}…").format(image=image), "disk.merge"
        )
        changes.append(
            _("Start Over from {image}…").format(image=image),
            "disk.start-over",
        )
        others = Gio.Menu()
        others.append(_("Show in Files"), "disk.show")
        others.append(_("Remove Disk"), "disk.remove")
        self.menu.remove_all()
        self.menu.append_section(None, changes)
        self.menu.append_section(None, others)

    def keeps_changes(self) -> bool:
        """
        Whether the disk, as saved and shown, has a private copy with
        changes, and its image its file.
        """

        disk = self.section.vm.disk(self.device)
        return (
            self.image is not None
            and self.image is disk.image
            and self.private
            and bool(disk.is_cow())
            and os.path.exists(disk.get_cow_path())
            and os.path.exists(self.image.get_path())
        )

    def save(self) -> SaveImageDialog:
        section = self.section
        dialog = SaveImageDialog(section.factory, section.vm, self.device)
        dialog.on_saved = self._saved
        dialog.on_done = self.update
        dialog.show(self._window())
        return dialog

    def _saved(self, image, use_it) -> None:
        # the row follows the disk, or OK would give it its old image
        if use_it:
            self.picker.choose(image)

    def merge(self) -> MergeDialog:
        section = self.section
        dialog = MergeDialog(section.factory, section.vm, self.device)
        dialog.on_saved = self._saved
        dialog.on_done = self.update
        dialog.show(self._window())
        return dialog

    def start_over(self) -> StartOverDialog:
        dialog = StartOverDialog(self.section.vm, self.device)
        dialog.on_done = self.update
        dialog.show(self._window())
        return dialog

    def show_in_files(self) -> None:
        show_in_files(self._window(), self.image.get_path())

    def remove(self) -> None:
        self.section.remove_disk(self.device)

    def _window(self):
        window = self.get_toplevel()
        return window if isinstance(window, Gtk.Window) else None


class DisksSection(Gtk.Box):
    """The disks of vm, and Add Disk."""

    def __init__(self, vm, factory, infos=None, manage=None) -> None:
        super().__init__(
            visible=True, orientation=Gtk.Orientation.VERTICAL, spacing=8
        )
        self.vm = vm
        self.factory = factory
        # the facts of the files, for all the pickers
        self.infos = images.InfoCache() if infos is None else infos
        # shows the Images tab
        self.manage = manage
        self.pack_start(_label(_("Disks"), bold=True), False, False, 0)
        self.list = Gtk.ListBox(
            visible=True, selection_mode=Gtk.SelectionMode.NONE
        )
        self.list.set_sort_func(
            lambda a, b: DISK_DEVICES.index(a.device)
            - DISK_DEVICES.index(b.device)
        )
        self.list.set_header_func(self._separate)
        self.list.set_placeholder(
            _label(
                _("No disk: add one to give the machine its disk."),
                dim=True,
                margin=12,
            )
        )
        frame = Gtk.Frame(visible=True)
        frame.add(self.list)
        self.pack_start(frame, False, False, 0)

        # Add Disk, and what goes beside it
        self.footer = Gtk.Box(visible=True, spacing=14)
        self.add_actions = Gio.SimpleActionGroup()
        add = Gio.SimpleAction.new("add", GLib.VariantType.new("s"))
        add.connect(
            "activate", lambda a, device: self.add_disk(device.unpack())
        )
        self.add_actions.add_action(add)
        self.insert_action_group("disks", self.add_actions)
        self.add_menu = Gio.Menu()
        self.add_button = Gtk.MenuButton(
            visible=True, menu_model=self.add_menu
        )
        box = Gtk.Box(visible=True, spacing=6)
        box.pack_start(
            Gtk.Image(visible=True, icon_name="list-add-symbolic"),
            False,
            False,
            0,
        )
        box.pack_start(_label(_("Add Disk")), False, False, 0)
        box.pack_start(
            Gtk.Image(visible=True, icon_name="pan-down-symbolic"),
            False,
            False,
            0,
        )
        self.add_button.add(box)
        self.footer.pack_start(self.add_button, False, False, 0)
        self.pack_start(self.footer, False, False, 0)

        for disk in vm.disks():
            if disk.image is not None:
                self.list.add(
                    DiskRow(self, disk.device, disk.image, disk.is_cow())
                )
        self._update_add()

    @staticmethod
    def _separate(row, before) -> None:
        if before is not None and row.get_header() is None:
            row.set_header(Gtk.Separator(visible=True))

    def row(self, device) -> DiskRow | None:
        for row in self.list.get_children():
            if row.device == device:
                return row
        return None

    def free(self) -> list[str]:
        """The devices without a disk, in order."""

        taken = {row.device for row in self.list.get_children()}
        return [device for device in DISK_DEVICES if device not in taken]

    def _update_add(self) -> None:
        self.add_menu.remove_all()
        for device in self.free():
            item = Gio.MenuItem.new(device, None)
            item.set_action_and_target_value(
                "disks.add", GLib.Variant.new_string(device)
            )
            self.add_menu.append_item(item)
        self.add_button.set_sensitive(bool(self.free()))

    def add_disk(self, device) -> DiskRow:
        """A disk on device, without an image yet, with a private copy."""

        row = DiskRow(self, device, None, True)
        self.list.add(row)
        self._update_add()
        return row

    def remove_disk(self, device) -> None:
        row = self.row(device)
        if row is not None:
            row.destroy()
            # the next row has no row above it any more
            for other in self.list.get_children():
                other.set_header(None)
            self.list.invalidate_headers()
        self._update_add()

    def apply(self) -> dict:
        """
        Give the images to the machine; return the modes of its disks as
        its settings. A device without a disk loses its image.
        """

        settings = {}
        for device in DISK_DEVICES:
            row = self.row(device)
            self.vm.set_image(device, None if row is None else row.image)
            if row is not None:
                settings["private" + device] = row.private
        return settings
