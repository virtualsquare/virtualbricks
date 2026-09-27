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

"""Lists of Pango text attributes."""

from twisted.trial import unittest

# first: it asks for the version of Pango
from virtualbricks.gui.pango import pango_attr_list  # isort: skip
from gi.repository import Pango  # noqa: E402


class TestAttrList(unittest.TestCase):

    def test_the_attributes(self):
        attributes = pango_attr_list(
            Pango.attr_weight_new(Pango.Weight.BOLD),
            Pango.attr_scale_new(1.15),
        )
        kinds = [
            attribute.klass.type for attribute in attributes.get_attributes()
        ]
        self.assertEqual(kinds, [Pango.AttrType.WEIGHT, Pango.AttrType.SCALE])

    def test_none(self):
        self.assertEqual(pango_attr_list().get_attributes(), [])
