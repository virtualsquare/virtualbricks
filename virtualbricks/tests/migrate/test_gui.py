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

import os
import tempfile

from twisted.internet import defer
from twisted.trial import unittest

from virtualbricks import locations
from virtualbricks.migrate import (
    FAILED,
    MIGRATED,
    MIGRATING,
    REPORT_FILE,
    SKIPPED,
    WAITING,
    Folder,
    InPlace,
    Item,
    Migration,
)
from virtualbricks.tests import (
    FakeLogger,
    hold_lock,
    isolate,
    lock_is_free,
    release,
    reset_settings,
)
from virtualbricks.tests.migrate.fixtures import (
    CONFIG1,
    write,
    write_project,
    write_settings,
)

from virtualbricks.tests.gui import has_display

if has_display:
    from gi.repository import Gtk

    from virtualbricks.migrate import gui


class FakeFileChooser:
    """Answer a file chooser dialog without showing it."""

    response = None
    filename = None
    instances = []

    def __init__(self, title, transient_for, action):
        self.title = title
        self.action = action
        self.initial = None
        self.current_name = None
        self.destroyed = False
        self.instances.append(self)

    def add_buttons(self, *buttons):
        pass

    def set_filename(self, filename):
        self.initial = filename

    def set_do_overwrite_confirmation(self, confirm):
        pass

    def set_current_name(self, name):
        self.current_name = name

    def run(self):
        return self.response

    def get_filename(self):
        return self.filename

    def destroy(self):
        self.destroyed = True


class GuiTestCase(unittest.TestCase):

    if not has_display:  # pragma: no cover
        skip = "GTK can't open a display"

    def setUp(self):
        self.root = isolate(self)
        reset_settings(self)
        self.workspace = os.path.join(self.root, "old")
        self.output = os.path.join(self.root, "new")
        write_project(self.workspace, "lab", CONFIG1)
        write_project(self.workspace, "wan", "[Switch:sw]\n")
        self.logger = FakeLogger()
        self.patch(gui, "logger", self.logger)
        self.chooser = type("Chooser", (FakeFileChooser,), {"instances": []})
        self.patch(gui.Gtk, "FileChooserDialog", self.chooser)

    def make_window(self, **kwargs):
        window = gui.MigrationWindow(**kwargs)
        # never shown: the tests don't open windows on the screen
        window.window.present = lambda: None
        # after the destroy, which stops a running migration
        self.addCleanup(lambda: release(window.lock))
        self.addCleanup(window.window.destroy)
        return window

    def form_window(self):
        window = self.make_window(workspace=self.workspace)
        window.output_entry.set_text(self.output)
        return window

    def rows(self, window):
        return [tuple(row) for row in window.store]

    def messages(self, window):
        buffer = window.messages.get_buffer()
        start, end = buffer.get_bounds()
        return buffer.get_text(start, end, False)


class TestStatusText(unittest.TestCase):

    if not has_display:  # pragma: no cover
        skip = "GTK can't open a display"

    def test_statuses(self):
        item = Item("lab", "project", "/lab")
        texts = {}
        for status in (
            WAITING,
            MIGRATING,
            MIGRATED,
            FAILED,
            SKIPPED,
        ):
            item.status = status
            texts[status] = gui.status_text(item)
        self.assertEqual(
            texts,
            {
                WAITING: "· Waiting",
                MIGRATING: "↻ Migrating",
                MIGRATED: "✓ Migrated",
                FAILED: "✗ Failed",
                SKIPPED: "– Skipped",
            },
        )

    def test_warnings(self):
        item = Item("lab", "project", "/lab", status=MIGRATED)
        item.report.warning("a")
        self.assertEqual(gui.status_text(item), "⚠ 1 warning")
        item.report.warning("b")
        self.assertEqual(gui.status_text(item), "⚠ 2 warnings")

    def test_default_output(self):
        self.assertEqual(
            gui.default_output(),
            os.path.join(tempfile.gettempdir(), "virtualbricks-migration"),
        )


class TestForm(GuiTestCase):

    def test_initial_state(self):
        window = self.make_window(
            workspace=self.workspace, settings_file="/x.conf"
        )
        self.assertEqual(window.workspace_entry.get_text(), self.workspace)
        self.assertEqual(window.settings_entry.get_text(), "/x.conf")
        self.assertEqual(window.output_entry.get_text(), gui.default_output())
        self.assertTrue(window.folder_radio.get_active())
        self.assertFalse(window.save_button.get_sensitive())
        self.assertFalse(window.fixed)
        window.show()
        self.assertIsNone(window.running)

    def test_in_place_disables_the_folder(self):
        window = self.form_window()
        box = window.output_entry.get_parent()
        window.in_place_radio.set_active(True)
        self.assertFalse(box.get_sensitive())
        window.folder_radio.set_active(True)
        self.assertTrue(box.get_sensitive())

    def test_make_migration(self):
        window = self.form_window()
        migration = window.make_migration(dry_run=True)
        self.assertIsInstance(migration.target, Folder)
        self.assertEqual(migration.target.folder, self.output)
        self.assertTrue(migration.dry_run)
        self.assertEqual(
            [item.name for item in migration.items], ["lab", "wan"]
        )
        window.in_place_radio.set_active(True)
        migration = window.make_migration(dry_run=False)
        self.assertIsInstance(migration.target, InPlace)
        self.assertEqual(migration.workspace, self.workspace)

    def test_make_migration_with_settings(self):
        old = write_settings(os.path.join(self.root, "vb.conf"), "/srv/vb")
        window = self.form_window()
        window.settings_entry.set_text(old)
        migration = window.make_migration(dry_run=True)
        self.assertEqual(migration.items[0].kind, "settings")

    def test_invalid_form(self):
        window = self.form_window()
        window.workspace_entry.set_text(os.path.join(self.root, "missing"))
        error = self.assertRaises(ValueError, window.make_migration, True)
        self.assertEqual(str(error), f"{self.root}/missing is not a folder")
        window.workspace_entry.set_text(self.workspace)
        window.settings_entry.set_text(self.root)
        error = self.assertRaises(ValueError, window.make_migration, True)
        self.assertEqual(str(error), f"{self.root} is not a file")
        window.settings_entry.set_text("")
        window.output_entry.set_text(self.workspace)
        error = self.assertRaises(ValueError, window.make_migration, True)
        self.assertEqual(
            str(error), f"{self.workspace} must be a new or empty folder"
        )
        window.output_entry.set_text(write(os.path.join(self.root, "f"), ""))
        self.assertRaises(ValueError, window.make_migration, True)

    def test_invalid_form_is_shown(self):
        window = self.form_window()
        window.workspace_entry.set_text("")
        self.assertIsNone(window.on_check_clicked(None))
        self.assertEqual(self.messages(window), " is not a folder")

    def test_choose_a_path(self):
        window = self.form_window()
        button = window.workspace_entry.get_parent().get_children()[1]
        self.chooser.response = Gtk.ResponseType.OK
        self.chooser.filename = "/chosen"
        button.clicked()
        dialog = self.chooser.instances[-1]
        self.assertEqual(dialog.action, Gtk.FileChooserAction.SELECT_FOLDER)
        self.assertEqual(dialog.initial, self.workspace)
        self.assertTrue(dialog.destroyed)
        self.assertEqual(window.workspace_entry.get_text(), "/chosen")

    def test_choose_a_path_cancelled(self):
        window = self.form_window()
        button = window.settings_entry.get_parent().get_children()[1]
        self.chooser.response = Gtk.ResponseType.CANCEL
        button.clicked()
        dialog = self.chooser.instances[-1]
        self.assertEqual(dialog.action, Gtk.FileChooserAction.OPEN)
        self.assertIsNone(dialog.initial)
        self.assertEqual(window.settings_entry.get_text(), "")


class TestRun(GuiTestCase):

    def test_fill(self):
        window = self.form_window()
        window.fill(window.make_migration(dry_run=True))
        self.assertEqual(
            self.rows(window),
            [("lab", "—", "· Waiting"), ("wan", "—", "· Waiting")],
        )
        self.assertEqual(window.progress.get_text(), "0 of 2")
        self.assertEqual(self.messages(window), "lab\nNo messages.\n")

    def test_fill_nothing(self):
        window = self.form_window()
        window.fill(Migration(self.output, Folder(self.output)))
        self.assertEqual(self.messages(window), "There is nothing to migrate.")
        self.assertEqual(window.progress.get_fraction(), 1.0)

    @defer.inlineCallbacks
    def test_check(self):
        window = self.form_window()
        running = window.on_check_clicked(None)
        self.assertFalse(window.form.get_sensitive())
        self.assertFalse(window.migrate_button.get_sensitive())
        migration = yield running
        self.assertTrue(migration.dry_run)
        self.assertFalse(os.path.exists(self.output))
        self.assertEqual(
            self.rows(window),
            [("lab", "3", "⚠ 1 warning"), ("wan", "1", "✓ Migrated")],
        )
        self.assertEqual(
            window.progress.get_text(), "2 of 2 projects migrated."
        )
        self.assertTrue(window.form.get_sensitive())
        self.assertTrue(window.check_button.get_sensitive())
        self.assertTrue(window.migrate_button.get_sensitive())
        self.assertTrue(window.save_button.get_sensitive())
        self.assertIsNone(window.running)
        # the form window doesn't log
        self.assertEqual(self.logger.events, [])

    @defer.inlineCallbacks
    def test_migrate(self):
        window = self.form_window()
        migration = yield window.on_migrate_clicked(None)
        self.assertFalse(migration.dry_run)
        self.assertTrue(
            os.path.isfile(
                os.path.join(self.output, "workspace", "lab", "project.toml")
            )
        )

    @defer.inlineCallbacks
    def test_progress_while_migrating(self):
        window = self.form_window()
        seen = []
        show_progress = window.show_progress

        def spy(current=None):
            show_progress(current)
            seen.append(window.progress.get_text())

        window.show_progress = spy
        yield window.on_check_clicked(None)
        self.assertEqual(
            seen,
            [
                "0 of 2",
                "Migrating lab · 1 of 2",
                "1 of 2",
                "Migrating wan · 2 of 2",
                "2 of 2 projects migrated.",
                "2 of 2 projects migrated.",
            ],
        )

    @defer.inlineCallbacks
    def test_messages_of_the_selected_row(self):
        window = self.form_window()
        yield window.on_check_clicked(None)
        self.assertEqual(
            self.messages(window),
            "lab\n"
            "warning  .project:2 [Image:martin] /vimages/vtatpa.martin.qcow2 "
            "not found, kept in the library\n"
            "info  .project:8 [Qemu:sender] name: it repeats the brick name, "
            "dropped\n"
            "info  .project:12 [Wirefilter:wf] became netemu\n",
        )
        window.view.get_selection().select_path(Gtk.TreePath(1))
        self.assertEqual(self.messages(window), "wan\nNo messages.\n")

    def test_message_without_place(self):
        window = self.form_window()
        migration = window.make_migration(dry_run=True)
        migration.items[0].report.error("it broke")
        window.fill(migration)
        self.assertEqual(self.messages(window), "lab\nerror  it broke\n")

    def test_skipped_items_are_not_counted(self):
        window = self.form_window()
        migration = window.make_migration(dry_run=True)
        migration.items[0].status = SKIPPED
        window.fill(migration)
        self.assertEqual(window.progress.get_text(), "0 of 1")


class TestLock(GuiTestCase):

    def in_place_window(self):
        window = self.form_window()
        window.in_place_radio.set_active(True)
        return window

    @defer.inlineCallbacks
    def test_migrate_in_place(self):
        window = self.in_place_window()
        running = window.on_migrate_clicked(None)
        self.assertFalse(lock_is_free())
        yield running
        self.assertTrue(lock_is_free())
        self.assertIsNone(window.lock)

    def test_while_virtualbricks_runs(self):
        hold_lock(self)
        window = self.in_place_window()
        self.assertIsNone(window.on_migrate_clicked(None))
        self.assertEqual(
            self.messages(window),
            "Virtualbricks is running: close it to migrate your files in "
            "place.",
        )
        self.assertIsNone(window.running)

    @defer.inlineCallbacks
    def test_check_needs_no_lock(self):
        hold_lock(self)
        yield self.in_place_window().on_check_clicked(None)

    @defer.inlineCallbacks
    def test_closed_while_migrating(self):
        window = self.in_place_window()
        running = window.on_migrate_clicked(None)
        window.window.destroy()
        yield running
        self.assertTrue(lock_is_free())


class TestReport(GuiTestCase):

    @defer.inlineCallbacks
    def test_save(self):
        window = self.form_window()
        migration = yield window.on_check_clicked(None)
        path = os.path.join(self.root, "report.txt")
        self.chooser.response = Gtk.ResponseType.OK
        self.chooser.filename = path
        window.save_button.clicked()
        dialog = self.chooser.instances[-1]
        self.assertEqual(dialog.current_name, REPORT_FILE)
        self.assertTrue(dialog.destroyed)
        with open(path) as fp:
            self.assertEqual(fp.read(), migration.text())

    def test_save_cancelled(self):
        window = self.form_window()
        before = sorted(os.listdir(self.root))
        self.chooser.response = Gtk.ResponseType.CANCEL
        window.on_save_clicked(None)
        self.assertEqual(sorted(os.listdir(self.root)), before)
        self.assertTrue(self.chooser.instances[-1].destroyed)


class TestFixedMigration(GuiTestCase):

    def migration(self):
        return Migration(self.workspace, InPlace(self.workspace))

    @defer.inlineCallbacks
    def test_runs_when_shown(self):
        window = self.make_window(migration=self.migration())
        self.assertTrue(window.fixed)
        self.assertFalse(window.form.get_sensitive())
        self.assertFalse(window.check_button.get_visible())
        self.assertFalse(window.migrate_button.get_visible())
        self.assertEqual(len(self.rows(window)), 2)
        window.show()
        running = window.running
        window.show()  # already running
        self.assertIs(window.running, running)
        migration = yield running
        self.assertTrue(
            os.path.isfile(
                os.path.join(self.workspace, "lab", locations.PROJECT_FILE)
            )
        )
        self.assertFalse(window.form.get_sensitive())
        self.assertTrue(window.save_button.get_sensitive())
        self.assertEqual(
            self.logger.formatted()[-1], "Migration: 2 of 2 projects migrated."
        )
        window.on_close_clicked(None)
        closed = yield window.closed
        self.assertIs(closed, migration)

    @defer.inlineCallbacks
    def test_close_while_running(self):
        window = self.make_window(migration=self.migration())
        window.show()
        running = window.running
        window.window.destroy()
        yield running
        self.assertTrue(window.closed.called)
        self.assertEqual(self.logger.events, [])
        # the migration stopped before the second project
        self.assertEqual(window.migration.items[1].status, WAITING)
        window.on_destroy(window.window)  # a second destroy does nothing


class TestCommand(GuiTestCase):

    def test_default_window(self):
        legacy_settings = locations.legacy_settings_file()
        window = gui.default_window()
        self.addCleanup(window.window.destroy)
        self.assertEqual(
            window.workspace_entry.get_text(),
            os.path.join(self.root, ".virtualbricks"),
        )
        self.assertEqual(window.settings_entry.get_text(), "")
        write_settings(legacy_settings, self.workspace)
        window = gui.default_window()
        self.addCleanup(window.window.destroy)
        self.assertEqual(window.workspace_entry.get_text(), self.workspace)
        self.assertEqual(window.settings_entry.get_text(), legacy_settings)

    def test_filled_window(self):
        old = write_settings(os.path.join(self.root, "vb.conf"), "/srv/vb")
        window = gui.default_window(
            workspace="/old", settings_file=old, output=self.output
        )
        self.addCleanup(window.window.destroy)
        self.assertEqual(window.workspace_entry.get_text(), "/old")
        self.assertEqual(window.settings_entry.get_text(), old)
        self.assertEqual(window.output_entry.get_text(), self.output)
        self.assertTrue(window.folder_radio.get_active())

    def test_in_place_window(self):
        window = gui.default_window(workspace=self.workspace, in_place=True)
        self.addCleanup(window.window.destroy)
        self.assertTrue(window.in_place_radio.get_active())
        self.assertEqual(window.output_entry.get_text(), gui.default_output())
        migration = window.make_migration(dry_run=True)
        self.assertIsInstance(migration.target, InPlace)
        self.assertEqual(migration.workspace, self.workspace)

    def test_run(self):
        windows = []
        options = []

        def default_window(**kwargs):
            options.append(kwargs)
            window = self.make_window()
            windows.append(window)
            return window

        class Reactor:
            stopped = False

            def run(self):
                windows[0].window.destroy()

            def stop(self):
                self.stopped = True

        reactor = Reactor()
        self.patch(gui, "default_window", default_window)
        gui.run(reactor, workspace="/old")
        self.assertEqual(options, [{"workspace": "/old"}])
        self.assertTrue(reactor.stopped)
        self.assertTrue(windows[0].closed.called)
