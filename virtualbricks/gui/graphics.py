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
from virtualbricks.tools import is_running

__all__ = [
    "get_image",
    "pixbuf_for_brick",
    "pixbuf_for_brick_at_size",
    "pixbuf_for_brick_type",
    "pixbuf_for_running_brick",
    "pixbuf_for_running_brick_at_size",
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


def saturate_if_stopped(brick, pixbuf):
    if not is_running(brick):
        pixbuf.saturate_and_pixelate(pixbuf, 0.0, True)
    return pixbuf


def pixbuf_for_brick_at_size(brick, width, height):
    filename = brick_icon(brick)
    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(filename, width, height)
    return saturate_if_stopped(brick, pixbuf)


def pixbuf_for_brick(brick):
    filename = brick_icon(brick)
    pixbuf = GdkPixbuf.Pixbuf.new_from_file(filename)
    return saturate_if_stopped(brick, pixbuf)


def pixbuf_for_brick_type(type):
    filename = get_data_filename("%s.png" % type.lower())
    if filename is None:
        return None
    return GdkPixbuf.Pixbuf.new_from_file(filename)


def pixbuf_for_running_brick(brick):
    return GdkPixbuf.Pixbuf.new_from_file(brick_icon(brick))


def pixbuf_for_running_brick_at_size(brick, witdh, height):
    return GdkPixbuf.Pixbuf.new_from_file_at_size(
        brick_icon(brick), witdh, height
    )
