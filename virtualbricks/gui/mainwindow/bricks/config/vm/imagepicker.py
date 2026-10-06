# -*- test-case-name: virtualbricks.tests.gui.mainwindow.bricks.config.vm.test_imagepicker -*-
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
The picker of the image of a disk: a button that shows the image, and a
popover with a search, the images of the library, No image, then Add an
Existing Image…, New Empty Disk… and Manage Images….

An image says its format, the size of its disk and the other machines that
use it, read with ``qemu-img info`` as the popover opens; an image whose
file is missing can't be chosen. What the Add items add is chosen for the
disk. Choosing emits ``chosen``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, TypeAlias

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GObject, Gtk, Pango

from virtualbricks.bricks.virtualmachine import Image, VirtualMachine
from virtualbricks.config import images
from virtualbricks.config.images import ImageInfo, InfoCache
from virtualbricks.engine import Engine
from virtualbricks.gui import imageinfo
from virtualbricks.gui.dialogs.addimage import (
    ExistingImageDialog,
    NewDiskDialog,
)
from virtualbricks.gui.pango import pango_attr_list
from virtualbricks.i18n import _

if TYPE_CHECKING:  # pragma: no cover
    from virtualbricks.remote.client import RemoteInfos

    # what the machine of the bricks says of its files
    Infos: TypeAlias = InfoCache | RemoteInfos

GAP = 10


def _label(
    text: str = "", dim: bool = False, bold: bool = False, **props: Any
) -> Gtk.Label:
    label = Gtk.Label(visible=True, label=text, xalign=0.0, **props)
    if dim:
        label.get_style_context().add_class("dim-label")
    if bold:
        label.set_attributes(
            pango_attr_list(Pango.attr_weight_new(Pango.Weight.BOLD))
        )
    return label


def _two_lines(name: Gtk.Widget, words: Gtk.Widget) -> Gtk.Box:
    box = Gtk.Box(
        visible=True, orientation=Gtk.Orientation.VERTICAL, hexpand=True
    )
    box.pack_start(name, False, False, 0)
    box.pack_start(words, False, False, 0)
    return box


class ImageOption(Gtk.ListBoxRow):
    """An image of the list of the picker, or No image."""

    def __init__(self, image: Image | None, chosen: bool) -> None:
        super().__init__(visible=True)
        self.image = image
        box = Gtk.Box(visible=True, spacing=GAP, margin=6)
        # the mark of the chosen image; the others keep its place
        check = Gtk.Image(visible=True, icon_name="object-select-symbolic")
        check.set_opacity(1.0 if chosen else 0.0)
        box.pack_start(check, False, False, 0)
        if image is None:
            name = _label(_("No image"), dim=True)
        else:
            name = _label(image.name, bold=True)
        self.words = _label(dim=True, ellipsize=Pango.EllipsizeMode.END)
        self.words.get_style_context().add_class("caption")
        box.pack_start(_two_lines(name, self.words), True, True, 0)
        self.add(box)
        self.show_words("")

    def show_words(self, text: str) -> None:
        self.words.set_text(text)
        self.words.set_visible(bool(text))


class ImagePicker(Gtk.MenuButton):
    """The image of a disk of vm, and the images to choose from."""

    __gsignals__ = {"chosen": (GObject.SignalFlags.RUN_FIRST, None, ())}

    def __init__(
        self,
        engine: Engine,
        vm: VirtualMachine,
        image: Image | None = None,
        infos: Infos | None = None,
        manage: Callable[[], object] | None = None,
    ) -> None:
        super().__init__(visible=True, hexpand=True)
        # it adds images; they are those of its factory
        self.engine = engine
        self.factory = engine.factory
        self.vm = vm
        self.image = image
        # the facts of the files, which the other pickers share
        self.infos = engine.machine.infos if infos is None else infos
        # shows the Images tab
        self.manage = manage
        self.build_ui()
        self.show_image()

    def build_ui(self) -> None:
        box = Gtk.Box(visible=True, spacing=GAP)
        box.pack_start(
            Gtk.Image(visible=True, icon_name="drive-harddisk-symbolic"),
            False,
            False,
            0,
        )
        self.name_label = _label(bold=True)
        self.facts_label = _label(dim=True, ellipsize=Pango.EllipsizeMode.END)
        box.pack_start(
            _two_lines(self.name_label, self.facts_label), True, True, 0
        )
        box.pack_start(
            Gtk.Image(visible=True, icon_name="pan-down-symbolic"),
            False,
            False,
            0,
        )
        self.add(box)

        self.popover = Gtk.Popover(width_request=400)
        content = Gtk.Box(
            visible=True, orientation=Gtk.Orientation.VERTICAL, spacing=6
        )
        content.set_property("margin", 6)
        self.search = Gtk.SearchEntry(
            visible=True, placeholder_text=_("Find an image")
        )
        self.search.connect(
            "search-changed", lambda entry: self.list.invalidate_filter()
        )
        content.pack_start(self.search, False, False, 0)
        self.list = Gtk.ListBox(visible=True)
        self.list.set_filter_func(self._visible)
        self.list.connect("row-activated", self.on_row_activated)
        scrolled = Gtk.ScrolledWindow(
            visible=True,
            hscrollbar_policy=Gtk.PolicyType.NEVER,
            propagate_natural_height=True,
            max_content_height=320,
        )
        scrolled.add(self.list)
        content.pack_start(scrolled, True, True, 0)
        content.pack_start(Gtk.Separator(visible=True), False, False, 0)
        self.add_buttons = []
        for label, icon, callback in (
            (
                _("Add an Existing Image…"),
                "document-open-symbolic",
                self.add_existing,
            ),
            (_("New Empty Disk…"), "list-add-symbolic", self.add_new),
            (
                _("Manage Images…"),
                "drive-multidisk-symbolic",
                self.manage_images,
            ),
        ):
            button = Gtk.Button(
                visible=True,
                relief=Gtk.ReliefStyle.NONE,
            )
            item = Gtk.Box(visible=True, spacing=GAP)
            item.pack_start(
                Gtk.Image(visible=True, icon_name=icon), False, False, 0
            )
            item.pack_start(_label(label), False, False, 0)
            button.add(item)
            button.connect("clicked", lambda button, call=callback: call())
            content.pack_start(button, False, False, 0)
            self.add_buttons.append(button)
        self.popover.add(content)
        self.popover.connect("show", lambda popover: self.fill())
        self.set_popover(self.popover)

    # The button

    def show_image(self) -> None:
        """Show the image chosen and what it is."""

        image = self.image
        if image is None:
            self.name_label.set_text(_("No image"))
            self.facts_label.set_text(_("Choose an image for this disk"))
            return
        self.name_label.set_text(image.name)
        path = image.path
        if not self.engine.machine.exists(path):
            self.facts_label.set_text(
                _("{path} isn't there").format(path=imageinfo.short_path(path))
            )
            return
        info = self.infos.get(path)
        if info is not None:
            self.facts_label.set_text(imageinfo.facts(info))
            return
        self.facts_label.set_text("")
        reading = self.infos.read(path)
        reading.addCallbacks(
            self._read, lambda failure: None, callbackArgs=(image,)
        )

    def _read(self, info: ImageInfo, image: Image) -> None:
        # another may be chosen by now
        if image is self.image:
            self.facts_label.set_text(imageinfo.facts(info))

    def choose(self, image: Image | None) -> None:
        """Make image the image of the disk, and say so."""

        self.image = image
        self.show_image()
        self.emit("chosen")

    # The popover

    def options(self) -> list[ImageOption]:
        return [
            row
            for row in self.list.get_children()
            if isinstance(row, ImageOption)
        ]

    def fill(self) -> None:
        """The images of the library, as they are now, then No image."""

        for option in self.options():
            option.destroy()
        self.search.set_text("")
        for image in self.factory.images:
            option = ImageOption(image, image is self.image)
            self.list.add(option)
            self.show_option(option)
        self.list.add(ImageOption(None, self.image is None))
        self.search.grab_focus()

    def show_option(
        self, option: ImageOption, info: ImageInfo | None = None
    ) -> None:
        image = option.image
        assert image is not None, "No image has nothing to show"
        path = image.path
        machine = self.engine.machine
        there = machine.exists(path)
        option.set_sensitive(there)
        if there and info is None:
            info = self.infos.get(path)
        uses = images.uses(self.factory, image, machine.taken)
        option.show_words(
            imageinfo.option_words(image, info, uses, self.vm, there)
        )
        # the facts, once read: after what is known now
        if there and info is None:
            self.infos.read(path).addCallbacks(
                lambda info: self.show_option(option, info),
                lambda failure: None,
            )

    def _visible(self, option: Gtk.ListBoxRow) -> bool:
        assert isinstance(option, ImageOption), "the list has images"
        text = self.search.get_text().strip().lower()
        if option.image is None:
            return not text
        return text in option.image.name.lower()

    def on_row_activated(
        self, listbox: Gtk.ListBox, option: ImageOption
    ) -> None:
        self.popover.popdown()
        self.choose(option.image)

    def _window(self) -> Gtk.Window | None:
        window = self.get_toplevel()
        return window if isinstance(window, Gtk.Window) else None

    def add_existing(self) -> ExistingImageDialog:
        self.popover.popdown()
        dialog = ExistingImageDialog(self.engine)
        dialog.on_added = self.choose
        dialog.show(self._window())
        return dialog

    def add_new(self) -> NewDiskDialog:
        self.popover.popdown()
        dialog = NewDiskDialog(self.engine)
        dialog.on_added = self.choose
        dialog.show(self._window())
        return dialog

    def manage_images(self) -> None:
        self.popover.popdown()
        if self.manage is not None:
            self.manage()
