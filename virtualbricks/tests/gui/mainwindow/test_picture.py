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
The picture of a lab: the icons, the names' font, the line of a brick
dragged, and the export.
"""

import os
import re
import zlib

import cairo

from virtualbricks.tests.gui import GuiTestCase, has_display
from virtualbricks.topology import ICON, layout

if has_display:
    from gi.repository import Gtk, Pango

    from virtualbricks.gui.mainwindow.picture import (
        FORMATS,
        LIGHT,
        MARGIN,
        Icons,
        Line,
        draw,
        export,
        icon_centre,
        scaled_font,
    )

FONT = "Sans 10"


def inflated(pdf):
    """A PDF with its compressed streams inflated: cairo keeps the pages'
    objects in them."""

    parts = [pdf]
    for stream in re.findall(rb"stream\r?\n(.*?)\r?\nendstream", pdf, re.S):
        try:
            parts.append(zlib.decompress(stream))
        except zlib.error:
            pass
    return b"".join(parts)


class PictureTestCase(GuiTestCase):

    def setUp(self):
        super().setUp()
        self.sw1 = self.factory.new_brick("switch", "sw1")
        self.sw2 = self.factory.new_brick("switch", "sw2")
        self.vm = self.factory.new_brick("qemu", "vm")
        self.vm.connect(self.sw1.socks[0])
        self.vm.connect(self.sw2.socks[0])
        for brick in self.factory.bricks:
            brick.is_running = lambda name=brick.name: name == "sw1"
        self.lab = layout(self.factory.bricks)
        self.font = Pango.FontDescription.from_string(FONT)


class TestIcons(PictureTestCase):

    def test_each_read_once(self):
        icons = Icons()
        icon = icons.get(self.sw1, True)
        # the same file
        self.assertIs(icons.get(self.sw2, True), icon)
        self.assertIsNot(icons.get(self.sw1, False), icon)

    def test_grey_when_stopped(self):
        icon = Icons().get(self.sw1, False)
        pixels = icon.get_pixels()
        channels = icon.get_n_channels()
        for i in range(0, len(pixels) - channels, channels * 7):
            r, g, b = pixels[i : i + 3]
            self.assertTrue(abs(r - g) <= 1 and abs(g - b) <= 1, (r, g, b))

    def test_an_icon_not_there(self):
        # a virtual machine's own icon
        self.vm.config.icon = "/nowhere.png"
        self.assertIsNone(Icons().get(self.vm, True))


class TestTheFontOfTheNames(PictureTestCase):

    def test_scaled(self):
        font = Pango.FontDescription.from_string("Sans 10")
        self.assertEqual(scaled_font(font, 2.0).get_size(), 20 * Pango.SCALE)
        self.assertEqual(font.get_size(), 10 * Pango.SCALE)
        font.set_absolute_size(12 * Pango.SCALE)
        big = scaled_font(font, 0.5)
        self.assertTrue(big.get_size_is_absolute())
        self.assertEqual(big.get_size(), 6 * Pango.SCALE)
        # never nothing
        self.assertEqual(scaled_font(font, 0.0).get_size(), 1)


class TestTheLineOfADrag(PictureTestCase):
    """sw1, vm and sw2 in a row, in this order, vm plugged into both."""

    def draw(self, hover=None, line=None):
        width = round(self.lab.width + 2 * MARGIN)
        height = round(self.lab.height + 2 * MARGIN)
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
        cr = cairo.Context(surface)
        cr.set_source_rgb(1, 1, 1)
        cr.paint()
        draw(
            cr,
            self.lab,
            1.0,
            (MARGIN, MARGIN),
            LIGHT,
            self.font,
            # the names as the tab lays them out
            Gtk.Label().create_pango_layout,
            Icons(),
            hover,
            line,
        )
        surface.flush()
        return surface

    def pixel(self, surface, x, y):
        data = surface.get_data()
        offset = int(y) * surface.get_stride() + int(x) * 4
        b, g, r, a = data[offset : offset + 4]
        return r, g, b

    def node(self, name):
        return next(n for n in self.lab.nodes if n.brick.name == name)

    def centre(self, name):
        """The middle of the icon of a brick, in the picture."""

        x, y = icon_centre(self.node(name))
        return MARGIN + x, MARGIN + y

    def row(self, surface, start, end, y):
        return [self.pixel(surface, x, y) for x in range(start, end)]

    def blue(self, pixel):
        r, g, b = pixel
        return b > r + 10

    def test_dashed_to_a_point(self):
        (x0, y), (x1, _y) = self.centre("sw1"), self.centre("vm")
        self.assertEqual(_y, y)
        middle = (x0 + x1) // 2
        surface = self.draw(line=Line(self.node("sw1"), (middle - MARGIN, 32)))
        # beyond the disc of sw1, to the point
        row = self.row(surface, int(x0) + 40, int(middle) - 1, y)
        dashes = [p for p in row if self.blue(p)]
        gaps = [p for p in row if p == (255, 255, 255)]
        self.assertGreater(len(dashes), len(row) * 0.4)
        self.assertGreater(len(gaps), len(row) * 0.2)
        # no further
        self.assertEqual(
            set(self.row(surface, int(middle) + 2, int(x1) - 40, y)),
            {(255, 255, 255)},
        )

    def test_solid_to_a_brick(self):
        (x0, y), (x1, _y) = self.centre("sw1"), self.centre("vm")
        line = Line(self.node("sw1"), (0, 0), self.node("vm"))
        surface = self.draw(line=line)
        row = self.row(surface, int(x0) + 40, int(x1) - 40, y)
        self.assertTrue(all(self.blue(p) for p in row), row)

    def test_under_the_bricks(self):
        # from vm into the icon of sw1, opaque as sw1 runs; the icons sit
        # above their middle
        x0, y0 = icon_centre(self.node("vm"))
        x1, y1 = 40, 14
        surface = self.draw(line=Line(self.node("vm"), (x1, y1)))
        plain = self.draw()
        spots = [
            (MARGIN + x, MARGIN + y0 + (y1 - y0) * (x - x0) / (x1 - x0))
            for x in range(44, 60)
        ]
        # the icon is there, and hides the line: nearly opaque, a little of
        # it shows through, but no blue
        for spot in spots:
            self.assertNotEqual(self.pixel(plain, *spot), (255, 255, 255))
            self.assertFalse(self.blue(self.pixel(surface, *spot)), spot)
        # and the line is there, out of the icon
        x = int(x0) - 50
        y = y0 + (y1 - y0) * (x - x0) / (x1 - x0)
        self.assertTrue(
            any(
                self.blue(self.pixel(surface, MARGIN + x + dx, MARGIN + y))
                for dx in range(10)
            )
        )

    def test_the_discs_of_both(self):
        def beside(name, side):
            x, y = self.centre(name)
            return x + side * (ICON / 2 + 3), y

        # sw1 on the left of vm: away from the line
        spots = beside("sw1", -1), beside("vm", 1), beside("sw2", 1)
        plain = self.draw()
        for spot in spots:
            self.assertEqual(self.pixel(plain, *spot), (255, 255, 255))
        line = Line(self.node("sw1"), (0, 0), self.node("vm"))
        surface = self.draw(line=line)
        dragged, target, other = (self.pixel(surface, *s) for s in spots)
        self.assertTrue(self.blue(dragged))
        self.assertTrue(self.blue(target))
        self.assertEqual(other, (255, 255, 255))
        # to a point: the brick dragged only
        surface = self.draw(line=Line(self.node("sw1"), (0, 0)))
        dragged, target, other = (self.pixel(surface, *s) for s in spots)
        self.assertTrue(self.blue(dragged))
        self.assertEqual(target, (255, 255, 255))


class TestExport(PictureTestCase):

    def path(self, name):
        return os.path.join(self.mktemp() + "-dir", name)

    def export(self, name):
        path = self.path(name)
        os.makedirs(os.path.dirname(path))
        export(self.lab, path, self.font)
        return path

    def start(self, path, size):
        with open(path, "rb") as fp:
            return fp.read(size)

    def test_the_formats(self):
        self.assertEqual(sorted(FORMATS), [".pdf", ".png", ".svg"])
        self.assertEqual(
            self.start(self.export("lab.png"), 8), b"\x89PNG\r\n\x1a\n"
        )
        self.assertIn(b"<svg", self.start(self.export("lab.svg"), 200))
        self.assertEqual(self.start(self.export("lab.pdf"), 5), b"%PDF-")
        # whatever the case of the extension
        self.assertEqual(self.start(self.export("LAB.PNG"), 4), b"\x89PNG")

    def test_another_format(self):
        path = self.path("lab.jpg")
        os.makedirs(os.path.dirname(path))
        self.assertRaises(ValueError, export, self.lab, path, self.font)
        self.assertRaises(
            ValueError, export, self.lab, self.path("lab"), self.font
        )
        self.assertFalse(os.path.exists(path))

    def test_at_100_percent_with_its_margins(self):
        surface = cairo.ImageSurface.create_from_png(self.export("lab.png"))
        self.assertEqual(
            (surface.get_width(), surface.get_height()),
            (
                round(self.lab.width + 2 * MARGIN),
                round(self.lab.height + 2 * MARGIN),
            ),
        )
        # the same size in points
        with open(self.export("lab.pdf"), "rb") as fp:
            pdf = inflated(fp.read())
        width = round(self.lab.width + 2 * MARGIN)
        height = round(self.lab.height + 2 * MARGIN)
        box = f"/MediaBox [ 0 0 {width} {height} ]".encode()
        self.assertTrue(box in pdf, box)

    def pixel(self, surface, x, y):
        data = surface.get_data()
        offset = int(y) * surface.get_stride() + int(x) * 4
        b, g, r, a = data[offset : offset + 4]
        return r, g, b

    def icon_colours(self, surface, name):
        node = next(n for n in self.lab.nodes if n.brick.name == name)
        x, y = MARGIN + node.x, MARGIN + node.y - node.height / 2 + ICON / 2
        return {
            self.pixel(surface, x + dx, y + dy)
            for dx in range(-ICON // 2 + 2, ICON // 2 - 2, 2)
            for dy in range(-ICON // 2 + 2, ICON // 2 - 2, 2)
        }

    def test_on_white_in_light_colours(self):
        surface = cairo.ImageSurface.create_from_png(self.export("lab.png"))
        self.assertEqual(self.pixel(surface, 1, 1), (255, 255, 255))
        coloured = self.icon_colours(surface, "sw1")
        self.assertTrue(any(len({r, g, b}) > 1 for r, g, b in coloured))
        grey = self.icon_colours(surface, "sw2")
        self.assertTrue(
            all(abs(r - g) <= 2 and abs(g - b) <= 2 for r, g, b in grey)
        )
        # the names in dark text
        node = next(n for n in self.lab.nodes if n.brick.name == "sw1")
        top = MARGIN + node.y - node.height / 2 + ICON
        darkest = min(
            (
                self.pixel(surface, MARGIN + node.x + dx, top + dy)
                for dx in range(-15, 15)
                for dy in range(0, 20)
            ),
            key=sum,
        )
        self.assertLess(sum(darkest), 3 * 120)

    def test_a_folder_not_there(self):
        for name in ("lab.png", "lab.svg", "lab.pdf"):
            self.assertRaises(
                OSError, export, self.lab, self.path(name), self.font
            )
