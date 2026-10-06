# -*- test-case-name: virtualbricks.tests.gui.dialogs.test_addimage -*-
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
The two ways to add a disk image to the library: an existing file, or a new
empty disk.

Add an Existing Image reads the file with ``qemu-img info`` as soon as it's
chosen, and waits for a file that is a disk image. The name starts from the
file name and is checked as it's typed. A file outside the workspace is
copied to the image folder by default, keeping its holes; Use It Where It Is
keeps its path, and a file above a backing file is always used where it is.
The description starts from a ``<file>.md`` beside the file, as plain text.

New Empty Disk asks a name, a size in MB or GB and a format, qcow2 or raw,
and makes the file in the image folder, or another folder, with ``qemu-img
create``.

Both add the image to the library, then call ``on_added`` with it. The
engine reads the file, makes the new one and adds the image; the copy is
made here.
"""

from __future__ import annotations

import math
import os
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gtk, Pango
from twisted.internet import defer, threads

from virtualbricks import errors
from virtualbricks.config import images
from virtualbricks.config.workspace import Workspace, copy_sparse
from virtualbricks.gui import imageinfo
from virtualbricks.gui.pango import pango_attr_list
from virtualbricks.gui.pathentry import PathCompletion
from virtualbricks.i18n import _

if TYPE_CHECKING:  # pragma: no cover
    from twisted.python.failure import Failure

    from virtualbricks.brickfactory import BrickFactory
    from virtualbricks.bricks.virtualmachine import Image
    from virtualbricks.config.images import ImageInfo
    from virtualbricks.engine import Engine
    from virtualbricks.remote.client import RemoteWorkspace

MARGIN = 18
GAP = 6
# The units of the size of a new disk, in bytes.
UNITS = (("MB", 1000**2), ("GB", 1000**3))
FORMATS = ("qcow2", "raw")


def _label(
    text: str = "",
    dim: bool = False,
    bold: bool = False,
    wrap: bool = False,
    visible: bool = True,
    **props: Any,
) -> Gtk.Label:
    label = Gtk.Label(
        visible=visible, label=text, xalign=0.0, wrap=wrap, **props
    )
    if dim:
        label.get_style_context().add_class("dim-label")
    if bold:
        label.set_attributes(
            pango_attr_list(Pango.attr_weight_new(Pango.Weight.BOLD))
        )
    return label


def _dialog(title: str, action: str) -> tuple[Gtk.Dialog, Gtk.Widget]:
    dialog = Gtk.Dialog(
        title=title,
        use_header_bar=True,
        modal=True,
        destroy_with_parent=True,
        default_width=460,
    )
    dialog.add_button(_("Cancel"), Gtk.ResponseType.CANCEL)
    button = dialog.add_button(action, Gtk.ResponseType.OK)
    button.get_style_context().add_class("suggested-action")
    dialog.set_default_response(Gtk.ResponseType.OK)
    return dialog, button


def check_name(factory: BrickFactory, name: str) -> str | None:
    """What is wrong with a name for a new image, if anything."""

    try:
        factory.check_name(name)
    except errors.InvalidNameError as exc:
        return str(exc)
    return None


def name_from_file(path: str) -> str:
    """A name for the image of a file: its name without extension."""

    stem = os.path.splitext(os.path.basename(path))[0]
    return stem.replace(" ", "_")


def read_description(path: str) -> str:
    """The description in ``<file>.md`` beside path, if there's one."""

    try:
        with open(path + ".md", encoding="utf-8") as fp:
            return fp.read().strip()
    except (OSError, UnicodeDecodeError):
        return ""


class _AddDialog:

    # called with the image added
    on_added: Callable[[Image], object] | None = None
    engine: Engine
    factory: BrickFactory
    # the workspace of the machine of the bricks
    workspace: Workspace | RemoteWorkspace
    dialog: Gtk.Dialog
    working: bool

    def check(self) -> bool:
        """Whether the dialog can add; if not, it says why."""

        raise NotImplementedError

    def show(self, parent: Gtk.Window | None = None) -> None:
        if parent is not None:
            self.dialog.set_transient_for(parent)
        self.dialog.show()

    def get_root_widget(self) -> Gtk.Dialog:
        return self.dialog

    def _image_folder(self) -> str:
        """The image folder, made if it isn't there: of this computer."""

        assert isinstance(self.workspace, Workspace), "files made here only"
        return images.image_folder(self.workspace)

    def _grid(self) -> Gtk.Grid:
        grid = Gtk.Grid(
            visible=True, row_spacing=GAP, column_spacing=12, margin=MARGIN
        )
        self.dialog.get_content_area().pack_start(grid, True, True, 0)
        return grid

    def _name_rows(self, grid: Gtk.Grid, row: int) -> None:
        label = _label(_("Name"), bold=True)
        self.name_entry = Gtk.Entry(
            visible=True, hexpand=True, activates_default=True
        )
        label.set_mnemonic_widget(self.name_entry)
        self.name_message = _label(dim=True, wrap=True, visible=False)
        grid.attach(label, 0, row, 1, 1)
        grid.attach(self.name_entry, 1, row, 1, 1)
        grid.attach(self.name_message, 1, row + 1, 1, 1)
        self.name_entry.connect("changed", lambda entry: self.check())

    def _error_row(self, grid: Gtk.Grid, row: int) -> None:
        self.error_label = _label(wrap=True, selectable=True, visible=False)
        self.error_label.get_style_context().add_class("error")
        grid.attach(self.error_label, 0, row, 2, 1)

    def _name_ok(self) -> bool:
        name = self.name_entry.get_text()
        # no word for a name not typed yet: the button says it
        message = check_name(self.factory, name) if name else None
        self.name_message.set_text(message or "")
        self.name_message.set_visible(message is not None)
        return bool(name) and message is None

    def _added(self, image: Image) -> Image:
        self.dialog.destroy()
        if self.on_added is not None:
            self.on_added(image)
        return image

    def _failed(self, failure: Failure) -> None:
        self.working = False
        self.error_label.set_text(failure.getErrorMessage())
        self.error_label.show()
        self.check()


class ExistingImageDialog(_AddDialog):
    """Add an image of an existing file."""

    def __init__(
        self,
        engine: Engine,
        workspace: Workspace | RemoteWorkspace | None = None,
    ) -> None:
        self.engine = engine
        self.factory = engine.factory
        self.workspace = engine.workspace if workspace is None else workspace
        self.path: str | None = None
        self.info: ImageInfo | None = None
        self.working = False
        self.build_ui()
        self.check()

    def build_ui(self) -> None:
        self.dialog, self.add_button = _dialog(
            _("Add an Existing Image"), _("Add")
        )
        grid = self._grid()
        label = _label(_("File"), bold=True)
        self.file_chooser: Gtk.FileChooserButton | None
        self.file_entry: Gtk.Entry | None
        chooser: Gtk.FileChooserButton | Gtk.Entry
        if self.engine.local:
            self.file_chooser = Gtk.FileChooserButton(
                visible=True,
                hexpand=True,
                action=Gtk.FileChooserAction.OPEN,
                title=_("Choose a Disk Image"),
            )
            self.file_chooser.connect("file-set", self.on_file_set)
            self.file_entry = None
            chooser = self.file_chooser
        else:
            # a file there: typed, with the folders there to complete it,
            # and read when Enter is pressed or the entry is left
            self.file_chooser = None
            self.file_entry = Gtk.Entry(visible=True, hexpand=True)
            self.file_entry.completer = (  # type: ignore[attr-defined]
                PathCompletion(self.engine, self.file_entry)
            )
            self.file_entry.connect("activate", self.on_file_typed)
            self.file_entry.connect("focus-out-event", self.on_file_left)
            chooser = self.file_entry
        label.set_mnemonic_widget(chooser)
        self.file_facts = _label(dim=True, wrap=True, visible=False)
        grid.attach(label, 0, 0, 1, 1)
        grid.attach(chooser, 1, 0, 1, 1)
        grid.attach(self.file_facts, 1, 1, 1, 1)
        self._name_rows(grid, 2)

        self.copy_radio = Gtk.RadioButton(
            label=_("Copy it to the image folder"), no_show_all=True
        )
        self.in_place_radio = Gtk.RadioButton(
            label=_("Use it where it is"),
            group=self.copy_radio,
            no_show_all=True,
        )
        self.copy_note = _label(dim=True, wrap=True, visible=False)
        grid.attach(self.copy_radio, 1, 4, 1, 1)
        grid.attach(self.in_place_radio, 1, 5, 1, 1)
        grid.attach(self.copy_note, 1, 6, 1, 1)

        label = _label(_("Description"), bold=True, valign=Gtk.Align.START)
        scrolled = Gtk.ScrolledWindow(
            visible=True,
            shadow_type=Gtk.ShadowType.IN,
            min_content_height=70,
            hexpand=True,
        )
        self.description_view = Gtk.TextView(
            visible=True, wrap_mode=Gtk.WrapMode.WORD_CHAR
        )
        scrolled.add(self.description_view)
        label.set_mnemonic_widget(self.description_view)
        grid.attach(label, 0, 7, 1, 1)
        grid.attach(scrolled, 1, 7, 1, 1)
        self.progress = Gtk.ProgressBar(no_show_all=True, show_text=True)
        grid.attach(self.progress, 0, 8, 2, 1)
        self._error_row(grid, 9)

        self.dialog.connect("response", self.on_response)

    # The file

    def on_file_set(self, chooser: Gtk.FileChooserButton) -> None:
        path = chooser.get_filename()
        if path is not None:
            self.choose(path)

    def on_file_typed(self, entry: Gtk.Entry) -> None:
        path = entry.get_text().strip()
        if path and path != self.path:
            self.choose(path)

    def on_file_left(self, entry: Gtk.Entry, event: Gdk.EventFocus) -> bool:
        self.on_file_typed(entry)
        return False

    def choose(self, path: str) -> defer.Deferred[None]:
        """Read path with qemu-img info, and start the name from it."""

        self.path = os.path.abspath(path)
        self.info = None
        self.error_label.hide()
        self.file_facts.set_text(_("Reading the file…"))
        self.file_facts.show()
        if not self.name_entry.get_text():
            self.name_entry.set_text(name_from_file(path))
        buffer = self.description_view.get_buffer()
        if not buffer.get_char_count() and self.engine.local:
            # what the file says of itself, beside it here
            buffer.set_text(read_description(self.path))
        reading = self.engine.image_info(self.path).addCallbacks(
            self._read,
            self._not_read,
            callbackArgs=(self.path,),
            errbackArgs=(self.path,),
        )
        self.check()
        return reading

    def _read(self, info: ImageInfo, path: str) -> None:
        if path != self.path:
            return
        self.info = info
        words = imageinfo.facts(info)
        if info.backing_file:
            words += imageinfo.SEPARATOR + _("above {file}").format(
                file=os.path.basename(info.backing_file)
            )
        self.file_facts.set_text(words)
        self.check()

    def _not_read(self, failure: Failure, path: str) -> None:
        if path != self.path:
            return
        self.file_facts.set_text(
            _("Not a disk image: {error}").format(
                error=failure.getErrorMessage()
            )
        )
        self.check()

    def outside(self) -> bool:
        """Whether the file is outside the workspace."""

        return self.path is not None and not images.is_inside(
            self.path, self.workspace.path
        )

    def copies(self) -> bool:
        """Whether Add copies the file to the image folder."""

        return (
            self.outside()
            and self.info is not None
            and not self.info.backing_file
            and self.copy_radio.get_active()
        )

    def check(self) -> bool:
        """Show what the file allows, and wait for a good file and name."""

        name_ok = self._name_ok()
        outside = self.outside() and self.info is not None
        backing = (
            outside and self.info is not None and bool(self.info.backing_file)
        )
        for widget in (self.copy_radio, self.in_place_radio):
            widget.set_visible(outside)
        # over a connection, a copy waits (19 R13)
        local = self.engine.local
        self.copy_radio.set_sensitive(not backing and local)
        if backing:
            self.in_place_radio.set_active(True)
            self.copy_note.set_text(
                _("It is above another file, so it's used where it is.")
            )
        elif outside and not local:
            self.in_place_radio.set_active(True)
            self.copy_note.set_text(
                _("No copy over a connection, for now: it's used where it is.")
            )
        elif outside:
            assert self.path is not None, "a file outside is a file"
            size = imageinfo.human_size(os.stat(self.path).st_blocks * 512)
            self.copy_note.set_text(
                _(
                    "The copy takes {size}, and keeps the file as it is."
                ).format(size=size)
            )
        self.copy_note.set_visible(outside)
        ready = self.info is not None and name_ok and not self.working
        self.add_button.set_sensitive(ready)
        return ready

    # The action

    def on_response(self, dialog: Gtk.Dialog, response_id: int) -> None:
        if response_id != Gtk.ResponseType.OK:
            dialog.destroy()
            return
        if not self.check():
            return
        self.add()

    def add(self) -> defer.Deferred[Any]:
        """Copy the file if it has to be, then add its image."""

        assert self.path is not None, "Add has a file"
        name = self.name_entry.get_text()
        buffer = self.description_view.get_buffer()
        description = buffer.get_text(
            buffer.get_start_iter(), buffer.get_end_iter(), False
        )
        path = self.path
        self.working = True
        self.check()
        copying: defer.Deferred[Any]
        if self.copies():
            folder = self._image_folder()
            path = images.free_path(folder, os.path.basename(self.path))
            self.progress.set_text(_("Copying the file…"))
            self.progress.show()
            self.progress.pulse()
            copying = threads.deferToThread(copy_sparse, self.path, path)
        else:
            copying = defer.succeed(None)
        copying.addCallback(
            lambda _: self.engine.new_image(name, path, description)
        )
        copying.addCallbacks(
            self._added, self._copy_failed, errbackArgs=(path,)
        )
        return copying

    def _copy_failed(self, failure: Failure, path: str) -> None:
        # a copy stopped halfway is of no use
        if path != self.path and os.path.exists(path):
            os.remove(path)
        self.progress.hide()
        self._failed(failure)


class NewDiskDialog(_AddDialog):
    """Add an image of a new empty disk."""

    def __init__(
        self,
        engine: Engine,
        workspace: Workspace | RemoteWorkspace | None = None,
    ) -> None:
        self.engine = engine
        self.factory = engine.factory
        self.workspace = engine.workspace if workspace is None else workspace
        self.working = False
        self.build_ui()
        self.check()

    def build_ui(self) -> None:
        self.dialog, self.create_button = _dialog(
            _("New Empty Disk"), _("Create")
        )
        grid = self._grid()
        self._name_rows(grid, 0)
        label = _label(_("Size"), bold=True)
        self.size_spin = Gtk.SpinButton(
            visible=True,
            adjustment=Gtk.Adjustment(
                value=10,
                lower=1,
                upper=1000000,
                step_increment=1,
                page_increment=10,
            ),
            numeric=True,
            digits=0,
            activates_default=True,
        )
        self.unit_combo = Gtk.ComboBoxText(visible=True)
        for unit, _size in UNITS:
            self.unit_combo.append(unit, unit)
        self.unit_combo.set_active_id("GB")
        size = Gtk.Box(visible=True, spacing=GAP)
        size.pack_start(self.size_spin, False, False, 0)
        size.pack_start(self.unit_combo, False, False, 0)
        label.set_mnemonic_widget(self.size_spin)
        grid.attach(label, 0, 2, 1, 1)
        grid.attach(size, 1, 2, 1, 1)
        label = _label(_("Format"), bold=True)
        self.format_combo = Gtk.ComboBoxText(visible=True)
        for name in FORMATS:
            self.format_combo.append(name, name)
        self.format_combo.set_active_id("qcow2")
        label.set_mnemonic_widget(self.format_combo)
        grid.attach(label, 0, 3, 1, 1)
        grid.attach(self.format_combo, 1, 3, 1, 1)
        label = _label(_("Folder"), bold=True)
        self.folder_chooser: Gtk.FileChooserButton | None
        folder: Gtk.FileChooserButton | Gtk.Entry
        if self.engine.local:
            self.folder_chooser = Gtk.FileChooserButton(
                visible=True,
                hexpand=True,
                action=Gtk.FileChooserAction.SELECT_FOLDER,
                title=_("Choose a Folder"),
            )
            self.folder_chooser.set_filename(self._image_folder())
            label.set_mnemonic_widget(self.folder_chooser)
            folder = self.folder_chooser
        else:
            # the image folder there, or another: a file chooser shows
            # those of here
            self.folder_chooser = None
            self.folder_entry = folder = Gtk.Entry(
                visible=True,
                hexpand=True,
                text=self.engine.machine.image_folder(),
            )
            folder.completer = (  # type: ignore[attr-defined]
                PathCompletion(self.engine, folder, folders=True)
            )
            folder.connect("changed", lambda entry: self.check())
            label.set_mnemonic_widget(folder)
        self.file_label = _label(dim=True, wrap=True)
        grid.attach(label, 0, 4, 1, 1)
        grid.attach(folder, 1, 4, 1, 1)
        grid.attach(self.file_label, 1, 5, 1, 1)
        self._error_row(grid, 6)

        self.format_combo.connect("changed", lambda combo: self.check())
        if self.folder_chooser is not None:
            self.folder_chooser.connect(
                "file-set", lambda chooser: self.check()
            )
        self.dialog.connect("response", self.on_response)

    def folder(self) -> str:
        if self.folder_chooser is None:
            return self.folder_entry.get_text().strip()
        return self.folder_chooser.get_filename() or self._image_folder()

    def target(self) -> str:
        """The file of the new disk."""

        name = self.name_entry.get_text().strip().replace(" ", "_")
        fmt = self.format_combo.get_active_id()
        return os.path.join(self.folder(), f"{name}.{fmt}")

    def size(self) -> int:
        """The size of the disk in bytes, a whole number of sectors."""

        unit_id = self.unit_combo.get_active_id()
        assert unit_id is not None, "a unit is always chosen"
        unit = dict(UNITS)[unit_id]
        size = self.size_spin.get_value_as_int() * unit
        return math.ceil(size / 512) * 512

    def check(self) -> bool:
        name_ok = self._name_ok()
        target = self.target()
        # over a connection, a file that isn't known there yet is refused
        # when the disk is made
        taken = name_ok and self.engine.machine.exists(target)
        if taken:
            self.file_label.set_text(
                _("{file} is there already").format(
                    file=imageinfo.short_path(target)
                )
            )
        elif name_ok:
            self.file_label.set_text(imageinfo.short_path(target))
        else:
            self.file_label.set_text("")
        ready = name_ok and not taken and not self.working
        self.create_button.set_sensitive(ready)
        return ready

    def on_response(self, dialog: Gtk.Dialog, response_id: int) -> None:
        if response_id != Gtk.ResponseType.OK:
            dialog.destroy()
            return
        if not self.check():
            return
        self.create()

    def create(self) -> defer.Deferred[Any]:
        """Make the file with qemu-img create, then add its image."""

        self.size_spin.update()
        name = self.name_entry.get_text()
        path = self.target()
        fmt = self.format_combo.get_active_id()
        assert fmt is not None, "a format is always chosen"
        self.working = True
        self.check()
        creating = self.engine.make_image(path, fmt, self.size())
        creating.addCallback(lambda _: self.engine.new_image(name, path))
        creating.addCallbacks(self._added, self._failed)
        return creating
