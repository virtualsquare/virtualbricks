# -*- test-case-name: virtualbricks.tests.gui.mainwindow.test_bricklist -*-
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
The list of the Bricks tab: a row per brick, in the order they were made.

A row shows the brick's icon, grey while it doesn't run; its name; its kind
and a summary of it, or its process while the list shows only the running
bricks; its state; a button that starts or stops it; and the button of its
menu. The rows follow the factory: a brick added, removed or changed. The
list keeps the bricks whose name or kind has the text of the search, and,
when asked, only the running ones, and it says so when none is left.

A row dropped on another connects the two bricks when one can plug into the
other, and only then is the row under the pointer framed.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GdkPixbuf, Gtk, Pango  # noqa: E402

from virtualbricks.gui.mainwindow import brickinfo, brickmenu  # noqa: E402
from virtualbricks.gui.mainwindow.brickinfo import (  # noqa: E402
    LABELS,
    SEPARATOR,
    State,
)
from virtualbricks.gui.mainwindow.picture import Icons  # noqa: E402
from virtualbricks.gui.mainwindow.tab import icon_button  # noqa: E402
from virtualbricks.gui.windows.base import pango_attr_list  # noqa: E402
from virtualbricks.i18n import _  # noqa: E402
from virtualbricks.tools import is_running  # noqa: E402

ICON_SIZE = 32
DRAG_ICON_SIZE = 24
# A stopped brick's icon, this opaque.
STOPPED_OPACITY = 0.55
TARGETS = [
    Gtk.TargetEntry.new("virtualbricks/brick", Gtk.TargetFlags.SAME_APP, 0)
]
WARNINGS = frozenset((State.NOT_CONNECTED, State.NOT_CONFIGURED))
STARTABLE = frozenset((State.RUNNING, State.STOPPED))

_css = Gtk.CssProvider()
_css.load_from_data(b"""
    .brick-dot {
        min-width: 8px;
        min-height: 8px;
        border-radius: 4px;
        background-color: alpha(currentColor, 0.4);
    }
    .brick-dot.running { background-color: #33d17a; }
    .brick-warning { color: #e5a50a; }
    """)


def _styled(widget, *classes):
    context = widget.get_style_context()
    context.add_provider(_css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    for name in classes:
        context.add_class(name)
    return widget


def state_tooltip(brick, state: State) -> str | None:
    if state is State.RUNNING:
        return _("Process {pid}").format(pid=brickinfo.process(brick))
    if state is State.NOT_CONNECTED:
        return _("Connect {name} first").format(name=brick.get_name())
    if state is State.NOT_CONFIGURED:
        return _("Configure {name} first").format(name=brick.get_name())
    return None


class BrickRow(Gtk.ListBoxRow):
    """A brick, what it is and what it does, and what can be done to it."""

    def __init__(self, gui, brick, icons, sizes) -> None:
        super().__init__(visible=True)
        self.gui = gui
        self.brick = brick
        self.icons = icons
        self.actions = brickmenu.BrickActions(gui, brick)
        self.insert_action_group(brickmenu.GROUP, self.actions)

        box = Gtk.Box(
            visible=True,
            spacing=12,
            margin_start=14,
            margin_end=8,
            margin_top=6,
            margin_bottom=6,
        )
        self.icon = Gtk.Image(visible=True, pixel_size=ICON_SIZE)
        box.pack_start(self.icon, False, False, 0)
        text = Gtk.Box(
            visible=True,
            orientation=Gtk.Orientation.VERTICAL,
            valign=Gtk.Align.CENTER,
        )
        self.name = Gtk.Label(
            visible=True,
            xalign=0.0,
            ellipsize=Pango.EllipsizeMode.END,
            attributes=pango_attr_list(
                Pango.attr_weight_new(Pango.Weight.BOLD)
            ),
        )
        self.detail = Gtk.Label(
            visible=True, xalign=0.0, ellipsize=Pango.EllipsizeMode.END
        )
        self.detail.get_style_context().add_class("dim-label")
        text.pack_start(self.name, False, False, 0)
        text.pack_start(self.detail, False, False, 0)
        box.pack_start(text, True, True, 0)

        self.state = Gtk.Box(visible=True, spacing=7)
        self.dot = _styled(
            Gtk.Box(valign=Gtk.Align.CENTER, halign=Gtk.Align.CENTER),
            "brick-dot",
        )
        self.warning = _styled(
            Gtk.Image.new_from_icon_name(
                "dialog-warning-symbolic", Gtk.IconSize.MENU
            ),
            "brick-warning",
        )
        self.state_label = Gtk.Label(visible=True, xalign=0.0)
        for widget in (self.dot, self.warning, self.state_label):
            self.state.pack_start(widget, False, False, 0)
        sizes.add_widget(self.state)
        box.pack_start(self.state, False, False, 0)

        self.startstop = Gtk.Button(
            visible=True, relief=Gtk.ReliefStyle.NONE, valign=Gtk.Align.CENTER
        )
        self.menu_button = Gtk.Button(
            visible=True, relief=Gtk.ReliefStyle.NONE, valign=Gtk.Align.CENTER
        )
        self.popover: Gtk.Popover | None = None
        box.pack_start(self.startstop, False, False, 0)
        box.pack_start(self.menu_button, False, False, 0)
        self.add(box)

        self.startstop.connect("clicked", self.on_startstop_clicked)
        self.menu_button.connect("clicked", self.on_menu_clicked)
        self.update()

    def open_menu(self) -> Gtk.Popover:
        """
        Show the menu of the brick under its button, made now: what it
        offers depends on the other bricks too.
        """

        # a popover shows no keys
        model = brickmenu.menu(self.brick, self.gui.brickfactory.bricks)
        self.popover = Gtk.Popover.new_from_model(self.menu_button, model)
        self.popover.connect("closed", self.on_menu_closed)
        self.popover.popup()
        return self.popover

    def update(self, processes=False) -> None:
        """
        Say again what the brick is and does. processes shows its process in
        place of its summary while it runs.
        """

        brick = self.brick
        name = brick.get_name()
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
        self.name.set_text(name)
        self.detail.set_text(detail)
        self.detail.set_tooltip_text(detail)

        pixbuf = self.icons.get(brick, running)
        if pixbuf is None:
            self.icon.set_from_icon_name("image-missing", Gtk.IconSize.DND)
        else:
            self.icon.set_from_pixbuf(pixbuf)
        self.icon.set_opacity(1.0 if running else STOPPED_OPACITY)

        warning = state in WARNINGS
        self.dot.set_visible(not warning)
        self.warning.set_visible(warning)
        context = self.dot.get_style_context()
        if running:
            context.add_class("running")
        else:
            context.remove_class("running")
        self.state_label.set_text(LABELS[state])
        self.state.set_tooltip_text(state_tooltip(brick, state))

        if running:
            icon, what = "media-playback-stop-symbolic", _("Stop {name}")
        else:
            icon, what = "media-playback-start-symbolic", _("Start {name}")
        icon_button(self.startstop, icon, what.format(name=name))
        self.startstop.set_sensitive(state in STARTABLE)
        icon_button(
            self.menu_button,
            "view-more-symbolic",
            _("Menu of {name}").format(name=name),
        )
        self.actions.update()

    def on_startstop_clicked(self, button) -> None:
        self.gui.startstop_brick(self.brick)

    def on_menu_clicked(self, button) -> None:
        self.open_menu()

    def on_menu_closed(self, popover) -> None:
        if popover is self.popover:
            self.popover = None
        popover.destroy()


class BrickList(Gtk.ListBox):
    """The bricks of the factory, a row each."""

    def __init__(self, gui, factory) -> None:
        super().__init__(
            visible=True,
            selection_mode=Gtk.SelectionMode.SINGLE,
            activate_on_single_click=False,
        )
        self.gui = gui
        self.factory = factory
        self.search = ""
        self.only_running = False
        self.icons = Icons(ICON_SIZE)
        self._sizes = Gtk.SizeGroup(mode=Gtk.SizeGroupMode.HORIZONTAL)
        self._rows: dict[object, BrickRow] = {}
        self._drag_icon: Gtk.Widget | None = None
        self._drag_label: Gtk.Label | None = None

        self.placeholder = Gtk.Label(
            visible=True,
            wrap=True,
            margin=24,
            justify=Gtk.Justification.CENTER,
        )
        self.placeholder.get_style_context().add_class("dim-label")
        self.set_placeholder(self.placeholder)
        self.set_filter_func(self._visible)
        for brick in factory.bricks:
            self._add(brick)
        self._update_placeholder()
        factory.connect("brick-added", self.on_brick_added)
        factory.connect("brick-removed", self.on_brick_removed)
        factory.connect("brick-changed", self.on_brick_changed)

    def close(self) -> None:
        """Stop following the factory."""

        self.factory.disconnect("brick-added", self.on_brick_added)
        self.factory.disconnect("brick-removed", self.on_brick_removed)
        self.factory.disconnect("brick-changed", self.on_brick_changed)

    def row_of(self, brick) -> BrickRow | None:
        return self._rows.get(brick)

    def selected_brick(self):
        row = self.get_selected_row()
        return None if row is None else row.brick

    def set_search(self, text: str) -> None:
        """Keep the bricks whose name or kind has text in it."""

        self.search = text
        self.invalidate_filter()
        self._update_placeholder()

    def set_only_running(self, only: bool) -> None:
        """Keep only the running bricks, and show their process."""

        self.only_running = only
        self.update()

    def update(self) -> None:
        for row in self._rows.values():
            row.update(self.only_running)
        self.invalidate_filter()
        self._update_placeholder()

    def _add(self, brick) -> None:
        row = BrickRow(self.gui, brick, self.icons, self._sizes)
        self._rows[brick] = row
        row.drag_source_set(
            Gdk.ModifierType.BUTTON1_MASK, TARGETS, Gdk.DragAction.LINK
        )
        row.drag_dest_set(0, TARGETS, Gdk.DragAction.LINK)
        row.connect("drag-begin", self.on_drag_begin)
        row.connect("drag-end", self.on_drag_end)
        row.connect("drag-motion", self.on_drag_motion)
        row.connect("drag-leave", self.on_drag_leave)
        row.connect("drag-drop", self.on_drag_drop)
        self.add(row)

    def _visible(self, row) -> bool:
        brick = row.brick
        if self.only_running and not is_running(brick):
            return False
        text = self.search.strip().casefold()
        return (
            text in brick.get_name().casefold()
            or text in brickinfo.kind(brick).casefold()
        )

    def _update_placeholder(self) -> None:
        text = self.search.strip()
        if text and self.only_running:
            words = _("No running brick matches “{text}”")
        elif text:
            words = _("No brick matches “{text}”")
        elif self.only_running:
            words = _("No brick is running")
        else:
            words = _("No bricks")
        self.placeholder.set_text(words.format(text=text))

    # The factory

    def on_brick_added(self, brick) -> None:
        # the list filters a row it takes
        self._add(brick)

    def on_brick_removed(self, brick) -> None:
        row = self._rows.pop(brick, None)
        if row is not None:
            row.destroy()
        # the bricks plugged into it are unplugged, and not told
        self.update()

    def on_brick_changed(self, brick) -> None:
        # every row: a brick's name and links show in the rows of others
        self.update()

    # Dragging a brick on another

    @staticmethod
    def dragged(context):
        """The brick dragged, if it comes from a row."""

        source = Gtk.drag_get_source_widget(context)
        return source.brick if isinstance(source, BrickRow) else None

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
        self._drag_label = Gtk.Label(visible=True, label=row.brick.get_name())
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
        if brickinfo.connection(source, row.brick) is None:
            Gdk.drag_status(context, Gdk.DragAction(0), time)
            row.drag_unhighlight()
            self._say(source.get_name())
        else:
            Gdk.drag_status(context, Gdk.DragAction.LINK, time)
            row.drag_highlight()
            self._say(
                _("Connect {brick} to {other}").format(
                    brick=source.get_name(), other=row.brick.get_name()
                )
            )
        return True

    def on_drag_leave(self, row, context, time) -> None:
        row.drag_unhighlight()
        source = self.dragged(context)
        if source is not None:
            self._say(source.get_name())

    def on_drag_drop(self, row, context, x, y, time) -> bool:
        source = self.dragged(context)
        done = source is not None and brickinfo.connect(source, row.brick)
        Gtk.drag_finish(context, done, False, time)
        return True
