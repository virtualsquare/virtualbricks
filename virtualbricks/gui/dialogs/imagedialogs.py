# -*- test-case-name: virtualbricks.tests.gui.dialogs.test_imagedialogs -*-
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

"""
What can be done to a disk image, in dialogs.

Remove lists the disks that lose the image; their private copies stay. The
file stays too, except that, when it's in the shared images and no other
project uses it, the dialog offers to move it to the trash, or, without a
trash, to delete it for good.

Find the File is for an image whose file is missing: it offers the file of
the same name in the shared images, if there's one, else a file to choose.
The private copies are pointed at the new file before the image is, with
``config.images.relink``.

The disk menu of a machine opens the other three, for a disk with a private
copy, while its machine is stopped. Save as a New Image writes the image
with the disk's changes as a file of its own in the shared images, and adds
it; by default the disk uses it then, with an empty private copy. Merge
writes the disk's changes into its image, after the list of the others
that use it. Both run in the archive process, with their progress, and can
be stopped; a stopped Save leaves no file. Start Over moves the private
copy to the trash, or deletes it without one: the next start makes an empty
one.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from typing import Any

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gio, Gtk
from twisted.internet import defer
from twisted.logger import Logger
from twisted.python.failure import Failure

from virtualbricks import errors, locations
from virtualbricks.brickfactory import BrickFactory
from virtualbricks.bricks.virtualmachine import Image, VirtualMachine
from virtualbricks.config import archive, images
from virtualbricks.config.archive import ArchiveJob
from virtualbricks.config.images import DiskUse
from virtualbricks.config.workspace import Workspace, projects
from virtualbricks.console import ampcommands, ampwire
from virtualbricks.engine import Engine
from virtualbricks.gui import imageinfo
from virtualbricks.gui.dialogs.addimage import check_name
from virtualbricks.gui.dialogs.base import (
    GAP,
    Window,
    action_dialog,
    text_label,
)
from virtualbricks.gui.pathentry import PathCompletion
from virtualbricks.i18n import _, ngettext

logger = Logger()
remove_failed = "Cannot remove the file {path}: {error}"
start_over_failed = "Cannot start {vm}'s {device} over: {error}"
show_failed = "Cannot show {path}: {error}"


def show_in_files(parent: Gtk.Window | None, path: str) -> None:
    """Open the folder of path in the file manager."""

    folder = os.path.dirname(path)
    uri = Gio.File.new_for_path(folder).get_uri()
    try:
        Gtk.show_uri_on_window(parent, uri, Gdk.CURRENT_TIME)
    except Exception as exc:
        logger.error(show_failed, path=folder, error=exc)


def disks_words(uses: Sequence[DiskUse]) -> str:
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

    def get_root_widget(self) -> Gtk.Dialog:
        return self.dialog

    def __init__(self, engine: Engine, image: Image) -> None:
        self.engine = engine
        self.factory = engine.factory
        # the files are those of the machine of the bricks
        self.machine = engine.machine
        self.image = image
        self.build_ui()

    def build_ui(self) -> None:
        self.dialog, self.remove_button, box = action_dialog(
            _("Remove Image"), _("Remove"), destructive=True
        )
        name = self.image.name
        path = self.image.path
        box.pack_start(
            text_label(
                _("Remove the image {name}?").format(name=name), heading=True
            ),
            False,
            False,
            0,
        )
        uses = images.uses(self.factory, self.image, self.machine.taken)
        box.pack_start(text_label(disks_words(uses)), False, False, 0)
        self.file_check: Gtk.CheckButton | None = None
        # what it says of the file: over a connection, once the other
        # projects are known there
        self.file_box = Gtk.Box(
            visible=True, orientation=Gtk.Orientation.VERTICAL, spacing=GAP
        )
        box.pack_start(self.file_box, False, False, 0)
        self.dialog.connect("response", self.on_response)
        if self.engine.local:
            self.show_file()
            return
        self.remove_button.set_sensitive(False)
        self.file_box.pack_start(
            text_label(_("Looking at the file…"), dim=True), False, False, 0
        )
        reading = self.machine.infos.read(path)
        reading.addBoth(lambda _: self.show_file())

    def show_file(self) -> None:
        """What the dialog says of the file, and offers to do with it."""

        for child in self.file_box.get_children():
            child.destroy()
        self.remove_button.set_sensitive(True)
        path = self.image.path
        box = self.file_box
        others = self.machine.other_projects(path)
        if others:
            projects_names = imageinfo.names(sorted({p for p, _i in others}))
            words = ngettext(
                "The project {names} uses the file too: it stays.",
                "The projects {names} use the file too: it stays.",
                len({p for p, _i in others}),
            ).format(names=projects_names)
            box.pack_start(text_label(words, dim=True), False, False, 0)
        elif self.offers_file():
            size = imageinfo.human_size(self.machine.taken(path) or 0)
            if self.machine.can_trash(path):
                label = _("Also move the file to the trash ({size})")
            else:
                label = _("Also delete the file ({size}): there is no trash")
            self.file_check = Gtk.CheckButton(
                visible=True, label=label.format(size=size)
            )
            box.pack_start(self.file_check, False, False, 0)
        else:
            box.pack_start(
                text_label(
                    _("The file stays: {path}").format(
                        path=imageinfo.short_path(path)
                    ),
                    dim=True,
                ),
                False,
                False,
                0,
            )

    def offers_file(self) -> bool:
        """Whether the dialog offers to remove the file too."""

        path = self.image.path
        return self.machine.exists(path) and images.is_inside(
            path, self.machine.image_folder()
        )

    def on_response(self, dialog: Gtk.Dialog, response_id: int) -> None:
        if response_id == Gtk.ResponseType.OK:
            self.remove()
        dialog.destroy()

    def remove(self) -> defer.Deferred[Any]:
        path = self.image.path
        removing = self.engine.remove(self.image)
        if self.file_check is not None and self.file_check.get_active():
            # to the trash, if there is one
            removing.addCallback(lambda _: self.engine.discard_file(path))
            removing.addErrback(self._not_removed, path)
        return removing

    def _not_removed(self, failure: Failure, path: str) -> None:
        # here, or there over a connection
        failure.trap(OSError, ampwire.CommandFailed, ampcommands.BadArgument)
        logger.error(remove_failed, path=path, error=failure.value)


class FindFileDialog(Window):
    """Give an image whose file is missing its file again."""

    def get_root_widget(self) -> Gtk.Dialog:
        return self.dialog

    def __init__(
        self, engine: Engine, image: Image, workspace: Workspace | None = None
    ) -> None:
        self.engine = engine
        self.factory = engine.factory
        self.image = image
        self.workspace = projects if workspace is None else workspace
        self.build_ui()

    def found(self) -> str | None:
        """The file of the same name in the shared images, if there's one."""

        if not self.engine.local:
            # there: not known here before it's asked
            return None
        folder = os.path.join(self.workspace.path, locations.SHARED_IMAGES)
        path = os.path.join(folder, os.path.basename(self.image.path))
        return path if os.path.isfile(path) else None

    def build_ui(self) -> None:
        self.dialog, self.use_button, box = action_dialog(
            _("Find the File"), _("Use This File")
        )
        name = self.image.name
        box.pack_start(
            text_label(
                _("Where is the file of {name}?").format(name=name),
                heading=True,
            ),
            False,
            False,
            0,
        )
        box.pack_start(
            text_label(
                _("{path} isn't there.").format(
                    path=imageinfo.short_path(self.image.path)
                )
            ),
            False,
            False,
            0,
        )
        self.file_chooser: Gtk.FileChooserButton | Gtk.Entry
        if self.engine.local:
            self.file_chooser = Gtk.FileChooserButton(
                visible=True,
                action=Gtk.FileChooserAction.OPEN,
                title=_("Choose the File"),
            )
            self.file_chooser.connect("file-set", self.on_file_set)
        else:
            # a file there: typed, with the folders there to complete it
            entry = self.file_chooser = Gtk.Entry(visible=True, hexpand=True)
            entry.completer = PathCompletion(  # type: ignore[attr-defined]
                self.engine, entry
            )
            entry.connect(
                "changed",
                lambda entry: self.choose(entry.get_text().strip() or None),
            )
        found = self.found()
        if found is not None:
            assert isinstance(
                self.file_chooser, Gtk.FileChooserButton
            ), "found() finds a file here only"
            self.file_chooser.set_filename(found)
            box.pack_start(
                text_label(
                    _("The shared images have a file of the same name."),
                    dim=True,
                ),
                False,
                False,
                0,
            )
        box.pack_start(self.file_chooser, False, False, 0)
        box.pack_start(
            text_label(
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
        self.error_label = text_label(selectable=True, visible=False)
        self.error_label.get_style_context().add_class("error")
        box.pack_start(self.error_label, False, False, 0)
        self.chosen = found
        self.use_button.set_sensitive(found is not None)
        self.dialog.connect("response", self.on_response)

    def on_file_set(self, chooser: Gtk.FileChooserButton) -> None:
        self.choose(chooser.get_filename())

    def choose(self, path: str | None) -> None:
        self.chosen = path
        self.error_label.hide()
        self.use_button.set_sensitive(path is not None)

    def on_response(self, dialog: Gtk.Dialog, response_id: int) -> None:
        if response_id != Gtk.ResponseType.OK:
            dialog.destroy()
            return
        if self.chosen is not None:
            self.use()

    def use(self) -> defer.Deferred[None]:
        assert self.chosen is not None, "Use This File has a file"
        self.use_button.set_sensitive(False)
        relinked = self.engine.relink(self.image, self.chosen)
        return relinked.addCallbacks(self._used, self._failed)

    def _used(self, result: object) -> None:
        self.dialog.destroy()

    def _failed(self, failure: Failure) -> None:
        self.error_label.set_text(failure.getErrorMessage())
        self.error_label.show()
        self.use_button.set_sensitive(True)


# The disk of a machine


def _stop_first(names: list[str]) -> str:
    return _("Stop {names} first.").format(names=imageinfo.names(names))


class _JobDialog(Window):
    """
    A dialog that runs a job of the archive process: its progress shows,
    and Cancel stops it.
    """

    job: ArchiveJob | None = None
    # called when the job is done
    on_done: Callable[[], object] | None = None
    dialog: Gtk.Dialog
    action_button: Gtk.Widget

    def get_root_widget(self) -> Gtk.Dialog:
        return self.dialog

    def check(self) -> bool:
        """Whether the job can run; if not, the dialog says why."""

        raise NotImplementedError

    def run(self) -> ArchiveJob:
        """Start the job."""

        raise NotImplementedError

    def _job_rows(self, box: Gtk.Box) -> None:
        self.progress = Gtk.ProgressBar(show_text=True, no_show_all=True)
        box.pack_start(self.progress, False, False, 0)
        self.error_label = text_label(selectable=True, visible=False)
        self.error_label.get_style_context().add_class("error")
        box.pack_start(self.error_label, False, False, 0)
        cancel = self.dialog.get_widget_for_response(Gtk.ResponseType.CANCEL)
        assert isinstance(cancel, Gtk.Button), "action_dialog() adds Cancel"
        self.cancel_button = cancel
        self.dialog.connect("response", self.on_response)

    def _say(self, text: str) -> None:
        self.error_label.set_text(text)
        self.error_label.set_visible(bool(text))

    def on_progress(self, step: str, done: int, total: int) -> None:
        fraction = done / total if total else 0.0
        self.progress.set_fraction(fraction)
        self.progress.set_text(f"{fraction:.0%}")

    def on_response(self, dialog: Gtk.Dialog, response_id: int) -> None:
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

    def _started(self, job: ArchiveJob) -> ArchiveJob:
        self.job = job
        self._say("")
        self.progress.set_fraction(0.0)
        self.progress.set_text("")
        self.progress.show()
        self.cancel_button.set_label(_("Stop"))
        self.check()
        job.done.addErrback(self._failed)
        return job

    def _failed(self, failure: Failure) -> None:
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
        self,
        factory: BrickFactory,
        vm: VirtualMachine,
        device: str,
        workspace: Workspace | None = None,
        start: Callable[..., ArchiveJob] | None = None,
    ) -> None:
        self.factory = factory
        self.vm = vm
        self.device = device
        image = vm.disk(device).image
        assert image is not None, "a disk with a private copy has its image"
        self.image = image
        self.workspace = projects if workspace is None else workspace
        # starts the job; the archive process's save_image
        self.start = archive.save_image if start is None else start
        # called with the new image, and whether the disk uses it
        self.on_saved: Callable[[Image, bool], object] | None = None
        self.build_ui()
        self.check()

    def build_ui(self) -> None:
        self.dialog, self.action_button, box = action_dialog(
            _("Save as a New Image"), _("Save")
        )
        vm, image = self.vm.name, self.image.name
        box.pack_start(
            text_label(
                _("Save {vm}'s {device} as a new image").format(
                    vm=vm, device=self.device
                ),
                heading=True,
            ),
            False,
            False,
            0,
        )
        box.pack_start(
            text_label(
                _(
                    "A file of its own in the shared images: {image} with the"
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
        self.name_message = text_label(dim=True, visible=False)
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
            text_label(
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
        running = self.vm.is_running()
        if running and self.job is None:
            self._say(_stop_first([self.vm.name]))
        ready = bool(name) and message is None and not running
        self.action_button.set_sensitive(ready and self.job is None)
        return ready

    def run(self) -> ArchiveJob:
        name = self.name_entry.get_text()
        use_it = self.use_check.get_active()
        job = self.start(
            self.vm.disk(self.device).get_cow_path(),
            self.output(),
            self.on_progress,
        )
        job.done.addCallback(self._saved, name, use_it)
        return self._started(job)

    def _saved(self, result: dict[str, Any], name: str, use_it: bool) -> None:
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
        self,
        factory: BrickFactory,
        vm: VirtualMachine,
        device: str,
        workspace: Workspace | None = None,
        start: Callable[..., ArchiveJob] | None = None,
    ) -> None:
        self.factory = factory
        self.vm = vm
        self.device = device
        image = vm.disk(device).image
        assert image is not None, "a disk with a private copy has its image"
        self.image = image
        self.workspace = projects if workspace is None else workspace
        # starts the job; the archive process's merge_image
        self.start = archive.merge_image if start is None else start
        # passed to Save as a New Image, instead
        self.on_saved: Callable[[Image, bool], object] | None = None
        self.build_ui()
        self.check()

    def others(self) -> list[DiskUse]:
        """The other disks of the project that use the image."""

        return [
            use
            for use in images.uses(self.factory, self.image)
            if not (use.vm is self.vm and use.device == self.device)
        ]

    def build_ui(self) -> None:
        image = self.image.name
        self.dialog, self.action_button, box = action_dialog(
            _("Merge into {image}").format(image=image),
            _("Merge"),
            destructive=True,
        )
        box.pack_start(
            text_label(
                _("Merge {vm}'s changes into {image}?").format(
                    vm=self.vm.name, image=image
                ),
                heading=True,
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
        box.pack_start(text_label(words), False, False, 0)
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

    def run(self) -> ArchiveJob:
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

    def get_root_widget(self) -> Gtk.Dialog:
        return self.dialog

    def __init__(
        self, engine: Engine, vm: VirtualMachine, device: str
    ) -> None:
        self.engine = engine
        self.vm = vm
        self.device = device
        # called when the copy is gone
        self.on_done: Callable[[], object] | None = None
        self.build_ui()

    def build_ui(self) -> None:
        vm = self.vm.name
        disk = self.vm.disk(self.device)
        assert (
            disk.image is not None
        ), "a disk with a private copy has its image"
        copy = disk.get_cow_path()
        self.dialog, self.action_button, box = action_dialog(
            _("Start Over"), _("Start Over"), destructive=True
        )
        box.pack_start(
            text_label(
                _("Start {vm}'s {device} over from {image}?").format(
                    vm=vm, device=self.device, image=disk.image.name
                ),
                heading=True,
            ),
            False,
            False,
            0,
        )
        machine = self.engine.machine
        size = imageinfo.human_size(machine.taken(copy) or 0)
        if machine.can_trash(copy):
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
            text_label(words.format(copy=os.path.basename(copy), size=size)),
            False,
            False,
            0,
        )
        running = self.vm.is_running()
        if running:
            box.pack_start(
                text_label(_stop_first([vm]), dim=True), False, False, 0
            )
        self.action_button.set_sensitive(not running)
        self.dialog.connect("response", self.on_response)

    def on_response(self, dialog: Gtk.Dialog, response_id: int) -> None:
        if response_id == Gtk.ResponseType.OK:
            self.start_over()
        dialog.destroy()

    def start_over(self) -> defer.Deferred[None]:
        starting = self.engine.start_over(self.vm, self.device)
        return starting.addCallbacks(
            self._started_over, self._not_started_over
        )

    def _started_over(self, trashed: bool) -> None:
        if self.on_done is not None:
            self.on_done()

    def _not_started_over(self, failure: Failure) -> None:
        # here, or there over a connection
        failure.trap(
            OSError,
            errors.Error,
            ampwire.CommandFailed,
            ampcommands.BadArgument,
        )
        logger.error(
            start_over_failed,
            vm=self.vm.name,
            device=self.device,
            error=failure.value,
        )
