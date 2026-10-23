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


"""The icons of the GUI, which come with the package."""

import os

from twisted.trial import unittest

from virtualbricks.brickfactory import BRICK_CLASSES
from virtualbricks.bricks.event import Event
from virtualbricks.gui import graphics


class FakeBrick:
    def __init__(self, type, icon=""):
        self.type = type
        self.config = type_config(icon)

    def get_type(self):
        return self.type


def type_config(icon):
    class Config:
        pass

    config = Config()
    config.icon = icon
    return config


class TestIcons(unittest.TestCase):
    def test_every_brick_has_one(self):
        for kind in [*BRICK_CLASSES.values(), Event]:
            with self.subTest(type=kind.type):
                path = graphics.icon_file(kind.type.lower() + ".png")
                self.assertTrue(os.path.isfile(path), path)

    def test_the_logo(self):
        pixbuf = graphics.load_pixbuf("virtualbricks.png")
        self.assertGreater(pixbuf.get_width(), 0)

    def test_in_the_package(self):
        self.assertEqual(
            graphics.icon_file("tap.png"),
            os.path.join(
                os.path.dirname(graphics.__file__), "data", "tap.png"
            ),
        )

    def test_brick_icon(self):
        self.assertEqual(
            graphics.brick_icon_file(FakeBrick("Switch")),
            graphics.icon_file("switch.png"),
        )
        self.assertEqual(
            graphics.brick_icon_file(FakeBrick("Qemu")),
            graphics.icon_file("qemu.png"),
        )
        machine = FakeBrick("Qemu", "/lab/router.png")
        self.assertEqual(graphics.brick_icon_file(machine), "/lab/router.png")
        # only a machine's own icon shows, for now
        switch = FakeBrick("Switch", "/lab/router.png")
        self.assertEqual(graphics.brick_icon_file(switch), "/lab/router.png")
