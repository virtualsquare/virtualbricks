# -*- test-case-name: virtualbricks.tests.gui.mainwindow.bricks.test_bricklist -*-
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
The list of the Bricks tab: a row per brick, in the order they were made,
on the rows of :mod:`virtualbricks.gui.mainwindow.rowtab`.

A row says the brick's kind and a summary of it, or its process while the
list shows only the running bricks; its state; and why it can't start, if it
can't. The search finds a brick by its name or its kind.

A row dropped on another connects the two bricks when one can plug into the
other, and only then is the row under the pointer framed.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GdkPixbuf, Gtk  # noqa: E402

from virtualbricks.bricks import brickinfo  # noqa: E402
from virtualbricks.gui.mainwindow.bricks import brickmenu  # noqa: E402
from virtualbricks.bricks.brickinfo import (  # noqa: E402
    LABELS,
    SEPARATOR,
    State,
)
from virtualbricks.gui.mainwindow.rowtab import Row, RowList  # noqa: E402
from virtualbricks.i18n import _  # noqa: E402

DRAG_ICON_SIZE = 24
TARGETS = [
    Gtk.TargetEntry.new("virtualbricks/brick", Gtk.TargetFlags.SAME_APP, 0)
]
WARNINGS = frozenset((State.NOT_CONNECTED, State.NOT_CONFIGURED))


def state_tooltip(brick, state: State) -> str | None:
    if state is State.RUNNING:
        return _("Process {pid}").format(pid=brickinfo.process(brick))
    if state is State.NOT_CONNECTED:
        return _("Connect {name} first").format(name=brick.name)
    if state is State.NOT_CONFIGURED:
        return _("Configure {name} first").format(name=brick.name)
    return None


class BrickRow(Row):
    """A brick, what it is and what it does, and what can be done to it."""

    GROUP = brickmenu.GROUP

    def make_actions(self):
        return brickmenu.BrickActions(self.gui, self.item)

    def menu_model(self):
        factory = self.gui.brickfactory
        return brickmenu.menu(self.item, factory.bricks, list(factory.events))

    def update(self, processes=False) -> None:
        brick = self.item
        state = brickinfo.state(brick)
        running = state is State.RUNNING
        kind = brickinfo.kind(brick)
        if processes and running:
            process = _("process {pid}").format(pid=brickinfo.process(brick))
            detail = SEPARATOR.join((kind, process))
        else:
            detail = SEPARATOR.join(
                part for part in (kind, brickinfo.summary(brick)) if part
            )
        self.show(
            detail,
            LABELS[state],
            running,
            state in WARNINGS,
            state_tooltip(brick, state),
        )

    def on_startstop_clicked(self, button) -> None:
        brickmenu.startstop(self.gui.engine, self.item)


class BrickList(RowList):
    """The bricks of the factory, a row each."""

    NONE = _("No bricks")
    NO_MATCH = _("No brick matches “{text}”")
    NONE_RUNNING = _("No brick is running")
    NO_RUNNING_MATCH = _("No running brick matches “{text}”")

    def __init__(self, gui, factory) -> None:
        super().__init__(gui, factory)
        self._drag_icon: Gtk.Widget | None = None
        self._drag_label: Gtk.Label | None = None

    def signals(self) -> tuple:
        factory = self.factory
        return (
            factory.brick_added,
            factory.brick_removed,
            factory.brick_changed,
        )

    def items(self) -> list:
        return list(self.factory.bricks)

    def make_row(self, item) -> BrickRow:
        return BrickRow(self.gui, item, self.icons, self._sizes)

    def kind(self, item) -> str:
        return brickinfo.kind(item)

    def prepare(self, row) -> None:
        row.drag_source_set(
            Gdk.ModifierType.BUTTON1_MASK, TARGETS, Gdk.DragAction.LINK
        )
        row.drag_dest_set(0, TARGETS, Gdk.DragAction.LINK)
        row.connect("drag-begin", self.on_drag_begin)
        row.connect("drag-end", self.on_drag_end)
        row.connect("drag-motion", self.on_drag_motion)
        row.connect("drag-leave", self.on_drag_leave)
        row.connect("drag-drop", self.on_drag_drop)

    # Dragging a brick on another

    @staticmethod
    def dragged(context):
        """The brick dragged, if it comes from a row."""

        source = Gtk.drag_get_source_widget(context)
        return source.item if isinstance(source, BrickRow) else None

    def on_drag_begin(self, row, context) -> None:
        icon = Gtk.Box(visible=True, spacing=8, margin=4)
        image = Gtk.Image(visible=True, pixel_size=DRAG_ICON_SIZE)
        pixbuf = row.icon.get_pixbuf()
        if pixbuf is not None:
            image.set_from_pixbuf(
                pixbuf.scale_simple(
                    DRAG_ICON_SIZE,
                    DRAG_ICON_SIZE,
                    GdkPixbuf.InterpType.BILINEAR,
                )
            )
        self._drag_label = Gtk.Label(visible=True, label=row.item.name)
        icon.pack_start(image, False, False, 0)
        icon.pack_start(self._drag_label, False, False, 0)
        self._drag_icon = icon
        Gtk.drag_set_icon_widget(context, icon, -8, -8)
        row.set_opacity(0.45)

    def on_drag_end(self, row, context) -> None:
        row.set_opacity(1.0)
        if self._drag_icon is not None:
            self._drag_icon.destroy()
        self._drag_icon = self._drag_label = None

    def _say(self, words) -> None:
        if self._drag_label is not None:
            self._drag_label.set_text(words)

    def on_drag_motion(self, row, context, x, y, time) -> bool:
        source = self.dragged(context)
        if source is None:
            return False
        if brickinfo.connection(source, row.item) is None:
            Gdk.drag_status(context, Gdk.DragAction(0), time)
            row.drag_unhighlight()
            self._say(source.name)
        else:
            Gdk.drag_status(context, Gdk.DragAction.LINK, time)
            row.drag_highlight()
            self._say(
                _("Connect {brick} to {other}").format(
                    brick=source.name, other=row.item.name
                )
            )
        return True

    def on_drag_leave(self, row, context, time) -> None:
        row.drag_unhighlight()
        source = self.dragged(context)
        if source is not None:
            self._say(source.name)

    def on_drag_drop(self, row, context, x, y, time) -> bool:
        source = self.dragged(context)
        if source is None:
            Gtk.drag_finish(context, False, False, time)
            return True

        def finish(done):
            # a failure goes on, to the log
            Gtk.drag_finish(context, done is True, False, time)
            return done

        self.gui.engine.connect(source, row.item).addBoth(finish)
        return True
