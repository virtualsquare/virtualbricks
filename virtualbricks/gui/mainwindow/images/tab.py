# -*- test-case-name: virtualbricks.tests.gui.mainwindow.images.test_tab -*-
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
The Images tab of the main window: the disk images of the project, on the
tab of rows of :mod:`virtualbricks.gui.mainwindow.rowtab`.

A row says what an image is, from ``qemu-img info``, read in the background
the first time, and which machines use it and how; its state says whether a
running machine uses it, or its file is missing. Images don't start or
stop: the switch shows all the images or those in use. The rows follow the
bricks too, which use the images.

Add Image offers an existing file or a new empty disk. The menu of an image
is :mod:`virtualbricks.gui.mainwindow.images.imagemenu`'s, and its details
are :mod:`virtualbricks.gui.mainwindow.images.imagedetails`'s.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GdkPixbuf, Gio, Gtk  # noqa: E402

from virtualbricks.bricks.virtualmachine import Image, ImageDraft  # noqa: E402
from virtualbricks.config import images  # noqa: E402
from virtualbricks.gui import imageinfo  # noqa: E402
from virtualbricks.gui.imageinfo import LABELS, State  # noqa: E402
from virtualbricks.gui.mainwindow.images import imagemenu  # noqa: E402
from virtualbricks.gui.mainwindow.images.imagedetails import (  # noqa: E402
    ImageDetails,
)
from virtualbricks.gui.mainwindow.rowtab import (  # noqa: E402
    EMPTY_ICON_SIZE,
    ICON_SIZE,
    Pictures,
    Row,
    RowList,
    RowsTab,
    ThemeIcons,
    theme_icon,
)
from virtualbricks.gui.mainwindow.tab import brick_signals  # noqa: E402
from virtualbricks.gui.dialogs.addimage import (  # noqa: E402
    ExistingImageDialog,
    NewDiskDialog,
)
from virtualbricks.i18n import _, ngettext  # noqa: E402

if TYPE_CHECKING:  # pragma: no cover
    from virtualbricks.brickfactory import BrickFactory
    from virtualbricks.bricks import Brick
    from virtualbricks.config.images import ImageInfo
    from virtualbricks.gui.mainwindow.bricks.config.vm.imagepicker import (
        Infos,
    )
    from virtualbricks.gui.mainwindow.window import VBGUI
    from virtualbricks.observable import Signal

# The icon of an image, the first that the theme has.
ICONS = ("drive-harddisk", "drive-harddisk-symbolic", "media-floppy")


def count(image_list: RowList[Image], items: list[Image]) -> str:
    """How many images are in use, of how many."""

    total = len(items)
    in_use = sum(1 for item in items if image_list.running(item))
    return ngettext(
        "{in_use} of {total} in use", "{in_use} of {total} in use", total
    ).format(in_use=in_use, total=total)


class ImageRow(Row[Image]):
    """An image, what it is and who uses it, and what can be done to it."""

    GROUP = imagemenu.GROUP
    DELETE = "remove"
    STARTS = False

    def __init__(
        self,
        gui: VBGUI,
        item: Image,
        icons: Pictures[Image],
        sizes: Gtk.SizeGroup,
        infos: Infos,
    ) -> None:
        # the first update() needs it
        self.infos = infos
        super().__init__(gui, item, icons, sizes)

    def make_actions(self) -> imagemenu.ImageActions:
        return imagemenu.ImageActions(self.gui, self.item)

    def menu_model(self) -> Gio.Menu:
        return imagemenu.menu(self.item, self.there())

    def there(self) -> bool:
        """Whether the file of the image is on the machine of the bricks."""

        return self.gui.engine.machine.exists(self.item.path)

    def info(self) -> ImageInfo | None:
        """What qemu-img info says of the file, once read; read it if not."""

        path = self.item.path
        info = self.infos.get(path)
        if info is None and self.there():
            reading = self.infos.read(path)
            reading.addErrback(lambda failure: None)
            reading.addCallback(self._read)
        return info

    def _read(self, info: ImageInfo | None) -> None:
        # the file may have gone, or the row with it; what the read says,
        # once: a file that a running machine keeps changing isn't read
        # again at each change
        if info is not None and self.get_parent() is not None:
            self.show_image(info)

    def update(self, processes: bool = False) -> None:
        self.show_image(None, read=True)

    def show_image(self, info: ImageInfo | None, read: bool = False) -> None:
        """Show the image with info, or what the cache has if read."""

        image = self.item
        machine = self.gui.engine.machine
        uses = images.uses(self.gui.brickfactory, image, machine.taken)
        there = self.there()
        image_state = imageinfo.state(image, uses, there)
        if image_state is State.MISSING:
            info = None
        elif read:
            info = self.info()
        self.show_state(
            imageinfo.summary(image, info, uses, there),
            LABELS[image_state],
            image_state is State.IN_USE,
            image_state is State.MISSING,
            imageinfo.tooltip(image, image_state, uses),
        )

    def on_startstop_clicked(
        self, button: Gtk.Button
    ) -> None:  # pragma: no cover
        # no Start or Stop for an image
        pass


class ImageList(RowList[Image]):
    """
    The images of the factory, a row each. The rows follow the bricks too:
    they say which machines use the images.
    """

    NONE = _("No images")
    NO_MATCH = _("No image matches “{text}”")
    NONE_RUNNING = _("No image is in use")
    NO_RUNNING_MATCH = _("No image in use matches “{text}”")

    def __init__(self, gui: VBGUI, factory: BrickFactory) -> None:
        # the rows need it, from the first
        self.infos = gui.engine.machine.infos
        super().__init__(gui, factory)
        # what the rows of the images say of the bricks
        for signal in brick_signals(factory):
            signal.connect(self.on_brick_changed)

    def signals(self) -> tuple[Signal, Signal, Signal]:
        factory = self.factory
        return (
            factory.image_added,
            factory.image_removed,
            factory.image_changed,
        )

    def items(self) -> list[Image]:
        return list(self.factory.images)

    def make_row(self, item: Image) -> ImageRow:
        return ImageRow(self.gui, item, self.icons, self._sizes, self.infos)

    def make_icons(self) -> ThemeIcons:
        return ThemeIcons(ICONS, ICON_SIZE)

    def running(self, item: Image) -> bool:
        return any(use.running for use in images.uses(self.factory, item))

    def close(self) -> None:
        super().close()
        for signal in brick_signals(self.factory):
            signal.disconnect(self.on_brick_changed)

    def on_brick_changed(self, brick: Brick) -> None:
        self.update()


class ImagesTab(RowsTab[Image]):
    """The disk images of the project, and what can be done with them."""

    title = _("_Images")
    NEW = _("Add Image")
    SEARCH = _("Search images")
    RUNNING = _("In use")
    EMPTY_TITLE = _("No Images Yet")
    EMPTY_WORDS = _(
        "A disk image is the disk a virtual machine starts from. Add one to"
        " give a machine its disk."
    )
    STARTS = False

    def __init__(self, gui: VBGUI, factory: BrickFactory) -> None:
        super().__init__(gui, factory)
        # the menu of Add Image, made at its first click
        self._add_menu: Gtk.Popover | None = None
        for signal in brick_signals(factory):
            signal.connect(self.on_changed)

    def empty_picture(self) -> GdkPixbuf.Pixbuf | None:
        return theme_icon(ICONS, EMPTY_ICON_SIZE, grey=True)

    def make_list(self) -> ImageList:
        return ImageList(self.gui, self.factory)

    def signals(self) -> tuple[Signal, Signal, Signal]:
        factory = self.factory
        return (
            factory.image_added,
            factory.image_removed,
            factory.image_changed,
        )

    def items(self) -> list[Image]:
        return list(self.factory.images)

    def count_text(self, items: list[Image]) -> str:
        return count(self.list, items)

    def new_item(self) -> None:
        """Offer an existing image or a new empty disk, under the button."""

        if self._add_menu is None:
            self._add_menu = self._make_add_menu()
        self._add_menu.popup()

    def _make_add_menu(self) -> Gtk.Popover:
        # a popover, as the menus of the rows: the screen readers find it
        # among the widgets of the window, where a Gtk.Menu isn't
        box = Gtk.Box(
            visible=True, orientation=Gtk.Orientation.VERTICAL, margin=6
        )
        for label, callback in (
            (_("Existing Image…"), self.add_existing),
            (_("New Empty Disk…"), self.add_new),
        ):
            # a model button closes the popover when clicked
            button = Gtk.ModelButton(visible=True, text=label)
            button.connect("clicked", lambda button, call=callback: call())
            box.pack_start(button, False, False, 0)
        popover = Gtk.Popover(
            relative_to=self.new_button, position=Gtk.PositionType.BOTTOM
        )
        popover.add(box)
        return popover

    def add_existing(self) -> ExistingImageDialog:
        dialog = ExistingImageDialog(self.gui.engine)
        dialog.show(self.gui.window)
        return dialog

    def add_new(self) -> NewDiskDialog:
        dialog = NewDiskDialog(self.gui.engine)
        dialog.show(self.gui.window)
        return dialog

    def popup(
        self, widget: Gtk.Widget, event: Gdk.EventButton | None, item: Image
    ) -> Gtk.Menu:
        return imagemenu.popup(widget, event, self.gui, item, True)

    def panel_for(self, item: Image) -> ImageDetails:
        return ImageDetails(
            ImageDraft(item, self.factory), self.gui.engine.machine
        )

    def settings_words(self, item: Image) -> str:
        return _("Disk image")

    def on_quit(self) -> None:
        super().on_quit()
        for signal in brick_signals(self.factory):
            signal.disconnect(self.on_changed)
