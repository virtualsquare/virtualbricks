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

import errno
import os

from twisted.internet import defer
from twisted.trial import unittest

from virtualbricks import config, errors, locations, project
from virtualbricks.config import ProjectFormatError
from virtualbricks.tests import FakeLogger, isolate, make_factory
from virtualbricks.tests import reset_settings


class ProjectTestCase(unittest.TestCase):

    def setUp(self):
        self.root = isolate(self)
        reset_settings(self)
        self.workspace = os.path.join(self.root, "workspace")
        self.manager = project.ProjectManager(self.workspace)
        self.factory = make_factory()
        self.logger = FakeLogger()
        self.patch(project, "logger", self.logger)

    def new_project(self, name="lab"):
        return self.manager.get_project(name).create()


class TestProject(ProjectTestCase):

    def test_create(self):
        config.set_app("cowfmt", "qcow")
        prj = self.new_project()
        self.assertTrue(prj.exists())
        data = config.load_toml(prj.project_file)
        self.assertEqual(data["format"], 1)
        self.assertEqual(data["settings"]["cowfmt"], "qcow")
        self.assertRaises(errors.ProjectExistsError, prj.create)
        prj.create(overwrite=True)
        self.assertTrue(prj.exists())

    def test_create_error(self):
        prj = self.manager.get_project("lab")
        os.makedirs(self.workspace)
        os.chmod(self.workspace, 0o500)
        self.addCleanup(os.chmod, self.workspace, 0o700)
        self.assertRaises(OSError, prj.create)

    def test_exists(self):
        prj = self.manager.get_project("lab")
        self.assertFalse(prj.exists())
        os.makedirs(prj.path)
        self.assertFalse(prj.exists())
        self.assertFalse(os.path.exists(prj.project_file))

    def test_open(self):
        prj = self.new_project()
        self.factory.new_brick("switch", "old")
        self.assertIs(prj.open(self.factory), prj)
        self.assertIs(self.manager.current, prj)
        self.assertEqual(self.factory.bricks, [])
        self.assertIs(config.project_settings(), prj.project_settings)
        self.assertEqual(config.current_project(), "lab")
        self.assertEqual(
            self.factory.runtime_dir,
            os.path.join(locations.runtime_dir(), "lab"),
        )
        self.assertTrue(os.path.isdir(self.factory.runtime_dir))
        # opening the open project does nothing
        self.assertIsNone(prj.open(self.factory))

    def test_open_missing(self):
        prj = self.manager.get_project("lab")
        self.assertRaises(errors.ProjectNotExistsError, prj.open, self.factory)

    def test_open_a_bad_file_keeps_the_open_project(self):
        good = self.new_project("good")
        good.open(self.factory)
        self.factory.new_brick("switch", "sw")
        bad = self.new_project("bad")
        with open(bad.project_file, "w") as fp:
            fp.write("[bricks\n")
        self.assertRaises(ProjectFormatError, bad.open, self.factory)
        self.assertIs(self.manager.current, good)
        self.assertEqual(len(self.factory.bricks), 1)
        config.dump_toml({"format": 9}, bad.project_file)
        self.assertRaises(ProjectFormatError, bad.open, self.factory)

    def test_open_logs_the_report(self):
        prj = self.new_project()
        data = config.load_toml(prj.project_file)
        data["color"] = "red"
        config.dump_toml(data, prj.project_file)
        prj.open(self.factory)
        self.assertIn("color: unknown field, dropped", self.logger.formatted())

    def test_close(self):
        prj = self.new_project()
        prj.open(self.factory)
        prj.close(self.factory)
        self.assertIsNone(self.manager.current)
        self.assertIsNone(prj.project_settings)
        self.assertIsNone(config.project_settings())
        # closing when nothing is open
        prj.close(self.factory)

    def test_save(self):
        prj = self.new_project()
        prj.open(self.factory)
        self.factory.new_brick("switch", "sw")
        config.set("femaleplugs", True)
        prj.set_description("A lab")
        prj.save(self.factory)
        data = config.load_toml(prj.project_file)
        self.assertIn("sw", data["bricks"])
        self.assertTrue(data["settings"]["femaleplugs"])
        self.assertFalse(config.get_app("femaleplugs"))
        with open(os.path.join(prj.path, "README")) as fp:
            self.assertEqual(fp.read(), "A lab")
        self.assertEqual(prj.get_description(), "A lab")

    def test_save_recreates_the_directory(self):
        prj = self.new_project()
        prj.open(self.factory)
        prj.delete()
        prj.save(self.factory)
        self.assertTrue(prj.exists())

    def test_description(self):
        prj = self.new_project()
        self.assertEqual(prj.get_description(), "")
        with open(os.path.join(prj.path, "README"), "w") as fp:
            fp.write("text")
        other = self.manager.get_project("lab")
        self.assertEqual(other.get_description(), "text")

    def test_save_as(self):
        prj = self.new_project()
        prj.open(self.factory)
        self.assertIsNone(prj.save_as("lab", self.factory))
        copy = prj.save_as("copy", self.factory)
        self.assertTrue(copy.exists())
        self.assertEqual(copy.name, "copy")

    def test_rename(self):
        prj = self.new_project()
        prj.open(self.factory)
        self.assertIsNone(prj.rename("lab"))
        prj.rename("lab2")
        self.assertEqual(prj.name, "lab2")
        self.assertTrue(prj.exists())
        self.assertEqual(config.current_project(), "lab2")
        other = self.new_project("other")
        other.rename("other2")
        self.assertEqual(config.current_project(), "lab2")

    def test_documents(self):
        prj = self.new_project()
        data = prj.read_document()
        data["bricks"] = {"sw": {"type": "switch"}}
        prj.write_document(data)
        self.assertEqual(prj.read_document()["bricks"], data["bricks"])

    def test_files_and_images(self):
        prj = self.new_project()
        self.assertEqual(prj.images(), ())
        os.makedirs(os.path.join(prj.path, ".images"))
        with open(os.path.join(prj.path, ".images", "deb"), "w"):
            pass
        self.assertEqual(prj.images(), ["deb"])
        names = sorted(fp.basename() for fp in prj.files())
        self.assertEqual(names, ["deb", "project.toml"])

    def test_delete(self):
        prj = self.new_project()
        prj.delete()
        self.assertFalse(os.path.exists(prj.path))
        prj.delete()

    def test_delete_error(self):
        prj = self.manager.get_project("lab")

        def fail():
            raise OSError(errno.EACCES, "denied")

        self.patch(prj._path, "remove", fail)
        self.assertRaises(OSError, prj.delete)

    def test_equality(self):
        prj = self.manager.get_project("lab")
        same = self.manager.get_project("lab")
        self.assertEqual(prj, same)
        self.assertFalse(prj != same)
        self.assertEqual(hash(prj), hash(same))
        self.assertNotEqual(prj, "lab")
        self.assertTrue(prj.__ne__("lab") is NotImplemented)
        self.assertIn("lab", repr(prj))


class TestManager(ProjectTestCase):

    def test_workspace(self):
        self.assertEqual(self.manager.path, self.workspace)
        manager = project.ProjectManager()
        config.set("workspace", "/srv/labs")
        self.assertEqual(manager.path, "/srv/labs")

    def test_get_project(self):
        self.assertRaises(
            errors.InvalidNameError, self.manager.get_project, "../x"
        )

    def test_iter(self):
        self.assertEqual(list(self.manager), [])
        self.new_project("a")
        os.makedirs(os.path.join(self.workspace, "old"))
        with open(os.path.join(self.workspace, "file"), "w"):
            pass
        self.assertEqual([p.name for p in self.manager], ["a"])

    def test_save_current_and_autosave(self):
        self.manager.save_current(self.factory)
        prj = self.new_project()
        prj.open(self.factory)
        self.factory.new_brick("switch", "sw")
        self.manager.autosave(self.factory)
        self.assertIn("sw", config.load_toml(prj.project_file)["bricks"])

    def test_autosave_error_is_logged(self):
        prj = self.new_project()
        prj.open(self.factory)

        def fail(*args):
            raise OSError("disk full")

        self.patch(config, "save", fail)
        self.manager.autosave(self.factory)
        self.assertEqual(self.logger.levels(), ["failure"])


class TestRestoreLast(ProjectTestCase):

    def test_open_the_current_project(self):
        self.new_project("lab")
        config.set_current_project("lab")
        prj = self.manager.restore_last(self.factory)
        self.assertEqual(prj.name, "lab")
        self.assertTrue(os.path.isdir(os.path.join(self.workspace, "vimages")))

    def test_create_the_default_project(self):
        prj = self.manager.restore_last(self.factory)
        self.assertEqual(prj.name, "new_project")
        self.assertNotIn("error", self.logger.levels())

    def test_default_project_directory_without_file(self):
        os.makedirs(os.path.join(self.workspace, "new_project"))
        prj = self.manager.restore_last(self.factory)
        self.assertEqual(prj.name, "new_project_0")
        self.assertEqual(self.logger.levels().count("error"), 1)

    def test_missing_project(self):
        config.set_current_project("gone")
        self.new_project("new_project_0")
        prj = self.manager.restore_last(self.factory)
        self.assertEqual(prj.name, "new_project_1")
        self.assertEqual(self.logger.levels().count("error"), 1)

    def test_invalid_name(self):
        config.set_current_project("../x")
        prj = self.manager.restore_last(self.factory)
        self.assertEqual(prj.name, "new_project_0")

    def test_unreadable_project(self):
        prj = self.new_project("lab")
        with open(prj.project_file, "w") as fp:
            fp.write("[bricks\n")
        config.set_current_project("lab")
        self.assertEqual(
            self.manager.restore_last(self.factory).name, "new_project_0"
        )
        self.assertIn("Cannot open project", self.logger.formatted()[0])


class FakeArchive:

    def __init__(self, files=None):
        self.files = files or {}
        self.created = []

    def extract(self, pathname, destination):
        for name, text in self.files.items():
            path = os.path.join(destination, name)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as fp:
                fp.write(text)
        return defer.succeed(None)

    def create(self, output, directory, files, images):
        self.created.append((output, directory, files, images))
        return defer.succeed(None)


class TestImport(ProjectTestCase):

    def test_new_format(self):
        data = config.dumps({"format": 1, "settings": {}})
        self.manager.archive = FakeArchive({"project.toml": data})
        prj = self.successResultOf(self.manager.import_prj("lab", "x.vbp"))
        self.assertTrue(prj.exists())

    def test_old_format_is_migrated(self):
        text = "[Switch:sw]\nnumports=8\n"
        self.manager.archive = FakeArchive({".project": text})
        prj = self.successResultOf(self.manager.import_prj("lab", "x.vbp"))
        self.assertEqual(prj.read_document()["bricks"]["sw"]["numports"], 8)

    def test_no_project(self):
        self.manager.archive = FakeArchive({"README": "x"})
        failure = self.failureResultOf(self.manager.import_prj("lab", "x.vbp"))
        failure.trap(errors.InvalidArchiveError)

    def test_errors(self):
        self.new_project("lab")
        self.failureResultOf(self.manager.import_prj("lab", "x")).trap(
            errors.ProjectExistsError
        )
        self.failureResultOf(self.manager.import_prj("../x", "x")).trap(
            errors.InvalidNameError
        )
        os.chmod(self.workspace, 0o500)
        self.addCleanup(os.chmod, self.workspace, 0o700)
        self.failureResultOf(self.manager.import_prj("other", "x")).trap(
            OSError
        )

    def test_export(self):
        self.manager.archive = archive = FakeArchive()
        self.successResultOf(self.manager.export("out.vbp", "/p", ["a"], ()))
        self.assertEqual(archive.created, [("out.vbp", "/p", ["a"], ())])


class TestArchive(unittest.TestCase):

    def run_command(self, calls):
        def run(exe, args, env):
            calls.append((exe, args))
            return defer.succeed((b"", b"", 0))

        return run

    def test_create_in_the_project_directory(self):
        calls = []
        tgz = project.Tgz()
        tgz.create(
            "/out.vbp",
            "/labs/lab",
            ["project.toml"],
            run=self.run_command(calls),
        )
        self.assertEqual(
            calls,
            [("tar", ["cfzh", "/out.vbp", "-C", "/labs/lab", "project.toml"])],
        )

    def test_create_with_images(self):
        directory = os.path.abspath(self.mktemp())
        os.makedirs(directory)
        image = os.path.join(directory, "deb.qcow2")
        with open(image, "w"):
            pass
        calls = []
        tgz = project.BsdTgz()
        d = tgz.create(
            "/out.vbp",
            directory,
            ["project.toml"],
            [("deb", image), ("gone", "/nonexistent")],
            run=self.run_command(calls),
        )
        self.successResultOf(d)
        exe, args = calls[0]
        self.assertEqual(exe, "bsdtar")
        self.assertIn(".images/deb", args)
        self.assertFalse(os.path.exists(os.path.join(directory, ".images")))

    def test_create_with_images_that_cannot_be_staged(self):
        directory = os.path.abspath(self.mktemp())
        os.makedirs(os.path.join(directory, ".images"))

        def remove(self):
            raise OSError(errno.EACCES, "Permission denied")

        self.patch(project.filepath.FilePath, "remove", remove)
        calls = []
        d = project.Tgz().create(
            "/out.vbp",
            directory,
            ["project.toml"],
            [("deb", "/deb.qcow2")],
            run=self.run_command(calls),
        )
        self.failureResultOf(d, OSError)
        self.assertEqual(calls, [])

    def test_extract(self):
        calls = []
        tgz = project.Tgz()
        self.successResultOf(
            tgz.extract("/in.vbp", "/dest", run=self.run_command(calls))
        )
        self.assertEqual(calls, [("tar", ["Sxfz", "/in.vbp", "-C", "/dest"])])

    def test_errors_are_reported(self):
        def run(exe, args, env):
            return defer.succeed((b"", b"no space", 2))

        self.failureResultOf(project.Tgz().extract("/a", "/b", run=run))
