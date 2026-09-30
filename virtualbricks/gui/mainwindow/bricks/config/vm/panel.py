# -*- test-case-name: virtualbricks.tests.gui.mainwindow.bricks.config.vm.test_panel -*-
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
The panel of a virtual machine: the sidebar, its sections, and the answers
of the machine's QEMU program.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402
from twisted.logger import Logger  # noqa: E402

from virtualbricks.gui.mainwindow.bricks.config.form import Form  # noqa: E402
from virtualbricks.gui.mainwindow.bricks.config.panel import (
    Panel,
)  # noqa: E402
from virtualbricks.gui.mainwindow.bricks.config.vm import (  # noqa: E402
    devices,
    machine,
    media,
    network,
    system,
)
from virtualbricks.i18n import _  # noqa: E402

logger = Logger()
qemu_error = "Cannot ask {program} what it has"
SIDEBAR_WIDTH = 170
GAP = 8


class Page:
    """
    A section of the sidebar: its key, its title and its form, and the keys
    of its problems that aren't rows.
    """

    def __init__(self, key: str, title: str, form: Form) -> None:
        self.key = key
        self.title = title
        self.form = form
        self.keys: set[str] = set()

    def has(self, key: str) -> bool:
        if key in self.keys or key in self.form.rows:
            return True
        return any(key in row.parts for row in self.form.rows.values())


class SidebarRow(Gtk.ListBoxRow):
    """A section in the sidebar, with a mark when it has a problem."""

    def __init__(self, page: Page) -> None:
        super().__init__(visible=True)
        self.page = page
        box = Gtk.Box(visible=True, spacing=GAP, margin=GAP, margin_start=12)
        box.pack_start(
            Gtk.Label(visible=True, xalign=0.0, label=page.title),
            True,
            True,
            0,
        )
        self.mark = Gtk.Image(icon_name="dialog-warning-symbolic")
        box.pack_start(self.mark, False, False, 0)
        self.add(box)

    def show_problems(self, error: bool, lack: bool) -> None:
        if error:
            self.mark.set_from_icon_name(
                "dialog-error-symbolic", Gtk.IconSize.MENU
            )
        else:
            self.mark.set_from_icon_name(
                "dialog-warning-symbolic", Gtk.IconSize.MENU
            )
        self.mark.set_visible(error or lack)


# The sections, in the order of the sidebar, and what builds each.
SECTIONS = (
    ("machine", _("Machine"), machine.build),
    ("disks", _("Disks"), media.build_disks),
    ("cdrom", _("CD-ROM and boot"), media.build_cdrom),
    ("network", _("Network"), network.build),
    ("display", _("Display"), devices.build_display),
    ("sound", _("Sound and USB"), devices.build_sound),
    ("kernel", _("Kernel"), system.build_kernel),
    ("advanced", _("Advanced"), system.build_advanced),
)


class VirtualMachinePanel(Panel):
    """The settings of a virtual machine."""

    def build(self, form):
        self.pages: list[Page] = []
        # called when the rows refresh, and when the QEMU answers
        self.refreshers = []
        self.fillers = []
        self.asked = None
        self.stack = Gtk.Stack(visible=True, vhomogeneous=False)
        self.sidebar = Gtk.ListBox(visible=True)
        self.sidebar.connect("row-selected", self.on_section_selected)
        for key, title, build in SECTIONS:
            page = Page(
                key,
                title,
                (
                    form
                    if key == "machine"
                    else Form(self.draft, self.on_changed, self.form.engine)
                ),
            )
            build(self, page)
            self.pages.append(page)
            self.stack.add_named(page.form.widget, key)
            self.sidebar.add(SidebarRow(page))
        self.sidebar.select_row(self.sidebar.get_row_at_index(0))

        self.status = Gtk.InfoBar(visible=True)
        self.status_words = Gtk.Label(visible=True, xalign=0.0, wrap=True)
        self.status.get_content_area().add(self.status_words)
        frame = Gtk.Frame(
            visible=True, width_request=SIDEBAR_WIDTH, valign=Gtk.Align.START
        )
        frame.add(self.sidebar)
        split = Gtk.Box(visible=True, spacing=12)
        split.pack_start(frame, False, False, 0)
        split.pack_start(self.stack, True, True, 0)
        root = Gtk.Box(
            visible=True, orientation=Gtk.Orientation.VERTICAL, spacing=GAP
        )
        root.pack_start(self.status, False, False, 0)
        root.pack_start(split, True, True, 0)
        self.ask()
        return root

    def page(self, key: str) -> Page:
        for page in self.pages:
            if page.key == key:
                return page
        raise KeyError(key)

    @property
    def rows(self) -> dict:
        rows = {}
        for page in self.pages:
            rows.update(page.form.rows)
        return rows

    def refresh(self) -> None:
        for page in self.pages:
            page.form.refresh()
        for refresh in self.refreshers:
            refresh()
        problems = self.draft.problems()
        for row in self.sidebar.get_children():
            found = [p for p in problems if row.page.has(p.key)]
            row.show_problems(
                any(p.error for p in found), any(not p.error for p in found)
            )

    def on_changed(self) -> None:
        super().on_changed()
        wanted = (
            self.draft.get("qemu_program"),
            self.draft.get("machine_type"),
        )
        if self.asked is not None and wanted != self.asked:
            self.ask()

    def on_section_selected(self, listbox, row) -> None:
        if row is not None:
            self.stack.set_visible_child_name(row.page.key)

    # the answers of the QEMU program

    def ask(self) -> None:
        program = self.draft.get("qemu_program")
        chosen = self.draft.get("machine_type")
        self.asked = (program, chosen)
        deferred = self.engine.qemu(program)
        deferred.addCallbacks(
            self.answered,
            self.not_answered,
            (program, chosen),
            None,
            (program, chosen),
        )

    def not_answered(self, failure, program: str, chosen: str) -> None:
        if self.asked != (program, chosen):
            return
        if not failure.check(FileNotFoundError):
            logger.failure(qemu_error, failure, program=program)
            return
        self.draft.qemu = None
        self.draft.machine_properties = frozenset()
        self.show_status(
            _(
                "{program} isn't in {folder}: the lists show only"
                " {brick}'s choices"
            ).format(
                program=program,
                folder=self.engine.machine.setting("qemu_path"),
                brick=self.draft.brick.name,
            ),
            Gtk.MessageType.WARNING,
        )
        self.fill()

    def answered(self, info, program: str, chosen: str) -> None:
        if self.asked != (program, chosen):
            return
        self.draft.qemu = info
        self.show_status(
            _("QEMU {version}, {path}").format(
                version=info.version, path=info.path
            ),
            Gtk.MessageType.INFO,
        )
        self.fill()
        self.on_changed()
        machine_type = chosen if info.has_machine(chosen) else ""
        deferred = self.engine.machine_properties(info, machine_type)
        deferred.addCallback(self.described, program, chosen)
        deferred.addErrback(
            lambda failure: logger.failure(
                qemu_error, failure, program=info.path
            )
        )

    def described(self, properties, program: str, chosen: str) -> None:
        if self.asked != (program, chosen):
            return
        self.draft.machine_properties = properties
        self.on_changed()

    def show_status(self, words: str, kind: Gtk.MessageType) -> None:
        self.status_words.set_text(words)
        self.status.set_message_type(kind)

    def fill(self) -> None:
        """The lists of the pickers, from the answers."""

        for fill in self.fillers:
            fill()
