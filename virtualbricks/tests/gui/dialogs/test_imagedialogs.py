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
Remove an image, maybe with its file; find the file of an image; save a
disk as a new image, merge it into its image, start it over.
"""

import os

from twisted.internet import defer

from virtualbricks.config.archive import ArchiveCancelled, ArchiveError
from virtualbricks.config.images import DiskUse
from virtualbricks.config.workspace import OpenProject
from virtualbricks.engine import LocalEngine
from virtualbricks.tests import FakeLogger, FakeTrash
from virtualbricks.tests.config.test_images import INFO, FakeQemuImg
from virtualbricks.tests.gui import GuiTestCase, has_display, untranslated

if has_display:
    from gi.repository import Gtk

    from virtualbricks.gui import imageinfo
    from virtualbricks.gui.dialogs import imagedialogs
    from virtualbricks.gui.dialogs.imagedialogs import (
        FindFileDialog,
        MergeDialog,
        RemoveImageDialog,
        SaveImageDialog,
        StartOverDialog,
        disks_words,
        show_in_files,
    )


class FakeWorkspace:
    """A workspace, its trash, and the projects other than the open one."""

    def __init__(self, path, trasher=None, others=()):
        self.path = path
        self.trasher = trasher
        self.current = None
        self.others = others

    def summaries(self):
        return self.others


class FakeVM:
    def __init__(self, name):
        self.name = name


def texts(dialog):
    """The labels of a dialog, those in its boxes too, in their order."""

    def labels(box):
        for child in box.get_children():
            if isinstance(child, Gtk.Label):
                yield child.get_text()
            elif isinstance(child, Gtk.Box):
                yield from labels(child)

    return list(labels(dialog.get_content_area()))


class DialogTestCase(GuiTestCase):

    def setUp(self):
        super().setUp()
        untranslated(self)
        self.logger = FakeLogger()
        self.patch(imagedialogs, "logger", self.logger)
        self.trash = FakeTrash()
        self.workspace = FakeWorkspace(self.folder("workspace"), self.trash)
        self.shared_images = self.folder(
            os.path.join("workspace", "shared_images")
        )
        # the private copies are in the open project
        self.manager.current = OpenProject(
            self.folder(os.path.join("workspace", "lab")), None
        )

    def engine(self, **fakes):
        """The engine of the dialogs, on the workspace of the test."""

        return LocalEngine(self.factory, workspace=self.workspace, **fakes)

    def file(self, folder, name="frr.qcow2", data=b"disk"):
        path = os.path.join(folder, name)
        with open(path, "wb") as fp:
            fp.write(data)
        return path

    def vm(self, name, image, private=True):
        vm = self.factory.new_brick("qemu", name)
        vm.update_config({"hda_image": image.name, "hda_private": private})
        return vm


class TestShowInFiles(DialogTestCase):

    def test_the_folder(self):
        shown = []
        self.patch(
            imagedialogs.Gtk,
            "show_uri_on_window",
            lambda parent, uri, time: shown.append((parent, uri)),
        )
        show_in_files(None, "/lab/images/frr.qcow2")
        self.assertEqual(shown, [(None, "file:///lab/images")])

    def test_no_file_manager(self):
        def fail(parent, uri, time):
            raise RuntimeError("no handler")

        self.patch(imagedialogs.Gtk, "show_uri_on_window", fail)
        show_in_files(None, "/lab/images/frr.qcow2")
        self.assertEqual(
            self.logger.formatted(), ["Cannot show /lab/images: no handler"]
        )


class TestDisksWords(DialogTestCase):

    def test_words(self):
        self.assertEqual(disks_words([]), "No disk uses it.")
        uses = [
            DiskUse(FakeVM("r1"), "hda", True, None, None, False),
            DiskUse(FakeVM("vm"), "hdb", False, None, None, False),
        ]
        self.assertEqual(
            disks_words(uses),
            "The disks r1 (hda) and vm (hdb) will have no image."
            " The private copy stays.",
        )
        self.assertEqual(
            disks_words(uses[1:]), "The disk vm (hdb) will have no image."
        )


class TestRemove(DialogTestCase):

    def dialog(self, image):
        dialog = RemoveImageDialog(self.engine(), image)
        self.addCleanup(dialog.dialog.destroy)
        return dialog

    def test_the_disks_lose_the_image(self):
        image = self.factory.new_image("frr", self.file(self.shared_images))
        vm = self.vm("r1", image)
        dialog = self.dialog(image)
        self.assertIn(
            "The disk r1 (hda) will have no image. The private copy stays.",
            texts(dialog.dialog),
        )
        dialog.dialog.response(Gtk.ResponseType.OK)
        self.assertIsNone(self.factory.get_image("frr"))
        self.assertIsNone(vm.disk("hda").image)
        # the file stays unless asked
        self.assertTrue(os.path.exists(image.path))

    def test_the_file_to_the_trash(self):
        image = self.factory.new_image("frr", self.file(self.shared_images))
        dialog = self.dialog(image)
        self.assertEqual(
            dialog.file_check.get_label(),
            "Also move the file to the trash (4.1 KB)",
        )
        dialog.file_check.set_active(True)
        dialog.dialog.response(Gtk.ResponseType.OK)
        self.assertEqual(self.trash.trashed, [image.path])

    def test_no_trash(self):
        self.workspace.trasher = None
        image = self.factory.new_image("frr", self.file(self.shared_images))
        dialog = self.dialog(image)
        self.assertIn("there is no trash", dialog.file_check.get_label())
        dialog.file_check.set_active(True)
        dialog.remove()
        self.assertFalse(os.path.exists(image.path))

    def test_the_trash_fails(self):
        self.trash.error = OSError(13, "Permission denied")
        image = self.factory.new_image("frr", self.file(self.shared_images))
        dialog = self.dialog(image)
        dialog.file_check.set_active(True)
        dialog.remove()
        self.assertIsNone(self.factory.get_image("frr"))
        self.assertEqual(self.logger.levels(), ["error"])

    def test_a_file_outside_the_image_folder(self):
        path = self.file(self.folder("lab"))
        image = self.factory.new_image("frr", path)
        dialog = self.dialog(image)
        self.assertIsNone(dialog.file_check)
        self.assertIn(
            f"The file stays: {imageinfo.short_path(path)}",
            texts(dialog.dialog),
        )

    def test_a_file_that_other_projects_use(self):
        from virtualbricks.tests.config.test_images import FakeWorkspace

        path = self.file(self.shared_images)
        others = FakeWorkspace(
            None, ospf=[("router", path)], bgp=[("a", path), ("b", path)]
        )
        self.workspace.others = others.summaries()
        image = self.factory.new_image("frr", path)
        dialog = self.dialog(image)
        self.assertIsNone(dialog.file_check)
        self.assertIn(
            "The projects bgp and ospf use the file too: it stays.",
            texts(dialog.dialog),
        )

    def test_cancel(self):
        image = self.factory.new_image("frr", self.file(self.shared_images))
        dialog = self.dialog(image)
        dialog.dialog.response(Gtk.ResponseType.CANCEL)
        self.assertIs(self.factory.get_image("frr"), image)


class TestFindFile(DialogTestCase):

    def setUp(self):
        super().setUp()
        self.qemu_img = FakeQemuImg()
        self.image = self.factory.new_image("frr", "/gone/frr.qcow2")

    def dialog(self):
        dialog = FindFileDialog(
            self.engine(qemu_img=self.qemu_img), self.image, self.workspace
        )
        self.addCleanup(dialog.dialog.destroy)
        return dialog

    def test_a_file_to_choose(self):
        dialog = self.dialog()
        self.assertIsNone(dialog.chosen)
        self.assertFalse(dialog.use_button.get_sensitive())
        self.assertFalse(dialog.error_label.get_visible())
        self.assertIn("/gone/frr.qcow2 isn't there.", texts(dialog.dialog))
        dialog.dialog.response(Gtk.ResponseType.OK)
        self.assertEqual(self.qemu_img.calls, [])

    def test_the_file_in_the_image_folder(self):
        path = self.file(self.shared_images)
        dialog = self.dialog()
        self.assertEqual(dialog.chosen, path)
        self.assertTrue(dialog.use_button.get_sensitive())
        self.assertIn(
            "The shared images have a file of the same name.",
            texts(dialog.dialog),
        )

    def test_show(self):
        parent = Gtk.Window()
        self.addCleanup(parent.destroy)
        dialog = self.dialog()
        dialog.show(parent)
        self.assertIs(dialog.get_root_widget(), dialog.dialog)
        self.assertIs(dialog.dialog.get_transient_for(), parent)
        self.assertTrue(dialog.dialog.get_visible())

    def test_use_the_file(self):
        path = self.file(self.folder("lab"))
        self.qemu_img.infos[path] = INFO
        dialog = self.dialog()
        dialog.choose(path)
        self.assertTrue(dialog.use_button.get_sensitive())
        dialog.dialog.response(Gtk.ResponseType.OK)
        self.assertEqual(self.image.path, path)

    def test_a_file_that_cant_be_used(self):
        path = self.file(self.folder("lab"))
        self.qemu_img.failing.add((path,))
        dialog = self.dialog()
        dialog.choose(path)
        # the dialog says why
        dialog.use()
        self.assertEqual(self.image.path, "/gone/frr.qcow2")
        self.assertTrue(dialog.error_label.get_visible())
        self.assertTrue(dialog.use_button.get_sensitive())

    def test_cancel(self):
        dialog = self.dialog()
        destroyed = []
        dialog.dialog.connect("destroy", destroyed.append)
        dialog.dialog.response(Gtk.ResponseType.CANCEL)
        self.assertEqual(len(destroyed), 1)


class FakeJob:
    """A job of the archive process, that ends when told."""

    def __init__(self, *args):
        self.args = args
        self.done = defer.Deferred()
        self.cancelled = False

    def cancel(self):
        self.cancelled = True
        self.done.errback(ArchiveCancelled())


class DiskTestCase(DialogTestCase):
    """r1, whose hda has a private copy on frr."""

    def setUp(self):
        super().setUp()
        self.frr = self.factory.new_image("frr", self.file(self.shared_images))
        self.r1 = self.vm("r1", self.frr)
        self.copy = self.r1.disk("hda").get_cow_path()
        with open(self.copy, "wb") as fp:
            fp.write(b"x" * 5000)
        self.jobs = []
        self.events = []

    def start(self, *args):
        job = FakeJob(*args)
        self.jobs.append(job)
        return job

    def track(self, dialog):
        dialog.on_done = lambda: self.events.append("done")
        dialog.dialog.connect(
            "destroy", lambda widget: self.events.append("destroyed")
        )
        self.addCleanup(dialog.dialog.destroy)
        return dialog


class TestSave(DiskTestCase):

    def dialog(self):
        dialog = SaveImageDialog(
            self.factory, self.r1, "hda", self.workspace, self.start
        )
        dialog.on_saved = lambda *args: self.events.append(("saved", *args))
        return self.track(dialog)

    def test_the_name(self):
        dialog = self.dialog()
        self.assertEqual(dialog.name_entry.get_text(), "frr-r1")
        self.assertEqual(
            dialog.output(), os.path.join(self.shared_images, "frr-r1.qcow2")
        )
        self.factory.new_image("frr-r1", "/lab/other.qcow2")
        self.assertEqual(self.dialog().name_entry.get_text(), "frr-r1-2")

    def test_a_name_in_use(self):
        dialog = self.dialog()
        dialog.name_entry.set_text("frr")
        self.assertTrue(dialog.name_message.get_visible())
        self.assertFalse(dialog.action_button.get_sensitive())
        dialog.name_entry.set_text("")
        self.assertFalse(dialog.name_message.get_visible())
        self.assertFalse(dialog.action_button.get_sensitive())

    def test_not_while_it_runs(self):
        self.r1.is_running = lambda: True
        dialog = self.dialog()
        self.assertEqual(dialog.error_label.get_text(), "Stop r1 first.")
        self.assertFalse(dialog.action_button.get_sensitive())
        dialog.dialog.response(Gtk.ResponseType.OK)
        self.assertEqual(self.jobs, [])

    def test_save_and_use(self):
        dialog = self.dialog()
        dialog.dialog.response(Gtk.ResponseType.OK)
        (job,) = self.jobs
        output = os.path.join(self.shared_images, "frr-r1.qcow2")
        self.assertEqual(job.args, (self.copy, output, dialog.on_progress))
        self.assertEqual(dialog.cancel_button.get_label(), "Stop")
        self.assertFalse(dialog.action_button.get_sensitive())
        self.assertTrue(dialog.progress.get_visible())
        dialog.on_progress("save", 50, 100)
        self.assertEqual(dialog.progress.get_fraction(), 0.5)
        self.assertEqual(dialog.progress.get_text(), "50%")
        job.done.callback({"output": output, "size": 4096})
        image = self.factory.get_image("frr-r1")
        self.assertEqual(image.path, output)
        self.assertIs(self.r1.disk("hda").image, image)
        self.assertEqual(self.trash.trashed, [self.copy])
        self.assertEqual(
            self.events, [("saved", image, True), "destroyed", "done"]
        )

    def test_save_only(self):
        dialog = self.dialog()
        dialog.use_check.set_active(False)
        dialog.run()
        self.jobs[0].done.callback({"output": "/lab/frr-r1.qcow2"})
        self.assertIs(self.r1.disk("hda").image, self.frr)
        self.assertEqual(self.trash.trashed, [])

    def test_stop(self):
        dialog = self.dialog()
        dialog.run()
        dialog.dialog.response(Gtk.ResponseType.CANCEL)
        self.assertTrue(self.jobs[0].cancelled)
        self.assertEqual(dialog.error_label.get_text(), "Stopped.")
        self.assertEqual(dialog.cancel_button.get_label(), "Cancel")
        self.assertTrue(dialog.action_button.get_sensitive())
        self.assertFalse(dialog.progress.get_visible())
        self.assertEqual(self.events, [])
        # and again
        dialog.run()
        self.assertEqual(dialog.error_label.get_text(), "")
        self.assertEqual(len(self.jobs), 2)

    def test_closed_while_it_saves(self):
        dialog = self.dialog()
        dialog.run()
        dialog.dialog.response(Gtk.ResponseType.DELETE_EVENT)
        self.assertTrue(self.jobs[0].cancelled)
        self.assertEqual(self.events, ["destroyed"])

    def test_a_failure(self):
        dialog = self.dialog()
        dialog.run()
        self.jobs[0].done.errback(ArchiveError("qemu-img: No space left"))
        self.assertEqual(
            dialog.error_label.get_text(), "qemu-img: No space left"
        )
        self.assertIsNone(self.factory.get_image("frr-r1"))

    def test_cancel(self):
        dialog = self.dialog()
        dialog.dialog.response(Gtk.ResponseType.CANCEL)
        self.assertEqual(self.events, ["destroyed"])


class TestMerge(DiskTestCase):

    def dialog(self):
        return self.track(
            MergeDialog(
                self.factory, self.r1, "hda", self.workspace, self.start
            )
        )

    def test_no_other_disk(self):
        self.assertIn("No other disk uses frr.", texts(self.dialog().dialog))

    def test_the_others(self):
        from virtualbricks.tests.config.test_images import FakeWorkspace

        self.vm("r2", self.frr)
        others = FakeWorkspace(None, ospf=[("router", self.frr.path)])
        self.workspace.others = others.summaries()
        self.assertIn(
            "frr changes for all that use it too: r2 (hda) and the project"
            " ospf, as router. Their private copies may stop working.",
            texts(self.dialog().dialog),
        )

    def test_not_while_one_runs(self):
        self.vm("r2", self.frr).is_running = lambda: True
        self.vm("r3", self.frr).is_running = lambda: True
        dialog = self.dialog()
        self.assertEqual(
            dialog.error_label.get_text(), "Stop r2 and r3 first."
        )
        self.assertFalse(dialog.action_button.get_sensitive())

    def test_merge(self):
        dialog = self.dialog()
        dialog.dialog.response(Gtk.ResponseType.OK)
        (job,) = self.jobs
        self.assertEqual(job.args, (self.copy, dialog.on_progress))
        self.assertFalse(dialog.instead_button.get_sensitive())
        job.done.callback({"disk": self.copy})
        self.assertEqual(self.events, ["destroyed", "done"])

    def test_instead(self):
        shown = []
        self.patch(
            SaveImageDialog,
            "show",
            lambda dialog, parent: shown.append(dialog),
        )
        dialog = self.dialog()
        dialog.on_saved = saved = object()
        save = dialog.instead()
        self.addCleanup(save.dialog.destroy)
        self.assertEqual(shown, [save])
        self.assertIs(save.on_saved, saved)
        self.assertIs(save.on_done, dialog.on_done)
        self.assertEqual(self.events, ["destroyed"])


class TestStartOver(DiskTestCase):

    def dialog(self):
        return self.track(StartOverDialog(self.engine(), self.r1, "hda"))

    def test_to_the_trash(self):
        dialog = self.dialog()
        self.assertIn(
            "r1_hda.cow goes to the trash, with the changes it keeps, 8.2 KB;"
            " the next start makes an empty one.",
            texts(dialog.dialog),
        )
        dialog.dialog.response(Gtk.ResponseType.OK)
        self.assertEqual(self.trash.trashed, [self.copy])
        self.assertEqual(self.events, ["done", "destroyed"])

    def test_without_a_trash(self):
        self.workspace.trasher = None
        dialog = self.dialog()
        self.assertIn("is deleted for good", texts(dialog.dialog)[1])
        dialog.start_over()
        self.assertFalse(os.path.exists(self.copy))

    def test_not_while_it_runs(self):
        self.r1.is_running = lambda: True
        dialog = self.dialog()
        self.assertIn("Stop r1 first.", texts(dialog.dialog))
        self.assertFalse(dialog.action_button.get_sensitive())

    def test_a_failure(self):
        self.trash.error = OSError(13, "Permission denied")
        dialog = self.dialog()
        dialog.start_over()
        self.assertEqual(self.logger.levels(), ["error"])
        self.assertEqual(self.events, [])

    def test_cancel(self):
        self.dialog().dialog.response(Gtk.ResponseType.CANCEL)
        self.assertTrue(os.path.exists(self.copy))
        self.assertEqual(self.events, ["destroyed"])
