# -*- test-case-name: virtualbricks.tests.migrate.test_gui -*-
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
The migration window, also started by the ``virtualbricks-migrate`` command,
by ``python -m virtualbricks.migrate --gui`` and by ``python -m
virtualbricks.migrate.gui``; they all take the options of the command line.

It lists the settings and the projects to migrate, shows the progress and the
messages of the selected row. Check runs the migration without writing
anything, Migrate writes.
"""

from __future__ import annotations

import os
import sys
import tempfile
from collections.abc import Iterator
from typing import TYPE_CHECKING, TypedDict

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

from twisted.internet import defer, task
from twisted.logger import Logger

from virtualbricks import i18n, locations
from virtualbricks.i18n import _, ngettext
from virtualbricks.migrate import engine
from virtualbricks.config import ERROR, INFO, WARNING

if TYPE_CHECKING:
    from twisted.internet.interfaces import IReactorCore
    from twisted.python.failure import Failure
    from twisted.python.lockfile import FilesystemLock
    from typing_extensions import Unpack

logger = Logger()
NAME, BRICKS, STATUS = range(3)
LEVEL_COLORS = {INFO: "#56655f", WARNING: "#7a4800", ERROR: "#982b22"}


class WindowOptions(TypedDict, total=False):
    """What fills the window of the command, see :func:`default_window`."""

    workspace: str | None
    settings_file: str | None
    output: str | None
    in_place: bool


def status_text(item: engine.Item) -> str:
    if item.status == engine.MIGRATED:
        warnings = item.report.warnings
        if warnings:
            text = ngettext("⚠ {0} warning", "⚠ {0} warnings", warnings)
            return text.format(warnings)
        return _("✓ Migrated")
    return {
        engine.WAITING: _("· Waiting"),
        engine.MIGRATING: _("↻ Migrating"),
        engine.FAILED: _("✗ Failed"),
        engine.SKIPPED: _("– Skipped"),
    }[item.status]


def default_output() -> str:
    return os.path.join(tempfile.gettempdir(), "virtualbricks-migration")


def _form_row(
    grid: Gtk.Grid, row: int, label: str, widget: Gtk.Widget
) -> None:
    caption = Gtk.Label(label=label, xalign=0.0)
    grid.attach(caption, 0, row, 1, 1)
    grid.attach(widget, 1, row, 1, 1)


def _path_entry(
    text: str, action: Gtk.FileChooserAction, title: str, parent: Gtk.Window
) -> tuple[Gtk.Box, Gtk.Entry, Gtk.Button]:
    """An entry with a button to pick the path it holds."""

    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    entry = Gtk.Entry(text=text, hexpand=True)
    button = Gtk.Button(label=_("Choose…"))

    def choose(_button: Gtk.Button) -> None:
        dialog = Gtk.FileChooserDialog(
            title=title, transient_for=parent, action=action
        )
        dialog.add_buttons(
            _("_Cancel"),
            Gtk.ResponseType.CANCEL,
            _("_Select"),
            Gtk.ResponseType.OK,
        )
        if entry.get_text():
            dialog.set_filename(entry.get_text())
        if dialog.run() == Gtk.ResponseType.OK:
            filename = dialog.get_filename()
            if filename is not None:
                entry.set_text(filename)
        dialog.destroy()

    button.connect("clicked", choose)
    box.pack_start(entry, True, True, 0)
    box.pack_start(button, False, False, 0)
    return box, entry, button


class MigrationWindow:
    """
    The window of a migration.

    With ``migration`` it shows that migration only, runs it as soon as it's
    shown and can't change what's migrated: this is how the application
    migrates the files of the user at startup.
    """

    migration: engine.Migration | None = None
    # Held while the files of the user are migrated from the form.
    lock: FilesystemLock | None = None

    def __init__(
        self,
        workspace: str = "",
        settings_file: str = "",
        migration: engine.Migration | None = None,
        output: str | None = None,
        in_place: bool = False,
    ) -> None:
        self.fixed = migration is not None
        # fires with the migration shown, if any, when the window closes
        self.closed: defer.Deferred[engine.Migration | None] = defer.Deferred()
        # fires with the steps of the migration running, when they are done
        self.running: defer.Deferred[Iterator[None]] | None = None
        self.build_ui(workspace, settings_file)
        if output is not None:
            self.output_entry.set_text(output)
        if in_place:
            self.in_place_radio.set_active(True)
        if migration is not None:
            self.fill(migration)
            self.form.set_sensitive(False)
            self.check_button.hide()
            self.migrate_button.hide()

    def build_ui(self, workspace: str, settings_file: str) -> None:
        self.window = Gtk.Window(title=_("Virtualbricks migration"))
        self.window.set_default_size(720, 560)
        self.window.connect("destroy", self.on_destroy)
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        outer.set_border_width(16)
        self.window.add(outer)

        self.form = grid = Gtk.Grid(column_spacing=12, row_spacing=8)
        box, self.workspace_entry, _button = _path_entry(
            workspace,
            Gtk.FileChooserAction.SELECT_FOLDER,
            _("Old workspace"),
            self.window,
        )
        _form_row(grid, 0, _("Old workspace"), box)
        box, self.settings_entry, _button = _path_entry(
            settings_file,
            Gtk.FileChooserAction.OPEN,
            _("Old settings"),
            self.window,
        )
        _form_row(grid, 1, _("Old settings"), box)
        choice = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.in_place_radio = Gtk.RadioButton(label=_("In place"))
        self.folder_radio = Gtk.RadioButton(
            label=_("Folder"), group=self.in_place_radio
        )
        self.folder_radio.set_active(True)
        box, self.output_entry, self.output_button = _path_entry(
            default_output(),
            Gtk.FileChooserAction.SELECT_FOLDER,
            _("Write to"),
            self.window,
        )
        self.folder_radio.connect("toggled", self.on_folder_toggled, box)
        choice.pack_start(self.in_place_radio, False, False, 0)
        choice.pack_start(self.folder_radio, False, False, 0)
        choice.pack_start(box, True, True, 0)
        _form_row(grid, 2, _("Write to"), choice)
        outer.pack_start(grid, False, False, 0)

        self.store = Gtk.ListStore(str, str, str)
        self.view = Gtk.TreeView(model=self.store)
        titles = (_("Project"), _("Bricks"), _("Status"))
        for column, title in enumerate(titles):
            renderer = Gtk.CellRendererText()
            view_column = Gtk.TreeViewColumn(title, renderer, text=column)
            view_column.set_expand(column == NAME)
            self.view.append_column(view_column)
        self.view.get_selection().connect("changed", self.on_selection_changed)
        scrolled = Gtk.ScrolledWindow(vexpand=True)
        scrolled.add(self.view)
        outer.pack_start(scrolled, True, True, 0)

        self.progress = Gtk.ProgressBar(show_text=True)
        outer.pack_start(self.progress, False, False, 0)

        self.messages = Gtk.TextView(editable=False, cursor_visible=False)
        self.messages.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        buffer = self.messages.get_buffer()
        for level, color in LEVEL_COLORS.items():
            buffer.create_tag(level, foreground=color)
        buffer.create_tag("name", weight=700)
        scrolled = Gtk.ScrolledWindow(vexpand=True)
        scrolled.add(self.messages)
        outer.pack_start(scrolled, True, True, 0)

        buttons = Gtk.ButtonBox(layout_style=Gtk.ButtonBoxStyle.END, spacing=8)
        self.save_button = Gtk.Button(label=_("Save report…"))
        self.save_button.set_sensitive(False)
        self.save_button.connect("clicked", self.on_save_clicked)
        self.check_button = Gtk.Button(label=_("Check"))
        self.check_button.connect("clicked", self.on_check_clicked)
        self.migrate_button = Gtk.Button(label=_("Migrate"))
        self.migrate_button.connect("clicked", self.on_migrate_clicked)
        self.close_button = Gtk.Button(label=_("Close"))
        self.close_button.connect("clicked", self.on_close_clicked)
        for button in (
            self.save_button,
            self.check_button,
            self.migrate_button,
            self.close_button,
        ):
            buttons.pack_start(button, False, False, 0)
        outer.pack_start(buttons, False, False, 0)
        outer.show_all()

    def show(self) -> None:
        self.window.present()
        if self.fixed and self.running is None:
            # a fixed window is filled with its migration
            assert self.migration is not None
            self.run(self.migration)

    # Building the migration from the form

    def make_migration(self, dry_run: bool) -> engine.Migration:
        """Return the migration chosen in the form; ValueError if invalid."""

        workspace = self.workspace_entry.get_text()
        settings_file = self.settings_entry.get_text() or None
        if not os.path.isdir(workspace):
            raise ValueError(_("{0} is not a folder").format(workspace))
        if settings_file is not None and not os.path.isfile(settings_file):
            raise ValueError(_("{0} is not a file").format(settings_file))
        output = None
        if self.folder_radio.get_active():
            output = self.output_entry.get_text()
            if os.path.exists(output) and (
                not os.path.isdir(output) or os.listdir(output)
            ):
                raise ValueError(
                    _("{0} must be a new or empty folder").format(output)
                )
        return engine.migration_for(
            workspace, settings_file, output, dry_run=dry_run
        )

    def fill(self, migration: engine.Migration) -> None:
        self.migration = migration
        self.store.clear()
        for item in migration.items:
            self.store.append(self.row(item))
        self.show_progress()
        if len(self.store):
            self.view.get_selection().select_path(Gtk.TreePath.new_first())
        else:
            self.show_text(_("There is nothing to migrate."))

    def row(self, item: engine.Item) -> list[str]:
        bricks = "—" if item.bricks is None else str(item.bricks)
        return [item.name, bricks, status_text(item)]

    # Running

    def run(
        self, migration: engine.Migration
    ) -> defer.Deferred[Iterator[None]]:
        self.fill(migration)
        for button in (self.check_button, self.migrate_button):
            button.set_sensitive(False)
        self.save_button.set_sensitive(False)
        self.form.set_sensitive(False)
        self.task = task.cooperate(self._steps(migration))
        self.running = self.task.whenDone()
        self.running.addCallbacks(
            self._finished, self._stopped, callbackArgs=(migration,)
        )
        return self.running

    def _steps(self, migration: engine.Migration) -> Iterator[None]:
        for item in migration.steps():
            index = migration.items.index(item)
            self.store[index] = self.row(item)  # type: ignore[index]
            self.show_progress(item)
            self.on_selection_changed(self.view.get_selection())
            yield None

    def _finished(
        self, _: Iterator[None], migration: engine.Migration
    ) -> engine.Migration:
        self._unlock()
        self.show_progress()
        self.save_button.set_sensitive(True)
        if self.fixed:
            migration.log(logger)
        else:
            self.form.set_sensitive(True)
            self.check_button.set_sensitive(True)
            self.migrate_button.set_sensitive(True)
        self.running = None
        return migration

    def _stopped(self, failure: Failure) -> None:
        failure.trap(task.TaskStopped)
        self._unlock()
        self.running = None

    def show_progress(self, current: engine.Item | None = None) -> None:
        # the window is filled before its progress is shown
        assert self.migration is not None
        items = self.migration.items
        total = sum(1 for item in items if item.status != engine.SKIPPED)
        done = sum(
            1
            for item in items
            if item.status in (engine.MIGRATED, engine.FAILED)
        )
        if current is not None and current.status == engine.MIGRATING:
            text = _("Migrating {0} · {1} of {2}").format(
                current.name, done + 1, total
            )
        elif total and done == total:
            text = self.migration.summary()
        else:
            text = _("{0} of {1}").format(done, total)
        self.progress.set_text(text)
        self.progress.set_fraction(done / total if total else 1.0)

    # Messages

    def show_text(self, text: str) -> None:
        buffer = self.messages.get_buffer()
        buffer.set_text(text)

    def show_messages(self, item: engine.Item) -> None:
        buffer = self.messages.get_buffer()
        buffer.set_text("")
        end = buffer.get_end_iter()
        buffer.insert_with_tags_by_name(end, item.name + "\n", "name")
        if not len(item.report):
            buffer.insert(buffer.get_end_iter(), _("No messages.") + "\n")
        for message in item.report:
            where = f"{message.where} " if message.where else ""
            buffer.insert_with_tags_by_name(
                buffer.get_end_iter(),
                f"{message.level}  {where}{message.text}\n",
                message.level,
            )

    # Signals

    def on_selection_changed(self, selection: Gtk.TreeSelection) -> None:
        model, itr = selection.get_selected()
        if itr is not None:
            # there are rows once the window is filled
            assert self.migration is not None
            index = model.get_path(itr).get_indices()[0]
            self.show_messages(self.migration.items[index])

    def on_folder_toggled(self, radio: Gtk.RadioButton, box: Gtk.Box) -> None:
        box.set_sensitive(radio.get_active())

    def _start(self, dry_run: bool) -> defer.Deferred[Iterator[None]] | None:
        try:
            migration = self.make_migration(dry_run)
        except ValueError as exc:
            self.show_text(str(exc))
            return None
        if isinstance(migration.target, engine.InPlace) and not dry_run:
            self.lock = engine.lock_in_place()
            if self.lock is None:
                self.show_text(
                    _(
                        "Virtualbricks is running: close it to migrate your "
                        "files in place."
                    )
                )
                return None
        return self.run(migration)

    def _unlock(self) -> None:
        if self.lock is not None:
            self.lock.unlock()
            self.lock = None

    def on_check_clicked(
        self, button: Gtk.Button
    ) -> defer.Deferred[Iterator[None]] | None:
        return self._start(dry_run=True)

    def on_migrate_clicked(
        self, button: Gtk.Button
    ) -> defer.Deferred[Iterator[None]] | None:
        return self._start(dry_run=False)

    def on_save_clicked(self, button: Gtk.Button) -> None:
        dialog = Gtk.FileChooserDialog(
            title=_("Save report"),
            transient_for=self.window,
            action=Gtk.FileChooserAction.SAVE,
        )
        dialog.add_buttons(
            _("_Cancel"),
            Gtk.ResponseType.CANCEL,
            _("_Save"),
            Gtk.ResponseType.OK,
        )
        dialog.set_do_overwrite_confirmation(True)
        dialog.set_current_name(engine.REPORT_FILE)
        if dialog.run() == Gtk.ResponseType.OK:
            filename = dialog.get_filename()
            if filename is not None:
                self.save_report(filename)
        dialog.destroy()

    def save_report(self, path: str) -> None:
        # the report can be saved once a migration has run
        assert self.migration is not None
        with open(path, "w", encoding="utf-8") as fp:
            fp.write(self.migration.text())

    def on_close_clicked(self, button: Gtk.Button) -> None:
        self.window.destroy()

    def on_destroy(self, window: Gtk.Window) -> None:
        if self.running is not None:
            self.task.stop()
        if not self.closed.called:
            self.closed.callback(self.migration)


def default_window(
    workspace: str | None = None,
    settings_file: str | None = None,
    output: str | None = None,
    in_place: bool = False,
) -> MigrationWindow:
    """
    The window of the command, filled with what is given or else with the old
    files of the user.
    """

    if workspace is None:
        workspace = engine.in_place_migration().workspace
    if settings_file is None:
        legacy_settings = locations.legacy_settings_file()
        if os.path.isfile(legacy_settings):
            settings_file = legacy_settings
    return MigrationWindow(
        workspace,
        settings_file or "",
        output=output,
        in_place=in_place,
    )


def run(reactor: IReactorCore, **options: Unpack[WindowOptions]) -> None:
    window = default_window(**options)
    window.closed.addBoth(lambda _: reactor.stop())
    window.show()
    reactor.run()


def main(
    **options: Unpack[WindowOptions],
) -> None:  # pragma: no cover (it installs the GTK reactor)
    """Open the window; the options are the ones of :func:`default_window`."""

    from twisted.internet import gtk3reactor

    gtk3reactor.install()
    from twisted.internet import reactor

    i18n.install()
    run(reactor, **options)


if __name__ == "__main__":  # pragma: no cover
    from virtualbricks.migrate.cli import gui_main

    sys.exit(gui_main())
