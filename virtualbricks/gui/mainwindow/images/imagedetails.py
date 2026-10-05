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

The name and the description can change, on a draft of the image,
:class:`virtualbricks.bricks.virtualmachine.ImageDraft`: a name that can't be
the image's says why under it, and OK waits for a good one. OK saves them,
and a new name reaches the disks that use the image. The rest is what
``qemu-img info`` and the project say: the file, its format and backing
file, the sizes, the snapshots, when the file changed, each disk that uses
the image with its mode and its machine's state, and the other projects that
use the file.
"""

from __future__ import annotations

import os
import time

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Pango  # noqa: E402

from virtualbricks.config import images  # noqa: E402
from virtualbricks.gui import imageinfo  # noqa: E402
from virtualbricks.gui.pango import pango_attr_list  # noqa: E402
from virtualbricks.gui.form import (  # noqa: E402
    show_problem,
)
from virtualbricks.gui.mainwindow.bricks.config.panel import (  # noqa: E402
    Panel,
)
from virtualbricks.i18n import _, ngettext  # noqa: E402

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
    if use.copy is None:
        # no project open
        return _("private copy")
    copy = os.path.basename(use.copy)
    if use.copy_size is None:
        return _("private copy {file}, made at the next start").format(
            file=copy
        )
    return _("private copy {file}, {size}").format(
        file=copy, size=imageinfo.human_size(use.copy_size)
    )


class ImageDetails(Panel):
    """The name, the description and the facts of an image, on a draft."""

    def __init__(self, draft, machine) -> None:
        self.image = draft.brick
        self.factory = draft.factory
        # what the windows read of the machine of the bricks: the facts of
        # the files, which the list of the tab reads too
        self.machine = machine
        self.infos = machine.infos
        super().__init__(draft)

    def build(self, form) -> Gtk.Box:
        self.panel = Gtk.Box(
            visible=True, orientation=Gtk.Orientation.VERTICAL, spacing=14
        )

        label = _label(_("Name"), bold=True)
        self.name_entry = Gtk.Entry(
            visible=True, hexpand=True, text=self.draft.get("name")
        )
        self.name_entry.connect("changed", self.on_name_changed)
        label.set_mnemonic_widget(self.name_entry)
        # why the name can't be the image's
        self.name_problem = _label(wrap=True)
        grid = Gtk.Grid(visible=True, row_spacing=GAP, column_spacing=12)
        grid.attach(label, 0, 0, 1, 1)
        grid.attach(self.name_entry, 1, 0, 1, 1)
        grid.attach(self.name_problem, 1, 1, 1, 1)
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
        buffer = self.description_view.get_buffer()
        buffer.set_text(self.draft.get("description"))
        buffer.connect("changed", self.on_description_changed)
        scrolled.add(self.description_view)
        label.set_mnemonic_widget(self.description_view)
        grid.attach(label, 0, 2, 1, 1)
        grid.attach(scrolled, 1, 2, 1, 1)
        self.panel.pack_start(grid, False, False, 0)

        self.facts = Gtk.Grid(visible=True, row_spacing=4, column_spacing=18)
        self.panel.pack_start(self.facts, False, False, 0)

        self.panel.pack_start(_label(_("Used by"), bold=True), False, False, 0)
        self.uses = Gtk.Grid(visible=True, row_spacing=4, column_spacing=14)
        self.panel.pack_start(self.uses, False, False, 0)
        self.show_uses()

        self.others = _label(dim=True, wrap=True)
        self.panel.pack_start(self.others, False, False, 0)
        self.read_facts()
        return self.panel

    def show_others(self) -> None:
        """The other projects with the file: known once the file is read."""

        others = self.machine.other_projects(self.image.path)
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

    def refresh(self) -> None:
        super().refresh()
        problems = [p for p in self.draft.problems() if p.key == "name"]
        problem = problems[0] if problems else None
        show_problem(self.name_problem, problem)
        context = self.name_entry.get_style_context()
        if problem is None:
            context.remove_class("error")
        else:
            context.add_class("error")

    def running(self) -> bool:
        # a machine that uses the image keeps its file, whatever its name
        return False

    def read_facts(self) -> None:
        """Show the facts of the file, and read them first if needed."""

        path = self.image.path
        info = self.infos.get(path)
        if info is not None or not self.machine.exists(path):
            self.show_facts(info)
            self.show_others()
            return
        self.show_facts(READING)
        self.show_others()
        # what the read says, once: a file that can't be read, or that a
        # machine keeps changing, is read again only when the details open
        reading = self.infos.read(path)
        reading.addCallbacks(
            self.show_facts, lambda failure: self.show_facts(None)
        )
        reading.addCallback(lambda _: self.show_others())

    def fact_rows(self, info) -> list[tuple[str, str]]:
        """
        The facts of the image, a name and a value each. info is what
        qemu-img info says of the file, None if it can't read it, or
        READING.
        """

        path = self.image.path
        rows = [(_("File"), imageinfo.short_path(path))]
        if not self.machine.exists(path):
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
        changed = self.machine.changed(path)
        if changed is not None:
            rows.append(
                (_("Changed"), time.strftime("%x %X", time.localtime(changed)))
            )
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
        uses = images.uses(self.factory, self.image, self.machine.taken)
        if not uses:
            self.uses.attach(
                _label(_("No disk uses it."), dim=True), 0, 0, 1, 1
            )
            return
        for row, use in enumerate(uses):
            state = _("Running") if use.running else _("Stopped")
            for column, label in enumerate(
                (
                    _label(use.vm.name, bold=True),
                    _label(use.device, dim=True),
                    _label(mode_words(use), hexpand=True),
                    _label(state, dim=not use.running),
                )
            ):
                self.uses.attach(label, column, row, 1, 1)

    # Signals

    def on_name_changed(self, entry) -> None:
        self.draft.set("name", entry.get_text())
        self.on_changed()

    def on_description_changed(self, buffer) -> None:
        text = buffer.get_text(
            buffer.get_start_iter(), buffer.get_end_iter(), False
        )
        self.draft.set("description", text)
        self.on_changed()
