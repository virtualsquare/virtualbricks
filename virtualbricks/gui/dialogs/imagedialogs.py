# -*- test-case-name: virtualbricks.tests.gui.dialogs.test_imagedialogs -*-
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

The disk menu of a machine opens the other three, for a disk with a private
copy, while its machine is stopped. Save as a New Image writes the image
with the disk's changes as a file of its own in the image folder, and adds
it; by default the disk uses it then, with an empty private copy. Merge
writes the disk's changes into its image, after the list of the others
that use it. Both run in the archive process, with their progress, and can
be stopped; a stopped Save leaves no file. Start Over moves the private
copy to the trash, or deletes it without one: the next start makes an empty
one.
"""

import os

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gio, Gtk, Pango
from twisted.logger import Logger

from virtualbricks import errors
from virtualbricks.config import archive, images
from virtualbricks.config.workspace import projects
from virtualbricks.gui import imageinfo
from virtualbricks.gui.dialogs.addimage import check_name
from virtualbricks.gui.dialogs.base import Window
from virtualbricks.gui.pango import pango_attr_list
from virtualbricks.i18n import _, ngettext

logger = Logger()
remove_failed = "Cannot remove the file {path}: {error}"
start_over_failed = "Cannot start {vm}'s {device} over: {error}"
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
        _("{vm} ({device})").format(vm=use.vm.name, device=use.device)
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


class RemoveImageDialog(Window):
    """Remove an image from the library, and maybe its file."""

    def get_root_widget(self):
        return self.dialog

    def __init__(self, factory, image, workspace=None):
        self.factory = factory
        self.image = image
        self.workspace = projects if workspace is None else workspace
        self.build_ui()

    def build_ui(self):
        self.dialog, self.remove_button, box = _dialog(
            _("Remove Image"), _("Remove"), destructive=True
        )
        name = self.image.name
        path = self.image.path
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

        path = self.image.path
        folder = os.path.join(self.workspace.path, images.IMAGE_FOLDER)
        return os.path.isfile(path) and images.is_inside(path, folder)

    def can_trash(self) -> bool:
        trasher = self.workspace.trasher
        return trasher is not None and trasher.can_trash(self.image.path)

    def on_response(self, dialog, response_id):
        if response_id == Gtk.ResponseType.OK:
            self.remove()
        dialog.destroy()

    def remove(self):
        self.factory.remove_disk_image(self.image)
        if self.file_check is None or not self.file_check.get_active():
            return
        path = self.image.path
        try:
            if self.can_trash():
                self.workspace.trasher.trash(path)
            else:
                os.remove(path)
        except OSError as exc:
            logger.error(remove_failed, path=path, error=exc)


class FindFileDialog(Window):
    """Give an image whose file is missing its file again."""

    def get_root_widget(self):
        return self.dialog

    def __init__(self, factory, image, workspace=None, qemu_img=None):
        self.factory = factory
        self.image = image
        self.workspace = projects if workspace is None else workspace
        self.qemu_img = qemu_img
        self.build_ui()

    def found(self) -> str | None:
        """The file of the same name in the image folder, if there's one."""

        folder = os.path.join(self.workspace.path, images.IMAGE_FOLDER)
        path = os.path.join(folder, os.path.basename(self.image.path))
        return path if os.path.isfile(path) else None

    def build_ui(self):
        self.dialog, self.use_button, box = _dialog(
            _("Find the File"), _("Use This File")
        )
        name = self.image.name
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
                    path=imageinfo.short_path(self.image.path)
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


# The disk of a machine


def _stop_first(names) -> str:
    return _("Stop {names} first.").format(names=imageinfo.names(names))


class _JobDialog(Window):
    """
    A dialog that runs a job of the archive process: its progress shows,
    and Cancel stops it.
    """

    job = None
    # called when the job is done
    on_done = None

    def get_root_widget(self):
        return self.dialog

    def _job_rows(self, box):
        self.progress = Gtk.ProgressBar(show_text=True, no_show_all=True)
        box.pack_start(self.progress, False, False, 0)
        self.error_label = _label(selectable=True, visible=False)
        self.error_label.get_style_context().add_class("error")
        box.pack_start(self.error_label, False, False, 0)
        self.cancel_button = self.dialog.get_widget_for_response(
            Gtk.ResponseType.CANCEL
        )
        self.dialog.connect("response", self.on_response)

    def _say(self, text) -> None:
        self.error_label.set_text(text)
        self.error_label.set_visible(bool(text))

    def on_progress(self, step, done, total) -> None:
        fraction = done / total if total else 0.0
        self.progress.set_fraction(fraction)
        self.progress.set_text(f"{fraction:.0%}")

    def on_response(self, dialog, response_id) -> None:
        if self.job is not None:
            # Stop, or the window closed: the job ends first
            self.job.cancel()
            if response_id != Gtk.ResponseType.CANCEL:
                dialog.destroy()
            return
        if response_id == Gtk.ResponseType.OK:
            if self.check():
                self.run()
            return
        dialog.destroy()

    def _started(self, job):
        self.job = job
        self._say("")
        self.progress.set_fraction(0.0)
        self.progress.set_text("")
        self.progress.show()
        self.cancel_button.set_label(_("Stop"))
        self.check()
        job.done.addErrback(self._failed)
        return job

    def _failed(self, failure) -> None:
        self.job = None
        self.progress.hide()
        self.cancel_button.set_label(_("Cancel"))
        if failure.check(archive.ArchiveCancelled):
            self._say(_("Stopped."))
        else:
            self._say(failure.getErrorMessage())
        self.check()

    def _ended(self) -> None:
        self.job = None
        self.dialog.destroy()
        if self.on_done is not None:
            self.on_done()


class SaveImageDialog(_JobDialog):
    """Save a disk of a machine, with its changes, as a new image."""

    def __init__(
        self, factory, vm, device, workspace=None, start=None
    ) -> None:
        self.factory = factory
        self.vm = vm
        self.device = device
        self.image = vm.disk(device).image
        self.workspace = projects if workspace is None else workspace
        # starts the job; the archive process's save_image
        self.start = archive.save_image if start is None else start
        # called with the new image, and whether the disk uses it
        self.on_saved = None
        self.build_ui()
        self.check()

    def build_ui(self) -> None:
        self.dialog, self.action_button, box = _dialog(
            _("Save as a New Image"), _("Save")
        )
        vm, image = self.vm.name, self.image.name
        box.pack_start(
            _label(
                _("Save {vm}'s {device} as a new image").format(
                    vm=vm, device=self.device
                ),
                bold=True,
            ),
            False,
            False,
            0,
        )
        box.pack_start(
            _label(
                _(
                    "A file of its own in the image folder: {image} with the"
                    " changes {vm} made to it."
                ).format(image=image, vm=vm)
            ),
            False,
            False,
            0,
        )
        row = Gtk.Box(visible=True, spacing=12)
        label = Gtk.Label(visible=True, label=_("Name"), xalign=0.0)
        self.name_entry = Gtk.Entry(
            visible=True,
            hexpand=True,
            activates_default=True,
            text=self.default_name(),
        )
        label.set_mnemonic_widget(self.name_entry)
        row.pack_start(label, False, False, 0)
        row.pack_start(self.name_entry, True, True, 0)
        box.pack_start(row, False, False, 0)
        self.name_message = _label(dim=True, visible=False)
        box.pack_start(self.name_message, False, False, 0)
        self.use_check = Gtk.CheckButton(
            visible=True,
            active=True,
            label=_("Use it for {vm}'s {device}").format(
                vm=vm, device=self.device
            ),
        )
        box.pack_start(self.use_check, False, False, 0)
        box.pack_start(
            _label(
                _(
                    "The disk starts again from it, with an empty private copy."
                ),
                dim=True,
            ),
            False,
            False,
            0,
        )
        self.dialog.set_default_response(Gtk.ResponseType.OK)
        self._job_rows(box)
        self.name_entry.connect("changed", lambda entry: self.check())

    def default_name(self) -> str:
        """The image's name and the machine's, free in the library."""

        stem = f"{self.image.name}-{self.vm.name}"
        name, number = stem, 2
        while check_name(self.factory, name) is not None:
            name = f"{stem}-{number}"
            number += 1
        return name

    def output(self) -> str:
        filename = self.name_entry.get_text().strip().replace(" ", "_")
        return images.free_path(
            images.image_folder(self.workspace), filename + ".qcow2"
        )

    def check(self) -> bool:
        name = self.name_entry.get_text()
        message = check_name(self.factory, name) if name else None
        self.name_message.set_text(message or "")
        self.name_message.set_visible(message is not None)
        running = self.vm.__isrunning__()
        if running and self.job is None:
            self._say(_stop_first([self.vm.name]))
        ready = bool(name) and message is None and not running
        self.action_button.set_sensitive(ready and self.job is None)
        return ready

    def run(self):
        name = self.name_entry.get_text()
        use_it = self.use_check.get_active()
        job = self.start(
            self.vm.disk(self.device).get_cow_path(),
            self.output(),
            self.on_progress,
        )
        job.done.addCallback(self._saved, name, use_it)
        return self._started(job)

    def _saved(self, result, name, use_it) -> None:
        image = images.adopt(
            self.factory,
            self.vm,
            self.device,
            name,
            result["output"],
            use_it,
            self.workspace.trasher,
        )
        if self.on_saved is not None:
            self.on_saved(image, use_it)
        self._ended()


class MergeDialog(_JobDialog):
    """Merge the changes of a disk of a machine into its image."""

    def __init__(
        self, factory, vm, device, workspace=None, start=None
    ) -> None:
        self.factory = factory
        self.vm = vm
        self.device = device
        self.image = vm.disk(device).image
        self.workspace = projects if workspace is None else workspace
        # starts the job; the archive process's merge_image
        self.start = archive.merge_image if start is None else start
        # passed to Save as a New Image, instead
        self.on_saved = None
        self.build_ui()
        self.check()

    def others(self) -> list:
        """The other disks of the project that use the image."""

        return [
            use
            for use in images.uses(self.factory, self.image)
            if not (use.vm is self.vm and use.device == self.device)
        ]

    def build_ui(self) -> None:
        image = self.image.name
        self.dialog, self.action_button, box = _dialog(
            _("Merge into {image}").format(image=image),
            _("Merge"),
            destructive=True,
        )
        box.pack_start(
            _label(
                _("Merge {vm}'s changes into {image}?").format(
                    vm=self.vm.name, image=image
                ),
                bold=True,
            ),
            False,
            False,
            0,
        )
        users = [
            _("{vm} ({device})").format(vm=use.vm.name, device=use.device)
            for use in self.others()
        ]
        users += [
            _("the project {project}, as {image}").format(
                project=project, image=name
            )
            for project, name in images.other_projects(
                self.workspace, self.image.path
            )
        ]
        if users:
            words = _(
                "{image} changes for all that use it too: {users}. Their"
                " private copies may stop working."
            ).format(image=image, users=imageinfo.names(users))
        else:
            words = _("No other disk uses {image}.").format(image=image)
        box.pack_start(_label(words), False, False, 0)
        self.instead_button = Gtk.Button(
            visible=True,
            halign=Gtk.Align.START,
            label=_("Save as a New Image Instead"),
        )
        self.instead_button.connect("clicked", lambda button: self.instead())
        box.pack_start(self.instead_button, False, False, 0)
        self._job_rows(box)

    def check(self) -> bool:
        running = sorted(
            {
                use.vm.name
                for use in images.uses(self.factory, self.image)
                if use.running
            }
        )
        if running and self.job is None:
            self._say(_stop_first(running))
        self.action_button.set_sensitive(not running and self.job is None)
        self.instead_button.set_sensitive(self.job is None)
        return not running

    def run(self):
        job = self.start(
            self.vm.disk(self.device).get_cow_path(), self.on_progress
        )
        job.done.addCallback(lambda result: self._ended())
        return self._started(job)

    def instead(self) -> SaveImageDialog:
        parent = self.dialog.get_transient_for()
        self.dialog.destroy()
        dialog = SaveImageDialog(
            self.factory, self.vm, self.device, self.workspace
        )
        dialog.on_saved = self.on_saved
        dialog.on_done = self.on_done
        dialog.show(parent)
        return dialog


class StartOverDialog(Window):
    """Start a disk over from its image, without its private copy."""

    def get_root_widget(self):
        return self.dialog

    def __init__(self, vm, device, workspace=None) -> None:
        self.vm = vm
        self.device = device
        self.workspace = projects if workspace is None else workspace
        # called when the copy is gone
        self.on_done = None
        self.build_ui()

    def build_ui(self) -> None:
        vm = self.vm.name
        disk = self.vm.disk(self.device)
        copy = disk.get_cow_path()
        self.dialog, self.action_button, box = _dialog(
            _("Start Over"), _("Start Over"), destructive=True
        )
        box.pack_start(
            _label(
                _("Start {vm}'s {device} over from {image}?").format(
                    vm=vm, device=self.device, image=disk.image.name
                ),
                bold=True,
            ),
            False,
            False,
            0,
        )
        size = imageinfo.human_size(images.space_taken(copy) or 0)
        trasher = self.workspace.trasher
        if trasher is not None and trasher.can_trash(copy):
            words = _(
                "{copy} goes to the trash, with the changes it keeps, {size};"
                " the next start makes an empty one."
            )
        else:
            words = _(
                "{copy} is deleted for good, with the changes it keeps,"
                " {size}: there is no trash. The next start makes an empty"
                " one."
            )
        box.pack_start(
            _label(words.format(copy=os.path.basename(copy), size=size)),
            False,
            False,
            0,
        )
        running = self.vm.__isrunning__()
        if running:
            box.pack_start(
                _label(_stop_first([vm]), dim=True), False, False, 0
            )
        self.action_button.set_sensitive(not running)
        self.dialog.connect("response", self.on_response)

    def on_response(self, dialog, response_id) -> None:
        if response_id == Gtk.ResponseType.OK:
            self.start_over()
        dialog.destroy()

    def start_over(self) -> None:
        try:
            images.start_over(self.vm, self.device, self.workspace.trasher)
        except (OSError, errors.Error) as exc:
            logger.error(
                start_over_failed,
                vm=self.vm.name,
                device=self.device,
                error=exc,
            )
            return
        if self.on_done is not None:
            self.on_done()
