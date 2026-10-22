# -*- test-case-name: virtualbricks.tests.gui.mainwindow.test_topology -*-
# Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
# Copyright (C) 2026 Virtualbricks team

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
The Topology tab of the main window: the picture of the lab.

The picture takes the whole tab. A bar floats over its top right corner:
zoom out, the zoom level, which goes back to 100%, zoom in and fit all, then
a menu with the layout, the links and the export. The tab lays the lab out
when it shows, and again when a brick changes while it shows; a project
without bricks shows a hint instead.

The layout is Graphviz's, left to right or top to bottom, or by hand once a
brick has a place (page 35). By Hand gives every brick the place it has in
the picture; Left to Right and Top to Bottom take the places away. The links
are straight, curved or at right angles, as the setting link_lines of the
project says; Links, in the menu, sets it (page 36). In a lab laid out by
hand, Graphviz routes the curves and the right angles around the bricks; the
routes stay while the boxes and the links do, as when a brick starts.

A click on a brick works as in the list of the bricks: the right button
opens its menu, a double click configures it. A brick dropped on another
connects the two, as in the list. A brick moved over free room stays there:
in a lab laid out by Graphviz, the first move gives every other brick the
place it has in the picture too.
"""

from __future__ import annotations

import dataclasses
import os
from collections.abc import Callable, Hashable, Mapping
from typing import TYPE_CHECKING

from gi.repository import Gdk, Gio, GLib, GObject, Gtk
from twisted.logger import Logger

from virtualbricks.brickfactory import BrickFactory
from virtualbricks.bricks import Brick, Point
from virtualbricks.config import settings
from virtualbricks.engine import Engine
from virtualbricks.gui.mainwindow import picture
from virtualbricks.gui.mainwindow.bricks import brickmenu
from virtualbricks.gui.mainwindow.tab import (
    Tab,
    brick_signals,
    icon_button,
)
from virtualbricks.gui.mainwindow.topologyview import (
    EPSILON,
    LEVELS,
    MARGIN,
    TopologyView,
)
from virtualbricks.i18n import _
from virtualbricks.topology import (
    CURVED,
    RIGHT_ANGLES,
    STRAIGHT,
    Layout,
    Link,
    arrange,
    by_hand,
    layout,
    places,
    route,
)

if TYPE_CHECKING:
    from virtualbricks.remote.mirror import MirrorFactory

logger = Logger()
drawing_topology = "drawing topology"
top_invalid_format = "Error saving topology: Invalid image format"
top_write_error = "Error saving topology: Could not write file"
top_unknown = "Error saving topology: Unknown error"
connect_error = "Cannot connect {brick} to {other}"
places_error = "Cannot change the places of the bricks"
move_error = "Cannot move {brick}"
lines_error = "Cannot change link_lines"

# Between the bar and the corner, and between the bar's groups, in pixels.
GAP = 6
ACTIONS = "topology"
# The layout of a lab whose bricks have places.
HAND = "hand"
# The setting of the project that chooses the lines of the links.
LINES = "link_lines"


def menu() -> Gio.Menu:
    """The menu at the end of the bar: the layout, the links, the export."""

    layouts = Gio.Menu()
    layouts.append(_("Left to Right"), f"{ACTIONS}.layout::LR")
    layouts.append(_("Top to Bottom"), f"{ACTIONS}.layout::TB")
    layouts.append(_("By Hand"), f"{ACTIONS}.layout::{HAND}")
    links = Gio.Menu()
    links.append(_("Straight"), f"{ACTIONS}.lines::{STRAIGHT}")
    links.append(_("Curved"), f"{ACTIONS}.lines::{CURVED}")
    links.append(_("Right Angles"), f"{ACTIONS}.lines::{RIGHT_ANGLES}")
    export = Gio.Menu()
    export.append(_("Export as Image…"), f"{ACTIONS}.export")
    result = Gio.Menu()
    result.append_section(_("Layout"), layouts)
    result.append_section(_("Links"), links)
    result.append_section(None, export)
    return result


def level(zoom: float) -> str:
    return f"{round(zoom * 100)}%"


def with_extension(filename: str, extension: str | None) -> str:
    """A file name with the extension of a format, if it hasn't one."""

    if os.path.splitext(filename)[1].lower() in picture.FORMATS:
        return filename
    return filename + (extension or ".png")


def extension_of(
    chooser: Gtk.FileChooser, formats: dict[Gtk.FileFilter, str]
) -> str | None:
    """The extension of the format chosen in chooser, if any."""

    chosen = chooser.get_filter()
    return None if chosen is None else formats.get(chosen)


class TopologyTab(Tab, Gtk.Overlay):
    """The picture of the bricks of the project and how they connect."""

    title = _("_Topology")
    help_page = "topology"

    def __init__(
        self,
        engine: Engine,
        window: Gtk.Window,
        factory: BrickFactory,
        configure: Callable[[Brick], None],
    ) -> None:
        super().__init__(visible=True)
        self.engine = engine
        # what the menu of a brick opens its dialogs over: the main window
        self.window = window
        self.factory = factory
        # the settings of a brick, which the Bricks tab shows
        self.configure = configure
        self._menu: Gtk.Menu | None = None
        # Graphviz's, when the bricks have no places
        self.direction = "LR"
        self._shown = False
        self._should_draw = True
        self._measuring: int | None = None
        # the links of the last lines, boxes and links routed
        self._routes: tuple[Hashable, tuple[Link, ...]] | None = None

        self.view = TopologyView()
        self.add(self.view)
        self.hint = Gtk.Label(
            label=_("No bricks yet. New Brick, in the Bricks tab, adds one."),
            wrap=True,
            xalign=0.0,
            halign=Gtk.Align.START,
            valign=Gtk.Align.START,
            margin=MARGIN,
        )
        self.hint.get_style_context().add_class("dim-label")
        self.add_overlay(self.hint)
        self.set_overlay_pass_through(self.hint, True)

        self.bar = Gtk.Box(
            visible=True,
            spacing=GAP,
            halign=Gtk.Align.END,
            valign=Gtk.Align.START,
            margin=GAP,
        )
        self.bar.get_style_context().add_class("osd")
        zoom = Gtk.Box(visible=True)
        zoom.get_style_context().add_class("linked")
        self.out_button = icon_button(
            Gtk.Button(visible=True), "zoom-out-symbolic", _("Zoom Out")
        )
        self.level_button = Gtk.Button(visible=True, label=level(1.0))
        # as wide at 100% as at 10%
        level_label = self.level_button.get_child()
        assert isinstance(level_label, Gtk.Label), "a label makes its label"
        level_label.set_width_chars(5)
        # the screen readers say the level, then the tooltip
        self.level_button.set_tooltip_text(_("Zoom to 100%"))
        self.in_button = icon_button(
            Gtk.Button(visible=True), "zoom-in-symbolic", _("Zoom In")
        )
        self.fit_button = icon_button(
            Gtk.ToggleButton(visible=True),
            "zoom-fit-best-symbolic",
            _("Fit All"),
        )
        for button in (
            self.out_button,
            self.level_button,
            self.in_button,
            self.fit_button,
        ):
            zoom.pack_start(button, False, False, 0)
        self.bar.pack_start(zoom, False, False, 0)
        self.menu_button = icon_button(
            Gtk.MenuButton(visible=True), "view-more-symbolic", _("More")
        )
        self.menu_button.set_menu_model(menu())
        self.bar.pack_start(self.menu_button, False, False, 0)
        self.add_overlay(self.bar)

        actions = Gio.SimpleActionGroup()
        self.layout_action = Gio.SimpleAction.new_stateful(
            "layout",
            GLib.VariantType.new("s"),
            GLib.Variant.new_string(self.direction),
        )
        self.layout_action.connect("change-state", self.on_layout)
        actions.add_action(self.layout_action)
        self.lines_action = Gio.SimpleAction.new_stateful(
            "lines",
            GLib.VariantType.new("s"),
            GLib.Variant.new_string(self._lines()),
        )
        self.lines_action.connect("change-state", self.on_lines)
        actions.add_action(self.lines_action)
        self.export_action = Gio.SimpleAction.new("export", None)
        self.export_action.connect("activate", self.on_export)
        actions.add_action(self.export_action)
        self.insert_action_group(ACTIONS, actions)

        self.out_button.connect("clicked", lambda b: self.view.zoom_out())
        self.in_button.connect("clicked", lambda b: self.view.zoom_in())
        self.level_button.connect("clicked", lambda b: self.view.zoom_to_100())
        self._fit_clicked = self.fit_button.connect("clicked", self.on_fit)
        self.view.connect("zoom-changed", self.on_zoom_changed)
        self.view.connect("brick-dropped", self.on_brick_dropped)
        self.view.connect("brick-moved", self.on_brick_moved)
        self.view.area.connect("button-press-event", self.on_button_press)
        self.bar.connect("size-allocate", self.on_bar_allocated)
        self.connect("destroy", self.on_destroy)
        # the lab is laid out again after a brick comes, goes or changes
        for signal in brick_signals(factory):
            signal.connect(self.on_brick_changed)
        # and when the lines of its links change, here or there
        settings.changed.connect(self.on_settings_changed)
        if not engine.local:
            engine.factory.settings_changed.connect(self.on_settings_changed)
        self._update()

    def lay_out(self) -> None:
        """Lay the lab out now if the tab shows, else when it shows."""

        if self._shown:
            self._draw()
        else:
            self._should_draw = True

    def _draw(self) -> None:
        logger.debug(drawing_topology)
        bricks = list(self.factory.bricks)
        lines = self._lines()
        if by_hand(bricks):
            new = arrange(bricks, self.view.measure)
            if lines != STRAIGHT:
                new = self._route(new, lines)
        else:
            new = layout(bricks, self.direction, self.view.measure, lines)
        self.view.set_layout(new)
        self._should_draw = False
        self._update()

    def _lines(self) -> str:
        return str(self.engine.machine.setting(LINES))

    def _route(self, lab: Layout, lines: str) -> Layout:
        """
        lab with its links routed with lines, again only if they or its
        geometry changed.
        """

        boxes = tuple(
            (node.brick, node.x, node.y, node.width, node.height)
            for node in lab.nodes
        )
        ends = tuple((link.tail, link.head) for link in lab.links)
        key = (lines, boxes, ends)
        if self._routes is None or self._routes[0] != key:
            self._routes = key, route(lab, lines).links
        return dataclasses.replace(lab, links=self._routes[1])

    def _update(self) -> None:
        """The bar, the hint, and the layout and links of the menu."""

        hand = by_hand(self.factory.bricks)
        state = HAND if hand else self.direction
        # the same state says nothing
        self.layout_action.set_state(GLib.Variant.new_string(state))
        self.lines_action.set_state(GLib.Variant.new_string(self._lines()))
        empty = not self.view.layout.nodes
        zoom = self.view.zoom
        self.level_button.set_label(level(zoom))
        with self.fit_button.handler_block(self._fit_clicked):
            self.fit_button.set_active(self.view.fitting and not empty)
        self.out_button.set_sensitive(not empty and zoom > LEVELS[0] + EPSILON)
        self.in_button.set_sensitive(not empty and zoom < LEVELS[-1] - EPSILON)
        self.level_button.set_sensitive(not empty)
        self.fit_button.set_sensitive(not empty)
        self.hint.set_visible(empty)
        self.export_action.set_enabled(not empty)

    def export(self, filename: str) -> None:
        """Save the picture of the lab in a file: PNG, SVG or PDF."""

        context = self.view.area.get_style_context()
        font = context.get_property("font", context.get_state())
        try:
            picture.export(self.view.layout, filename, font)
        except ValueError:
            logger.failure(top_invalid_format)
        except IOError:
            logger.failure(top_write_error)
        except Exception:
            logger.failure(top_unknown)

    # What the main window tells

    def on_shown(self) -> None:
        self._shown = True
        if self._should_draw:
            self._draw()

    def on_left(self) -> None:
        self._shown = False

    def on_quit(self) -> None:
        for signal in brick_signals(self.factory):
            signal.disconnect(self.on_brick_changed)
        settings.changed.disconnect(self.on_settings_changed)
        if not self.engine.local:
            self.engine.factory.settings_changed.disconnect(
                self.on_settings_changed
            )

    # Signals

    def on_brick_changed(self, brick: Brick) -> None:
        self.lay_out()

    def on_settings_changed(self, what: str | MirrorFactory) -> None:
        # the name of a setting here, or the copy there: the routes stay
        self._update()
        self.lay_out()

    def on_zoom_changed(self, view: TopologyView) -> None:
        self._update()

    def on_brick_dropped(
        self, view: TopologyView, brick: Brick, other: Brick
    ) -> None:
        self.engine.connect(brick, other).addErrback(
            lambda failure: logger.failure(
                connect_error, failure, brick=brick.name, other=other.name
            )
        )

    def on_brick_moved(
        self, view: TopologyView, brick: Brick, place: Point
    ) -> None:
        moved: dict[Brick, Point | None] = {brick: place}
        if not by_hand(self.factory.bricks):
            # the others stay where the picture shows them
            moved = {**places(self.view.layout), **moved}
        self.engine.place(moved).addErrback(
            lambda failure: logger.failure(
                move_error, failure, brick=brick.name
            )
        )

    def on_fit(self, button: Gtk.ToggleButton) -> None:
        # a click fits, even on the button that is on; the zoom says after
        self.view.fit()

    def on_layout(self, action: Gio.SimpleAction, value: GLib.Variant) -> None:
        choice = value.get_string()
        bricks = list(self.factory.bricks)
        if choice == HAND:
            # in a lab without bricks, nothing to place
            if bricks and not by_hand(bricks):
                # the places that the picture shows
                laid_out = layout(bricks, self.direction, self.view.measure)
                self._place(places(laid_out))
        elif by_hand(bricks):
            self.direction = choice
            self._place({brick: None for brick in bricks})
        else:
            action.set_state(value)
            self.direction = choice
            self.lay_out()

    def on_lines(self, action: Gio.SimpleAction, value: GLib.Variant) -> None:
        # the picture follows the setting, here or there
        self.engine.set_settings({LINES: value.get_string()}).addErrback(
            lambda failure: logger.failure(lines_error, failure)
        )

    def _place(self, places: Mapping[Brick, Point | None]) -> None:
        # the bricks that change lay the lab out again
        self.engine.place(places).addErrback(
            lambda failure: logger.failure(places_error, failure)
        )

    def on_export(
        self, action: Gio.SimpleAction, parameter: GLib.Variant | None
    ) -> None:
        chooser = Gtk.FileChooserDialog(
            title=_("Export as Image"), action=Gtk.FileChooserAction.SAVE
        )
        chooser.add_buttons(
            "_Cancel", Gtk.ResponseType.CANCEL, "_Save", Gtk.ResponseType.OK
        )
        toplevel = self.get_toplevel()
        if isinstance(toplevel, Gtk.Window):
            chooser.set_transient_for(toplevel)
        chooser.set_do_overwrite_confirmation(True)
        # the extension of each filter
        formats: dict[Gtk.FileFilter, str] = {}
        for extension, name in picture.FORMATS.items():
            kind = Gtk.FileFilter()
            kind.set_name(name)
            kind.add_pattern(f"*{extension}")
            kind.add_pattern(f"*{extension.upper()}")
            chooser.add_filter(kind)
            formats[kind] = extension
        current = self.engine.workspace.current
        name = current.name if current is not None else "topology"
        # in the folder of the project, when it is here
        if current is not None and current.path and self.engine.local:
            chooser.set_current_folder(current.path)
        chooser.set_current_name(f"{name}.png")
        chooser.connect("notify::filter", self.on_export_format, formats)
        chooser.connect("response", self.on_export_response, formats)
        chooser.show()

    def on_export_format(
        self,
        chooser: Gtk.FileChooserDialog,
        pspec: GObject.ParamSpec,
        formats: dict[Gtk.FileFilter, str],
    ) -> None:
        # the name follows the format
        extension = extension_of(chooser, formats)
        base, old = os.path.splitext(chooser.get_current_name())
        if extension is not None and old.lower() in picture.FORMATS:
            chooser.set_current_name(base + extension)

    def on_export_response(
        self,
        dialog: Gtk.FileChooserDialog,
        response_id: int,
        formats: dict[Gtk.FileFilter, str],
    ) -> None:
        try:
            if response_id == Gtk.ResponseType.OK:
                extension = extension_of(dialog, formats)
                filename = dialog.get_filename()
                assert filename is not None, "Save has a file name"
                self.export(with_extension(filename, extension))
        finally:
            dialog.destroy()

    def on_button_press(
        self, area: Gtk.DrawingArea, event: Gdk.EventButton
    ) -> bool:
        brick = self.view.brick_at(event.x, event.y)
        if brick is None:
            return False
        if event.button == 3:
            # kept while it shows
            self._menu = brickmenu.popup(
                area,
                event,
                self.engine,
                self.window,
                brick,
                self.configure,
            )
        elif (
            event.button == 1
            and event.type == Gdk.EventType.DOUBLE_BUTTON_PRESS
        ):
            self.configure(brick)
        return True

    def on_bar_allocated(
        self, bar: Gtk.Box, allocation: Gdk.Rectangle
    ) -> None:
        # the room of the bar in the view; not now, GTK would lose the resize
        if self._measuring is None:
            self._measuring = GLib.idle_add(self._measure)

    def _measure(self) -> bool:
        self._measuring = None
        self.view.set_top(self.bar.get_allocated_height() + 2 * GAP)
        return GLib.SOURCE_REMOVE

    def on_destroy(self, tab: TopologyTab) -> None:
        if self._measuring is not None:
            GLib.source_remove(self._measuring)
            self._measuring = None
