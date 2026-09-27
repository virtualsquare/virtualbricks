# -*- test-case-name: virtualbricks.tests.test_graphics -*-
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

# This module is ported to new GTK3 using PyGObject

from gi.repository import GdkPixbuf

from virtualbricks.path import get_resource_filename

__all__ = [
    "get_image",
    "pixbuf_for_brick_type",
    "get_data_filename",
]


def get_data_filename(resource):
    return get_resource_filename("virtualbricks.gui", resource)


def get_image(name):
    return get_data_filename(name)


def has_custom_icon(brick):
    return getattr(brick.config, "icon", "")


def brick_icon(brick):
    if has_custom_icon(brick):
        return brick.config.icon
    else:
        return get_data_filename(brick.get_type().lower() + ".png")


def pixbuf_for_brick_type(type):
    filename = get_data_filename("%s.png" % type.lower())
    if filename is None:
        return None
    return GdkPixbuf.Pixbuf.new_from_file(filename)
