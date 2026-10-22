# -*- test-case-name: virtualbricks.tests.gui.mainwindow.test_picture -*-
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
cairo in the Topology tab or in a file.

The same drawing serves both. The links are in the text colour, fainter; a
stopped brick is grey and faded, its name too; the brick under the pointer
sits on a disc of the selection colour. A brick dragged in the tab keeps its
disc, with a line in the selection colour under the bricks: dashed to the
pointer, or solid to the brick it connects to, on a disc too; or dashed to
a faded copy of the brick on a disc, over the bricks, where a move puts it,
with thin guides to the bricks it lines up with. The tab draws at its zoom
in the colours of the theme. A file gets the lab at 100%, on white, in the
colours of a light theme, as PNG, SVG or PDF by the extension of its name.
"""

from __future__ import annotations

import dataclasses
import math
import os
from collections.abc import Callable
from typing import Any

import cairo
from gi.repository import (
    Gdk,
    GdkPixbuf,
    GLib,
    Pango,
    PangoCairo,
)

from virtualbricks.bricks import Base, Brick, is_running
from virtualbricks.gui import graphics
from virtualbricks.i18n import _
from virtualbricks.topology import ICON, Layout, Node

# Around the lab, in pixels.
MARGIN = 20
# The links in the text colour, and the stopped bricks, this opaque.
LINK_ALPHA = 0.6
STOPPED_ALPHA = 0.5
HOVER_ALPHA = 0.18
# The width of the links, in pixels, and the gap between the icon and the
# disc of the brick under the pointer, in points.
LINE_WIDTH = 1.6
DISC_GAP = 6
# The line of a brick dragged, in pixels: its width, and the dashes and the
# gaps of the line that goes nowhere.
DRAG_WIDTH = 2.0
DASHES = (6.0, 4.0)
# The copy of a brick moved this opaque, and its guides: their width in
# pixels, and how far they go past their ends, in points.
GHOST_ALPHA = 0.45
GUIDE_WIDTH = 1.0
GUIDE_ALPHA = 0.8
GUIDE_PAST = ICON / 2 + DISC_GAP
# The formats of an exported picture, by the extension of the file.
FORMATS = {
    ".png": _("PNG image"),
    ".svg": _("SVG image"),
    ".pdf": _("PDF document"),
}


@dataclasses.dataclass(frozen=True)
class Palette:
    """The colours of a picture, each (red, green, blue) from 0 to 1."""

    ink: tuple[float, float, float]
    selection: tuple[float, float, float]


@dataclasses.dataclass(frozen=True)
class Guide:
    """A guide from the middle of an icon to the middle of another's."""

    start: tuple[float, float]
    end: tuple[float, float]


@dataclasses.dataclass(frozen=True)
class Line:
    """
    The line of a brick dragged: from its node to end, a point of the lab,
    or to target, the node of the brick it connects to. With ghost, a copy
    of the brick has the middle of its icon at end, and guides go to it.
    """

    node: Node
    end: tuple[float, float]
    target: Node | None = None
    ghost: bool = False
    guides: tuple[Guide, ...] = ()


def icon_centre(node: Node) -> tuple[float, float]:
    return node.x, node.y - node.height / 2 + ICON / 2


# Adwaita's text and selection: an exported picture's, on white.
LIGHT = Palette(
    (0x2E / 255, 0x34 / 255, 0x36 / 255), (0x35 / 255, 0x84 / 255, 0xE4 / 255)
)
WHITE = (1.0, 1.0, 1.0)


class Icons:
    """
    The icons of the bricks, grey for the stopped ones, each read once, at
    their size or at size pixels.
    """

    def __init__(self, size: int | None = None) -> None:
        self.size = size
        self._icons: dict[tuple[str, bool], GdkPixbuf.Pixbuf | None] = {}

    def get(self, brick: Base, running: bool) -> GdkPixbuf.Pixbuf | None:
        filename = graphics.brick_icon_file(brick)
        key = (filename, running)
        if key not in self._icons:
            try:
                if self.size is None:
                    pixbuf = GdkPixbuf.Pixbuf.new_from_file(filename)
                else:
                    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(
                        filename, self.size, self.size
                    )
            except GLib.Error:
                pixbuf = None
            if pixbuf is not None and not running:
                pixbuf = greyed(pixbuf)
            self._icons[key] = pixbuf
        return self._icons[key]


def greyed(pixbuf: GdkPixbuf.Pixbuf) -> GdkPixbuf.Pixbuf:
    """A copy of pixbuf, grey."""

    grey = pixbuf.copy()
    assert grey is not None, "only out of memory is there no copy"
    pixbuf.saturate_and_pixelate(grey, 0.0, False)
    return grey


def scaled_font(
    font: Pango.FontDescription, zoom: float
) -> Pango.FontDescription:
    """A font, for the names at a zoom."""

    scaled = font.copy()
    assert scaled is not None, "a copy of a font is a font"
    size = max(1, round(scaled.get_size() * zoom))
    if scaled.get_size_is_absolute():
        scaled.set_absolute_size(size)
    else:
        scaled.set_size(size)
    return scaled


def draw(
    cr: cairo.Context[Any],
    layout: Layout,
    zoom: float,
    origin: tuple[float, float],
    palette: Palette,
    font: Pango.FontDescription,
    text: Callable[[str], Pango.Layout],
    icons: Icons,
    hover: Node | None = None,
    line: Line | None = None,
) -> None:
    """
    Draw a layout at a zoom, from origin, a point (x, y) of cr.

    font is the names' at 100%; text(name) gives a Pango layout of a name
    to draw with cr. hover is the node on a disc, if any; line, the line of
    a brick dragged, whose ends are on discs too.
    """

    ox, oy = origin
    cr.save()
    cr.translate(ox, oy)
    cr.scale(zoom, zoom)
    cr.set_source_rgba(*palette.ink, LINK_ALPHA)
    cr.set_line_width(min(max(1.0, LINE_WIDTH * zoom), 3.0) / zoom)
    for link in layout.links:
        (x, y), rest = link.points[0], link.points[1:]
        cr.move_to(x, y)
        for i in range(0, len(rest) - 2, 3):
            cr.curve_to(*rest[i], *rest[i + 1], *rest[i + 2])
        cr.stroke()
    discs = [hover]
    if line is not None:
        discs += [line.node, line.target]
        cr.save()
        cr.set_source_rgb(*palette.selection)
        cr.set_line_width(DRAG_WIDTH / zoom)
        if line.target is None:
            cr.set_dash([length / zoom for length in DASHES])
        cr.move_to(*icon_centre(line.node))
        cr.line_to(
            *(line.end if line.target is None else icon_centre(line.target))
        )
        cr.stroke()
        cr.set_dash([])
        cr.set_line_width(GUIDE_WIDTH / zoom)
        cr.set_source_rgba(*palette.selection, GUIDE_ALPHA)
        for guide in line.guides:
            _guide(cr, guide)
        cr.restore()
    for node in layout.nodes:
        running = is_running(node.brick)
        top = node.y - node.height / 2
        if any(node is disc for disc in discs):
            cr.set_source_rgba(*palette.selection, HOVER_ALPHA)
            cr.arc(node.x, top + ICON / 2, ICON / 2 + DISC_GAP, 0, 2 * math.pi)
            cr.fill()
        icon = icons.get(node.brick, running)
        if icon is not None:
            cr.save()
            cr.translate(node.x - ICON / 2, top)
            cr.scale(ICON / icon.get_width(), ICON / icon.get_height())
            Gdk.cairo_set_source_pixbuf(cr, icon, 0, 0)
            cr.get_source().set_filter(cairo.FILTER_GOOD)
            cr.paint_with_alpha(1.0 if running else STOPPED_ALPHA)
            cr.restore()
    if line is not None and line.ghost:
        _ghost(cr, line.node.brick, line.end, palette, icons)
    cr.restore()

    # the names at the size of the zoom, laid out by Pango at that size
    font = scaled_font(font, zoom)
    for node in layout.nodes:
        alpha = 1.0 if is_running(node.brick) else STOPPED_ALPHA
        name = text(node.brick.name)
        name.set_font_description(font)
        name.set_width(round(node.width * zoom * Pango.SCALE))
        name.set_alignment(Pango.Alignment.CENTER)
        name.set_ellipsize(Pango.EllipsizeMode.END)
        top = node.y - node.height / 2 + ICON
        cr.move_to(ox + (node.x - node.width / 2) * zoom, oy + top * zoom + 2)
        cr.set_source_rgba(*palette.ink, alpha)
        PangoCairo.show_layout(cr, name)


def _guide(cr: cairo.Context[Any], guide: Guide) -> None:
    """A guide, past both its ends."""

    (x0, y0), (x1, y1) = guide.start, guide.end
    length = math.hypot(x1 - x0, y1 - y0)
    if length == 0:
        return
    dx, dy = (x1 - x0) / length * GUIDE_PAST, (y1 - y0) / length * GUIDE_PAST
    cr.move_to(x0 - dx, y0 - dy)
    cr.line_to(x1 + dx, y1 + dy)
    cr.stroke()


def _ghost(
    cr: cairo.Context[Any],
    brick: Brick,
    centre: tuple[float, float],
    palette: Palette,
    icons: Icons,
) -> None:
    """A faded copy of the icon of brick, on a disc, its middle at centre."""

    x, y = centre
    cr.set_source_rgba(*palette.selection, HOVER_ALPHA)
    cr.arc(x, y, ICON / 2 + DISC_GAP, 0, 2 * math.pi)
    cr.fill()
    icon = icons.get(brick, is_running(brick))
    if icon is None:
        return
    cr.save()
    cr.translate(x - ICON / 2, y - ICON / 2)
    cr.scale(ICON / icon.get_width(), ICON / icon.get_height())
    Gdk.cairo_set_source_pixbuf(cr, icon, 0, 0)
    cr.get_source().set_filter(cairo.FILTER_GOOD)
    cr.paint_with_alpha(GHOST_ALPHA)
    cr.restore()


def export(layout: Layout, filename: str, font: Pango.FontDescription) -> None:
    """
    Write the lab at 100%, on white, in a light theme's colours. The
    extension of filename chooses the format; another raises ValueError.
    """

    extension = os.path.splitext(filename)[1].lower()
    if extension not in FORMATS:
        raise ValueError(f"Unknown image format {extension!r}")
    width = math.ceil(layout.width + 2 * MARGIN)
    height = math.ceil(layout.height + 2 * MARGIN)
    surface: cairo.Surface
    if extension == ".png":
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    elif extension == ".svg":
        surface = cairo.SVGSurface(filename, width, height)
    else:
        surface = cairo.PDFSurface(filename, width, height)
    cr = cairo.Context(surface)
    cr.set_source_rgb(*WHITE)
    cr.paint()

    def text(name: str) -> Pango.Layout:
        result = PangoCairo.create_layout(cr)
        result.set_text(name, -1)
        return result

    draw(cr, layout, 1.0, (MARGIN, MARGIN), LIGHT, font, text, Icons())
    if extension == ".png":
        surface.write_to_png(filename)
    surface.finish()
