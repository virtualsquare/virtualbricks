# Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
# Copyright (C) 2018 Virtualbricks team

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

import six
import operator

from twisted.trial import unittest
from twisted.python.filepath import FilePath
from twisted.internet import defer

from virtualbricks import errors, project
from virtualbricks._settings import Settings
from virtualbricks.tests import get_filename, failureResultOf, stubs
from virtualbricks.tests.stubs import Factory


NAME = "test_project"


class TestProjectManager(unittest.TestCase):

    def test_path_exists(self):
        """
        All the projects are in path defined at contruction time. Assert that
        that path exists.
        """

        manager = project.ProjectManager(self.mktemp())
        self.assertTrue(FilePath(manager.path).exists())

    def test_exists_bizarre_name(self):
        manager = project.ProjectManager(self.mktemp())
        self.assertRaises(errors.InvalidNameError, manager.get_project,
                          "test/bizarre")

    def test_import_project_exists(self):
        """
        Import a project but a project with the same name already exists.
        """

        manager = project.ProjectManager(self.mktemp())
        prj = manager.get_project(NAME)
        prj.create()
        d = manager.import_prj(NAME, "/example/test.vbp")
        failureResultOf(self, d, errors.ProjectExistsError)

    def test_import(self):
        """Import a project."""

        def _assert(prj):
            self.assertTrue(prj.exists())
            self.assertEquals(prj.name, NAME)

        manager = project.ProjectManager(self.mktemp())
        return manager.import_prj(NAME, get_filename("test.vbp"))

    def test_iter(self):
        """
        Iterating througt the manager returns the projects. The order is
        arbitrary.
        """

        NAME1 = "prj1"
        NAME2 = "prj2"
        manager = project.ProjectManager(self.mktemp())
        prj1 = manager.get_project(NAME1)
        prj1.create()
        prj2 = manager.get_project(NAME2)
        prj2.create()
        self.assertEqual(sorted(manager, key=lambda p: p.name), [prj1, prj2])

    def test_iter2(self):
        """Returns only prooved projects."""

        path = self.mktemp()
        manager = project.ProjectManager(path)
        # a file is not a project
        FilePath(path).child("child1").touch()
        prj = manager.get_project(NAME)
        prj.create()
        # a directory without a .project file is not a project
        FilePath(path).child("prj2").makedirs()
        self.assertEqual(list(manager), [prj])

    def test_get_project_invalid_name(self):
        """Name could not contains path traversal."""

        manager = project.ProjectManager(self.mktemp())
        self.assertRaises(errors.InvalidNameError, manager.get_project,
                          "../ciccio")

    def test_restore_last_project(self):
        """Restore last used project."""

        manager = project.ProjectManager(self.mktemp())
        prj = manager.get_project(NAME)
        prj.create()
        settings = Settings(self.mktemp())
        settings.set("current_project", NAME)
        self.assertEqual(manager.restore_last(Factory(), settings), prj)

    def test_restore_last_project_not_exists(self):
        """
        If the last project does not exists, don't create a new one with the
        same name but use a default name.
        """

        settings = Settings(self.mktemp())
        settings.set("current_project", NAME)
        manager = project.ProjectManager(self.mktemp())
        prj = manager.get_project(NAME)
        self.assertFalse(prj.exists())
        prj = manager.restore_last(Factory(), settings)
        self.assertEqual(prj.name, settings.DEFAULT_PROJECT + "_0")


class TestProject(unittest.TestCase):

    def test_equality(self):
        """
        Two projects are equal if they have the same name and the same path.
        """

        manager = project.ProjectManager(self.mktemp())
        prj1 = manager.get_project(NAME)
        prj2 = manager.get_project(NAME)
        self.assertEqual(prj1, prj2)

    def test_delete(self):
        """Delete a project."""

        manager = project.ProjectManager(self.mktemp())
        prj = manager.get_project(NAME)
        prj.create()
        self.assertTrue(prj.exists())
        prj.delete()
        self.assertFalse(prj.exists())

    def test_open(self):
        """Open a project."""

        manager = project.ProjectManager(self.mktemp())
        prj = manager.get_project(NAME)
        prj.create()
        prj.open(Factory(), Settings(self.mktemp()))

    def test_open_project_does_not_exists(self):
        """Try to open a project that does not exists."""

        manager = project.ProjectManager(self.mktemp())
        prj = manager.get_project(NAME)
        self.assertRaises(errors.ProjectNotExistsError, prj.open, Factory())

    def test_open_project_set_virtualbricks_home(self):
        """
        Every time a project is opened, settings.VIRTUALBRICKS_HOME is set to
        the project's path.
        """

        manager = project.ProjectManager(self.mktemp())
        settings = Settings(self.mktemp())
        prj = manager.get_project(NAME)
        prj.create()
        self.assertEqual(settings.VIRTUALBRICKS_HOME, settings.DEFAULT_HOME)
        prj.open(Factory(), settings)
        self.assertEqual(prj.path, settings.VIRTUALBRICKS_HOME)
        self.assertNotEqual(settings.VIRTUALBRICKS_HOME,
                            settings.DEFAULT_HOME)

    def test_save(self):
        """Save a project."""

        class ProjectCmp:
            def __init__(self, prj):
                self.data = prj._project.getContent()
            def __eq__(self, other):
                return not self.__ne__(other)
            def __ne__(self, other):
                return self.data != ProjectCmp(other).data

        manager = project.ProjectManager(self.mktemp())
        prj = manager.get_project(NAME)
        prj.create()
        cmparator = ProjectCmp(prj)
        factory = Factory()
        factory.new_brick("vm", "test")
        prj.save(factory)
        self.assertNotEqual(cmparator, prj)

    def test_save_after_delete(self):
        manager = project.ProjectManager(self.mktemp())
        prj = manager.get_project(NAME)
        prj.create()
        prj.delete()
        prj.save(Factory())
        self.assertTrue(prj.exists())

    def test_save_as(self):
        """Create a copy of the project with a different name."""

        NEW_PROJET_NAME = "copy"
        manager = project.ProjectManager(self.mktemp())
        prj = manager.get_project(NAME)
        prj.create()
        new = prj.save_as(NEW_PROJET_NAME, Factory())
        self.assertTrue(FilePath(new.path).exists())
        self.assertNotEqual(prj.path, new.path)

    def test_rename(self):
        """Rename a project."""

        NEWNAME = "rename_test"
        manager = project.ProjectManager(self.mktemp())
        prj = manager.get_project(NAME)
        prj.create()
        self.assertTrue(prj.exists())
        old_path = prj.path
        prj.rename(NEWNAME, False, Settings(self.mktemp()))
        self.assertEqual(prj.name, NEWNAME)
        self.assertTrue(prj.exists())
        self.assertNotEqual(prj.path, old_path)
        self.assertFalse(FilePath(old_path).exists())

    def test_rename_invalid(self):
        """If an invalid name is given an exception is raised."""

        manager = project.ProjectManager(self.mktemp())
        prj = manager.get_project(NAME)
        prj.create()
        self.assertRaises(errors.InvalidNameError, prj.rename, "test/invalid")

    def test_rename_invalid_pathological(self):
        """If the name is really strange, the error is not raised."""

        manager = project.ProjectManager(self.mktemp())
        prj = manager.get_project(NAME)
        prj.create()
        prj.rename("test/../invalid", False, Settings(self.mktemp()))
        self.assertEqual(prj.name, "invalid")

    def test_rename_exists(self):
        """If a project with the same name exists an exception is raised."""

        NEWNAME = "test2"
        manager = project.ProjectManager(self.mktemp())
        prj = manager.get_project(NAME)
        prj.create()
        manager.get_project(NEWNAME).create()
        self.assertRaises(errors.ProjectExistsError, prj.rename, NEWNAME)

    def test_description(self):
        """Return a description of brand new project."""

        manager = project.ProjectManager(self.mktemp())
        prj = manager.get_project(NAME)
        self.assertEqual(prj.get_description(), "")

    def test_set_description(self):
        """Set the description of a project."""

        DESCRIPTION = "hello world"
        manager = project.ProjectManager(self.mktemp())
        prj = manager.get_project(NAME)
        prj.set_description(DESCRIPTION)
        self.assertEqual(prj.get_description(), DESCRIPTION)

    def test_save_description(self):
        """Save the description when the project is saved."""

        DESCRIPTION = "hello world"
        manager = project.ProjectManager(self.mktemp())
        prj = manager.get_project(NAME)
        prj.set_description(DESCRIPTION)
        readme = FilePath(prj.path).child("README")
        self.assertFalse(readme.exists())
        prj.save(Factory())
        self.assertEqual(readme.getContent(), DESCRIPTION)

    def test_files(self):
        manager = project.ProjectManager(self.mktemp())
        prj = manager.get_project(NAME)
        prj.create()
        files = [FilePath(prj.path).child(".project")]
        self.assertEqual(list(prj.files()), files)
        afile = FilePath(prj.path).child("file")
        afile.open("w").close()
        files.append(afile)
        self.assertEqual(sorted(prj.files()), sorted(files))

    def test_exists(self):
        """Test if a project with certain name exists."""

        manager = project.ProjectManager(self.mktemp())
        prj = manager.get_project(NAME)
        self.assertFalse(prj.exists())
        prj.create(NAME)
        self.assertTrue(prj.exists())

    def test_create(self):
        """Create a new project."""

        manager = project.ProjectManager(self.mktemp())
        prj = manager.get_project(NAME)
        prj.create()
        self.assertTrue(prj.exists())

    def test_create_already_exists(self):
        """
        Create a new project but a project with the same name already exists.
        """

        manager = project.ProjectManager(self.mktemp())
        prj = manager.get_project(NAME)
        prj.create()
        self.assertTrue(prj.exists())
        self.assertRaises(errors.ProjectExistsError, prj.create)
        prj.create(overwrite=True)

    def test_close(self):
        """A project cannot be closed if one or more bricks are running."""

        factory = stubs.Factory()
        brick = factory.new_brick("_stub", "test")
        brick.poweron()
        manager = project.ProjectManager(self.mktemp())
        prj = manager.get_project(NAME)
        self.assertRaises(errors.BrickRunningError, prj.close, factory)


class TestTarArchive(unittest.TestCase):

    def setUp(self):
        from virtualbricks import settings

        self.tmp = self.mktemp()
        self.patch(settings, "VIRTUALBRICKS_HOME", self.tmp)

    def run_process(self, exe, args, environ):
        self.exe = exe
        self.args = args
        self.environ = environ
        return defer.Deferred()

    def test_create(self):
        """Create a simple archive."""

        archive = project.BsdTgz()
        archive.create("test.tgz", ["a", "b"], run=self.run_process)
        self.assertEqual(self.args, ["cfzh", "test.tgz", "-C", self.tmp, "a",
                                     "b"])

    def test_create_images(self):
        """Create an archive with images."""

        tmp = FilePath(self.mktemp())
        tmp.makedirs()
        a = tmp.child("a")
        a.touch()
        b = tmp.child("b")
        b.touch()
        files = ["a", "b"]
        images = [("img_a", a.path), ("img_b", b.path)]
        archive = project.BsdTgz()
        archive.create("test.tgz", files, images, self.run_process)
        expected = ["cfzh", "test.tgz", "-C", self.tmp, "a", "b",
                    ".images/img_a", ".images/img_b"]
        self.assertEqual(self.args, expected)


PROJECT = """[Image:test_qcow2.qcow2]
path = /images/test qcow2.qcow2

[Image:vtatpa.martin.qcow2]
path = /images/vtatpa.martin.qcow2

[Qemu:test]
hda = vtatpa.martin.qcow2
name = test
privatehda = *
snapshot = *
use_virtio = *

link|sender|sw1|rtl8139|00:11:22:33:44:55
"""


class PseudoOrderedDict(dict):

    def __init__(self, arg):
        super(PseudoOrderedDict, self).__init__(arg)
        self._order = map(operator.itemgetter(0), arg)

    def __iter__(self):
        return iter(self._order)


class TestProjectEntry(unittest.TestCase):

    def setUp(self):
        fp = six.StringIO(PROJECT)
        self.entry = project.ProjectEntry.from_fileobj(fp)

    def test_get_images(self):
        self.assertEqual(self.entry.get_images(),
                         [(('Image', 'test_qcow2.qcow2'),
                           {'path': '/images/test qcow2.qcow2'}),
                          (('Image', 'vtatpa.martin.qcow2'),
                           {'path': '/images/vtatpa.martin.qcow2'})])

    def test_get_virtualmachines(self):
        self.assertEqual(self.entry.get_virtualmachines(),
                         [(("Qemu", "test"),
                           {"hda": "vtatpa.martin.qcow2",
                            "name": "test",
                            "privatehda": "*",
                            "snapshot": "*",
                            "use_virtio": "*"})])

    def test_get_disks(self):
        self.assertEqual(self.entry.get_disks(),
                         {"test": [("hda", "vtatpa.martin.qcow2")]})

    def test_device_for_image_empty(self):
        devs = list(self.entry.device_for_image("test_qcow2.qcow2"))
        self.assertEqual([], devs)

    def test_device_for_image(self):
        devs = list(self.entry.device_for_image("vtatpa.martin.qcow2"))
        self.assertEqual([("test", "hda")], devs)

    def test_dump(self):
        sections = {
            ("Image", "test_qcow2.qcow2"): {
                "path": "/images/test qcow2.qcow2"
            },
            ("Image", "vtatpa.martin.qcow2"): {
                "path": "/images/vtatpa.martin.qcow2"
            },
            ("Qemu", "test"): PseudoOrderedDict([
                ("hda", "vtatpa.martin.qcow2"),
                ("name", "test"),
                ("privatehda", "*"),
                ("snapshot", "*"),
                ("use_virtio", "*"),
            ]),
        }
        links = [("link", "sender", "sw1", "rtl8139", "00:11:22:33:44:55")]
        sio = six.StringIO()
        project.ProjectEntry(sections, links).dump(sio)
        self.assertEquals(sio.getvalue(), PROJECT)
