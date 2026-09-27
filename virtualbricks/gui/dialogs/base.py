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
Code shared by the windows and dialogs that build their UI in Python.

Every window subclasses ``_Dialog`` or ``Window`` and implements
``build_ui()``, that creates the widgets, and ``get_root_widget()``, that
returns the main widget. Who wants to know when a window closes connects to
the ``destroy`` signal of that widget. The brick
configuration panels have their own base, in
:mod:`virtualbricks.gui.mainwindow.bricks.config.base`.
"""

import functools
from typing import Callable

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf, Pango

from virtualbricks.gui import graphics
from virtualbricks.tools import dispose

TRANSLATION_DOMAIN = "virtualbricks"


def load_pixbuf(name: str) -> GdkPixbuf.Pixbuf:
    """
    Load an image from the ``virtualbricks/gui/data`` directory, the same
    directory Gtk.Builder used to resolve the image paths of the Glade files.
    """

    return GdkPixbuf.Pixbuf.new_from_file(graphics.get_image(name))


def pango_attr_list(*attributes: Pango.Attribute) -> Pango.AttrList:
    """Return a Pango.AttrList with the given attributes."""

    attr_list = Pango.AttrList()
    for attribute in attributes:
        attr_list.insert(attribute)
    return attr_list


def destroy_on_exit(func: Callable) -> Callable:
    @functools.wraps(func)
    def on_response(self, dialog, *args):
        try:
            return func(self, dialog, *args)
        finally:
            dialog.destroy()

    return on_response


NUMERIC = set(map(str, range(10)))
NUMPAD = set(map(lambda i: "KP_%d" % i, range(10)))
EXTRA = set(["BackSpace", "Delete", "Left", "Right", "Home", "End", "Tab"])
VALIDKEY = NUMERIC | NUMPAD | EXTRA


class _Dialog:
    """A window or a dialog: show() shows it, above parent if given."""

    def show(self, parent=None):
        window = self.get_root_widget()
        if parent is not None:
            window.set_transient_for(parent)
        window.show()


class Window:
    """
    Base class for the dialogs that used ``virtualbricks.gui.dialogs.Window``.

    The UI is built when the instance is created.
    """

    def __init__(self):
        self.build_ui()

    def set_transient_for(self, parent):
        self.get_root_widget().set_transient_for(parent)

    def show(self, parent=None):
        window = self.get_root_widget()
        if parent is not None:
            window.set_transient_for(parent)
        window.connect("destroy", self.on_window_destroy)
        window.show()

    def on_window_destroy(self, window):
        dispose(self)

    def __dispose__(self):
        pass
