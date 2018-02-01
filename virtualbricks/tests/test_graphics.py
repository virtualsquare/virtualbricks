# Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
# Copyright (C) 2018 Virtualbricks team

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

import os
from virtualbricks.tests import unittest, stubs
from virtualbricks.gui import graphics
import virtualbricks.gui


GUI_PATH = os.path.dirname(virtualbricks.gui.__file__)


class TestGraphics(unittest.TestCase):

    def setUp(self):
        self.factory = stubs.FactoryStub()
        self.brick = stubs.BrickStub(self.factory, "Test")

    def test_get_filename(self):
        filename = graphics.get_filename("virtualbricks.gui", "data/test")
        self.assertTrue(filename.endswith("virtualbricks/gui/data/test"))

    def test_get_data_filename(self):
        filename = graphics.get_data_filename("randompath")
        self.assertTrue(filename.endswith("virtualbricks/gui/data/randompath"))

    def test_brick_icon(self):
        self.assertEqual(graphics.brick_icon(self.brick),
                         GUI_PATH + "/data/stub.png")
