# -*- test-case-name: virtualbricks.tests.gui.mainwindow.test_picture -*-
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
cairo in the Topology tab or in a file.

The same drawing serves both. The links are in the text colour, fainter; a
stopped brick is grey and faded, its name too; the brick under the pointer
sits on a disc of the selection colour. The tab draws at its zoom in the
colours of the theme. A file gets the lab at 100%, on white, in the colours
of a light theme, as PNG, SVG or PDF by the extension of its name.
"""

from __future__ import annotations

import dataclasses
import math
import os

import cairo
import gi

gi.require_version("Gdk", "3.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import (  # noqa: E402
    Gdk,
    GdkPixbuf,
    GLib,
    Pango,
    PangoCairo,
)

from virtualbricks.gui import graphics  # noqa: E402
from virtualbricks.i18n import _  # noqa: E402
from virtualbricks.bricks import is_running  # noqa: E402
from virtualbricks.topology import ICON  # noqa: E402

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

    def get(self, brick, running: bool) -> GdkPixbuf.Pixbuf | None:
        filename = graphics.brick_icon(brick)
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
                grey = pixbuf.copy()
                pixbuf.saturate_and_pixelate(grey, 0.0, False)
                pixbuf = grey
            self._icons[key] = pixbuf
        return self._icons[key]


def scaled_font(font: Pango.FontDescription, zoom: float):
    """A font, for the names at a zoom."""

    font = font.copy()
    size = max(1, round(font.get_size() * zoom))
    if font.get_size_is_absolute():
        font.set_absolute_size(size)
    else:
        font.set_size(size)
    return font


def draw(cr, layout, zoom, origin, palette, font, text, icons, hover=None):
    """
    Draw a layout at a zoom, from origin, a point (x, y) of cr.

    font is the names' at 100%; text(name) gives a Pango layout of a name
    to draw with cr. hover is the node on a disc, if any.
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
    for node in layout.nodes:
        running = is_running(node.brick)
        top = node.y - node.height / 2
        if node is hover:
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


def export(layout, filename: str, font: Pango.FontDescription) -> None:
    """
    Write the lab at 100%, on white, in a light theme's colours. The
    extension of filename chooses the format; another raises ValueError.
    """

    extension = os.path.splitext(filename)[1].lower()
    if extension not in FORMATS:
        raise ValueError(f"Unknown image format {extension!r}")
    width = math.ceil(layout.width + 2 * MARGIN)
    height = math.ceil(layout.height + 2 * MARGIN)
    if extension == ".png":
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    elif extension == ".svg":
        surface = cairo.SVGSurface(filename, width, height)
    else:
        surface = cairo.PDFSurface(filename, width, height)
    cr = cairo.Context(surface)
    cr.set_source_rgb(*WHITE)
    cr.paint()

    def text(name):
        result = PangoCairo.create_layout(cr)
        result.set_text(name, -1)
        return result

    draw(cr, layout, 1.0, (MARGIN, MARGIN), LIGHT, font, text, Icons())
    if extension == ".png":
        surface.write_to_png(filename)
    surface.finish()
