# -*- test-case-name: virtualbricks.tests.gui.windows.test_imagedialogs -*-
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
What can be done to a disk image, in dialogs.

Remove lists the disks that lose the image; their private copies stay. The
file stays too, except that, when it's in the image folder and no other
project uses it, the dialog offers to move it to the trash, or, without a
trash, to delete it for good.

Find the File is for an image whose file is missing: it offers the file of
the same name in the image folder, if there's one, else a file to choose.
The private copies are pointed at the new file before the image is, with
``config.images.relink``.
"""

import os

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gio, Gtk, Pango
from twisted.logger import Logger

from virtualbricks.config import images
from virtualbricks.config.workspace import projects
from virtualbricks.gui import imageinfo
from virtualbricks.gui.windows.base import pango_attr_list
from virtualbricks.i18n import _, ngettext

logger = Logger()
remove_failed = "Cannot remove the file {path}: {error}"
show_failed = "Cannot show {path}: {error}"

MARGIN = 18
GAP = 8


def show_in_files(parent, path):
    """Open the folder of path in the file manager."""

    folder = os.path.dirname(path)
    uri = Gio.File.new_for_path(folder).get_uri()
    try:
        Gtk.show_uri_on_window(parent, uri, Gdk.CURRENT_TIME)
    except Exception as exc:
        logger.error(show_failed, path=folder, error=exc)


def _label(text="", dim=False, bold=False, visible=True, **props):
    label = Gtk.Label(
        visible=visible,
        label=text,
        xalign=0.0,
        wrap=True,
        max_width_chars=56,
        **props,
    )
    if dim:
        label.get_style_context().add_class("dim-label")
    if bold:
        label.set_attributes(
            pango_attr_list(
                Pango.attr_weight_new(Pango.Weight.BOLD),
                Pango.attr_scale_new(1.15),
            )
        )
    return label


def _dialog(title, action, destructive=False):
    dialog = Gtk.Dialog(
        title=title,
        use_header_bar=True,
        modal=True,
        destroy_with_parent=True,
        default_width=440,
    )
    dialog.add_button(_("Cancel"), Gtk.ResponseType.CANCEL)
    button = dialog.add_button(action, Gtk.ResponseType.OK)
    style = "destructive-action" if destructive else "suggested-action"
    button.get_style_context().add_class(style)
    box = dialog.get_content_area()
    box.set_properties(spacing=GAP, margin=MARGIN)
    return dialog, button, box


def disks_words(uses) -> str:
    """Which disks lose an image, and that their private copies stay."""

    if not uses:
        return _("No disk uses it.")
    disks = [
        _("{vm} ({device})").format(vm=use.vm.get_name(), device=use.device)
        for use in uses
    ]
    words = ngettext(
        "The disk {disks} will have no image.",
        "The disks {disks} will have no image.",
        len(disks),
    ).format(disks=imageinfo.names(disks))
    copies = sum(1 for use in uses if use.private)
    if copies:
        words += " " + ngettext(
            "The private copy stays.", "The private copies stay.", copies
        )
    return words


class _Dialog:

    def show(self, parent=None):
        if parent is not None:
            self.dialog.set_transient_for(parent)
        self.dialog.show()

    def get_root_widget(self):
        return self.dialog


class RemoveImageDialog(_Dialog):
    """Remove an image from the library, and maybe its file."""

    def __init__(self, factory, image, workspace=None):
        self.factory = factory
        self.image = image
        self.workspace = projects if workspace is None else workspace
        self.build_ui()

    def build_ui(self):
        self.dialog, self.remove_button, box = _dialog(
            _("Remove Image"), _("Remove"), destructive=True
        )
        name = self.image.get_name()
        path = self.image.get_path()
        box.pack_start(
            _label(_("Remove the image {name}?").format(name=name), bold=True),
            False,
            False,
            0,
        )
        uses = images.uses(self.factory, self.image)
        box.pack_start(_label(disks_words(uses)), False, False, 0)
        self.file_check = None
        others = images.other_projects(self.workspace, path)
        if others:
            projects_names = imageinfo.names(sorted({p for p, _i in others}))
            words = ngettext(
                "The project {names} uses the file too: it stays.",
                "The projects {names} use the file too: it stays.",
                len({p for p, _i in others}),
            ).format(names=projects_names)
            box.pack_start(_label(words, dim=True), False, False, 0)
        elif self.offers_file():
            size = imageinfo.human_size(os.stat(path).st_blocks * 512)
            if self.can_trash():
                label = _("Also move the file to the trash ({size})")
            else:
                label = _("Also delete the file ({size}): there is no trash")
            self.file_check = Gtk.CheckButton(
                visible=True, label=label.format(size=size)
            )
            box.pack_start(self.file_check, False, False, 0)
        else:
            box.pack_start(
                _label(
                    _("The file stays: {path}").format(
                        path=imageinfo.short_path(path)
                    ),
                    dim=True,
                ),
                False,
                False,
                0,
            )
        self.dialog.connect("response", self.on_response)

    def offers_file(self) -> bool:
        """Whether the dialog offers to remove the file too."""

        path = self.image.get_path()
        folder = os.path.join(self.workspace.path, images.IMAGE_FOLDER)
        return os.path.isfile(path) and images.is_inside(path, folder)

    def can_trash(self) -> bool:
        trasher = self.workspace.trasher
        return trasher is not None and trasher.can_trash(self.image.get_path())

    def on_response(self, dialog, response_id):
        if response_id == Gtk.ResponseType.OK:
            self.remove()
        dialog.destroy()

    def remove(self):
        self.factory.remove_disk_image(self.image)
        if self.file_check is None or not self.file_check.get_active():
            return
        path = self.image.get_path()
        try:
            if self.can_trash():
                self.workspace.trasher.trash(path)
            else:
                os.remove(path)
        except OSError as exc:
            logger.error(remove_failed, path=path, error=exc)


class FindFileDialog(_Dialog):
    """Give an image whose file is missing its file again."""

    def __init__(self, factory, image, workspace=None, qemu_img=None):
        self.factory = factory
        self.image = image
        self.workspace = projects if workspace is None else workspace
        self.qemu_img = qemu_img
        self.build_ui()

    def found(self) -> str | None:
        """The file of the same name in the image folder, if there's one."""

        folder = os.path.join(self.workspace.path, images.IMAGE_FOLDER)
        path = os.path.join(folder, os.path.basename(self.image.get_path()))
        return path if os.path.isfile(path) else None

    def build_ui(self):
        self.dialog, self.use_button, box = _dialog(
            _("Find the File"), _("Use This File")
        )
        name = self.image.get_name()
        box.pack_start(
            _label(
                _("Where is the file of {name}?").format(name=name), bold=True
            ),
            False,
            False,
            0,
        )
        box.pack_start(
            _label(
                _("{path} isn't there.").format(
                    path=imageinfo.short_path(self.image.get_path())
                )
            ),
            False,
            False,
            0,
        )
        self.file_chooser = Gtk.FileChooserButton(
            visible=True,
            action=Gtk.FileChooserAction.OPEN,
            title=_("Choose the File"),
        )
        found = self.found()
        if found is not None:
            self.file_chooser.set_filename(found)
            box.pack_start(
                _label(
                    _("The image folder has a file of the same name."),
                    dim=True,
                ),
                False,
                False,
                0,
            )
        box.pack_start(self.file_chooser, False, False, 0)
        box.pack_start(
            _label(
                _(
                    "The private copies of its disks are pointed at the file"
                    " first, so that they keep their changes."
                ),
                dim=True,
            ),
            False,
            False,
            0,
        )
        self.error_label = _label(selectable=True, visible=False)
        self.error_label.get_style_context().add_class("error")
        box.pack_start(self.error_label, False, False, 0)
        self.chosen = found
        self.use_button.set_sensitive(found is not None)
        self.file_chooser.connect("file-set", self.on_file_set)
        self.dialog.connect("response", self.on_response)

    def on_file_set(self, chooser):
        self.choose(chooser.get_filename())

    def choose(self, path):
        self.chosen = path
        self.error_label.hide()
        self.use_button.set_sensitive(path is not None)

    def on_response(self, dialog, response_id):
        if response_id != Gtk.ResponseType.OK:
            dialog.destroy()
            return
        if self.chosen is not None:
            self.use()

    def use(self):
        self.use_button.set_sensitive(False)
        relinked = images.relink(
            self.factory, self.image, self.chosen, self.qemu_img
        )
        relinked.addCallbacks(self._used, self._failed)
        return relinked

    def _used(self, result):
        self.dialog.destroy()

    def _failed(self, failure):
        self.error_label.set_text(failure.getErrorMessage())
        self.error_label.show()
        self.use_button.set_sensitive(True)
