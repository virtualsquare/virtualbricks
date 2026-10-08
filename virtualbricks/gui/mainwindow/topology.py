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
a menu with the direction of the layout and the export. The tab lays the
lab out when it shows, and again when a brick changes while it shows; a
project without bricks shows a hint instead.

A click on a brick works as in the list of the bricks: the right button
opens its menu, a double click configures it.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gio, GLib, GObject, Gtk  # noqa: E402
from twisted.logger import Logger  # noqa: E402

from virtualbricks.brickfactory import BrickFactory  # noqa: E402
from virtualbricks.bricks import Brick  # noqa: E402
from virtualbricks.gui.mainwindow import picture  # noqa: E402
from virtualbricks.gui.mainwindow.bricks import brickmenu  # noqa: E402
from virtualbricks.gui.mainwindow.tab import (  # noqa: E402
    Tab,
    brick_signals,
    icon_button,
)
from virtualbricks.gui.mainwindow.topologyview import (  # noqa: E402
    EPSILON,
    LEVELS,
    MARGIN,
    TopologyView,
)
from virtualbricks.i18n import _  # noqa: E402
from virtualbricks.topology import layout  # noqa: E402

if TYPE_CHECKING:  # pragma: no cover
    from virtualbricks.gui.mainwindow.window import VBGUI

logger = Logger()
drawing_topology = "drawing topology"
top_invalid_format = "Error saving topology: Invalid image format"
top_write_error = "Error saving topology: Could not write file"
top_unknown = "Error saving topology: Unknown error"

# Between the bar and the corner, and between the bar's groups, in pixels.
GAP = 6
ACTIONS = "topology"


def menu() -> Gio.Menu:
    """The menu at the end of the bar: the layout, and the export."""

    directions = Gio.Menu()
    directions.append(_("Left to Right"), f"{ACTIONS}.direction::LR")
    directions.append(_("Top to Bottom"), f"{ACTIONS}.direction::TB")
    export = Gio.Menu()
    export.append(_("Export as Image…"), f"{ACTIONS}.export")
    result = Gio.Menu()
    result.append_section(_("Layout"), directions)
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

    def __init__(self, gui: VBGUI, factory: BrickFactory) -> None:
        super().__init__(visible=True)
        self.gui = gui
        self.factory = factory
        self._menu: Gtk.Menu | None = None
        self.direction = "LR"
        self._shown = False
        self._should_draw = True
        self._measuring: int | None = None

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
        self.direction_action = Gio.SimpleAction.new_stateful(
            "direction",
            GLib.VariantType.new("s"),
            GLib.Variant.new_string(self.direction),
        )
        self.direction_action.connect("change-state", self.on_direction)
        actions.add_action(self.direction_action)
        self.export_action = Gio.SimpleAction.new("export", None)
        self.export_action.connect("activate", self.on_export)
        actions.add_action(self.export_action)
        self.insert_action_group(ACTIONS, actions)

        self.out_button.connect("clicked", lambda b: self.view.zoom_out())
        self.in_button.connect("clicked", lambda b: self.view.zoom_in())
        self.level_button.connect("clicked", lambda b: self.view.zoom_to_100())
        self._fit_clicked = self.fit_button.connect("clicked", self.on_fit)
        self.view.connect("zoom-changed", self.on_zoom_changed)
        self.view.area.connect("button-press-event", self.on_button_press)
        self.bar.connect("size-allocate", self.on_bar_allocated)
        self.connect("destroy", self.on_destroy)
        # the lab is laid out again after a brick comes, goes or changes
        for signal in brick_signals(factory):
            signal.connect(self.on_brick_changed)
        self._update()

    def lay_out(self) -> None:
        """Lay the lab out now if the tab shows, else when it shows."""

        if self._shown:
            self._draw()
        else:
            self._should_draw = True

    def _draw(self) -> None:
        logger.debug(drawing_topology)
        self.view.set_layout(
            layout(self.factory.bricks, self.direction, self.view.measure)
        )
        self._should_draw = False
        self._update()

    def _update(self) -> None:
        """The bar and the hint, for the zoom and the lab."""

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

    # Signals

    def on_brick_changed(self, brick: Brick) -> None:
        self.lay_out()

    def on_zoom_changed(self, view: TopologyView) -> None:
        self._update()

    def on_fit(self, button: Gtk.ToggleButton) -> None:
        # a click fits, even on the button that is on; the zoom says after
        self.view.fit()

    def on_direction(
        self, action: Gio.SimpleAction, value: GLib.Variant
    ) -> None:
        action.set_state(value)
        self.direction = value.get_string()
        self.lay_out()

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
        current = self.gui.engine.workspace.current
        name = current.name if current is not None else "topology"
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
            self._menu = brickmenu.popup(area, event, self.gui, brick)
        elif event.button == 1 and event.type == Gdk.EventType._2BUTTON_PRESS:
            self.gui.curtain_up(brick)
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
