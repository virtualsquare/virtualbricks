# -*- test-case-name: virtualbricks.tests.gui.test_graphics -*-
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

"""The icons of the GUI, in ``virtualbricks/gui/data``."""

import os

import gi

gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf

__all__ = ["brick_icon", "icon_file", "load_pixbuf"]

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def icon_file(name: str) -> str:
    """The path of an icon of the GUI."""

    return os.path.join(DATA_DIR, name)


def load_pixbuf(name: str) -> GdkPixbuf.Pixbuf:
    """Load an icon of the GUI."""

    return GdkPixbuf.Pixbuf.new_from_file(icon_file(name))


def has_custom_icon(brick):
    # every brick has an icon, but only a machine's shows, for now
    return brick.get_type() == "Qemu" and brick.config.icon


def brick_icon(brick):
    if has_custom_icon(brick):
        return brick.config.icon
    else:
        return icon_file(brick.get_type().lower() + ".png")
