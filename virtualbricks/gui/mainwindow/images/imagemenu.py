# -*- test-case-name: virtualbricks.tests.gui.mainwindow.images.test_imagemenu -*-
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
The menu of a disk image, in the Images tab.

``menu()`` makes the ``Gio.Menu`` of an image, and ``ImageActions`` the
group of actions its items call, under the prefix ``image``: Details,
Rename, Show in Files and Remove. For an image whose file is missing, Find
the File comes first, and Show in Files can't show it.
"""

from __future__ import annotations

import functools
import os

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gio, Gtk  # noqa: E402

from virtualbricks.gui.mainwindow import tab  # noqa: E402
from virtualbricks.gui.mainwindow.tab import (  # noqa: E402
    menu_item,
    menu_of,
    menu_section,
)
from virtualbricks.gui.windows.imagedialogs import (  # noqa: E402
    FindFileDialog,
    show_in_files,
)
from virtualbricks.gui.windows.renamedialog import RenameDialog  # noqa: E402
from virtualbricks.i18n import _  # noqa: E402

GROUP = "image"

_item = functools.partial(menu_item, GROUP)


def menu(image, keys=False) -> Gio.Menu:
    """
    The menu of image. keys shows the keys of the Images tab next to the
    items: Enter, F2 and Delete.
    """

    def key(name):
        return name if keys else None

    missing = not os.path.exists(image.get_path())
    return menu_of(
        menu_section(
            _item(_("Find the File…"), "find-file") if missing else None
        ),
        menu_section(_item(_("Details…"), "details", keys=key("Return"))),
        menu_section(
            _item(_("Rename…"), "rename", keys=key("F2")),
            _item(_("Show in Files"), "show"),
        ),
        menu_section(_item(_("Remove…"), "remove", keys=key("Delete"))),
    )


class ImageActions(Gio.SimpleActionGroup):
    """What the items of the menu of an image do."""

    def __init__(self, gui, image) -> None:
        super().__init__()
        self.gui = gui
        self.image = image
        for name, callback in (
            ("find-file", self.find_file),
            ("details", self.details),
            ("rename", self.rename),
            ("show", self.show),
            ("remove", self.remove),
        ):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", lambda a, p, call=callback: call())
            self.add_action(action)
        self.update()

    def update(self) -> None:
        """The actions that the image allows now."""

        there = os.path.exists(self.image.get_path())
        self.lookup_action("find-file").set_enabled(not there)
        self.lookup_action("show").set_enabled(there)

    def find_file(self) -> None:
        FindFileDialog(self.gui.brickfactory, self.image).show(self.gui.window)

    def details(self) -> None:
        self.gui.curtain_up(self.image)

    def rename(self) -> None:
        RenameDialog(self.gui.brickfactory, self.image).show(self.gui.window)

    def show(self) -> None:
        show_in_files(self.gui.window, self.image.get_path())

    def remove(self) -> None:
        self.gui.ask_remove_image(self.image)


def popup(widget, event, gui, image, keys=False) -> Gtk.Menu:
    """
    Open the menu of image: at the pointer, for a click on widget, or under
    widget when event is None, as for the Menu key. Keep the menu that it
    returns while it shows.
    """

    return tab.popup(
        widget, event, menu(image, keys), GROUP, ImageActions(gui, image)
    )
