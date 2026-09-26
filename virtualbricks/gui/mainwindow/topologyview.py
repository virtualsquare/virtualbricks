# -*- test-case-name: virtualbricks.tests.gui.mainwindow.test_topologyview -*-
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
The picture of a lab: a layout of :mod:`virtualbricks.topology`, drawn with
cairo at any zoom.

Zoom in and zoom out step through LEVELS. Fit all picks the zoom that shows
the whole lab, never above 100%, and stays on until another zoom: the
picture fits again when the view changes size or gets another layout. The
buttons and the keys zoom around the centre of the view; Ctrl and the wheel,
and a pinch, around the pointer. Dragging the background moves the picture.

Room can be kept free at the top, for what floats over the view: the lab
starts below it, and fitting leaves it out.

The picture is drawn by :mod:`virtualbricks.gui.mainwindow.picture` in the
colours of the theme, on the view's background; the brick under the pointer
sits on a disc of the selection colour, with its name, type and state in a
tooltip.
"""

from __future__ import annotations

import math

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, GObject, Gtk  # noqa: E402

from virtualbricks.gui.mainwindow.picture import (  # noqa: E402
    MARGIN,
    Icons,
    Palette,
    draw,
)
from virtualbricks.topology import Layout  # noqa: E402

# The zooms of zoom in and zoom out, the first and the last also the limits.
LEVELS = (0.1, 0.25, 0.33, 0.5, 0.67, 0.8, 1.0, 1.25, 1.5, 2.0, 3.0, 4.0)
# The step of the arrows, in pixels.
ARROW_STEP = 40
# Two zooms this close are the same level.
EPSILON = 0.001


def clamp(zoom: float) -> float:
    return min(max(zoom, LEVELS[0]), LEVELS[-1])


def zoom_in(zoom: float) -> float:
    """The next level above zoom."""

    return next(
        (level for level in LEVELS if level > zoom + EPSILON), LEVELS[-1]
    )


def zoom_out(zoom: float) -> float:
    """The next level below zoom."""

    return next(
        (level for level in reversed(LEVELS) if level < zoom - EPSILON),
        LEVELS[0],
    )


def fit_zoom(layout: Layout, width: float, height: float) -> float:
    """The zoom that shows the whole lab in width × height, never above 1."""

    if not layout.nodes:
        return 1.0
    return clamp(
        min(
            (width - 2 * MARGIN) / layout.width,
            (height - 2 * MARGIN) / layout.height,
            1.0,
        )
    )


def origin(size: float, zoom: float, room: float) -> float:
    """
    Where the lab starts along a side of room pixels: in the middle when it
    fits, after the margin when it doesn't.
    """

    return max(MARGIN, (room - size * zoom) / 2)


def tooltip_text(brick) -> str:
    return f"{brick.get_name()} · {brick.get_type()} · {brick.get_state()}"


class TopologyView(Gtk.ScrolledWindow):
    """A layout, drawn at a zoom, and the zoom's controls."""

    __gsignals__ = {
        # the zoom, or fitting, changed
        "zoom-changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self) -> None:
        super().__init__(visible=True)
        self.layout = Layout()
        # the room at the top that the lab leaves free, in pixels
        self.top = 0
        self.zoom = 1.0
        # fit all is on
        self.fitting = True
        # the node under the pointer
        self.hover = None
        self.icons = Icons()
        # the scroll, once the area has the size of the new zoom
        self._scroll_to: tuple[float, float] | None = None
        self._fitting_later: int | None = None
        self._size = (0, 0)
        # where a drag of the background started: pointer and scroll
        self._drag: tuple[float, float, float, float] | None = None
        self._wheel = 0.0
        self._pinch_zoom = 1.0
        self._pinch_anchor = (0.0, 0.0)

        self.area = Gtk.DrawingArea(
            visible=True, can_focus=True, has_tooltip=True
        )
        # the background of the views
        self.area.get_style_context().add_class("view")
        self.area.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.POINTER_MOTION_MASK
            | Gdk.EventMask.SCROLL_MASK
            | Gdk.EventMask.SMOOTH_SCROLL_MASK
            | Gdk.EventMask.LEAVE_NOTIFY_MASK
            | Gdk.EventMask.KEY_PRESS_MASK
        )
        self.add(self.area)
        self.pinch = Gtk.GestureZoom.new(self.area)

        self.area.connect("draw", self.on_draw)
        self.area.connect("size-allocate", self.on_area_allocated)
        self.area.connect("button-press-event", self.on_button_press)
        self.area.connect("button-release-event", self.on_button_release)
        self.area.connect("motion-notify-event", self.on_motion)
        self.area.connect("leave-notify-event", self.on_leave)
        self.area.connect("scroll-event", self.on_scroll)
        self.area.connect("key-press-event", self.on_key_press)
        self.area.connect("query-tooltip", self.on_query_tooltip)
        self.pinch.connect("begin", self.on_pinch_begin)
        self.pinch.connect("scale-changed", self.on_pinch)
        self.connect("size-allocate", self.on_allocated)
        self.connect("destroy", self.on_destroy)

    # The layout and the zoom

    def set_layout(self, layout: Layout) -> None:
        self.layout = layout
        self.hover = None
        if self.fitting:
            self.fit()
        else:
            self._resize()

    def set_top(self, top: int) -> None:
        """Keep top pixels free at the top."""

        if top == self.top:
            return
        self.top = top
        if self.fitting:
            self.fit()
        else:
            self._resize()

    def fit(self) -> None:
        """Show the whole lab, and again after a change, until a zoom."""

        self.fitting = True
        width, height = self.room()
        self._zoom(fit_zoom(self.layout, width, height - self.top), None)

    def set_zoom(self, zoom: float, anchor=None) -> None:
        """
        Zoom around anchor, a point of the view, or its centre: fit all is
        off.
        """

        self.fitting = False
        self._zoom(clamp(zoom), anchor)

    def zoom_in(self, anchor=None) -> None:
        self.set_zoom(zoom_in(self.zoom), anchor)

    def zoom_out(self, anchor=None) -> None:
        self.set_zoom(zoom_out(self.zoom), anchor)

    def zoom_to_100(self) -> None:
        self.set_zoom(1.0)

    def room(self) -> tuple[int, int]:
        """The size of the view, what the lab can show in."""

        return self.get_allocated_width(), self.get_allocated_height()

    def _zoom(self, zoom: float, anchor) -> None:
        width, height = self.room()
        ax, ay = (width / 2, height / 2) if anchor is None else anchor
        hadjustment, vadjustment = (
            self.get_hadjustment(),
            self.get_vadjustment(),
        )
        # the point of the lab under the anchor stays there
        x, y = self.to_layout(
            hadjustment.get_value() + ax, vadjustment.get_value() + ay
        )
        self.zoom = zoom
        area_width = max(self.layout.width * zoom + 2 * MARGIN, width)
        area_height = max(
            self.layout.height * zoom + 2 * MARGIN + self.top, height
        )
        self._scroll_to = (
            x * zoom + origin(self.layout.width, zoom, area_width) - ax,
            y * zoom
            + self.top
            + origin(self.layout.height, zoom, area_height - self.top)
            - ay,
        )
        self._resize()
        self.emit("zoom-changed")

    def _resize(self) -> None:
        if self.layout.nodes:
            self.area.set_size_request(
                math.ceil(self.layout.width * self.zoom + 2 * MARGIN),
                math.ceil(
                    self.layout.height * self.zoom + 2 * MARGIN + self.top
                ),
            )
        else:
            self.area.set_size_request(-1, -1)
        # allocated even if the size is the same, for the scroll
        self.area.queue_resize()
        self.area.queue_draw()

    # Where things are

    def origin(self) -> tuple[float, float]:
        """Where the lab starts in the area."""

        width = self.area.get_allocated_width()
        height = self.area.get_allocated_height() - self.top
        return (
            origin(self.layout.width, self.zoom, width),
            self.top + origin(self.layout.height, self.zoom, height),
        )

    def to_layout(self, x: float, y: float) -> tuple[float, float]:
        """A point of the area, in the lab."""

        ox, oy = self.origin()
        return (x - ox) / self.zoom, (y - oy) / self.zoom

    def node_at(self, x: float, y: float):
        """The node whose box holds a point of the area, or None."""

        lx, ly = self.to_layout(x, y)
        for node in reversed(self.layout.nodes):
            if (
                abs(lx - node.x) <= node.width / 2
                and abs(ly - node.y) <= node.height / 2
            ):
                return node
        return None

    def measure(self, name: str) -> int:
        """The width of a name at 100%, in the font of the view."""

        context = self.area.get_style_context()
        text = self.area.create_pango_layout(name)
        text.set_font_description(
            context.get_property("font", context.get_state())
        )
        return text.get_pixel_size()[0]

    def brick_at(self, x: float, y: float):
        node = self.node_at(x, y)
        return None if node is None else node.brick

    # Drawing

    def on_draw(self, area, cr) -> bool:
        context = area.get_style_context()
        width, height = area.get_allocated_width(), area.get_allocated_height()
        Gtk.render_background(context, cr, 0, 0, width, height)
        if not self.layout.nodes:
            return False
        ink = context.get_color(context.get_state())
        found, selection = context.lookup_color("theme_selected_bg_color")
        if not found:
            selection = ink
        palette = Palette(
            (ink.red, ink.green, ink.blue),
            (selection.red, selection.green, selection.blue),
        )
        draw(
            cr,
            self.layout,
            self.zoom,
            self.origin(),
            palette,
            context.get_property("font", context.get_state()),
            area.create_pango_layout,
            self.icons,
            self.hover,
        )
        return False

    # Signals

    def on_allocated(self, view, allocation) -> None:
        size = (allocation.width, allocation.height)
        if size != self._size:
            self._size = size
            # not now: GTK would lose the new size of the area
            if self.fitting and self._fitting_later is None:
                self._fitting_later = GLib.idle_add(self._fit_later)

    def _fit_later(self) -> bool:
        self._fitting_later = None
        if self.fitting:
            self.fit()
        return GLib.SOURCE_REMOVE

    def on_area_allocated(self, area, allocation) -> None:
        # the adjustments know the new size now
        if self._scroll_to is not None:
            x, y = self._scroll_to
            self._scroll_to = None
            self.get_hadjustment().set_value(x)
            self.get_vadjustment().set_value(y)

    def on_button_press(self, area, event) -> bool:
        area.grab_focus()
        if event.button != 1 or self.node_at(event.x, event.y) is not None:
            # the bricks are the tab's
            return False
        self._drag = (
            event.x_root,
            event.y_root,
            self.get_hadjustment().get_value(),
            self.get_vadjustment().get_value(),
        )
        self._set_cursor("grabbing")
        return True

    def on_button_release(self, area, event) -> bool:
        if event.button == 1 and self._drag is not None:
            self._drag = None
            self._set_cursor(None)
            return True
        return False

    def on_motion(self, area, event) -> bool:
        if self._drag is not None:
            x0, y0, h, v = self._drag
            self.get_hadjustment().set_value(h - (event.x_root - x0))
            self.get_vadjustment().set_value(v - (event.y_root - y0))
            return True
        node = self.node_at(event.x, event.y)
        if node is not self.hover:
            self.hover = node
            self._set_cursor(None if node is None else "pointer")
            area.trigger_tooltip_query()
            area.queue_draw()
        return False

    def on_leave(self, area, event) -> bool:
        if self.hover is not None and self._drag is None:
            self.hover = None
            area.queue_draw()
        return False

    def on_scroll(self, area, event) -> bool:
        if not event.state & Gdk.ModifierType.CONTROL_MASK:
            # the scrolled window scrolls
            return False
        if event.direction == Gdk.ScrollDirection.UP:
            steps = -1
        elif event.direction == Gdk.ScrollDirection.DOWN:
            steps = 1
        elif event.direction == Gdk.ScrollDirection.SMOOTH:
            # a touchpad: a step for each whole unit
            self._wheel += event.delta_y
            steps = math.trunc(self._wheel)
            self._wheel -= steps
        else:
            return True
        anchor = (
            event.x - self.get_hadjustment().get_value(),
            event.y - self.get_vadjustment().get_value(),
        )
        for _ in range(abs(steps)):
            if steps < 0:
                self.zoom_in(anchor)
            else:
                self.zoom_out(anchor)
        return True

    def on_key_press(self, area, event) -> bool:
        modifiers = event.state & Gtk.accelerator_get_default_mod_mask()
        control = modifiers & ~Gdk.ModifierType.SHIFT_MASK
        key = event.keyval
        hadjustment, vadjustment = (
            self.get_hadjustment(),
            self.get_vadjustment(),
        )
        if control == Gdk.ModifierType.CONTROL_MASK:
            if key in (Gdk.KEY_plus, Gdk.KEY_equal, Gdk.KEY_KP_Add):
                self.zoom_in()
            elif key in (Gdk.KEY_minus, Gdk.KEY_KP_Subtract):
                self.zoom_out()
            elif key in (Gdk.KEY_0, Gdk.KEY_KP_0):
                self.zoom_to_100()
            else:
                return False
        elif modifiers:
            return False
        elif key in (Gdk.KEY_f, Gdk.KEY_F):
            self.fit()
        elif key in (Gdk.KEY_Left, Gdk.KEY_Right):
            step = ARROW_STEP if key == Gdk.KEY_Right else -ARROW_STEP
            hadjustment.set_value(hadjustment.get_value() + step)
        elif key in (Gdk.KEY_Up, Gdk.KEY_Down):
            step = ARROW_STEP if key == Gdk.KEY_Down else -ARROW_STEP
            vadjustment.set_value(vadjustment.get_value() + step)
        elif key in (Gdk.KEY_Page_Up, Gdk.KEY_Page_Down):
            page = vadjustment.get_page_increment()
            step = page if key == Gdk.KEY_Page_Down else -page
            vadjustment.set_value(vadjustment.get_value() + step)
        else:
            return False
        return True

    def on_query_tooltip(self, area, x, y, keyboard, tooltip) -> bool:
        node = self.node_at(x, y)
        if node is None:
            return False
        tooltip.set_text(tooltip_text(node.brick))
        return True

    def on_pinch_begin(self, gesture, sequence) -> None:
        self._pinch_zoom = self.zoom
        found, x, y = gesture.get_bounding_box_center()
        if found:
            self._pinch_anchor = (
                x - self.get_hadjustment().get_value(),
                y - self.get_vadjustment().get_value(),
            )
        else:
            self._pinch_anchor = None

    def on_pinch(self, gesture, scale) -> None:
        self.set_zoom(self._pinch_zoom * scale, self._pinch_anchor)

    def on_destroy(self, view) -> None:
        if self._fitting_later is not None:
            GLib.source_remove(self._fitting_later)
            self._fitting_later = None

    def _set_cursor(self, name) -> None:
        window = self.area.get_window()
        if window is None:
            return
        cursor = (
            None
            if name is None
            else Gdk.Cursor.new_from_name(self.area.get_display(), name)
        )
        window.set_cursor(cursor)
