# -*- test-case-name: virtualbricks.tests.gui.mainwindow.images.test_imagedetails -*-
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
The details of a disk image, in the Images tab, as the settings of a brick.

The name and the description can change; OK saves them, and a new name
reaches the disks that use the image. The rest is what ``qemu-img info``
and the project say: the file, its format and backing file, the sizes, the
snapshots, when the file changed, each disk that uses the image with its
mode and its machine's state, and the other projects that use the file.
"""

from __future__ import annotations

import os
import time

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Pango  # noqa: E402
from twisted.logger import Logger  # noqa: E402

from virtualbricks import errors  # noqa: E402
from virtualbricks.config import images  # noqa: E402
from virtualbricks.config.workspace import projects  # noqa: E402
from virtualbricks.gui import imageinfo  # noqa: E402
from virtualbricks.gui.windows.base import (  # noqa: E402
    ConfigController,
    pango_attr_list,
)
from virtualbricks.i18n import _, ngettext  # noqa: E402

logger = Logger()
invalid_name = "Cannot rename the image {name}: {error}"

GAP = 8
# the facts of a file that qemu-img reads
READING = object()


def _label(text="", dim=False, bold=False, **props):
    label = Gtk.Label(visible=True, label=text, xalign=0.0, **props)
    if dim:
        label.get_style_context().add_class("dim-label")
    if bold:
        label.set_attributes(
            pango_attr_list(Pango.attr_weight_new(Pango.Weight.BOLD))
        )
    return label


def mode_words(use) -> str:
    """How a disk uses its image: its private copy, or the image itself."""

    if not use.private:
        return _("the image itself")
    copy = os.path.basename(use.copy)
    if use.copy_size is None:
        return _("private copy {file}, made at the next start").format(
            file=copy
        )
    return _("private copy {file}, {size}").format(
        file=copy, size=imageinfo.human_size(use.copy_size)
    )


class ImageDetails(ConfigController):
    """The name, the description and the facts of an image."""

    def __init__(self, original, factory, infos, workspace=None) -> None:
        self.factory = factory
        # the facts of the files, which the list of the tab reads too
        self.infos = infos
        self.workspace = projects if workspace is None else workspace
        super().__init__(original)

    def build_ui(self) -> None:
        image = self.original
        self.panel = Gtk.Box(
            visible=True, orientation=Gtk.Orientation.VERTICAL, spacing=14
        )

        form = Gtk.Grid(visible=True, row_spacing=GAP, column_spacing=12)
        label = _label(_("Name"), bold=True)
        self.name_entry = Gtk.Entry(
            visible=True, hexpand=True, text=image.get_name()
        )
        label.set_mnemonic_widget(self.name_entry)
        form.attach(label, 0, 0, 1, 1)
        form.attach(self.name_entry, 1, 0, 1, 1)
        label = _label(_("Description"), bold=True, valign=Gtk.Align.START)
        scrolled = Gtk.ScrolledWindow(
            visible=True,
            shadow_type=Gtk.ShadowType.IN,
            min_content_height=60,
            hexpand=True,
        )
        self.description_view = Gtk.TextView(
            visible=True, wrap_mode=Gtk.WrapMode.WORD_CHAR
        )
        self.description_view.get_buffer().set_text(image.get_description())
        scrolled.add(self.description_view)
        label.set_mnemonic_widget(self.description_view)
        form.attach(label, 0, 1, 1, 1)
        form.attach(scrolled, 1, 1, 1, 1)
        self.panel.pack_start(form, False, False, 0)

        self.facts = Gtk.Grid(visible=True, row_spacing=4, column_spacing=18)
        self.panel.pack_start(self.facts, False, False, 0)
        self.read_facts()

        self.panel.pack_start(_label(_("Used by"), bold=True), False, False, 0)
        self.uses = Gtk.Grid(visible=True, row_spacing=4, column_spacing=14)
        self.panel.pack_start(self.uses, False, False, 0)
        self.show_uses()

        others = images.other_projects(self.workspace, image.get_path())
        self.others = _label(dim=True, wrap=True)
        if others:
            self.others.set_text(
                ngettext(
                    "The project {names} uses the same file.",
                    "The projects {names} use the same file.",
                    len(others),
                ).format(
                    names=imageinfo.names(
                        [
                            _("{project}, as {image}").format(
                                project=project, image=name
                            )
                            for project, name in others
                        ]
                    )
                )
            )
        # no gap for no project
        self.others.set_visible(bool(others))
        self.panel.pack_start(self.others, False, False, 0)

    def read_facts(self) -> None:
        """Show the facts of the file, and read them first if needed."""

        path = self.original.get_path()
        info = self.infos.get(path)
        if info is not None or not os.path.exists(path):
            self.show_facts(info)
            return
        self.show_facts(READING)
        # what the read says, once: a file that can't be read, or that a
        # machine keeps changing, is read again only when the details open
        self.infos.read(path).addCallbacks(
            self.show_facts, lambda failure: self.show_facts(None)
        )

    def fact_rows(self, info) -> list[tuple[str, str]]:
        """
        The facts of the image, a name and a value each. info is what
        qemu-img info says of the file, None if it can't read it, or
        READING.
        """

        path = self.original.get_path()
        rows = [(_("File"), imageinfo.short_path(path))]
        if not os.path.exists(path):
            rows.append((_("State"), _("The file isn't there")))
            return rows
        if info is READING:
            rows.append((_("Format"), "\N{HORIZONTAL ELLIPSIS}"))
            return rows
        if info is None:
            rows.append((_("Format"), _("Unknown")))
            return rows
        backing = info.backing_file
        rows.append(
            (
                _("Format"),
                (
                    info.format
                    if not backing
                    else _("{format}, above {file}").format(
                        format=info.format, file=imageinfo.short_path(backing)
                    )
                ),
            )
        )
        rows.append(
            (
                _("Size"),
                _("{disk} disk, {taken} on disk").format(
                    disk=imageinfo.human_size(info.virtual_size),
                    taken=imageinfo.human_size(info.actual_size),
                ),
            )
        )
        if info.snapshots:
            rows.append((_("Snapshots"), ", ".join(info.snapshots)))
        changed = time.localtime(os.stat(path).st_mtime)
        rows.append((_("Changed"), time.strftime("%x %X", changed)))
        return rows

    def show_facts(self, info) -> None:
        for child in self.facts.get_children():
            child.destroy()
        for row, (name, value) in enumerate(self.fact_rows(info)):
            self.facts.attach(_label(name, dim=True), 0, row, 1, 1)
            self.facts.attach(
                _label(
                    value,
                    selectable=True,
                    ellipsize=Pango.EllipsizeMode.MIDDLE,
                ),
                1,
                row,
                1,
                1,
            )

    def show_uses(self) -> None:
        uses = images.uses(self.factory, self.original)
        if not uses:
            self.uses.attach(
                _label(_("No disk uses it."), dim=True), 0, 0, 1, 1
            )
            return
        for row, use in enumerate(uses):
            state = _("Running") if use.running else _("Stopped")
            for column, label in enumerate(
                (
                    _label(use.vm.get_name(), bold=True),
                    _label(use.device, dim=True),
                    _label(mode_words(use), hexpand=True),
                    _label(state, dim=not use.running),
                )
            ):
                self.uses.attach(label, column, row, 1, 1)

    def get_config_view(self, gui):
        return self.panel

    def configure_brick(self, gui) -> None:
        image = self.original
        name = self.name_entry.get_text()
        if name != image.get_name():
            try:
                # through the factory: the disks follow
                self.factory.rename(image, name)
            except errors.InvalidNameError as exc:
                logger.error(invalid_name, name=image.get_name(), error=exc)
        buffer = self.description_view.get_buffer()
        image.set_description(
            buffer.get_text(
                buffer.get_start_iter(), buffer.get_end_iter(), False
            )
        )
