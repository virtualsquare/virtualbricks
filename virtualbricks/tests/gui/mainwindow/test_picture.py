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

"""The picture of a lab: the icons, the names' font, and the export."""

import os
import re
import zlib

import cairo

from virtualbricks.tests.gui import GuiTestCase, has_display
from virtualbricks.topology import ICON, layout

if has_display:
    from gi.repository import Pango

    from virtualbricks.gui.mainwindow.picture import (
        FORMATS,
        MARGIN,
        Icons,
        export,
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
