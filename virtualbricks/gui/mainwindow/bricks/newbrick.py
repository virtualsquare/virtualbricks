# -*- test-case-name: virtualbricks.tests.gui.mainwindow.bricks.test_newbrick -*-
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
New Brick: a popover of the kinds of bricks, under the button.

The kinds are those of :data:`brickinfo.NEW_KINDS`, in their groups. Each is
a row: its picture, its name and a line, which says what it is or, when this
computer lacks a program of its bricks, the issue, after a warning sign. The
tooltip says more, the issue first. The rows say it again each time the
popover opens: a program may have been installed since.

A click on a row, or Enter, makes a brick of the kind, named after it, as
``tap1``, and hands it on; the popover opens next on that kind. A kind with an
issue can still be made: its bricks start once the program is installed. A
row is greyed only when the name wouldn't fit the sockets of the project, and
its tooltip says why.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GdkPixbuf, GLib, Gtk, Pango  # noqa: E402

from virtualbricks import errors  # noqa: E402
from virtualbricks.config.settings import get_setting  # noqa: E402
from virtualbricks.gui import graphics  # noqa: E402
from virtualbricks.gui.mainwindow.bricks.brickinfo import (  # noqa: E402
    NEW_KINDS,
    issue,
    new_name,
)
from virtualbricks.gui.mainwindow.rowtab import styled  # noqa: E402
from virtualbricks.gui.pango import pango_attr_list  # noqa: E402

ICON_SIZE = 24
# The longest line, in characters: the tooltip has it whole.
LINE_CHARS = 40
MARGIN = 6


def picture(kind) -> GdkPixbuf.Pixbuf | None:
    """The picture of the bricks of kind, at the size of a row."""

    filename = graphics.get_data_filename(kind.type.lower() + ".png")
    try:
        return GdkPixbuf.Pixbuf.new_from_file_at_size(
            filename, ICON_SIZE, ICON_SIZE
        )
    except GLib.Error:
        return None


class KindRow(Gtk.ListBoxRow):
    """A kind of brick, and what this computer has for it."""

    def __init__(self, kind) -> None:
        super().__init__(visible=True)
        self.kind = kind
        box = Gtk.Box(
            visible=True,
            spacing=10,
            margin_start=2 * MARGIN,
            margin_end=2 * MARGIN,
            margin_top=MARGIN // 2,
            margin_bottom=MARGIN // 2,
        )
        image = Gtk.Image(visible=True, pixel_size=ICON_SIZE)
        pixbuf = picture(kind)
        if pixbuf is None:
            image.set_from_icon_name(
                "image-missing", Gtk.IconSize.LARGE_TOOLBAR
            )
        else:
            image.set_from_pixbuf(pixbuf)
        box.pack_start(image, False, False, 0)

        text = Gtk.Box(visible=True, orientation=Gtk.Orientation.VERTICAL)
        self.name = Gtk.Label(visible=True, label=kind.words, xalign=0.0)
        self.warning = styled(
            Gtk.Image.new_from_icon_name(
                "dialog-warning-symbolic", Gtk.IconSize.MENU
            ),
            "state-warning",
        )
        self.line = Gtk.Label(
            visible=True,
            xalign=0.0,
            ellipsize=Pango.EllipsizeMode.END,
            max_width_chars=LINE_CHARS,
        )
        line = Gtk.Box(visible=True, spacing=5)
        line.pack_start(self.warning, False, False, 0)
        line.pack_start(self.line, True, True, 0)
        text.pack_start(self.name, False, False, 0)
        text.pack_start(line, False, False, 0)
        box.pack_start(text, True, True, 0)
        self.add(box)
        self.show_kind()

    def show_kind(self) -> None:
        """What the kind is, and nothing in the way."""

        self._show(self.kind.line, None, True)

    def show_issue(self, found) -> None:
        """A program is missing: the bricks can be made, and won't start."""

        self._show(found.line, found.text, True)

    def show_refused(self, reason: str) -> None:
        """No brick of the kind can be made, for reason."""

        self._show(self.kind.line, reason, False)

    def _show(self, line: str, first: str | None, sensitive: bool) -> None:
        issue_shown = first is not None and sensitive
        self.line.set_text(line)
        context = self.line.get_style_context()
        if issue_shown:
            context.remove_class("dim-label")
        else:
            context.add_class("dim-label")
        self.warning.set_visible(issue_shown)
        about = self.kind.about
        self.set_tooltip_text(
            about if first is None else f"{first}\n\n{about}"
        )
        self.set_sensitive(sensitive)


def _group_header(row, before) -> None:
    """A title over the first row of each group, a line above all but one."""

    if before is not None and before.kind.group == row.kind.group:
        row.set_header(None)
        return
    if row.get_header() is not None:
        return
    header = Gtk.Box(visible=True, orientation=Gtk.Orientation.VERTICAL)
    if before is not None:
        header.pack_start(
            Gtk.Separator(visible=True, margin_top=MARGIN // 2),
            False,
            False,
            0,
        )
    title = Gtk.Label(
        visible=True,
        label=row.kind.group,
        xalign=0.0,
        margin_start=2 * MARGIN,
        margin_top=MARGIN,
        margin_bottom=MARGIN // 2,
        attributes=pango_attr_list(Pango.attr_weight_new(Pango.Weight.BOLD)),
    )
    title.get_style_context().add_class("dim-label")
    header.pack_start(title, False, False, 0)
    row.set_header(header)


class NewBrickPopover(Gtk.Popover):
    """
    The kinds of bricks, to make one of them; made(brick) gets each brick
    made. The popover stays, from one opening to the next.
    """

    def __init__(self, factory, made) -> None:
        super().__init__(position=Gtk.PositionType.BOTTOM)
        self.factory = factory
        self.made = made
        # the kind of the brick made last, where the popover opens
        self.last = None
        self.list = Gtk.ListBox(
            visible=True,
            selection_mode=Gtk.SelectionMode.BROWSE,
            margin_bottom=MARGIN,
        )
        self.list.set_header_func(_group_header)
        self.rows = [KindRow(kind) for kind in NEW_KINDS]
        for row in self.rows:
            self.list.add(row)
        self.add(self.list)
        self.list.connect("row-activated", self.on_row_activated)

    def popup_at(self, widget) -> None:
        """Open under widget, on the kind made last or else the first."""

        self.set_relative_to(widget)
        self.refresh()
        row = self.row_to_open_on()
        self.list.select_row(row)
        self.popup()
        row.grab_focus()

    def row_to_open_on(self) -> KindRow:
        for row in self.rows:
            if row.kind is self.last and row.get_sensitive():
                return row
        return self.rows[0]

    def refresh(self) -> None:
        """Say what each kind lacks on this computer, today."""

        vde_folder = get_setting("vde_path")
        qemu_folder = get_setting("qemu_path")
        for row in self.rows:
            kind = row.kind
            try:
                self.factory.check_name(
                    kind.type, new_name(self.factory, kind)
                )
            except errors.InvalidNameError as exc:
                row.show_refused(str(exc))
                continue
            found = issue(kind, vde_folder, qemu_folder)
            if found is None:
                row.show_kind()
            else:
                row.show_issue(found)

    def on_row_activated(self, listbox, row) -> None:
        self.popdown()
        kind = row.kind
        brick = self.factory.new_brick(kind.type, new_name(self.factory, kind))
        self.last = kind
        self.made(brick)
