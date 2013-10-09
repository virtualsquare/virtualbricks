import os
import StringIO
import operator

from twisted.trial import unittest
from twisted.python import filepath, failure
from twisted.internet import defer, error

from virtualbricks import settings, project, configfile, errors
from virtualbricks.tests import patch_settings, stubs


class TestBase(object):

    def setUp(self):
        self.tmp = filepath.FilePath(self.mktemp())
        self.tmp.makedirs()
        patch_settings(self, workspace=self.tmp.path,
                       current_project="new_project")
        self.manager = project.ProjectManager()
        self.factory = stubs.FactoryStub()
        self.addCleanup(self.manager.close, self.factory)

    def create_project(self, name):
        prj = self.tmp.child(name)
        prj.makedirs()
        prj.child(".project").touch()
        return prj


class TestProject(TestBase, unittest.TestCase):

    def assert_initial_status(self):
        self.assertIs(project.current, None)
        self.assertEqual(settings.VIRTUALBRICKS_HOME, settings.DEFAULT_HOME)

    def test_restore_save(self):
        def save_restore(f, prjname):
            self.assertIs(f, self.factory)
            self.assertTrue(filepath.FilePath(prjname).exists())

        self.assert_initial_status()
        prj = self.manager.create("test", self.factory, False)
        self.patch(configfile, "restore", save_restore)
        self.patch(configfile, "save", save_restore)
        prj.save(self.factory)
        prj.restore(self.factory)

    def test_restore_project_set_virtualbricks_home(self):
        self.assert_initial_status()
        self.patch(configfile, "restore", lambda fa, fi: None)
        prj = self.manager.create("test", self.factory)
        self.assertEqual(prj.path, settings.VIRTUALBRICKS_HOME)
        self.assertNotEqual(settings.VIRTUALBRICKS_HOME,
                            settings.DEFAULT_HOME)

    def test_open_create_set_current(self):
        """Everytime ProjectManager's open or create are called,
        virtualbricks.project.current is set to the current project."""

        PROJECT1 = "new1"
        PROJECT2 = "new2"
        self.assert_initial_status()
        self.manager.create(PROJECT1, self.factory, False)
        prj1 = self.manager.open(PROJECT1, self.factory)
        self.assertIs(project.current, prj1)
        prj2 = self.manager.create(PROJECT2, self.factory)
        self.assertIs(project.current, prj2)
        prj3 = self.manager.open(PROJECT1, self.factory)
        self.assertIs(project.current, prj3)
        # Two projects returned by two manager.open are different
        self.assertIsNot(prj1, prj3)

    def test_files(self):
        self.assert_initial_status()
        prj = self.manager.create("test", self.factory, False)
        files = [prj.filepath.child(".project")]
        self.assertEqual(list(prj.files()), files)
        afile = prj.filepath.child("file")
        afile.open("w").close()
        files.append(afile)
        self.assertEqual(sorted(prj.files()), sorted(files))


class TestProjectManager(TestBase, unittest.TestCase):

    def test_iter(self):
        """Returns only prooved projects."""

        # a file is not a project
        self.tmp.child("child1").touch()
        self.create_project("prj1")
        # a directory without a .project file is not a project
        self.tmp.child("prj2").makedirs()
        self.assertEqual(list(self.manager), ["prj1"])

    def test_open_project(self):
        """Simple open test."""

        prjpath = self.create_project("prj1")
        prj = self.manager.open("prj1", self.factory)
        self.assertTrue(isinstance(prj, project.Project))
        self.assertEqual(prj.filepath, prjpath)

    def test_open_project_invalid_name(self):
        """Name could not contains path traversal."""

        self.assertRaises(errors.InvalidNameError, self.manager.open,
                          "../ciccio", None)

    def test_open_project_does_not_exists(self):
        """Try to open a project that does not exists."""

        self.addCleanup(self.manager.close, self.factory)
        self.assertRaises(errors.ProjectNotExistsError, project.manager.open,
                          "project", self.factory)

    def test_open_project_does_not_exists_dot_project(self):
        """Try to open a project but the .project file does not exists."""

        prj = self.create_project("project")
        prj.child(".project").remove()
        self.assertFalse(prj.child(".project").isfile())
        self.assertRaises(errors.ProjectNotExistsError, project.manager.open,
                          "project", self.factory)

    def test_create_project(self):
        """Create a project."""

        self.assertEqual(settings.get("current_project"), "new_project")
        prj = self.manager.create("prj", self.factory)
        self.assertEqual(settings.get("current_project"), prj.name)
        self.assertTrue(prj.dot_project().isfile())

    def test_create_project_already_exists(self):
        """Create a project but it exists already."""

        self.create_project("prj")
        self.assertRaises(errors.ProjectExistsError, self.manager.create,
                          "prj", self.factory)

    def test_restore_last_project(self):
        """Restore last used project."""

        settings.set("current_project", "prj")
        self.create_project("prj")
        prj = project.restore_last(self.factory)
        self.assertEqual(prj.name, "prj")

    def test_restore_last_project_not_exists(self):
        """
        If the last project does not exists, don't create a new one with the
        same name but use a default name.
        """

        events = []

        def append(ev):
            events.append(ev)

        settings.set("current_project", "prj")
        self.assertFalse(self.tmp.child("prj").isdir())
        project.logger.publisher.addObserver(append)
        self.addCleanup(project.logger.publisher.removeObserver, append)
        prj = project.restore_last(self.factory)
        self.assertEqual(prj.name, settings.DEFAULT_PROJECT + "_0")

    def test_delete_project(self):
        """If a project does not exists, the error is not raised."""

        fp = self.tmp.child("prj")
        self.assertFalse(fp.exists())
        self.manager.delete("prj")
        self.create_project("prj")
        fp.changed()
        self.assertTrue(fp.exists())
        self.assertTrue(fp.child(".project").exists())
        self.manager.delete("prj")
        fp.changed()
        self.assertFalse(fp.exists())


class TestImport(TestBase, unittest.TestCase):

    def assert_project_equal(self, project, name, vbp):
        """
        These values are hard coded in the virtualbricks/tests/test.vbp file.
        """

        self.assertEqual(project.name, name)
        self.assertTrue(project.filepath.exists())
        self.assertEqual([project.name], list(self.manager))
        self.assertTrue(project.dot_project().exists())

    # def walk_tar(self, vbp):
    #     return tarfile.open(vbp).getnames()

    def get_vbp(self):
        return os.path.join(os.path.dirname(__file__), "test.vbp")

    def null_mapper(self, i):
        return defer.succeed(())

    def patch_rebase_should_fail(self):
        self.manager._ProjectManager__rebase = lambda *a: 1 / 0

    def assert_defer_fail(self, fail, *errors):
        self.assertIsInstance(fail, failure.Failure,
                              "Deferred succeeded (%r returned)" % (fail, ))
        self.assertIsNot(fail.check(*errors), None,
                         "%s raised instead of %s:\n %s" % (
                             fail.type, [e.__name__ for e in errors],
                             fail.getTraceback()))

    def test_import_wrong_file_type(self):
        """Raise an exception if the file is not a valid .vbp."""

        d = self.manager.import2("test_project", __file__, None, None)
        return d.addErrback(self.assert_defer_fail, error.ProcessTerminated)

    def test_import(self):
        """Simple import test."""

        PROJECT_NAME = "test_import"
        vbp = self.get_vbp()
        d = self.manager.import2(PROJECT_NAME, vbp, self.factory,
                                 lambda i: defer.succeed(()), False)
        return d.addCallback(self.assert_project_equal, PROJECT_NAME, vbp)

    def test_import2(self):
        """Simple import test."""

        PROJECT_NAME = "test_import"
        vbp = self.get_vbp()
        d = self.manager.import2(PROJECT_NAME, vbp, self.factory,
                                 self.null_mapper, False)
        return d.addCallback(self.assert_project_equal, PROJECT_NAME, vbp)

    def test_failed_import_does_not_create_project(self):
        """If an import is failed, the project is not created."""

        def assert_cb(_):
            self.assertEqual([], list(self.manager))

        self.patch_rebase_should_fail()
        d = self.manager.import2("test", self.get_vbp(), self.factory,
                                 self.null_mapper)
        return d.addErrback(assert_cb)

    def test_import_failed_does_not_call_restore(self):
        """If manager.import fails, manager.restore is not called."""

        def assert_cb(_, l):
            self.assertEqual(l, [])

        l = []
        self.manager.restore = lambda p, f: l.append(1)
        self.patch_rebase_should_fail()
        d = self.manager.import2("test", self.get_vbp(), self.factory,
                                 self.null_mapper)
        return d.addErrback(assert_cb, l)

    def get_entry(self, string):
        return project.ProjectEntry.from_fileobj(StringIO.StringIO(string))

    def prepare_rebase(self):
        self.args = []
        self.manager._real_rebase = self.real_rebase

    def real_rebase(self, backing_file, cow):
        self.args.append((backing_file, cow))
        return defer.succeed(None)

    def assert_rebase(self, _, expected):
        self.assertEqual(self.args, expected)

    def rebase(self, mapp=(), entry="", project=None):
        if isinstance(entry, basestring):
            entry = self.get_entry(PROJECT)
        if project is None:
            project = self.manager.create("test", self.factory, False)
        self.prepare_rebase()
        return self.manager._ProjectManager__rebase(mapp, entry, project)

    def test_nothing_rebase(self):
        """If there no images to map, don't rebase."""

        result = self.rebase()
        self.assertIs(result, None)
        self.assert_rebase(None, [])

    def test_rebase_images_are_not_used(self):
        """Unused images are not rebased."""

        mapp = [("test_qcow2.qcow2", "")]
        d = self.rebase(mapp, PROJECT)
        return d.addCallback(self.assert_rebase, [])

    def test_rebase_empty(self):
        """If the path is empty do not rebase."""

        mapp = [("vtatpa.martin.qcow2", "")]
        project = self.manager.create("test", self.factory, False)
        # create a fake cow file
        project.filepath.child("test_hda.cow").touch()
        d = self.rebase(mapp, PROJECT, project)
        return d.addCallback(self.assert_rebase, [])


class TestTarArchive(unittest.TestCase):

    def setUp(self):
        self.exe = None
        self.args = []
        self.environ = None
        self.archive = project.BsdTgz()
        self.tmp = self.mktemp()
        self.patch(settings, "VIRTUALBRICKS_HOME", self.tmp)

    def run_process(self, exe, args, environ):
        self.exe = exe
        self.args = args
        self.environ = environ
        return defer.Deferred()

    def test_create(self):
        """Create a simple archive."""

        self.archive.create("test.tgz", ["a", "b"],
                            run=self.run_process)
        self.assertEqual(self.args, ["cfzh", "test.tgz", "-C", self.tmp, "a",
                                     "b"])

    def test_create_images(self):
        """Create an archive with images."""

        tmp = filepath.FilePath(self.mktemp())
        tmp.makedirs()
        a = tmp.child("a")
        a.touch()
        b = tmp.child("b")
        b.touch()
        files = ["a", "b"]
        images = [a.path, b.path]
        self.archive.create("test.tgz", files, images, self.run_process)
        expected = ["cfzh", "test.tgz", "-C", self.tmp, "a", "b", ".images/a",
                    ".images/b"]
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


class PseudoOerderedDict(dict):

    def __init__(self, arg):
        super(PseudoOerderedDict, self).__init__(arg)
        self._order = map(operator.itemgetter(0), arg)

    def __iter__(self):
        return iter(self._order)


class TestProjectEntry(unittest.TestCase):

    def setUp(self):
        self.entry = project.ProjectEntry.from_fileobj(StringIO.StringIO(
            PROJECT))

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
            ("Qemu", "test"): PseudoOerderedDict([
                ("hda", "vtatpa.martin.qcow2"),
                ("name", "test"),
                ("privatehda", "*"),
                ("snapshot", "*"),
                ("use_virtio", "*"),
            ]),
        }
        links = [("link", "sender", "sw1", "rtl8139", "00:11:22:33:44:55")]
        sio = StringIO.StringIO()
        project.ProjectEntry(sections, links).dump(sio)
        self.assertEquals(sio.getvalue(), PROJECT)
