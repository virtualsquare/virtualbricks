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

"""The import window: one page, fed by the archive process."""

import os

from twisted.internet import defer

from virtualbricks import locations

from virtualbricks.config import (
    ArchiveCancelled,
    ArchiveContents,
    ArchiveError,
    ArchiveMember,
    ImportResult,
    Report,
    set_app_setting,
)
from virtualbricks.tests import FakeLogger
from virtualbricks.tests.gui import GuiTestCase, has_display

if has_display:
    from virtualbricks.gui.windows import importdialog

    find_qemu_img = importdialog.find_qemu_img


class FakeJob:
    def __init__(self):
        self.done = defer.Deferred()
        self.cancelled = False

    def cancel(self):
        self.cancelled = True
        if not self.done.called:
            self.done.errback(ArchiveCancelled())


def data(**images):
    return {
        "format": 1,
        "settings": {"qemupath": "/opt/elsewhere/qemu"},
        "images": {name: {"path": path} for name, path in images.items()},
        "events": {"ev": {}},
        "bricks": {
            "vm": {
                "type": "qemu",
                "disks": {"hda": {"image": "deb", "private": True}},
            },
            "sw1": {"type": "switch"},
            "sw2": {"type": "switch"},
        },
    }


class ImportTestCase(GuiTestCase):

    def setUp(self):
        super().setUp()
        self.logger = FakeLogger()
        self.patch(importdialog, "logger", self.logger)
        self.patch(importdialog, "find_qemu_img", lambda: "/usr/bin/qemu-img")
        # as short as a real one: the test's leaves no room to the bricks;
        # never created
        self.patch(locations, "runtime_dir", lambda: "/run/vb-tests")
        self.patch(locations, "ensure_private_dir", lambda path: path)
        self.ours = self.folder("bin")
        set_app_setting("qemupath", self.ours)
        set_app_setting("vdepath", self.ours)
        self.inspected = []
        self.imports = []
        self.dialog = importdialog.ImportDialog(
            self.factory, inspect=self.inspect, run=self.run_import
        )
        self.addCleanup(self.destroy)
        self.archive = os.path.join(self.root, "ospf-lab.vbp")

    def destroy(self):
        if not self.dialog.destroyed:
            self.dialog.window.destroy()

    def inspect(self, path, on_head, on_progress):
        job = FakeJob()
        job.on_head = on_head
        job.on_progress = on_progress
        self.inspected.append((path, job))
        return job

    def run_import(self, plan, workspace, on_progress, qemu_img):
        job = FakeJob()
        job.on_progress = on_progress
        self.imports.append((plan, workspace, qemu_img, job))
        return job

    def contents(self, complete=True, in_archive=("deb",), **images):
        images = images or {"deb": "/other/deb.qcow2"}
        members = [ArchiveMember("project.toml", 10, "project")]
        for name in in_archive:
            members.append(ArchiveMember(f".images/{name}", 2000, "image"))
        return ArchiveContents(
            self.archive,
            data(**images),
            "OSPF between routers\n\nDetails.",
            members,
            complete,
        )

    def read(self, contents=None):
        self.dialog.choose(self.archive)
        path, job = self.inspected[-1]
        job.done.callback(contents or self.contents())
        return job

    def rows(self):
        return self.dialog.rows


class TestReading(ImportTestCase):

    def test_first_the_file(self):
        self.assertEqual(self.dialog.page(), "choose")
        self.assertFalse(self.dialog.import_button.get_sensitive())

    def test_the_file_button(self):
        class Button:
            def __init__(self, filename):
                self.filename = filename

            def get_filename(self):
                return self.filename

        self.dialog.on_file_set(Button(None))
        self.assertEqual(self.inspected, [])
        self.dialog.on_file_set(Button(self.archive))
        self.assertEqual(self.inspected[0][0], self.archive)

    def test_reading(self):
        self.dialog.choose(self.archive)
        self.assertEqual(self.dialog.page(), "reading")
        path, job = self.inspected[0]
        job.on_progress("read", 500_000, 2_000_000)
        self.assertEqual(self.dialog.reading_bar.get_fraction(), 0.25)
        self.assertEqual(
            self.dialog.reading_bar.get_text(), "500.0 KB / 2.0 MB"
        )
        job.on_progress("read", 0, 0)
        self.assertEqual(self.dialog.reading_bar.get_fraction(), 0.0)

    def test_the_form(self):
        self.read()
        dialog = self.dialog
        self.assertEqual(dialog.page(), "form")
        self.assertEqual(dialog.name_entry.get_text(), "ospf-lab")
        self.assertEqual(
            dialog.description_label.get_text(), "OSPF between routers"
        )
        self.assertEqual(
            dialog.facts_label.get_text(), "1 qemu · 2 switch · 1 event"
        )
        self.assertFalse(dialog.scan_box.get_visible())
        [row] = self.rows()
        self.assertEqual(row.used_label.get_text(), "Used by vm.hda")
        self.assertTrue(row.copy_button.get_active())
        library = os.path.join(self.manager.path, "vimages")
        self.assertEqual(
            row.path_label.get_text(),
            f"Copied to {library}/deb.qcow2",
        )
        self.assertEqual(
            row.copy_button.get_tooltip_text(), "2.0 KB in the archive"
        )
        self.assertEqual(list(dialog.machine_checks), ["qemupath"])
        self.assertTrue(dialog.machine_checks["qemupath"].get_active())
        self.assertTrue(dialog.import_button.get_sensitive())
        self.assertFalse(dialog.problems_label.get_visible())

    def test_no_images_and_no_description(self):
        contents = self.contents(in_archive=())
        contents.data["images"] = {}
        contents.data["settings"] = {}
        contents.description = ""
        self.read(contents)
        self.assertFalse(self.dialog.images_frame.get_visible())
        self.assertTrue(self.dialog.no_images_label.get_visible())
        self.assertFalse(self.dialog.description_label.get_visible())
        self.assertFalse(self.dialog.paths_heading.get_visible())

    def test_the_head_first(self):
        self.dialog.choose(self.archive)
        path, job = self.inspected[0]
        job.on_head(self.contents(complete=False, in_archive=()))
        self.assertEqual(self.dialog.page(), "form")
        self.assertTrue(self.dialog.scan_box.get_visible())
        [row] = self.rows()
        self.assertTrue(row.copy_button.get_sensitive())
        self.assertIn("Looking in the archive", row.path_label.get_text())
        # a second head changes nothing
        job.on_head(self.contents(complete=False, in_archive=()))
        self.assertEqual(len(self.rows()), 1)
        # the end of the archive: deb isn't there
        job.done.callback(self.contents(in_archive=()))
        self.assertFalse(self.dialog.scan_box.get_visible())
        self.assertFalse(row.copy_button.get_sensitive())
        self.assertEqual(
            row.copy_button.get_tooltip_text(), "Not in the archive"
        )
        self.assertTrue(row.skip_button.get_active())

    def test_reading_fails(self):
        self.dialog.choose(self.archive)
        path, job = self.inspected[0]
        job.done.errback(ArchiveError("not an archive"))
        self.assertEqual(self.dialog.page(), "failed")
        self.assertIn("not an archive", self.dialog.error_label.get_text())
        self.assertTrue(self.dialog.close_button.get_visible())

    def test_another_file(self):
        self.dialog.choose(self.archive)
        first = self.inspected[0][1]
        self.dialog.choose(self.archive)
        self.assertTrue(first.cancelled)
        # the first job's end is ignored
        self.assertEqual(self.dialog.page(), "reading")

    def test_late_results_after_the_window_is_gone(self):
        self.dialog.choose(self.archive)
        job = self.inspected[0][1]
        self.dialog.window.destroy()
        self.assertTrue(job.cancelled)
        job.on_head(self.contents())


class TestChoices(ImportTestCase):

    def test_the_name(self):
        self.read()
        dialog = self.dialog
        dialog.name_entry.set_text(".lab")
        self.assertEqual(dialog.plan.name, ".lab")
        self.assertEqual(
            dialog.name_message.get_text(), "The name cannot start with a dot"
        )
        self.assertFalse(dialog.import_button.get_sensitive())
        self.manager.create("taken")
        dialog.name_entry.set_text("taken")
        self.assertEqual(
            dialog.name_message.get_text(),
            "A project with this name already exists",
        )
        dialog.name_entry.set_text("lab")
        self.assertFalse(dialog.name_message.get_visible())
        self.assertTrue(dialog.import_button.get_sensitive())

    def test_leave_unset_and_copy_again(self):
        self.read()
        [row] = self.rows()
        copied = row.image.path
        row.skip_button.set_active(True)
        self.assertEqual(row.image.choice, "skip")
        self.assertIn("Unset", row.path_label.get_text())
        row.copy_button.set_active(True)
        self.assertEqual((row.image.choice, row.image.path), ("copy", copied))

    def test_use_a_file(self):
        self.read()
        [row] = self.rows()
        mine = os.path.join(self.folder("images"), "mine.qcow2")
        with open(mine, "w"):
            pass
        answers = [None, mine]
        self.patch(self.dialog, "choose_image", lambda image: answers.pop(0))
        # cancelled: the choice stays
        row.use_button.set_active(True)
        self.assertEqual(row.image.choice, "copy")
        self.assertTrue(row.copy_button.get_active())
        row.use_button.set_active(True)
        self.assertEqual((row.image.choice, row.image.path), ("use", mine))
        self.assertEqual(row.path_label.get_text(), f"Uses {mine}")
        self.assertTrue(self.dialog.import_button.get_sensitive())
        # and the file goes away
        os.remove(mine)
        self.dialog.check()
        self.assertFalse(self.dialog.import_button.get_sensitive())
        self.assertIn("doesn't exist", self.dialog.problems_label.get_text())
        # copying again takes a free name in the library
        row.copy_button.set_active(True)
        self.assertEqual(
            row.image.path,
            os.path.join(self.manager.path, "vimages", "deb.qcow2"),
        )

    def test_machine_paths_and_open(self):
        self.read()
        plan = self.dialog.plan
        self.dialog.machine_checks["qemupath"].set_active(False)
        self.assertFalse(plan.machine_paths[0].use_ours)
        self.dialog.open_check.set_active(False)
        self.assertFalse(plan.open)


class TestImport(ImportTestCase):

    def start(self, contents=None):
        self.read(contents)
        self.dialog.import_button.clicked()
        plan, workspace, qemu_img, job = self.imports[-1]
        return plan, job

    def test_import(self):
        plan, job = self.start()
        self.assertIs(plan, self.dialog.plan)
        self.assertEqual(self.imports[0][2], "/usr/bin/qemu-img")
        self.assertEqual(self.dialog.page(), "running")
        self.assertEqual(self.dialog.cancel_button.get_label(), "Stop")
        self.assertFalse(self.dialog.import_button.get_visible())
        job.on_progress("extract", 1000, 4000)
        self.assertEqual(
            self.dialog.step_label.get_text(), "Extracting the archive"
        )
        self.assertEqual(self.dialog.run_bar.get_fraction(), 0.25)
        job.on_progress("other", 0, 0)
        self.assertEqual(self.dialog.step_label.get_text(), "other")
        # the process made the project, and the window opens it
        self.manager.create("ospf-lab")
        report = Report()
        report.warning("left unset", "images.deb")
        job.done.callback(ImportResult("ospf-lab", report))
        self.assertEqual(self.dialog.page(), "done")
        self.assertEqual(
            self.dialog.done_label.get_text(), 'Imported as "ospf-lab".'
        )
        self.assertEqual(self.manager.current.name, "ospf-lab")
        [row] = self.dialog.warnings_list.get_children()
        self.assertTrue(self.dialog.warnings_frame.get_visible())
        self.assertIn('Project imported as "{name}"', self.logger.events[0])
        self.assertTrue(self.dialog.close_button.get_visible())
        self.dialog.close_button.clicked()
        self.assertTrue(self.dialog.destroyed)

    def test_import_without_opening(self):
        self.read()
        self.dialog.open_check.set_active(False)
        self.dialog.import_button.clicked()
        job = self.imports[0][3]
        job.done.callback(ImportResult("ospf-lab", Report()))
        self.assertIsNone(self.manager.current)
        self.assertFalse(self.dialog.warnings_frame.get_visible())

    def test_the_project_cannot_be_opened(self):
        plan, job = self.start()
        job.done.callback(ImportResult("gone", Report()))
        [row] = self.dialog.warnings_list.get_children()
        self.assertEqual(self.logger.levels()[-1], "error")

    def test_import_during_the_scan(self):
        self.dialog.choose(self.archive)
        inspection = self.inspected[0][1]
        inspection.on_head(self.contents(complete=False, in_archive=()))
        self.dialog.import_button.clicked()
        self.assertTrue(inspection.cancelled)
        plan = self.imports[0][0]
        self.assertFalse(plan.images[0].known)
        self.assertEqual(self.dialog.page(), "running")

    def test_import_waits_for_a_good_plan(self):
        self.read()
        self.dialog.name_entry.set_text("")
        self.dialog.on_import_clicked(self.dialog.import_button)
        self.assertEqual(self.imports, [])

    def test_stop(self):
        plan, job = self.start()
        self.dialog.cancel_button.clicked()
        self.assertTrue(job.cancelled)
        self.assertEqual(self.dialog.page(), "form")
        self.assertEqual(self.dialog.cancel_button.get_label(), "Cancel")

    def test_failure(self):
        plan, job = self.start()
        job.done.errback(ArchiveError("disk full"))
        self.assertEqual(self.dialog.page(), "failed")
        self.assertEqual(self.dialog.error_label.get_text(), "disk full")
        self.assertEqual(self.logger.levels(), ["error"])

    def test_the_import_goes_on_without_the_window(self):
        plan, job = self.start()
        self.dialog.window.destroy()
        self.assertFalse(job.cancelled)
        job.on_progress("extract", 1, 2)
        self.manager.create("ospf-lab")
        job.done.callback(ImportResult("ospf-lab", Report()))
        self.assertIn('Project imported as "{name}"', self.logger.events[0])
        self.assertEqual(self.manager.current.name, "ospf-lab")

    def test_failures_without_the_window(self):
        plan, job = self.start()
        self.dialog.window.destroy()
        job.done.errback(ArchiveError("disk full"))
        self.assertEqual(self.logger.levels(), ["error"])
        plan, job = self.start_again()
        self.dialog.window.destroy()
        job.cancel()

    def start_again(self):
        self.dialog = importdialog.ImportDialog(
            self.factory, inspect=self.inspect, run=self.run_import
        )
        return self.start()

    def test_cancel_closes(self):
        self.dialog.cancel_button.clicked()
        self.assertTrue(self.dialog.destroyed)


class TestHelpers(ImportTestCase):

    def test_sizes(self):
        size = importdialog.human_size
        self.assertEqual(size(999), "999 B")
        self.assertEqual(size(1500), "1.5 KB")
        self.assertEqual(size(3_000_000_000_000), "3000.0 GB")

    def test_facts(self):
        self.assertEqual(importdialog.facts({}), "No bricks")
        self.assertEqual(
            importdialog.facts({"bricks": "x", "events": {"a": {}, "b": {}}}),
            "2 events",
        )

    def test_find_qemu_img(self):
        from virtualbricks import spawn

        def missing(name):
            raise FileNotFoundError(name)

        self.patch(spawn, "abspath_qemu", missing)
        self.assertEqual(find_qemu_img(), "")
        self.patch(spawn, "abspath_qemu", lambda name: "/usr/bin/" + name)
        self.assertEqual(find_qemu_img(), "/usr/bin/qemu-img")
