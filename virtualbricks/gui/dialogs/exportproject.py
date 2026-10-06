# -*- test-case-name: virtualbricks.tests.gui.dialogs.test_exportproject -*-
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
Export a project to an archive.

Three choices, with their sizes: the project, always; its private disks, on;
the images of its library, off. The other files of the folder are behind an
expander, all included. The archive is written in the archive process, to a
temporary file renamed at the end, so a stopped export leaves nothing.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable, Sized
from typing import Any

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Pango
from twisted.logger import Logger
from twisted.python.failure import Failure

from virtualbricks import locations
from virtualbricks.config.archive import (
    ArchiveCancelled,
    ArchiveJob,
    export_project,
)
from virtualbricks.config.archive import DISK, find_qemu_img, member_kind
from virtualbricks.i18n import _
from virtualbricks.gui.pango import pango_attr_list
from virtualbricks.i18n import ngettext

logger = Logger()
exported = 'Project "{name}" exported to {path}'
export_failed = 'Cannot export the project "{name}": {error}'

MARGIN = 18
# Files of the folder that aren't the project's, left by older versions:
# the images and the project file of before.
INTERNAL = frozenset(
    (
        ".images",
        locations.LEGACY_PROJECT_FILE,
        locations.LEGACY_PROJECT_FILE + "~",
    )
)
# The README of a project not opened since 3.0 still has its old name.
REQUIRED = (locations.PROJECT_FILE, locations.README, locations.LEGACY_README)
STEPS = {
    "pack": _("Compressing the disks…"),
    "write": _("Writing the archive…"),
}


def human_size(size: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1000 or unit == "GB":
            if unit == "B":
                return f"{size:.0f} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1000
    return f"{size:.1f} TB"  # pragma: no cover


def usage(path: str) -> int:
    """The bytes a file takes on disk, without its holes."""

    try:
        return os.lstat(path).st_blocks * 512
    except OSError:
        return 0


def archive_filename(filename: str) -> str:
    """The file name, with the .vbp extension."""

    return filename if filename.endswith(".vbp") else f"{filename}.vbp"


def project_files(path: str) -> tuple[list[str], list[str], list[str]]:
    """(required, private disks, other files) of the folder, relative."""

    required: list[str] = []
    disks: list[str] = []
    others: list[str] = []
    for folder, dirs, files in os.walk(path):
        relative = os.path.relpath(folder, path)
        if relative == ".":
            dirs[:] = [d for d in dirs if d not in INTERNAL]
            relative = ""
        for filename in sorted(files):
            name = os.path.join(relative, filename)
            if name in INTERNAL:
                continue
            if name in REQUIRED:
                required.append(name)
            elif member_kind(name) == DISK:
                disks.append(name)
            else:
                others.append(name)
        dirs.sort()
    return required, disks, others


def ngettext_n(singular: str, plural: str, items: Sized) -> str:
    count = len(items)
    return ngettext(singular, plural, count).format(n=count)


def _label(
    text: str = "",
    dim: bool = False,
    bold: bool = False,
    wrap: bool = False,
    xalign: float = 0.0,
    **props: Any,
) -> Gtk.Label:
    label = Gtk.Label(
        visible=True, label=text, xalign=xalign, wrap=wrap, **props
    )
    if dim:
        label.get_style_context().add_class("dim-label")
    if bold:
        label.set_attributes(
            pango_attr_list(Pango.attr_weight_new(Pango.Weight.BOLD))
        )
    return label


class ExportProjectDialog:
    """Export a project: images is a list of (name, path)."""

    def __init__(
        self,
        path: str,
        images: Iterable[tuple[str, str]] = (),
        run: Callable[..., ArchiveJob] = export_project,
    ) -> None:
        self.path = path
        self.name = os.path.basename(path)
        self.images = [(n, p) for n, p in images if os.path.isfile(p)]
        self._run = run
        self.required, self.disks, self.others = project_files(path)
        self.job: ArchiveJob | None = None
        self.destroyed = False
        self.build_ui()
        self.filename_entry.set_text(
            os.path.join(os.path.expanduser("~"), f"{self.name}.vbp")
        )

    # The widgets

    def build_ui(self) -> None:
        self.window = Gtk.Window(
            title=_("Export Project"),
            default_width=520,
            window_position=Gtk.WindowPosition.CENTER_ON_PARENT,
            destroy_with_parent=True,
        )
        header = Gtk.HeaderBar(
            visible=True, title=_("Export Project"), subtitle=self.name
        )
        self.cancel_button = Gtk.Button(visible=True, label=_("Cancel"))
        header.pack_start(self.cancel_button)
        self.export_button = Gtk.Button(visible=True, label=_("Export"))
        self.export_button.get_style_context().add_class("suggested-action")
        header.pack_end(self.export_button)
        self.close_button = Gtk.Button(visible=False, label=_("Close"))
        header.pack_end(self.close_button)
        self.window.set_titlebar(header)

        self.stack = Gtk.Stack(visible=True)
        self.stack.add_named(self._build_form(), "form")
        self.stack.add_named(self._build_running(), "running")
        self.stack.add_named(self._build_done(), "done")
        self.window.add(self.stack)

        self.window.connect("destroy", self.on_destroyed)
        self.cancel_button.connect("clicked", self.on_cancel_clicked)
        self.export_button.connect("clicked", self.on_export_clicked)
        self.close_button.connect("clicked", lambda b: self.window.destroy())
        self.choose_button.connect("clicked", self.on_choose_clicked)
        self.filename_entry.connect("changed", self.on_changed)

    def _page(self) -> Gtk.Box:
        return Gtk.Box(
            visible=True,
            orientation=Gtk.Orientation.VERTICAL,
            spacing=8,
            margin=MARGIN,
        )

    def _check(
        self,
        label: str,
        size: int,
        active: bool = True,
        sensitive: bool = True,
    ) -> Gtk.CheckButton:
        check = Gtk.CheckButton(
            visible=True, active=active, sensitive=sensitive
        )
        box = Gtk.Box(visible=True, spacing=12)
        box.pack_start(_label(label), True, True, 0)
        box.pack_end(_label(human_size(size), dim=True), False, False, 0)
        check.add(box)
        check.connect("toggled", self.on_changed)
        return check

    def size_of(self, names: Iterable[str]) -> int:
        return sum(usage(os.path.join(self.path, name)) for name in names)

    def _build_form(self) -> Gtk.Box:
        box = self._page()
        box.pack_start(_label(_("Save as"), bold=True), False, False, 0)
        row = Gtk.Box(visible=True, spacing=6)
        self.filename_entry = Gtk.Entry(visible=True, hexpand=True)
        row.pack_start(self.filename_entry, True, True, 0)
        self.choose_button = Gtk.Button(visible=True, label=_("Choose…"))
        row.pack_start(self.choose_button, False, False, 0)
        box.pack_start(row, False, False, 0)

        box.pack_start(
            _label(_("Include"), bold=True, margin_top=6), False, False, 0
        )
        self.project_check = self._check(
            _("The project: its file and its README"),
            self.size_of(self.required),
            sensitive=False,
        )
        box.pack_start(self.project_check, False, False, 0)
        self.disks_check = self._check(
            ngettext_n("{n} private disk", "{n} private disks", self.disks),
            self.size_of(self.disks),
        )
        self.disks_check.set_visible(bool(self.disks))
        box.pack_start(self.disks_check, False, False, 0)
        image_names = ", ".join(name for name, _path in self.images)
        self.images_check = self._check(
            _("The images: {names}").format(names=image_names),
            sum(usage(path) for _name, path in self.images),
            active=False,
        )
        self.images_check.set_visible(bool(self.images))
        box.pack_start(self.images_check, False, False, 0)

        self.others_expander = Gtk.Expander(
            visible=bool(self.others),
            label=ngettext_n("{n} other file", "{n} other files", self.others),
        )
        others_box = Gtk.Box(
            visible=True,
            orientation=Gtk.Orientation.VERTICAL,
            margin_start=12,
        )
        self.other_checks: dict[str, Gtk.CheckButton] = {}
        for name in self.others:
            check = self._check(name, self.size_of([name]))
            self.other_checks[name] = check
            others_box.pack_start(check, False, False, 0)
        self.others_expander.add(others_box)
        box.pack_start(self.others_expander, False, False, 0)
        self.total_label = _label(dim=True, margin_top=6)
        box.pack_start(self.total_label, False, False, 0)
        self.form_error = _label(wrap=True)
        self.form_error.get_style_context().add_class("error")
        self.form_error.set_visible(False)
        box.pack_start(self.form_error, False, False, 0)
        return box

    def _build_running(self) -> Gtk.Box:
        box = self._page()
        box.set_valign(Gtk.Align.CENTER)
        self.step_label = _label(_("Compressing the disks…"), xalign=0.5)
        box.pack_start(self.step_label, False, False, 0)
        self.progress_bar = Gtk.ProgressBar(visible=True, show_text=True)
        box.pack_start(self.progress_bar, False, False, 0)
        return box

    def _build_done(self) -> Gtk.Box:
        box = self._page()
        box.set_valign(Gtk.Align.CENTER)
        self.done_label = _label(wrap=True, selectable=True, xalign=0.5)
        box.pack_start(self.done_label, False, False, 0)
        return box

    def get_root_widget(self) -> Gtk.Window:
        return self.window

    def show(self, parent: Gtk.Window | None = None) -> None:
        if parent is not None:
            self.window.set_transient_for(parent)
        self.window.show()
        self.on_changed()

    def show_page(self, name: str) -> None:
        self.stack.set_visible_child_name(name)
        self.export_button.set_visible(name == "form")
        self.close_button.set_visible(name == "done")
        self.cancel_button.set_visible(name != "done")
        self.cancel_button.set_label(
            _("Stop") if name == "running" else _("Cancel")
        )

    # The choices

    def files(self) -> list[str]:
        """The files of the folder to include, relative to it."""

        files = list(self.required)
        if self.disks_check.get_active():
            files += self.disks
        files += [n for n, c in self.other_checks.items() if c.get_active()]
        return files

    def chosen_images(self) -> list[tuple[str, str]]:
        return self.images if self.images_check.get_active() else []

    def output(self) -> str:
        text = self.filename_entry.get_text().strip()
        return archive_filename(os.path.expanduser(text)) if text else ""

    def on_changed(self, *args: object) -> None:
        size = self.size_of(self.files()) + sum(
            usage(path) for _name, path in self.chosen_images()
        )
        self.total_label.set_text(
            _("{size} before compression").format(size=human_size(size))
        )
        output = self.output()
        problem = None
        if output and os.path.isdir(output):
            problem = _("{path} is a folder").format(path=output)
        elif output and not os.path.isdir(os.path.dirname(output) or "."):
            problem = _("The folder of {path} doesn't exist").format(
                path=output
            )
        self.form_error.set_text(problem or "")
        self.form_error.set_visible(bool(problem))
        self.export_button.set_sensitive(bool(output) and problem is None)

    def on_choose_clicked(self, button: Gtk.Button) -> None:
        path = self.choose_file()
        if path:
            self.filename_entry.set_text(archive_filename(path))

    def choose_file(self) -> str | None:
        """Ask where to save; None if cancelled."""

        chooser = Gtk.FileChooserNative.new(
            _("Export Project"),
            self.window,
            Gtk.FileChooserAction.SAVE,
            None,
            None,
        )
        chooser.set_do_overwrite_confirmation(True)
        current = self.output()
        if current:
            chooser.set_current_folder(os.path.dirname(current))
            chooser.set_current_name(os.path.basename(current))
        vbp = Gtk.FileFilter()
        vbp.set_name(_("Virtualbricks archives"))
        vbp.add_pattern("*.vbp")
        chooser.add_filter(vbp)
        try:
            if chooser.run() == Gtk.ResponseType.ACCEPT:
                return chooser.get_filename()
            return None
        finally:
            chooser.destroy()

    def confirm_overwrite(self, path: str) -> bool:
        dialog = Gtk.MessageDialog(
            transient_for=self.window,
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            text=_('"{name}" already exists. Replace it?').format(
                name=os.path.basename(path)
            ),
        )
        dialog.format_secondary_text(
            _(
                "The archive in {folder} is replaced when the export ends."
            ).format(folder=os.path.dirname(path))
        )
        dialog.add_button(_("Cancel"), Gtk.ResponseType.CANCEL)
        replace = dialog.add_button(_("Replace"), Gtk.ResponseType.ACCEPT)
        replace.get_style_context().add_class("destructive-action")
        try:
            return dialog.run() == Gtk.ResponseType.ACCEPT
        finally:
            dialog.destroy()

    # Running the export

    def on_export_clicked(self, button: Gtk.Button) -> None:
        output = self.output()
        if not output:
            return
        if os.path.exists(output) and not self.confirm_overwrite(output):
            return
        self.start(output)

    def start(self, output: str) -> None:
        self.progress_bar.set_fraction(0.0)
        self.progress_bar.set_text("")
        self.show_page("running")
        self.job = self._run(
            self.path,
            output,
            self.files(),
            self.chosen_images(),
            on_progress=self.on_progress,
            qemu_img=find_qemu_img(),
        )
        self.job.done.addCallbacks(
            self.on_exported, self.on_failed, errbackArgs=(output,)
        )

    def on_progress(self, step: str, done: int, total: int) -> None:
        if self.destroyed:
            return
        self.step_label.set_text(STEPS.get(step, step))
        self.progress_bar.set_fraction(min(done / total, 1.0) if total else 0)
        self.progress_bar.set_text(
            f"{human_size(min(done, total))} / {human_size(total)}"
        )

    def on_exported(self, result: dict[str, Any]) -> None:
        self.job = None
        logger.info(exported, name=self.name, path=result["output"])
        if self.destroyed:
            return
        self.done_label.set_text(
            _("Exported to {path}, {size}.").format(
                path=result["output"], size=human_size(result["size"])
            )
        )
        self.show_page("done")

    def on_failed(self, failure: Failure, output: str) -> None:
        self.job = None
        if failure.check(ArchiveCancelled):
            if not self.destroyed:
                self.show_page("form")
            return None
        logger.error(
            export_failed, name=self.name, error=failure.getErrorMessage()
        )
        if not self.destroyed:
            self.done_label.set_text(
                _("Cannot export to {path}: {error}").format(
                    path=output, error=failure.getErrorMessage()
                )
            )
            self.show_page("done")
        return None

    def on_cancel_clicked(self, button: Gtk.Button) -> None:
        if self.job is not None:
            self.job.cancel()
        else:
            self.window.destroy()

    def on_destroyed(self, window: Gtk.Window) -> None:
        # A running export goes on, and logs when it's done.
        self.destroyed = True
