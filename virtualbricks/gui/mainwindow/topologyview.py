# -*- test-case-name: virtualbricks.tests.gui.mainwindow.test_topologyview -*-
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

A brick pressed with the left button and moved by the drag threshold is
dragged: a line follows the pointer, and ends on a brick that the one
dragged connects to, as a drop on the Bricks list would, with what a release
does under it. A release there says brick-dropped. Over free room, a faded
copy of the brick ends the line, where the brick goes, held as the brick was
pressed; near the column or the row of another brick, it lines up with it,
along a guide. A release there says brick-moved, with the place (page 35).
Over another brick, Escape or a lost grab end the drag with nothing. Near
an edge of the view, the view scrolls.

Zoomed and not fitted, a new layout keeps the point of the lab in the
middle of the view where it was, by its place: the bricks that kept their
places stay where they were, as long as the lab is larger than the view.
"""

from __future__ import annotations

import math
from typing import Any

import cairo
from gi.repository import Gdk, GLib, GObject, Gtk

from virtualbricks.bricks import Brick, Point, brickinfo
from virtualbricks.gui.mainwindow.picture import (
    MARGIN,
    Guide,
    Icons,
    Line,
    Palette,
    draw,
    icon_centre,
)
from virtualbricks.i18n import _
from virtualbricks.topology import Layout, Node

# The zooms of zoom in and zoom out, the first and the last also the limits.
LEVELS = (0.1, 0.25, 0.33, 0.5, 0.67, 0.8, 1.0, 1.25, 1.5, 2.0, 3.0, 4.0)
# The step of the arrows, in pixels.
ARROW_STEP = 40
# Two zooms this close are the same level.
EPSILON = 0.001
# A drag scrolls the view while the pointer is this near one of its edges,
# in pixels: every EDGE_DELAY milliseconds, by up to EDGE_STEP pixels, more
# the nearer the edge.
EDGE = 32
EDGE_STEP = 20
EDGE_DELAY = 30
# The words of a drag, in pixels: the padding and the corners of their box,
# and its gap under the brick.
WORDS_PADDING = 6
WORDS_RADIUS = 5
WORDS_GAP = 6
# A brick moved lines up with the column or the row of another this near,
# in pixels.
SNAP = 8


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


def tooltip_text(brick: Brick) -> str:
    return f"{brick.name} · {brick.get_type()} · {brick.get_state()}"


def edge_step(position: float, size: float) -> int:
    """
    How far a drag scrolls along a side of the view, size pixels long, with
    the pointer at position: back near its start, on near its end, else 0.
    """

    if position < EDGE:
        return -math.ceil(EDGE_STEP * min(1.0, (EDGE - position) / EDGE))
    if position > size - EDGE:
        return math.ceil(EDGE_STEP * min(1.0, (position - size + EDGE) / EDGE))
    return 0


def line_up(
    point: tuple[float, float],
    others: list[tuple[float, float]],
    reach: float,
) -> tuple[tuple[float, float], tuple[Guide, ...]]:
    """
    point lined up with the nearest of others, each way, if it is within
    reach: the point, and a guide from each one it lined up with to it.
    """

    x, y = point
    guides = []
    column = min(others, key=lambda other: abs(other[0] - x), default=None)
    if column is not None and abs(column[0] - x) <= reach:
        x = column[0]
    else:
        column = None
    row = min(others, key=lambda other: abs(other[1] - y), default=None)
    if row is not None and abs(row[1] - y) <= reach:
        y = row[1]
    else:
        row = None
    if column is not None:
        guides.append(Guide((x, column[1]), (x, y)))
    if row is not None:
        guides.append(Guide((row[0], y), (x, y)))
    return (x, y), tuple(guides)


def rounded_rectangle(
    cr: cairo.Context[Any], x: float, y: float, width: float, height: float
) -> None:
    r = WORDS_RADIUS
    cr.new_sub_path()
    cr.arc(x + width - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + width - r, y + height - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + height - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()


class TopologyView(Gtk.ScrolledWindow):
    """A layout, drawn at a zoom, and the zoom's controls."""

    __gsignals__ = {
        # the zoom, or fitting, changed
        "zoom-changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
        # a brick dropped on another that it connects to: both
        "brick-dropped": (
            GObject.SignalFlags.RUN_FIRST,
            None,
            (object, object),
        ),
        # a brick moved over free room: the brick and its place
        "brick-moved": (
            GObject.SignalFlags.RUN_FIRST,
            None,
            (object, object),
        ),
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
        self.hover: Node | None = None
        self.icons = Icons()
        # the scroll, once the area has the size of the new zoom
        self._scroll_to: tuple[float, float] | None = None
        self._fitting_later: int | None = None
        self._size = (0, 0)
        # where a drag of the background started: pointer and scroll
        self._drag: tuple[float, float, float, float] | None = None
        # the brick under a press of the left button, and where it was
        self._pressed: tuple[Brick, float, float] | None = None
        # the brick dragged, and the pointer in the view
        self.dragging: Brick | None = None
        self._pointer = (0.0, 0.0)
        # where the brick dragged was pressed, from the middle of its icon,
        # in points
        self._grab = (0.0, 0.0)
        self._edge_scroll: int | None = None
        self._wheel = 0.0
        self._pinch_zoom = 1.0
        self._pinch_anchor: tuple[float, float] | None = (0.0, 0.0)

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
        # a viewport of its own: the one that GTK adds scrolls to the corner
        # of the picture once the area has the focus, as after a press
        viewport = Gtk.Viewport(visible=True)
        viewport.add(self.area)
        self.add(viewport)
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
        self.area.connect("grab-broken-event", self.on_grab_broken)
        self.area.connect("grab-notify", self.on_grab_notify)
        self.pinch.connect("begin", self.on_pinch_begin)
        self.pinch.connect("scale-changed", self.on_pinch)
        self.connect("size-allocate", self.on_allocated)
        self.connect("destroy", self.on_destroy)

    # The layout and the zoom

    def set_layout(self, layout: Layout) -> None:
        old = self.layout
        width, height = self.room()
        # the point in the middle, by its place
        x, y = self.to_layout(
            self.get_hadjustment().get_value() + width / 2,
            self.get_vadjustment().get_value() + height / 2,
        )
        x, y = x + old.left - layout.left, y + old.top - layout.top
        self.layout = layout
        self.hover = None
        # a drag holds the bricks, not their places
        if (
            self._pressed is not None
            and self.node_of(self._pressed[0]) is None
        ):
            self._pressed = None
        if self.dragging is not None and self.node_of(self.dragging) is None:
            self._end_drag()
        if self.fitting:
            self.fit()
        else:
            self._show((x, y), (width / 2, height / 2))

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

    def set_zoom(
        self, zoom: float, anchor: tuple[float, float] | None = None
    ) -> None:
        """
        Zoom around anchor, a point of the view, or its centre: fit all is
        off.
        """

        self.fitting = False
        self._zoom(clamp(zoom), anchor)

    def zoom_in(self, anchor: tuple[float, float] | None = None) -> None:
        self.set_zoom(zoom_in(self.zoom), anchor)

    def zoom_out(self, anchor: tuple[float, float] | None = None) -> None:
        self.set_zoom(zoom_out(self.zoom), anchor)

    def zoom_to_100(self) -> None:
        self.set_zoom(1.0)

    def room(self) -> tuple[int, int]:
        """The size of the view, what the lab can show in."""

        return self.get_allocated_width(), self.get_allocated_height()

    def _zoom(self, zoom: float, anchor: tuple[float, float] | None) -> None:
        width, height = self.room()
        ax, ay = (width / 2, height / 2) if anchor is None else anchor
        hadjustment, vadjustment = (
            self.get_hadjustment(),
            self.get_vadjustment(),
        )
        # the point of the lab under the anchor stays there
        point = self.to_layout(
            hadjustment.get_value() + ax, vadjustment.get_value() + ay
        )
        self.zoom = zoom
        self._show(point, (ax, ay))
        self.emit("zoom-changed")

    def _show(
        self, point: tuple[float, float], anchor: tuple[float, float]
    ) -> None:
        """
        Show point, of the lab, at anchor, of the view, once the area has its
        size.
        """

        width, height = self.room()
        (x, y), (ax, ay), zoom = point, anchor, self.zoom
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

    def node_at(
        self, x: float, y: float, skip: Brick | None = None
    ) -> Node | None:
        """
        The node whose box holds a point of the area, or None; never the
        node of skip.
        """

        lx, ly = self.to_layout(x, y)
        for node in reversed(self.layout.nodes):
            if node.brick is skip:
                continue
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

    def brick_at(self, x: float, y: float) -> Brick | None:
        node = self.node_at(x, y)
        return None if node is None else node.brick

    def node_of(self, brick: Brick) -> Node | None:
        return next((n for n in self.layout.nodes if n.brick is brick), None)

    def pointer(self) -> tuple[float, float]:
        """Where the pointer of a drag is, in the area."""

        x, y = self._pointer
        return (
            x + self.get_hadjustment().get_value(),
            y + self.get_vadjustment().get_value(),
        )

    def drop_target(self) -> Node | None:
        """The node under the pointer that the brick dragged connects to."""

        if self.dragging is None:
            return None
        node = self.node_at(*self.pointer())
        if (
            node is None
            or brickinfo.connection(self.dragging, node.brick) is None
        ):
            return None
        return node

    def ghost(self) -> tuple[tuple[float, float], tuple[Guide, ...]] | None:
        """
        Where the brick dragged goes, the middle of its icon in the lab, and
        the guides it lines up along; None over another brick.
        """

        if self.dragging is None:
            return None
        x, y = self.pointer()
        if self.node_at(x, y, skip=self.dragging) is not None:
            return None
        lx, ly = self.to_layout(x, y)
        others = [
            icon_centre(node)
            for node in self.layout.nodes
            if node.brick is not self.dragging
        ]
        return line_up(
            (lx - self._grab[0], ly - self._grab[1]), others, SNAP / self.zoom
        )

    def place_at(self, x: float, y: float) -> Point:
        """The place of a point of the lab."""

        return Point(round(x + self.layout.left), round(y + self.layout.top))

    # Dragging a brick

    def _start_drag(self, brick: Brick, x: float, y: float) -> None:
        """Drag brick, pressed at x, y of the area."""

        node = self.node_of(brick)
        assert node is not None, "a brick pressed is in the picture"
        lx, ly = self.to_layout(x, y)
        cx, cy = icon_centre(node)
        self._grab = (lx - cx, ly - cy)
        self.dragging = brick
        self.hover = None
        self._set_cursor("grabbing")
        # the tooltips wait for the end
        self.area.set_has_tooltip(False)

    def _call_off(self) -> None:
        """No drag of a brick, now or after the press."""

        self._pressed = None
        if self.dragging is not None:
            self._end_drag()

    def _end_drag(self) -> None:
        self.dragging = None
        self._pressed = None
        if self._edge_scroll is not None:
            GLib.source_remove(self._edge_scroll)
            self._edge_scroll = None
        self._set_cursor(None)
        self.area.set_has_tooltip(True)
        self.area.queue_draw()

    def _edge_steps(self) -> tuple[int, int]:
        width, height = self.room()
        x, y = self._pointer
        return edge_step(x, width), edge_step(y, height)

    def _scroll_edges(self) -> bool:
        dx, dy = self._edge_steps()
        hadjustment, vadjustment = (
            self.get_hadjustment(),
            self.get_vadjustment(),
        )
        before = (hadjustment.get_value(), vadjustment.get_value())
        hadjustment.set_value(before[0] + dx)
        vadjustment.set_value(before[1] + dy)
        if (hadjustment.get_value(), vadjustment.get_value()) == before:
            # away from the edges, or at the end of the picture
            self._edge_scroll = None
            return GLib.SOURCE_REMOVE
        self.area.queue_draw()
        return GLib.SOURCE_CONTINUE

    # Drawing

    def on_draw(self, area: Gtk.DrawingArea, cr: cairo.Context[Any]) -> bool:
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
        line = None
        if self.dragging is not None:
            node = self.node_of(self.dragging)
            assert node is not None, "a brick gone ends its drag"
            target = self.drop_target()
            ghost = None if target is not None else self.ghost()
            if ghost is not None:
                end, guides = ghost
                line = Line(node, end, ghost=True, guides=guides)
            else:
                line = Line(node, self.to_layout(*self.pointer()), target)
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
            line,
        )
        if line is not None and line.target is not None:
            self._draw_words(cr, line.target)
        return False

    def _draw_words(self, cr: cairo.Context[Any], node: Node) -> None:
        """Under node, in sight, what a release does, in a box like the bar's."""

        assert self.dragging is not None, "words for a drag"
        words = _("Connect {brick} to {other}").format(
            brick=self.dragging.name, other=node.brick.name
        )
        # the style of a label of the bar; kept, or the style is no one's
        label = Gtk.Label()
        style = label.get_style_context()
        style.add_class("osd")
        text = self.area.create_pango_layout(words)
        text_width, text_height = text.get_pixel_size()
        width = text_width + 2 * WORDS_PADDING
        height = text_height + 2 * WORDS_PADDING
        ox, oy = self.origin()
        h = self.get_hadjustment().get_value()
        v = self.get_vadjustment().get_value()
        room_width, room_height = self.room()
        x = ox + node.x * self.zoom - width / 2
        y = oy + (node.y + node.height / 2) * self.zoom + WORDS_GAP
        x = max(min(x, h + room_width - width - WORDS_GAP), h + WORDS_GAP)
        y = max(min(y, v + room_height - height - WORDS_GAP), v + WORDS_GAP)
        background = style.get_property("background-color", style.get_state())
        rounded_rectangle(cr, x, y, width, height)
        Gdk.cairo_set_source_rgba(cr, background)
        cr.fill()
        Gtk.render_layout(
            style, cr, x + WORDS_PADDING, y + WORDS_PADDING, text
        )

    # Signals

    def on_allocated(
        self, view: TopologyView, allocation: Gdk.Rectangle
    ) -> None:
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

    def on_area_allocated(
        self, area: Gtk.DrawingArea, allocation: Gdk.Rectangle
    ) -> None:
        # the adjustments know the new size now
        if self._scroll_to is not None:
            x, y = self._scroll_to
            self._scroll_to = None
            self.get_hadjustment().set_value(x)
            self.get_vadjustment().set_value(y)

    def on_button_press(
        self, area: Gtk.DrawingArea, event: Gdk.EventButton
    ) -> bool:
        area.grab_focus()
        if event.button != 1:
            return False
        node = self.node_at(event.x, event.y)
        if node is not None:
            # the bricks are the tab's, but one moved is dragged; not after a
            # double click, which configures it
            if event.type == Gdk.EventType.DOUBLE_BUTTON_PRESS:
                self._pressed = None
            else:
                self._pressed = (node.brick, event.x, event.y)
            return False
        self._drag = (
            event.x_root,
            event.y_root,
            self.get_hadjustment().get_value(),
            self.get_vadjustment().get_value(),
        )
        self._set_cursor("grabbing")
        return True

    def on_button_release(
        self, area: Gtk.DrawingArea, event: Gdk.EventButton
    ) -> bool:
        if event.button == 1:
            self._pressed = None
        if event.button == 1 and self.dragging is not None:
            self._follow(event)
            source, target = self.dragging, self.drop_target()
            ghost = None if target is not None else self.ghost()
            self._end_drag()
            if target is not None:
                self.emit("brick-dropped", source, target.brick)
            elif ghost is not None:
                self.emit("brick-moved", source, self.place_at(*ghost[0]))
            return True
        if event.button == 1 and self._drag is not None:
            self._drag = None
            self._set_cursor(None)
            return True
        return False

    def on_motion(self, area: Gtk.DrawingArea, event: Gdk.EventMotion) -> bool:
        if self._drag is not None:
            x0, y0, h, v = self._drag
            self.get_hadjustment().set_value(h - (event.x_root - x0))
            self.get_vadjustment().set_value(v - (event.y_root - y0))
            return True
        if self._pressed is not None:
            brick, x, y = self._pressed
            if area.drag_check_threshold(
                int(x), int(y), int(event.x), int(event.y)
            ):
                self._pressed = None
                self._start_drag(brick, x, y)
        if self.dragging is not None:
            self._follow(event)
            if self._edge_scroll is None and any(self._edge_steps()):
                self._edge_scroll = GLib.timeout_add(
                    EDGE_DELAY, self._scroll_edges
                )
            area.queue_draw()
            return True
        node = self.node_at(event.x, event.y)
        if node is not self.hover:
            self.hover = node
            self._set_cursor(None if node is None else "pointer")
            area.trigger_tooltip_query()
            area.queue_draw()
        return False

    def _follow(self, event: Gdk.EventMotion | Gdk.EventButton) -> None:
        """The pointer of a drag, in the view."""

        self._pointer = (
            event.x - self.get_hadjustment().get_value(),
            event.y - self.get_vadjustment().get_value(),
        )

    def on_leave(
        self, area: Gtk.DrawingArea, event: Gdk.EventCrossing
    ) -> bool:
        if self.hover is not None and self._drag is None:
            self.hover = None
            area.queue_draw()
        return False

    def on_scroll(self, area: Gtk.DrawingArea, event: Gdk.EventScroll) -> bool:
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
        for _step in range(abs(steps)):
            if steps < 0:
                self.zoom_in(anchor)
            else:
                self.zoom_out(anchor)
        return True

    def on_key_press(self, area: Gtk.DrawingArea, event: Gdk.EventKey) -> bool:
        if self.dragging is not None and event.keyval == Gdk.KEY_Escape:
            self._end_drag()
            return True
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
            vadjustment.set_value(
                vadjustment.get_value()
                + (page if key == Gdk.KEY_Page_Down else -page)
            )
        else:
            return False
        return True

    def on_query_tooltip(
        self,
        area: Gtk.DrawingArea,
        x: int,
        y: int,
        keyboard: bool,
        tooltip: Gtk.Tooltip,
    ) -> bool:
        node = self.node_at(x, y)
        if node is None:
            return False
        tooltip.set_text(tooltip_text(node.brick))
        return True

    def on_grab_broken(
        self, area: Gtk.DrawingArea, event: Gdk.EventGrabBroken
    ) -> bool:
        self._call_off()
        return False

    def on_grab_notify(self, area: Gtk.DrawingArea, was_grabbed: bool) -> None:
        # another widget takes the input, as a dialog that opens
        if not was_grabbed:
            self._call_off()

    def on_pinch_begin(
        self, gesture: Gtk.GestureZoom, sequence: Gdk.EventSequence | None
    ) -> None:
        self._pinch_zoom = self.zoom
        found, x, y = gesture.get_bounding_box_center()
        if found:
            self._pinch_anchor = (
                x - self.get_hadjustment().get_value(),
                y - self.get_vadjustment().get_value(),
            )
        else:
            self._pinch_anchor = None

    def on_pinch(self, gesture: Gtk.GestureZoom, scale: float) -> None:
        self.set_zoom(self._pinch_zoom * scale, self._pinch_anchor)

    def on_destroy(self, view: TopologyView) -> None:
        if self._fitting_later is not None:
            GLib.source_remove(self._fitting_later)
            self._fitting_later = None
        if self._edge_scroll is not None:
            GLib.source_remove(self._edge_scroll)
            self._edge_scroll = None

    def _set_cursor(self, name: str | None) -> None:
        window = self.area.get_window()
        if window is None:
            return
        cursor = (
            None
            if name is None
            else Gdk.Cursor.new_from_name(self.area.get_display(), name)
        )
        window.set_cursor(cursor)
