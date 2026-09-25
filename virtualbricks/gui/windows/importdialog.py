# -*- test-case-name: virtualbricks.tests.gui.windows.test_importdialog -*-
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
Import a project from an archive, on one page.

Choosing a file reads the archive in the archive process. The page shows
the project, a name, and a choice for each image the project uses, each with
a default: copy it from the archive, use a file of this computer, or leave it
unset. The import runs in the archive process too; the window follows its
progress, and can be closed meanwhile.
"""

import collections
import os

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Pango
from twisted.logger import Logger

from virtualbricks.config import (
    ArchiveCancelled,
    import_project,
    inspect_archive,
    plan_import,
    projects,
    update_plan,
)
from virtualbricks.config.importing import COPY, SKIP, USE
from virtualbricks.gui.windows.base import _, Window, pango_attr_list
from virtualbricks.i18n import ngettext

logger = Logger()
imported = 'Project imported as "{name}"'
import_failed = "Cannot import {path}: {error}"
open_failed = 'Cannot open the imported project "{name}": {error}'

MARGIN = 18
STEPS = {
    "read": _("Reading the archive"),
    "extract": _("Extracting the archive"),
}
PATTERNS = ("*.vbp", "*.tar.gz", "*.tgz", "*.tar")


def first_paragraph(text):
    return text.strip().split("\n\n", 1)[0].strip()


def facts(data):
    """ "3 bricks · 1 event" for the project file data."""

    bricks = data.get("bricks", {})
    events = data.get("events", {})
    counts = collections.Counter(
        str(table.get("type", "?"))
        for table in (bricks.values() if isinstance(bricks, dict) else [])
        if isinstance(table, dict)
    )
    parts = [
        _("{count} {type}").format(count=count, type=kind)
        for kind, count in sorted(counts.items())
    ]
    n_events = len(events) if isinstance(events, dict) else 0
    if n_events:
        parts.append(
            ngettext("{n} event", "{n} events", n_events).format(n=n_events)
        )
    return " · ".join(parts) if parts else _("No bricks")


def human_size(size):
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1000 or unit == "GB":
            return (
                f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
            )
        size /= 1000
    return f"{size:.1f} TB"  # pragma: no cover


def find_qemu_img():
    from virtualbricks.spawn import abspath_qemu

    try:
        return abspath_qemu("qemu-img")
    except FileNotFoundError:
        return ""


def _label(text="", dim=False, bold=False, wrap=False, xalign=0.0, **props):
    label = Gtk.Label(
        visible=True, label=text, xalign=xalign, wrap=wrap, **props
    )
    if dim:
        label.get_style_context().add_class("dim-label")
    if bold:
        label.set_attributes(pango_attr_list(Pango.attr_weight_new(700)))
    return label


class ImageRow:
    """The choice for one image: copy it, use a file, leave it unset."""

    def __init__(self, dialog, image):
        self.dialog = dialog
        self.image = image
        self.row = Gtk.ListBoxRow(visible=True, activatable=False)
        grid = Gtk.Grid(
            visible=True,
            column_spacing=12,
            row_spacing=4,
            margin=10,
        )
        self.name_label = _label(image.name, bold=True, hexpand=True)
        grid.attach(self.name_label, 0, 0, 1, 1)
        used_by = ", ".join(image.used_by) or _("no disk")
        self.used_label = _label(
            _("Used by {disks}").format(disks=used_by), dim=True
        )
        grid.attach(self.used_label, 0, 1, 1, 1)
        box = Gtk.Box(visible=True)
        box.get_style_context().add_class("linked")
        self.copy_button = Gtk.RadioButton(
            visible=True, label=_("Copy"), draw_indicator=False
        )
        self.use_button = Gtk.RadioButton(
            visible=True,
            label=_("Use a file…"),
            draw_indicator=False,
            group=self.copy_button,
        )
        self.skip_button = Gtk.RadioButton(
            visible=True,
            label=_("Leave unset"),
            draw_indicator=False,
            group=self.copy_button,
        )
        for button in (self.copy_button, self.use_button, self.skip_button):
            box.pack_start(button, False, False, 0)
        grid.attach(box, 1, 0, 1, 2)
        self.path_label = _label(
            dim=True, ellipsize=Pango.EllipsizeMode.MIDDLE
        )
        grid.attach(self.path_label, 0, 2, 2, 1)
        self.row.add(grid)
        self.buttons = {
            COPY: self.copy_button,
            USE: self.use_button,
            SKIP: self.skip_button,
        }
        self._updating = False
        self.update()
        for choice, button in self.buttons.items():
            button.connect("toggled", self.on_toggled, choice)

    def update(self):
        image = self.image
        self._updating = True
        try:
            self.buttons[image.choice].set_active(True)
        finally:
            self._updating = False
        in_archive = image.in_archive is not None or not image.known
        self.copy_button.set_sensitive(in_archive)
        if not image.known:
            self.copy_button.set_tooltip_text(_("Looking in the archive…"))
        elif image.in_archive is None:
            self.copy_button.set_tooltip_text(_("Not in the archive"))
        else:
            self.copy_button.set_tooltip_text(
                _("{size} in the archive").format(
                    size=human_size(image.in_archive)
                )
            )
        self.path_label.set_text(self.describe())
        self.path_label.set_tooltip_text(image.path or None)

    def describe(self):
        image = self.image
        if image.choice == COPY and not image.known:
            return _(
                "Looking in the archive… if it's there, copied to {path}"
            ).format(path=image.path)
        if image.choice == COPY:
            return _("Copied to {path}").format(path=image.path)
        if image.choice == USE:
            return _("Uses {path}").format(path=image.path)
        return _("Unset: its disks get an image later, in their settings")

    def on_toggled(self, button, choice):
        if self._updating or not button.get_active():
            return
        if choice == USE:
            path = self.dialog.choose_image(self.image)
            if not path:
                self.update()
                return
            self.image.path = path
        elif choice == COPY:
            self.image.path = (
                self.image.path
                if self.image.choice == COPY
                else (self.dialog.copy_destination(self.image))
            )
        self.image.choice = choice
        self.update()
        self.dialog.check()


class ImportDialog(Window):
    """Import a project from an archive (board I1)."""

    def __init__(
        self,
        factory,
        workspace=None,
        inspect=inspect_archive,
        run=import_project,
    ):
        self.factory = factory
        self.workspace = projects if workspace is None else workspace
        self._inspect = inspect
        self._run = run
        self.archive_path = None
        self.plan = None
        self.rows = []
        self.inspect_job = None
        self.import_job = None
        self.result = None
        self.scanning = False
        self.destroyed = False
        super().__init__()

    # The widgets

    def build_ui(self):
        self.window = Gtk.Window(
            title=_("Import Project"),
            default_width=680,
            default_height=600,
            window_position=Gtk.WindowPosition.CENTER_ON_PARENT,
            destroy_with_parent=True,
        )
        header = Gtk.HeaderBar(visible=True, title=_("Import Project"))
        self.cancel_button = Gtk.Button(visible=True, label=_("Cancel"))
        header.pack_start(self.cancel_button)
        self.import_button = Gtk.Button(
            visible=True, label=_("Import"), sensitive=False
        )
        self.import_button.get_style_context().add_class("suggested-action")
        header.pack_end(self.import_button)
        self.close_button = Gtk.Button(visible=False, label=_("Close"))
        header.pack_end(self.close_button)
        self.window.set_titlebar(header)

        self.stack = Gtk.Stack(visible=True)
        self.stack.add_named(self._build_choose(), "choose")
        self.stack.add_named(self._build_reading(), "reading")
        self.stack.add_named(self._build_form(), "form")
        self.stack.add_named(self._build_running(), "running")
        self.stack.add_named(self._build_done(), "done")
        self.stack.add_named(self._build_failed(), "failed")
        self.window.add(self.stack)

        self.window.connect("destroy", self.on_destroyed)
        self.cancel_button.connect("clicked", self.on_cancel_clicked)
        self.import_button.connect("clicked", self.on_import_clicked)
        self.close_button.connect("clicked", self.on_close_clicked)
        self.file_button.connect("file-set", self.on_file_set)
        self.name_entry.connect("changed", self.on_name_changed)
        self.open_check.connect("toggled", self.on_open_toggled)

    def _page(self):
        return Gtk.Box(
            visible=True,
            orientation=Gtk.Orientation.VERTICAL,
            spacing=12,
            margin=MARGIN,
        )

    def _build_choose(self):
        box = self._page()
        box.set_valign(Gtk.Align.CENTER)
        box.pack_start(
            _label(
                _("Choose an archive of a Virtualbricks project."),
                xalign=0.5,
            ),
            False,
            False,
            0,
        )
        file_filter = Gtk.FileFilter()
        file_filter.set_name(_("Virtualbricks archives"))
        for pattern in PATTERNS:
            file_filter.add_pattern(pattern)
        self.file_button = Gtk.FileChooserButton(
            visible=True,
            title=_("Choose an archive"),
            action=Gtk.FileChooserAction.OPEN,
            halign=Gtk.Align.CENTER,
            width_chars=30,
        )
        self.file_button.add_filter(file_filter)
        box.pack_start(self.file_button, False, False, 0)
        return box

    def _build_reading(self):
        box = self._page()
        box.set_valign(Gtk.Align.CENTER)
        self.reading_label = _label(_("Reading the archive…"), xalign=0.5)
        box.pack_start(self.reading_label, False, False, 0)
        self.reading_bar = Gtk.ProgressBar(visible=True, show_text=True)
        box.pack_start(self.reading_bar, False, False, 0)
        return box

    def _build_form(self):
        scrolled = Gtk.ScrolledWindow(
            visible=True, hscrollbar_policy=Gtk.PolicyType.NEVER
        )
        box = self._page()
        self.archive_label = _label(
            dim=True, ellipsize=Pango.EllipsizeMode.MIDDLE
        )
        box.pack_start(self.archive_label, False, False, 0)

        box.pack_start(_label(_("Name"), bold=True), False, False, 0)
        self.name_entry = Gtk.Entry(visible=True, activates_default=True)
        box.pack_start(self.name_entry, False, False, 0)
        self.name_message = _label(dim=True, wrap=True)
        box.pack_start(self.name_message, False, False, 0)

        self.description_label = _label(wrap=True, selectable=True)
        box.pack_start(self.description_label, False, False, 0)
        self.facts_label = _label(dim=True)
        box.pack_start(self.facts_label, False, False, 0)

        self.images_heading = _label(_("Images"), bold=True)
        box.pack_start(self.images_heading, False, False, 0)
        self.scan_box = Gtk.Box(visible=False, spacing=12)
        self.scan_label = _label(_("Looking in the archive…"), dim=True)
        self.scan_bar = Gtk.ProgressBar(visible=True, hexpand=True)
        self.scan_bar.set_valign(Gtk.Align.CENTER)
        self.scan_box.pack_start(self.scan_label, False, False, 0)
        self.scan_box.pack_start(self.scan_bar, True, True, 0)
        box.pack_start(self.scan_box, False, False, 0)
        frame = Gtk.Frame(visible=True)
        self.images_list = Gtk.ListBox(
            visible=True, selection_mode=Gtk.SelectionMode.NONE
        )
        frame.add(self.images_list)
        self.images_frame = frame
        box.pack_start(frame, False, False, 0)
        self.no_images_label = _label(
            _("The project uses no image."), dim=True
        )
        box.pack_start(self.no_images_label, False, False, 0)

        self.paths_heading = _label(_("This computer's paths"), bold=True)
        box.pack_start(self.paths_heading, False, False, 0)
        self.paths_box = Gtk.Box(
            visible=True, orientation=Gtk.Orientation.VERTICAL, spacing=6
        )
        box.pack_start(self.paths_box, False, False, 0)
        self.machine_checks = {}

        self.open_check = Gtk.CheckButton(
            visible=True,
            label=_("Open the project after the import"),
            active=True,
        )
        box.pack_start(self.open_check, False, False, 0)
        self.problems_label = _label(wrap=True)
        self.problems_label.get_style_context().add_class("error")
        box.pack_start(self.problems_label, False, False, 0)
        scrolled.add(box)
        return scrolled

    def _build_running(self):
        box = self._page()
        box.set_valign(Gtk.Align.CENTER)
        self.step_label = _label(xalign=0.5)
        box.pack_start(self.step_label, False, False, 0)
        self.run_bar = Gtk.ProgressBar(visible=True, show_text=True)
        box.pack_start(self.run_bar, False, False, 0)
        box.pack_start(
            _label(
                _(
                    "You can close this window: the Messages window says"
                    " when the import is done."
                ),
                dim=True,
                wrap=True,
                xalign=0.5,
            ),
            False,
            False,
            0,
        )
        return box

    def _build_done(self):
        box = self._page()
        self.done_label = _label(wrap=True, bold=True)
        box.pack_start(self.done_label, False, False, 0)
        self.warnings_heading = _label(_("To check"), bold=True)
        box.pack_start(self.warnings_heading, False, False, 0)
        frame = Gtk.Frame(visible=True)
        self.warnings_list = Gtk.ListBox(
            visible=True, selection_mode=Gtk.SelectionMode.NONE
        )
        frame.add(self.warnings_list)
        self.warnings_frame = frame
        box.pack_start(frame, False, False, 0)
        return box

    def _build_failed(self):
        box = self._page()
        box.set_valign(Gtk.Align.CENTER)
        self.error_label = _label(wrap=True, selectable=True, xalign=0.5)
        box.pack_start(self.error_label, False, False, 0)
        return box

    def get_root_widget(self):
        return self.window

    def page(self):
        return self.stack.get_visible_child_name()

    def show_page(self, name):
        self.stack.set_visible_child_name(name)
        running = name == "running"
        finished = name in ("done", "failed")
        self.import_button.set_visible(name in ("choose", "reading", "form"))
        self.close_button.set_visible(finished)
        self.cancel_button.set_visible(not finished)
        self.cancel_button.set_label(_("Stop") if running else _("Cancel"))

    # Reading the archive

    def choose(self, path):
        """Read the archive at path."""

        if self.inspect_job is not None:
            self.inspect_job.cancel()
        self.archive_path = path
        self.plan = None
        self.reading_bar.set_fraction(0.0)
        self.reading_bar.set_text("")
        self.show_page("reading")
        job = self.inspect_job = self._inspect(
            path, on_head=self.on_head, on_progress=self.on_read_progress
        )
        job.done.addCallbacks(
            self.on_contents,
            self.on_inspect_failed,
            callbackArgs=(job,),
            errbackArgs=(job,),
        )

    def on_read_progress(self, step, done, total):
        fraction = done / total if total else 0.0
        self.reading_bar.set_fraction(fraction)
        self.reading_bar.set_text(f"{human_size(done)} / {human_size(total)}")
        self.scan_bar.set_fraction(fraction)

    def on_head(self, contents):
        if self.destroyed or self.plan is not None:
            return
        self.scanning = True
        self.show_form(plan_import(contents, self.workspace))

    def on_contents(self, contents, job):
        if job is not self.inspect_job or self.destroyed:
            return
        self.inspect_job = None
        self.scanning = False
        if self.plan is None:
            self.show_form(plan_import(contents, self.workspace))
        else:
            update_plan(self.plan, contents)
            self.refresh()

    def on_inspect_failed(self, failure, job):
        if job is not self.inspect_job or self.destroyed:
            return None
        self.inspect_job = None
        self.scanning = False
        if failure.check(ArchiveCancelled):
            return None
        self.fail(
            _("Cannot read {path}: {error}").format(
                path=self.archive_path, error=failure.getErrorMessage()
            )
        )
        return None

    # The form

    def show_form(self, plan):
        self.plan = plan
        self.archive_label.set_text(plan.contents.path)
        self.name_entry.set_text(plan.name)
        description = first_paragraph(plan.contents.description)
        self.description_label.set_text(description)
        self.description_label.set_visible(bool(description))
        self.facts_label.set_text(facts(plan.contents.data))
        for child in self.images_list.get_children():
            self.images_list.remove(child)
        self.rows = [ImageRow(self, image) for image in plan.images]
        for row in self.rows:
            self.images_list.add(row.row)
        self.images_frame.set_visible(bool(self.rows))
        self.no_images_label.set_visible(not self.rows)
        for child in self.paths_box.get_children():
            self.paths_box.remove(child)
        self.machine_checks = {}
        for path in plan.machine_paths:
            check = Gtk.CheckButton(
                visible=True,
                active=path.use_ours,
                label=_(
                    "Use this computer's {key}, {ours}, instead of {theirs}"
                ).format(key=path.key, ours=path.ours, theirs=path.theirs),
            )
            check.connect("toggled", self.on_machine_path_toggled, path)
            self.machine_checks[path.key] = check
            self.paths_box.add(check)
        self.paths_heading.set_visible(bool(plan.machine_paths))
        self.open_check.set_active(plan.open)
        self.show_page("form")
        self.refresh()

    def refresh(self):
        self.scan_box.set_visible(self.scanning)
        for row in self.rows:
            row.update()
        self.check()

    def check(self):
        """Show what stops the import; Import waits for none."""

        if self.plan is None:
            return
        problems = self.plan.problems(self.workspace)
        name_problem = self.workspace.check_name(self.plan.name)
        self.name_message.set_text(name_problem or "")
        self.name_message.set_visible(bool(name_problem))
        others = [p for p in problems if p != name_problem]
        self.problems_label.set_text("\n".join(others))
        self.problems_label.set_visible(bool(others))
        self.import_button.set_sensitive(not problems)

    def on_name_changed(self, entry):
        if self.plan is not None:
            self.plan.name = entry.get_text()
            self.check()

    def on_open_toggled(self, check):
        if self.plan is not None:
            self.plan.open = check.get_active()

    def on_machine_path_toggled(self, check, path):
        path.use_ours = check.get_active()

    def copy_destination(self, image):
        from virtualbricks.config.importing import free_file

        name = os.path.basename(image.original) or image.name
        return free_file(os.path.join(self.plan.library, name))

    def choose_image(self, image):
        """Ask for the file of an image; None if cancelled."""

        chooser = Gtk.FileChooserNative.new(
            _("The file of {name}").format(name=image.name),
            self.window,
            Gtk.FileChooserAction.OPEN,
            None,
            None,
        )
        folder = os.path.dirname(image.path or image.original)
        if folder and os.path.isdir(folder):
            chooser.set_current_folder(folder)
        try:
            if chooser.run() == Gtk.ResponseType.ACCEPT:
                return chooser.get_filename()
            return None
        finally:
            chooser.destroy()

    # Running the import

    def start_import(self):
        if self.inspect_job is not None:
            # The import reads the whole archive anyway.
            job, self.inspect_job = self.inspect_job, None
            job.cancel()
            self.scanning = False
        plan = self.plan
        self.step_label.set_text(_("Importing {name}").format(name=plan.name))
        self.run_bar.set_fraction(0.0)
        self.run_bar.set_text("")
        self.show_page("running")
        job = self.import_job = self._run(
            plan,
            self.workspace,
            self.on_import_progress,
            qemu_img=find_qemu_img(),
        )
        job.done.addCallbacks(self.on_imported, self.on_import_failed)

    def on_import_progress(self, step, done, total):
        if self.destroyed:
            return
        self.step_label.set_text(STEPS.get(step, step))
        self.run_bar.set_fraction(done / total if total else 0.0)
        self.run_bar.set_text(f"{human_size(done)} / {human_size(total)}")

    def on_imported(self, result):
        self.import_job = None
        self.result = result
        logger.info(imported, name=result.name)
        result.report.log(logger)
        if self.plan.open:
            self.open_project(result)
        if self.destroyed:
            return
        self.done_label.set_text(
            _('Imported as "{name}".').format(name=result.name)
        )
        for child in self.warnings_list.get_children():
            self.warnings_list.remove(child)
        for message in result.report:
            row = Gtk.ListBoxRow(visible=True, activatable=False)
            box = Gtk.Box(
                visible=True,
                orientation=Gtk.Orientation.VERTICAL,
                margin=8,
                spacing=2,
            )
            box.pack_start(_label(message.text, wrap=True), False, False, 0)
            if message.where:
                box.pack_start(
                    _label(message.where, dim=True), False, False, 0
                )
            row.add(box)
            self.warnings_list.add(row)
        has_messages = len(result.report) > 0
        self.warnings_heading.set_visible(has_messages)
        self.warnings_frame.set_visible(has_messages)
        self.show_page("done")

    def open_project(self, result):
        try:
            self.workspace.save(self.factory)
            report = self.workspace.open(result.name, self.factory)
        except Exception as exc:
            logger.error(open_failed, name=result.name, error=exc)
            result.report.error(
                _("cannot be opened: {error}").format(error=exc), result.name
            )
        else:
            result.report.extend(report)

    def on_import_failed(self, failure):
        self.import_job = None
        if failure.check(ArchiveCancelled):
            if not self.destroyed:
                self.show_page("form")
                self.check()
            return None
        logger.error(
            import_failed,
            path=self.archive_path,
            error=failure.getErrorMessage(),
        )
        if not self.destroyed:
            self.fail(failure.getErrorMessage())
        return None

    def fail(self, message):
        self.error_label.set_text(message)
        self.show_page("failed")

    # Signals

    def on_file_set(self, button):
        path = button.get_filename()
        if path:
            self.choose(path)

    def on_import_clicked(self, button):
        if self.plan is not None and not self.plan.problems(self.workspace):
            self.start_import()

    def on_cancel_clicked(self, button):
        if self.import_job is not None:
            self.import_job.cancel()
            return
        self.window.destroy()

    def on_close_clicked(self, button):
        self.window.destroy()

    def on_destroyed(self, window):
        self.destroyed = True
        if self.inspect_job is not None:
            self.inspect_job.cancel()
            self.inspect_job = None
        # A running import goes on, and logs when it's done.
