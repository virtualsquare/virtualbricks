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

"""The export of projects, until the archive process makes it."""

import errno
import os

from twisted.internet import defer
from twisted.trial import unittest

from virtualbricks import project
from virtualbricks.config import workspace
from virtualbricks.tests import FakeLogger, isolate, make_factory
from virtualbricks.tests import reset_settings, use_workspace


class ProjectTestCase(unittest.TestCase):

    def setUp(self):
        self.root = isolate(self)
        reset_settings(self)
        self.workspace = os.path.join(self.root, "workspace")
        self.projects = use_workspace(self, self.workspace)
        self.manager = project.Archives(self.projects)
        self.factory = make_factory()
        self.patch(project, "logger", FakeLogger())
        self.patch(workspace, "logger", FakeLogger())


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


class TestExport(ProjectTestCase):

    def test_path(self):
        self.assertEqual(self.manager.path, self.workspace)

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
