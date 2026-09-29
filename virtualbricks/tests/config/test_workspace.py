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

"""The workspace: listing, names, changing projects, the open project."""

import os
import shutil
import subprocess
import sys
import time

from twisted.trial import unittest

from virtualbricks import errors, locations
from virtualbricks.config.projectfile import ProjectFormatError
from virtualbricks.config.settings import (
    current_project,
    project_settings,
    set_setting,
)
from virtualbricks.config.tomlfile import dump_toml, load_toml
from virtualbricks.config import workspace
from virtualbricks.config.projectfile import FORMAT
from virtualbricks.config.workspace import (
    DiskUsage,
    ImageSummary,
    OpenProject,
    Workspace,
)
from virtualbricks.config.settings import set_current_project
from virtualbricks.tests import FakeLogger, FakeTrash, isolate, make_factory
from virtualbricks.tests import reset_settings

# 28 bytes, as /run/user/1000/virtualbricks: a project name of 40 bytes
# leaves 18 bytes to the names of its bricks.
RUNTIME = "/run/user/1000/virtualbricks"
MiB = 1 << 20


class WorkspaceTestCase(unittest.TestCase):

    def setUp(self):
        self.root = isolate(self)
        reset_settings(self)
        self.path = os.path.join(self.root, "workspace")
        self.projects = Workspace(self.path)
        self.factory = make_factory()
        self.logger = FakeLogger()
        self.patch(workspace, "logger", self.logger)

    def project_file(self, name):
        return os.path.join(self.path, name, locations.PROJECT_FILE)

    def write(self, name, data):
        dump_toml(data, self.project_file(name))

    def file(self, *segments, text=""):
        path = os.path.join(self.path, *segments)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fp:
            fp.write(text)
        return path

    def set_mtime(self, name, when):
        os.utime(self.project_file(name), (when, when))

    def fixed_runtime_dir(self):
        self.patch(locations, "runtime_dir", lambda: RUNTIME)


class TestPaths(WorkspaceTestCase):

    def test_the_setting_unless_given(self):
        self.assertEqual(self.projects.path, self.path)
        set_setting("workspace", "/srv/labs")
        self.assertEqual(Workspace().path, "/srv/labs")
        self.assertEqual(Workspace().project_path("lab"), "/srv/labs/lab")

    def test_the_shared_workspace(self):
        from virtualbricks.config.workspace import projects

        self.assertIsInstance(projects, Workspace)

    def test_a_folder_instead_of_the_setting(self):
        projects = Workspace()
        projects.path = "/srv/labs"
        set_setting("workspace", "/home/alice/labs")
        self.assertEqual(projects.path, "/srv/labs")
        self.assertEqual(projects.project_path("lab"), "/srv/labs/lab")
        projects.path = None
        self.assertEqual(projects.path, "/home/alice/labs")

    def test_another_folder_forgets_the_summaries(self):
        self.projects.create("lab")
        self.assertEqual(len(self.projects.summaries()), 1)
        self.projects.path = os.path.join(self.root, "other")
        self.assertEqual(self.projects._summaries, {})
        self.assertEqual(self.projects.summaries(), [])


class TestNames(WorkspaceTestCase):

    def test_no_workspace(self):
        self.assertEqual(self.projects.names(), [])
        self.assertEqual(self.projects.summaries(), [])

    def test_only_folders_with_a_project_file(self):
        self.projects.create("b")
        self.projects.create("a")
        os.makedirs(os.path.join(self.path, "no-file"))
        self.file("a-file")
        self.file(".importing-lab-x", locations.PROJECT_FILE)
        self.assertEqual(self.projects.names(), ["a", "b"])
        self.assertTrue(self.projects.exists("a"))
        self.assertFalse(self.projects.exists("no-file"))
        self.assertFalse(self.projects.exists(".."))
        self.assertFalse(self.projects.exists(""))

    def test_check_name(self):
        check = self.projects.check_name
        self.assertIsNone(check("lab"))
        self.assertEqual(check(""), "The name is empty")
        self.assertEqual(check("a/b"), 'The name cannot contain "/"')
        self.assertEqual(check(".lab"), "The name cannot start with a dot")
        self.assertIsNone(check("x" * 40))
        self.assertEqual(
            check("x" * 41), "The name is 41 bytes long, at most 40"
        )
        # bytes, not characters
        self.assertIsNone(check("è" * 20))
        self.assertEqual(
            check("è" * 21), "The name is 42 bytes long, at most 40"
        )

    def test_check_a_name_in_use(self):
        self.projects.create("lab")
        os.makedirs(os.path.join(self.path, "folder"))
        message = "A project with this name already exists"
        self.assertEqual(self.projects.check_name("lab"), message)
        self.assertEqual(self.projects.check_name("folder"), message)
        # a project keeps its own name
        self.assertIsNone(self.projects.check_name("lab", renaming="lab"))

    def test_the_bricks_must_fit_in_the_socket_paths(self):
        self.fixed_runtime_dir()
        self.assertEqual(
            locations.brick_name_room(os.path.join(RUNTIME, "x" * 40)), 18
        )
        check = self.projects.check_name
        self.assertIsNone(check("x" * 40, bricks=["b" * 18]))
        self.assertEqual(
            check("x" * 40, bricks=["b" * 19, "sw"]),
            "The name leaves 18 bytes to the names of the bricks,"
            " and the longest has 19",
        )
        self.assertIsNone(check("x" * 39, bricks=["b" * 19]))

    def test_renaming_reads_the_bricks_of_the_project(self):
        self.fixed_runtime_dir()
        self.projects.create("lab")
        data = load_toml(self.project_file("lab"))
        data["bricks"] = {"b" * 19: {"type": "switch"}}
        self.write("lab", data)
        self.assertIsNotNone(self.projects.check_name("x" * 40, "lab"))
        self.assertIsNone(self.projects.check_name("x" * 39, "lab"))
        # the bricks given win over the file's
        self.assertIsNone(self.projects.check_name("x" * 40, "lab", []))

    def test_renaming_an_unreadable_project(self):
        self.fixed_runtime_dir()
        self.file("lab", locations.PROJECT_FILE, text="[bricks\n")
        self.assertIsNone(self.projects.check_name("x" * 40, "lab"))
        self.assertIsNone(self.projects.check_name("x" * 40, "gone"))

    def test_free_name(self):
        free = self.projects.free_name
        self.assertEqual(free("lab"), "lab")
        self.projects.create("lab")
        self.assertEqual(free("lab"), "lab-2")
        self.projects.create("lab-2")
        os.makedirs(os.path.join(self.path, "lab-3"))
        self.assertEqual(free("lab"), "lab-4")
        self.assertEqual(free("lab-2"), "lab-4")
        self.assertEqual(free("new-lab"), "new-lab")


class TestCreate(WorkspaceTestCase):

    def test_create(self):
        self.projects.create("lab")
        data = load_toml(self.project_file("lab"))
        self.assertEqual(data["format"], FORMAT)
        self.assertEqual(data["settings"]["cow_format"], "qcow2")
        self.assertFalse(
            os.path.exists(os.path.join(self.path, "lab", "README"))
        )

    def test_a_new_project_copies_the_open_one(self):
        self.projects.create("lab")
        self.projects.open("lab", self.factory)
        set_setting("cow_format", "qcow")
        self.projects.create("lab2")
        data = load_toml(self.project_file("lab2"))
        self.assertEqual(data["settings"]["cow_format"], "qcow")

    def test_description(self):
        self.projects.create("lab", "OSPF between three routers")
        with open(os.path.join(self.path, "lab", "README")) as fp:
            self.assertEqual(fp.read(), "OSPF between three routers")

    def test_a_folder_that_appears_meanwhile(self):
        folder = os.path.join(self.path, "lab")

        def validate(name, renaming=None, bricks=None):
            # after the check, before the folder is made
            os.makedirs(folder)

        self.patch(self.projects, "_validate", validate)
        self.assertRaises(errors.InvalidNameError, self.projects.create, "lab")
        self.assertEqual(os.listdir(folder), [])

    def test_bad_names(self):
        self.projects.create("lab")
        self.assertRaises(errors.InvalidNameError, self.projects.create, "lab")
        os.makedirs(os.path.join(self.path, "folder"))
        self.assertRaises(
            errors.InvalidNameError, self.projects.create, "folder"
        )
        self.assertRaises(
            errors.InvalidNameError, self.projects.create, "../lab"
        )
        self.assertRaises(errors.InvalidNameError, self.projects.create, "")

    def test_cannot_write(self):
        os.makedirs(self.path)
        os.chmod(self.path, 0o500)
        self.addCleanup(os.chmod, self.path, 0o700)
        self.assertRaises(OSError, self.projects.create, "lab")


class TestRename(WorkspaceTestCase):

    def test_rename(self):
        self.projects.create("lab")
        self.projects.rename("lab", "ospf")
        self.assertEqual(self.projects.names(), ["ospf"])
        # the state isn't about a project that isn't open
        self.assertNotEqual(current_project(self.path), "ospf")
        # the same name does nothing
        self.projects.rename("ospf", "ospf")
        self.assertEqual(self.projects.names(), ["ospf"])

    def test_rename_the_open_project(self):
        self.projects.create("lab")
        self.projects.open("lab", self.factory)
        runtime_dir = self.factory.runtime_dir
        self.projects.rename("lab", "ospf")
        self.assertEqual(self.projects.current.name, "ospf")
        self.assertEqual(
            self.projects.current.path, os.path.join(self.path, "ospf")
        )
        self.assertEqual(current_project(self.path), "ospf")
        # the running bricks keep their sockets
        self.assertEqual(self.factory.runtime_dir, runtime_dir)
        self.projects.save(self.factory)
        self.assertEqual(self.projects.names(), ["ospf"])

    def test_errors(self):
        self.projects.create("lab")
        self.projects.create("other")
        rename = self.projects.rename
        error = self.assertRaises(errors.InvalidNameError, rename, "gone", "x")
        self.assertEqual(str(error), 'There is no project "gone"')
        self.assertRaises(errors.InvalidNameError, rename, "lab", "other")
        self.assertRaises(errors.InvalidNameError, rename, "lab", ".lab")
        self.assertEqual(self.projects.names(), ["lab", "other"])

    def test_the_bricks_must_fit(self):
        self.fixed_runtime_dir()
        self.projects.create("lab")
        self.assertRaises(
            errors.InvalidNameError,
            self.projects.rename,
            "lab",
            "x" * 40,
            bricks=["b" * 19],
        )
        self.projects.rename("lab", "x" * 40, bricks=["b" * 18])


class TestDuplicate(WorkspaceTestCase):

    def test_copy_with_the_private_disks(self):
        self.projects.create("lab", "A lab")
        self.set_mtime("lab", 1000)
        disk = os.path.join(self.path, "lab", "vm_hda.cow")
        with open(disk, "wb") as fp:
            fp.write(b"head")
            fp.seek(64 * MiB)
            fp.write(b"tail")
        self.projects.duplicate("lab", "copy")
        self.assertEqual(self.projects.names(), ["copy", "lab"])
        copy = os.path.join(self.path, "copy", "vm_hda.cow")
        with open(copy, "rb") as fp:
            self.assertEqual(fp.read(4), b"head")
            fp.seek(64 * MiB)
            self.assertEqual(fp.read(), b"tail")
        # the holes stay holes
        self.assertLess(os.stat(copy).st_blocks * 512, MiB)
        self.assertEqual(os.stat(copy).st_size, os.stat(disk).st_size)
        # the copy is the one used last
        modified = os.stat(self.project_file("copy")).st_mtime
        self.assertGreater(modified, time.time() - 60)
        self.assertEqual(self.projects.summaries()[0].name, "copy")
        self.assertEqual(self.projects.summary("copy").description, "A lab")

    def test_a_file_that_ends_with_a_hole(self):
        self.projects.create("lab")
        disk = os.path.join(self.path, "lab", "vm_hda.cow")
        with open(disk, "wb") as fp:
            fp.write(b"data")
            fp.truncate(8 * MiB)
        self.projects.duplicate("lab", "copy")
        copy = os.path.join(self.path, "copy", "vm_hda.cow")
        self.assertEqual(os.stat(copy).st_size, 8 * MiB)
        with open(copy, "rb") as fp:
            self.assertEqual(fp.read(5), b"data\0")

    def test_errors(self):
        self.projects.create("lab")
        duplicate = self.projects.duplicate
        self.assertRaises(errors.InvalidNameError, duplicate, "gone", "x")
        self.assertRaises(errors.InvalidNameError, duplicate, "lab", "lab")
        self.assertRaises(errors.InvalidNameError, duplicate, "lab", "a/b")


class TestRemove(WorkspaceTestCase):

    def setUp(self):
        super().setUp()
        self.trash = FakeTrash()
        self.patch(self.projects, "trasher", self.trash)
        self.projects.create("lab")
        self.projects.create("open")
        self.projects.open("open", self.factory)

    def test_trash(self):
        self.assertTrue(self.projects.trash("lab"))
        self.assertEqual(self.trash.trashed, [os.path.join(self.path, "lab")])
        self.assertTrue(os.path.isdir(os.path.join(self.path, "lab")))

    def test_the_desktop_has_no_trash_for_it(self):
        self.trash.error = errors.TrashNotSupportedError("/lab")
        self.assertRaises(
            errors.TrashNotSupportedError, self.projects.trash, "lab"
        )
        # not deleted instead
        self.assertEqual(self.projects.names(), ["lab", "open"])

    def test_can_trash(self):
        self.assertTrue(self.projects.can_trash("lab"))
        self.trash.allowed = False
        self.assertFalse(self.projects.can_trash("lab"))
        self.assertEqual(
            self.trash.asked, [os.path.join(self.path, "lab")] * 2
        )

    def test_without_a_desktop_the_project_is_deleted(self):
        # a console or a script: no trasher
        self.patch(self.projects, "trasher", None)
        self.file("lab", "vm_hda.cow")
        self.assertFalse(self.projects.can_trash("lab"))
        self.assertFalse(self.projects.trash("lab"))
        self.assertEqual(self.projects.names(), ["open"])
        self.assertFalse(os.path.exists(os.path.join(self.path, "lab")))
        self.assertEqual(self.trash.trashed, [])

    def test_the_workspace_has_no_desktop_by_default(self):
        self.assertIsNone(Workspace(self.path).trasher)

    def test_delete(self):
        self.file("lab", "vm_hda.cow")
        self.projects.delete("lab")
        self.assertEqual(self.projects.names(), ["open"])
        self.assertFalse(os.path.exists(os.path.join(self.path, "lab")))
        self.assertEqual(self.trash.trashed, [])

    def test_a_folder_without_a_project_file(self):
        os.makedirs(os.path.join(self.path, "broken"))
        self.projects.delete("broken")
        self.assertFalse(os.path.exists(os.path.join(self.path, "broken")))

    def test_not_the_open_project(self):
        for trasher in (self.trash, None):
            self.patch(self.projects, "trasher", trasher)
            for remove in (self.projects.trash, self.projects.delete):
                self.assertRaises(errors.ProjectOpenError, remove, "open")
        self.assertEqual(self.trash.trashed, [])
        self.assertEqual(self.projects.names(), ["lab", "open"])

    def test_missing(self):
        for trasher in (self.trash, None):
            self.patch(self.projects, "trasher", trasher)
            for remove in (self.projects.trash, self.projects.delete):
                for name in ("gone", "..", "", "a/b"):
                    self.assertRaises(errors.InvalidNameError, remove, name)
        self.assertEqual(self.trash.trashed, [])

    def test_the_summary_is_forgotten(self):
        self.projects.summaries()
        self.projects.trash("lab")
        self.assertNotIn("lab", self.projects._summaries)
        self.projects.summaries()
        self.patch(self.projects, "trasher", None)
        self.projects.create("other")
        self.projects.summaries()
        self.projects.trash("other")
        self.assertNotIn("other", self.projects._summaries)


class TestWithoutTheDesktop(unittest.TestCase):

    def test_the_workspace_imports_no_graphics_library(self):
        # in a process of its own: the tests of the windows load GTK
        code = (
            "import sys; import virtualbricks.config.workspace; "
            "print([m for m in sys.modules if m == 'gi'"
            " or m.startswith(('gi.', 'gtk', 'gobject'))])"
        )
        result = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "[]")


class TestSummaries(WorkspaceTestCase):

    def lab(self):
        self.projects.create("lab", "OSPF between routers\n\nDetails")
        image = self.file("vimages", "deb.qcow2")
        self.file("lab", "local.qcow2")
        data = load_toml(self.project_file("lab"))
        data["images"] = {
            "deb": {"path": image},
            "local": {"path": "local.qcow2"},
            "gone": {"path": "/nonexistent/gone.qcow2"},
            "empty": {"path": ""},
        }
        data["events"] = {"ev": {}}
        data["bricks"] = {
            "r1": {"type": "qemu"},
            "r2": {"type": "qemu"},
            "sw": {"type": "switch"},
        }
        self.write("lab", data)
        self.set_mtime("lab", 2000)
        return image

    def test_summary(self):
        image = self.lab()
        summary = self.projects.summary("lab")
        self.assertEqual(summary.name, "lab")
        self.assertEqual(summary.path, os.path.join(self.path, "lab"))
        self.assertEqual(
            summary.description, "OSPF between routers\n\nDetails"
        )
        self.assertEqual(summary.modified, 2000)
        self.assertEqual(summary.bricks, {"qemu": 2, "switch": 1})
        self.assertEqual(summary.events, 1)
        local = os.path.join(self.path, "lab", "local.qcow2")
        self.assertEqual(
            summary.images,
            (
                ImageSummary("deb", image, True),
                ImageSummary("local", local, True),
                ImageSummary("gone", "/nonexistent/gone.qcow2", False),
                ImageSummary("empty", "", False),
            ),
        )
        self.assertIsNone(summary.problem)

    def test_most_recent_first(self):
        for name, when in (("a", 1000), ("b", 3000), ("c", 2000)):
            self.projects.create(name)
            self.set_mtime(name, when)
        names = [s.name for s in self.projects.summaries()]
        self.assertEqual(names, ["b", "c", "a"])

    def test_unreadable_projects(self):
        self.file("bad", locations.PROJECT_FILE, text="[bricks\n")
        self.file("newer", locations.PROJECT_FILE, text="format = 9\n")
        self.file("secret", locations.PROJECT_FILE)
        os.chmod(self.project_file("secret"), 0)
        self.addCleanup(os.chmod, self.project_file("secret"), 0o600)
        summaries = {s.name: s for s in self.projects.summaries()}
        self.assertIn("bad", summaries["bad"].problem)
        self.assertIn("newer Virtualbricks", summaries["newer"].problem)
        self.assertIn("Permission denied", summaries["secret"].problem)
        self.assertEqual(summaries["bad"].bricks, {})

    def test_tables_that_are_not_tables(self):
        self.projects.create("lab")
        data = load_toml(self.project_file("lab"))
        data["images"] = "deb"
        data["bricks"] = {"sw": "switch"}
        self.write("lab", data)
        summary = self.projects.summary("lab")
        self.assertEqual((summary.images, summary.bricks), ((), {}))

    def test_read_again_only_when_the_file_changes(self):
        self.lab()
        read = []
        original = self.projects._read_summary

        def read_summary(name, path, modified):
            read.append(name)
            return original(name, path, modified)

        self.patch(self.projects, "_read_summary", read_summary)
        first = self.projects.summary("lab")
        self.assertIs(self.projects.summary("lab"), first)
        self.assertEqual(read, ["lab"])
        self.set_mtime("lab", 3000)
        self.assertEqual(self.projects.summary("lab").modified, 3000)
        self.assertEqual(read, ["lab", "lab"])

    def test_removed_projects_are_forgotten(self):
        self.projects.create("lab")
        self.projects.summaries()
        os.remove(self.project_file("lab"))
        self.assertEqual(self.projects.summaries(), [])
        self.assertEqual(self.projects._summaries, {})

    def test_a_project_removed_while_listing(self):
        self.projects.create("lab")
        self.patch(self.projects, "names", lambda: ["lab", "gone"])
        self.assertEqual([s.name for s in self.projects.summaries()], ["lab"])

    def test_disk_usage(self):
        self.projects.create("lab")
        with open(os.path.join(self.path, "lab", "vm_hda.cow"), "wb") as fp:
            fp.write(b"x" * MiB)
            fp.truncate(100 * MiB)
        name = "vm_hda.cow.bak-2026-09-25_10-00"
        with open(os.path.join(self.path, "lab", name), "wb") as fp:
            fp.write(b"x" * MiB)
        self.file("lab", "notes", "vm_hdb.cow", text="x" * 5000)
        usage = self.projects.disk_usage("lab")
        self.assertIsInstance(usage, DiskUsage)
        # what the files take, without the holes
        self.assertGreaterEqual(usage.private_disks, 2 * MiB)
        self.assertLess(usage.private_disks, 3 * MiB)
        # in a subfolder, a disk isn't a private disk
        self.assertGreaterEqual(usage.other_files, 5000)
        self.assertLess(usage.other_files, MiB)
        self.assertEqual(usage.total, usage.private_disks + usage.other_files)


class TestOpen(WorkspaceTestCase):

    def test_open(self):
        self.projects.create("lab")
        self.factory.new_brick("switch", "old")
        report = self.projects.open("lab", self.factory)
        self.assertEqual(len(report), 0)
        self.assertIsInstance(self.projects.current, OpenProject)
        self.assertEqual(self.projects.current.name, "lab")
        self.assertEqual(self.factory.bricks, [])
        self.assertIs(project_settings(), self.projects.current.settings)
        self.assertEqual(current_project(self.path), "lab")
        self.assertEqual(
            self.factory.runtime_dir,
            os.path.join(locations.runtime_dir(), "lab"),
        )
        self.assertTrue(os.path.isdir(self.factory.runtime_dir))

    def test_open_the_open_project(self):
        self.projects.create("lab")
        self.projects.open("lab", self.factory)
        current = self.projects.current
        self.factory.new_brick("switch", "sw")
        self.assertEqual(len(self.projects.open("lab", self.factory)), 0)
        self.assertIs(self.projects.current, current)
        self.assertEqual(len(self.factory.bricks), 1)

    def test_missing(self):
        self.assertRaises(
            errors.InvalidNameError, self.projects.open, "lab", None
        )
        for name in ("../lab", "", ".."):
            self.assertRaises(
                errors.InvalidNameError, self.projects.open, name, None
            )

    def test_the_open_project_is_saved_first(self):
        self.projects.create("lab")
        self.projects.create("other")
        self.projects.open("lab", self.factory)
        self.factory.new_brick("switch", "sw")
        set_setting("allow_female_plugs", True)
        self.projects.current.set_description("A lab")
        self.projects.open("other", self.factory)
        # what the factory held is in the file, not lost with the reset
        data = load_toml(self.project_file("lab"))
        self.assertIn("sw", data["bricks"])
        self.assertTrue(data["settings"]["allow_female_plugs"])
        with open(os.path.join(self.path, "lab", "README")) as fp:
            self.assertEqual(fp.read(), "A lab")
        self.assertEqual(self.projects.current.name, "other")
        self.assertEqual(self.factory.bricks, [])
        # and it comes back
        self.projects.open("lab", self.factory)
        self.assertEqual([b.name for b in self.factory.bricks], ["sw"])

    def test_the_open_project_stays_if_it_cannot_be_saved(self):
        self.projects.create("lab")
        self.projects.create("other")
        self.projects.open("lab", self.factory)
        self.factory.new_brick("switch", "sw")

        def fail(*args):
            raise OSError("disk full")

        self.patch(workspace, "save_project", fail)
        self.assertRaises(OSError, self.projects.open, "other", self.factory)
        self.assertEqual(self.projects.current.name, "lab")
        self.assertEqual([b.name for b in self.factory.bricks], ["sw"])
        self.assertEqual(current_project(self.path), "lab")

    def test_a_project_that_cannot_be_read_is_not_a_reason_to_save(self):
        self.projects.create("lab")
        self.projects.open("lab", self.factory)
        self.factory.new_brick("switch", "sw")
        self.file("bad", locations.PROJECT_FILE, text="[bricks\n")
        self.assertRaises(
            ProjectFormatError, self.projects.open, "bad", self.factory
        )
        self.assertNotIn("bricks", load_toml(self.project_file("lab")))
        self.assertEqual(len(self.factory.bricks), 1)

    def test_a_bad_file_keeps_the_open_project(self):
        self.projects.create("good")
        self.projects.open("good", self.factory)
        self.factory.new_brick("switch", "sw")
        self.file("bad", locations.PROJECT_FILE, text="[bricks\n")
        self.assertRaises(
            ProjectFormatError, self.projects.open, "bad", self.factory
        )
        self.assertEqual(self.projects.current.name, "good")
        self.assertEqual(len(self.factory.bricks), 1)
        self.write("bad", {"format": 9})
        self.assertRaises(
            ProjectFormatError, self.projects.open, "bad", self.factory
        )

    def test_the_report_is_logged_and_returned(self):
        self.projects.create("lab")
        data = load_toml(self.project_file("lab"))
        data["color"] = "red"
        self.write("lab", data)
        report = self.projects.open("lab", self.factory)
        self.assertEqual(len(report), 1)
        self.assertIn("color: unknown field, dropped", self.logger.formatted())

    def test_bricks_too_long_for_their_sockets(self):
        self.fixed_runtime_dir()
        self.patch(locations, "ensure_private_dir", lambda path: path)
        self.projects.create("x" * 40)
        data = load_toml(self.project_file("x" * 40))
        data["bricks"] = {
            "b" * 19: {"type": "switch"},
            "b" * 18: {"type": "switch"},
        }
        self.write("x" * 40, data)
        report = self.projects.open("x" * 40, self.factory)
        # the brick is there, and the report names it
        self.assertEqual(len(self.factory.bricks), 2)
        messages = [str(m) for m in report if "sockets" in str(m)]
        [message] = messages
        self.assertIn(f"bricks.{'b' * 19}:", message)
        self.assertIn("18 bytes", message)

    def test_close(self):
        self.projects.create("lab")
        self.projects.open("lab", self.factory)
        self.factory.new_brick("switch", "sw")
        self.projects.close(self.factory)
        self.assertIsNone(self.projects.current)
        self.assertIsNone(project_settings())
        self.assertEqual(self.factory.bricks, [])
        # closing when nothing is open
        self.projects.close(self.factory)

    def test_save(self):
        self.projects.create("lab")
        self.projects.open("lab", self.factory)
        self.factory.new_brick("switch", "sw")
        set_setting("allow_female_plugs", True)
        self.projects.current.set_description("A lab")
        self.projects.save(self.factory)
        data = load_toml(self.project_file("lab"))
        self.assertIn("sw", data["bricks"])
        self.assertTrue(data["settings"]["allow_female_plugs"])
        with open(os.path.join(self.path, "lab", "README")) as fp:
            self.assertEqual(fp.read(), "A lab")

    def test_save_without_an_open_project(self):
        self.projects.save(self.factory)
        self.assertEqual(self.projects.names(), [])

    def test_save_recreates_the_folder(self):
        self.projects.create("lab")
        self.projects.open("lab", self.factory)
        shutil.rmtree(os.path.join(self.path, "lab"))
        self.projects.save(self.factory)
        self.assertEqual(self.projects.names(), ["lab"])

    def test_autosave(self):
        self.projects.create("lab")
        self.projects.open("lab", self.factory)
        self.factory.new_brick("switch", "sw")
        self.projects.autosave(self.factory)
        self.assertIn("sw", load_toml(self.project_file("lab"))["bricks"])

    def test_autosave_errors_are_logged(self):
        self.projects.create("lab")
        self.projects.open("lab", self.factory)

        def fail(*args):
            raise OSError("disk full")

        self.patch(workspace, "save_project", fail)
        self.projects.autosave(self.factory)
        self.assertEqual(self.logger.levels(), ["failure"])


class TestOpenProject(WorkspaceTestCase):

    def test_description(self):
        path = os.path.join(self.path, "lab")
        prj = OpenProject(path, None)
        self.assertEqual(prj.name, "lab")
        self.assertEqual(prj.project_file, self.project_file("lab"))
        self.assertEqual(prj.get_description(), "")
        self.file("lab", "README", text="text")
        # read once
        self.assertEqual(prj.get_description(), "")
        self.assertEqual(OpenProject(path, None).get_description(), "text")
        prj.set_description("new")
        self.assertEqual(prj.get_description(), "new")
        self.assertIn("lab", repr(prj))


class TestStartUp(WorkspaceTestCase):

    def test_open_last(self):
        self.projects.create("lab")
        set_current_project(self.path, "lab")
        self.projects.open_last(self.factory)
        self.assertEqual(self.projects.current.name, "lab")
        self.assertTrue(os.path.isdir(os.path.join(self.path, "vimages")))

    def test_the_last_project_of_each_workspace(self):
        other = Workspace(os.path.join(self.root, "other"))
        self.projects.create("lab")
        other.create("ospf")
        self.projects.open("lab", self.factory)
        other.open("ospf", make_factory())
        self.assertEqual(self.projects.last_name(), "lab")
        self.assertEqual(other.last_name(), "ospf")
        self.assertEqual(
            Workspace(os.path.join(self.root, "never")).last_name(),
            "new_project",
        )

    def test_the_first_run_creates_new_project(self):
        self.projects.open_last(self.factory)
        self.assertEqual(self.projects.current.name, "new_project")
        set_current_project(self.path, "new_project_3")
        self.projects.close(self.factory)
        self.projects.open_last(self.factory)
        self.assertEqual(self.projects.current.name, "new_project_3")

    def test_open_last_raises(self):
        set_current_project(self.path, "gone")
        self.assertRaises(
            errors.InvalidNameError,
            self.projects.open_last,
            self.factory,
        )
        self.file("new_project", "notes")
        set_current_project(self.path, "new_project")
        self.assertRaises(
            errors.InvalidNameError,
            self.projects.open_last,
            self.factory,
        )
        self.assertIsNone(self.projects.current)

    def test_restore_the_last_project(self):
        self.projects.create("lab")
        set_current_project(self.path, "lab")
        self.projects.restore_last(self.factory)
        self.assertEqual(self.projects.current.name, "lab")
        self.assertEqual(self.logger.levels(), [])

    def test_restore_creates_the_default_project(self):
        self.projects.restore_last(self.factory)
        self.assertEqual(self.projects.current.name, "new_project")
        self.assertNotIn("error", self.logger.levels())

    def test_default_project_folder_without_file(self):
        os.makedirs(os.path.join(self.path, "new_project"))
        self.projects.restore_last(self.factory)
        self.assertEqual(self.projects.current.name, "new_project_0")
        self.assertEqual(self.logger.levels().count("error"), 1)

    def test_missing_project(self):
        set_current_project(self.path, "gone")
        self.projects.create("new_project_0")
        self.projects.restore_last(self.factory)
        self.assertEqual(self.projects.current.name, "new_project_1")
        self.assertEqual(self.logger.levels().count("error"), 1)

    def test_invalid_name(self):
        set_current_project(self.path, "../x")
        self.projects.restore_last(self.factory)
        self.assertEqual(self.projects.current.name, "new_project_0")

    def test_unreadable_project(self):
        self.file("lab", locations.PROJECT_FILE, text="[bricks\n")
        set_current_project(self.path, "lab")
        self.projects.restore_last(self.factory)
        self.assertEqual(self.projects.current.name, "new_project_0")
        self.assertIn("Cannot open project", self.logger.formatted()[0])
