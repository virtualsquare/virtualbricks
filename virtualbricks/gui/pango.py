# -*- test-case-name: virtualbricks.tests.gui.test_pango -*-
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

"""Pango for the widgets built in Python: lists of text attributes."""

import gi

gi.require_version("Pango", "1.0")
from gi.repository import Pango  # noqa: E402


def pango_attr_list(*attributes: Pango.Attribute) -> Pango.AttrList:
    """Return a Pango.AttrList with the given attributes."""

    attr_list = Pango.AttrList()
    for attribute in attributes:
        attr_list.insert(attribute)
    return attr_list
