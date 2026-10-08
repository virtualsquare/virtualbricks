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

"""The export of a project: the choices, and the job it runs."""

import os

from twisted.internet import defer

from virtualbricks import locations
from virtualbricks.config.archive import ArchiveCancelled
from virtualbricks.config.archive import ArchiveError
from virtualbricks.tests import FakeLogger
from virtualbricks.tests.gui import GuiTestCase, has_display

if has_display:
    from virtualbricks.gui.dialogs import exportproject


class FakeJob:
    def __init__(self):
        self.done = defer.Deferred()
        self.cancelled = False

    def cancel(self):
        self.cancelled = True
        self.done.errback(ArchiveCancelled())


class ExportTestCase(GuiTestCase):

    def setUp(self):
        super().setUp()
        self.logger = FakeLogger()
        self.patch(exportproject, "logger", self.logger)
        self.patch(exportproject, "find_qemu_img", lambda: "/usr/bin/qemu-img")
        self.manager.create("lab", "A lab")
        self.project = self.manager.project_path("lab")
        for name, size in (
            ("notes.txt", 100),
            ("sub/more.txt", 10),
            ("vm_hda.cow", 5000),
            (locations.LEGACY_PROJECT_FILE, 1),
            (".images/old", 1),
        ):
            self.write(os.path.join(self.project, name), size)
        self.deb = self.write(os.path.join(self.root, "deb.qcow2"), 8000)
        self.runs = []

    def write(self, path, size):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as fp:
            fp.write(b"x" * size)
        return path

    def run_export(
        self, project, output, files, images, on_progress, qemu_img
    ):
        job = FakeJob()
        job.on_progress = on_progress
        job.qemu_img = qemu_img
        self.runs.append((project, output, files, images, job))
        return job

    def dialog(self, images=None):
        if images is None:
            images = [("deb", self.deb), ("gone", "/nowhere")]
        dialog = exportproject.ExportProjectDialog(
            self.project, images, run=self.run_export
        )
        self.addCleanup(self.destroy, dialog)
        dialog.on_changed()
        return dialog

    def destroy(self, dialog):
        if not dialog.destroyed:
            dialog.window.destroy()


class TestChoices(ExportTestCase):

    def test_the_files_of_the_folder(self):
        required, disks, others = exportproject.project_files(self.project)
        self.assertEqual(required, ["README.md", "project.toml"])
        self.assertEqual(disks, ["vm_hda.cow"])
        self.assertEqual(others, ["notes.txt", "sub/more.txt"])

    def test_defaults(self):
        dialog = self.dialog()
        self.assertEqual(
            dialog.filename_entry.get_text(),
            os.path.join(os.path.expanduser("~"), "lab.vbp"),
        )
        self.assertFalse(dialog.project_check.get_sensitive())
        self.assertTrue(dialog.disks_check.get_active())
        self.assertFalse(dialog.images_check.get_active())
        # the images that aren't here are left out
        self.assertEqual(dialog.images, [("deb", self.deb)])
        self.assertEqual(
            dialog.files(),
            [
                "README.md",
                "project.toml",
                "vm_hda.cow",
                "notes.txt",
                "sub/more.txt",
            ],
        )
        self.assertEqual(dialog.chosen_images(), [])
        self.assertIn("before compression", dialog.total_label.get_text())
        self.assertTrue(dialog.export_button.get_sensitive())

    def test_choices(self):
        dialog = self.dialog()
        dialog.disks_check.set_active(False)
        dialog.images_check.set_active(True)
        dialog.other_checks["notes.txt"].set_active(False)
        self.assertEqual(
            dialog.files(), ["README.md", "project.toml", "sub/more.txt"]
        )
        self.assertEqual(dialog.chosen_images(), [("deb", self.deb)])

    def test_nothing_to_choose(self):
        empty = self.manager.project_path("empty")
        self.manager.create("empty")
        dialog = exportproject.ExportProjectDialog(
            empty, [], run=self.run_export
        )
        self.addCleanup(dialog.window.destroy)
        self.assertFalse(dialog.disks_check.get_visible())
        self.assertFalse(dialog.images_check.get_visible())
        self.assertFalse(dialog.others_expander.get_visible())

    def test_the_file_name(self):
        dialog = self.dialog()
        dialog.filename_entry.set_text(os.path.join(self.root, "out"))
        self.assertEqual(dialog.output(), os.path.join(self.root, "out.vbp"))
        dialog.filename_entry.set_text("")
        self.assertFalse(dialog.export_button.get_sensitive())
        dialog.filename_entry.set_text("/nowhere/out.vbp")
        self.assertFalse(dialog.export_button.get_sensitive())
        self.assertIn("doesn't exist", dialog.form_error.get_text())
        folder = os.path.join(self.root, "folder.vbp")
        os.makedirs(folder)
        dialog.filename_entry.set_text(folder)
        self.assertIn("is a folder", dialog.form_error.get_text())

    def test_choose(self):
        dialog = self.dialog()
        answers = [None, os.path.join(self.root, "chosen")]
        self.patch(dialog, "choose_file", lambda: answers.pop(0))
        dialog.choose_button.clicked()
        self.assertTrue(dialog.filename_entry.get_text().endswith("lab.vbp"))
        dialog.choose_button.clicked()
        self.assertEqual(
            dialog.filename_entry.get_text(),
            os.path.join(self.root, "chosen.vbp"),
        )


class TestExport(ExportTestCase):

    def start(self, dialog=None):
        dialog = dialog or self.dialog()
        dialog.filename_entry.set_text(os.path.join(self.root, "out.vbp"))
        dialog.export_button.clicked()
        return dialog, self.runs[-1][-1]

    def test_export(self):
        dialog, job = self.start()
        project, output, files, images, job = self.runs[0]
        self.assertEqual(project, self.project)
        self.assertEqual(output, os.path.join(self.root, "out.vbp"))
        self.assertIn("vm_hda.cow", files)
        self.assertEqual(images, [])
        self.assertEqual(job.qemu_img, "/usr/bin/qemu-img")
        self.assertEqual(dialog.stack.get_visible_child_name(), "running")
        self.assertEqual(dialog.cancel_button.get_label(), "Stop")
        job.on_progress("pack", 10, 100)
        self.assertEqual(
            dialog.step_label.get_text(), "Compressing the disks…"
        )
        job.on_progress("write", 500, 1000)
        self.assertEqual(dialog.step_label.get_text(), "Writing the archive…")
        self.assertEqual(dialog.progress_bar.get_fraction(), 0.5)
        # a little more than the data: the headers
        job.on_progress("write", 1200, 1000)
        self.assertEqual(dialog.progress_bar.get_fraction(), 1.0)
        job.on_progress("write", 0, 0)
        report = [["warning", "stored as it is: no qemu-img", "vm_hda.cow"]]
        job.done.callback(
            {"output": output, "size": 2_500_000, "report": report}
        )
        self.assertEqual(dialog.stack.get_visible_child_name(), "done")
        self.assertIn("2.5 MB", dialog.done_label.get_text())
        # the report goes to the logs
        self.assertEqual(self.logger.levels(), ["info", "warn"])
        dialog.close_button.clicked()
        self.assertTrue(dialog.destroyed)

    def test_replace_an_archive(self):
        dialog = self.dialog()
        self.write(os.path.join(self.root, "out.vbp"), 1)
        answers = [False, True]
        self.patch(dialog, "confirm_overwrite", lambda path: answers.pop(0))
        dialog.filename_entry.set_text(os.path.join(self.root, "out.vbp"))
        dialog.export_button.clicked()
        self.assertEqual(self.runs, [])
        dialog.export_button.clicked()
        self.assertEqual(len(self.runs), 1)

    def test_stop(self):
        dialog, job = self.start()
        dialog.cancel_button.clicked()
        self.assertTrue(job.cancelled)
        self.assertEqual(dialog.stack.get_visible_child_name(), "form")

    def test_failure(self):
        dialog, job = self.start()
        job.done.errback(ArchiveError("disk full"))
        self.assertIn("disk full", dialog.done_label.get_text())
        self.assertEqual(self.logger.levels(), ["error"])

    def test_the_export_goes_on_without_the_window(self):
        dialog, job = self.start()
        dialog.window.destroy()
        self.assertFalse(job.cancelled)
        job.on_progress("write", 1, 2)
        job.done.callback({"output": "/out.vbp", "size": 1, "report": []})
        self.assertEqual(self.logger.levels(), ["info"])
        dialog, job = self.start(self.dialog())
        dialog.window.destroy()
        job.done.errback(ArchiveError("disk full"))
        dialog, job = self.start(self.dialog())
        dialog.window.destroy()
        job.cancel()

    def test_cancel_closes(self):
        dialog = self.dialog()
        closed = []
        dialog.show()
        dialog.window.connect("destroy", lambda window: closed.append(True))
        dialog.cancel_button.clicked()
        self.assertEqual(closed, [True])

    def test_no_file_name(self):
        dialog = self.dialog()
        dialog.filename_entry.set_text(" ")
        dialog.on_export_clicked(dialog.export_button)
        self.assertEqual(self.runs, [])


class TestHelpers(GuiTestCase):

    def test_names_and_sizes(self):
        self.assertEqual(exportproject.archive_filename("a"), "a.vbp")
        self.assertEqual(exportproject.archive_filename("a.vbp"), "a.vbp")
        self.assertEqual(exportproject.human_size(999), "999 B")
        self.assertEqual(exportproject.usage("/nowhere"), 0)
