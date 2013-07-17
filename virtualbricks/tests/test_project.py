import os
import errno
import tarfile
import StringIO
import shutil

from twisted.trial import unittest
from twisted.python import filepath
from twisted.internet import utils, defer

from virtualbricks import settings, project, configfile, errors, tests
from virtualbricks.tests import successResultOf, patch_settings, Skip


class FactoryStub:

    bricks = []

    def reset(self):
        pass


class TestProject(unittest.TestCase):

    def create_project_manager(self):
        path = filepath.FilePath(self.mktemp())
        path.makedirs()
        self.addCleanup(lambda old: settings.set("workspace", old),
                        settings.get("workspace"))
        settings.set("workspace", path.path)
        return project.ProjectManager()

    def create_project(self, name, factory):
        pm = self.create_project_manager()
        prj = pm.create(name, factory, False)
        self.addCleanup(pm.close, factory)
        return prj

    def restore_home(self):
        settings.VIRTUALBRICKS_HOME = settings.DEFAULT_HOME

    @Skip("restore change a global state")
    def test_restore_save(self):

        def save_restore(f, prjname):
            self.assertIs(f, factory)
            self.assertTrue(filepath.FilePath(prjname).exists())

        factory = FactoryStub()
        self.addCleanup(self.restore_home)
        prj = self.create_project("test", factory)
        self.patch(configfile, "restore", save_restore)
        self.patch(configfile, "save", save_restore)
        prj.save(factory)
        prj.restore(factory)

    @Skip("restore change a global state")
    def test_restore_project_set_virtualbricks_home(self):
        self.addCleanup(self.restore_home)
        self.assertEqual(settings.VIRTUALBRICKS_HOME,
                         settings.DEFAULT_HOME)
        self.patch(configfile, "restore", lambda fa, fi: None)
        prj = self.create_project("test", FactoryStub())
        self.assertEqual(prj.path, settings.VIRTUALBRICKS_HOME)
        self.assertNotEqual(settings.VIRTUALBRICKS_HOME,
                            settings.DEFAULT_HOME)

    @Skip("restore change a global state")
    def test_open_create_set_current(self):
        """Everytime ProjectManager's open or create are called,
        virtualbricks.project.current is set to the current project."""
        factory = FactoryStub()
        pm = self.create_project_manager()
        prj1 = pm.open("new1", factory, True)
        self.assertIs(project.current, prj1)
        prj2 = pm.create("new2", factory)
        self.addCleanup(pm.close)
        self.assertIs(project.current, prj2)
        prj3 = pm.open("new1", factory)
        self.assertIs(project.current, prj3)

    def test_files(self):
        prj = self.create_project("test", FactoryStub())
        files = [prj.filepath.child(".project")]
        self.assertEqual(list(prj.files()), files)
        afile = prj.filepath.child("file")
        afile.open("w").close()
        files.append(afile)
        self.assertEqual(sorted(prj.files()), sorted(files))


def qemu_img(*args):
    return utils.getProcessOutput("qemu-img", args, os.environ)


def grep(out, match):
    return [l for l in out.splitlines() if match in l]


def cut(lines, delimiter, field):
    ret = []
    for line in lines:
        try:
            ret.append(line.split(delimiter)[field])
        except IndexError:
            ret.append("")
    return ret


def call_shift(func):
    def wrapper(ignore, *args):
        return func(*args)
    return wrapper


class TestImport(unittest.TestCase):

    def setUp(self):
        self.project = self.mktemp()
        os.mkdir(self.project)
        self.archive = self.mktemp()
        dot_project = self.mktemp()
        open(dot_project, "w").close()
        tf = tarfile.open(self.archive, "w")
        tf.add(dot_project, ".project")
        tf.close()

    def test_remap_images_cb(self):
        sections = {("Image", "cucu"): {"path": "/vimages/cucu.img"}}
        prjentry = project.ProjectEntry(sections, [])
        project.manager._remap_images_cb({"cucu": "/newpath"}, prjentry)
        self.assertEqual(prjentry.get_images(),
                         [(("Image", "cucu"), {"path": "/newpath"})])

    def test_rebase(self):
        rebase_l = []

        class ProjectManagerMock(project.ProjectManager):
            def _real_rebase(self, backing_file, cow):
                rebase_l.append((backing_file, cow))
                return defer.succeed(None)

        tmp = self.mktemp()
        os.mkdir(tmp)
        path = filepath.FilePath(tmp)
        cow = path.child("test_hda.cow")
        cow.touch()
        prj = project.Project(path)
        sections = {("Image", "cucu"): {"path": "/vmimages/cucu.img"},
                    ("Qemu", "test"): {"hda": "cucu"}}
        prjentry = project.ProjectEntry(sections, [])
        manager = ProjectManagerMock()
        d = manager._rebase_cb(prj, prjentry)
        self.assertEqual(successResultOf(self, d), prj)
        self.assertEqual(rebase_l, [("/vmimages/cucu.img", cow.path)])

    def test_real_rebase(self):
        tmp = self.mktemp()
        os.mkdir(tmp)
        testdir = os.path.dirname(tests.__file__)
        shutil.copy(os.path.join(testdir, "test.img"), tmp)
        shutil.copy(os.path.join(testdir, "test2.img"), tmp)
        shutil.copy(os.path.join(testdir, "cow.img"), tmp)
        cow = os.path.join(tmp, "cow.img")
        deferred = qemu_img("info", cow)
        deferred.addCallback(grep, "backing")
        deferred.addCallback(cut, " ", 2)
        deferred.addCallback(self.assertEqual, ["test.img"])
        deferred.addCallback(call_shift(project.manager._real_rebase),
                             "test2.img", cow)
        deferred.addCallback(call_shift(qemu_img), "info", cow)
        deferred.addCallback(grep, "backing")
        deferred.addCallback(cut, " ", 2)
        deferred.addCallback(self.assertEqual, ["test2.img"])
        return deferred

    # def test_import(self):
    #     self.assertRaises(errors.InvalidArchiveError, project.manager.import_,
    #                       self.project, )


DUMP = """[Image:martin]
path = /vimages/cucu

link|sender|sw1|rtl8139|00:11:22:33:44:55
"""


class TestArchive(unittest.TestCase):

    def test_base(self):
        """If the file is not a valid archive, an error is raised."""
        filename = self.mktemp()
        exp = self.assertRaises(IOError, project.Archive, filename)
        self.assertEquals(exp.errno, errno.ENOENT)
        open(filename, "w").close()
        exp = self.assertRaises(tarfile.TarError, project.Archive, filename)
        tarfile.open(filename, "w").close()
        project.Archive(filename)

    def test_get_project(self):
        filename = self.mktemp()
        project_entry = self.mktemp()
        open(project_entry, "w").close()
        tarfile.open(filename, "w").close()
        archive = project.Archive(filename)
        self.assertRaises(KeyError, archive.get_project)
        tf = tarfile.open(filename, "w")
        tf.add(project_entry, ".project")
        tf.close()
        archive = project.Archive(filename)
        self.assertIsNot(None, archive.get_project())

    def test_project_entry_dump(self):
        sections = {("Image", "martin"): {"path": "/vimages/cucu"}}
        links = [("link", "sender", "sw1", "rtl8139", "00:11:22:33:44:55")]
        entry = project.ProjectEntry(sections, links)
        sio = StringIO.StringIO()
        entry.dump(sio)
        self.assertEquals(sio.getvalue(), DUMP)


class ProjectManager(project.ProjectManager):

    def __init__(self):
        self.restored = []

    def restore(self, project, factory):
        self.restored.append(project)
        return project

    def close(self):
        pass


class TestProjectManager(unittest.TestCase):

    def setUp(self):
        self.tmp = filepath.FilePath(self.mktemp())
        self.tmp.makedirs()
        patch_settings(self, workspace=self.tmp.path)
        self.manager = ProjectManager()

    def test_iter(self):
        self.tmp.child("child1").touch()
        prj1 = self.tmp.child("prj1")
        prj1.makedirs()
        prj1.child(".project").touch()
        self.tmp.child("prj2").makedirs()
        self.assertEqual(list(self.manager), ["prj1"])

    def test_open_fails(self):
        self.assertRaises(errors.InvalidNameError, self.manager.open,
                          "../ciccio", None)
        self.assertRaises(errors.ProjectNotExistsError, self.manager.open,
                          "test", None)
        self.tmp.child("test").touch()
        self.assertRaises(errors.ProjectNotExistsError, self.manager.open,
                          "test", None)

    def test_open(self):
        prjpath = self.tmp.child("prj1")
        prjpath.makedirs()
        prjpath.child(".project").touch()
        self.manager.open("prj1", None)
        prj = self.manager.restored[0]
        self.assertTrue(isinstance(prj, project.Project))
        self.assertEqual(prj.filepath, prjpath)

    def test_open_create(self):
        prj = self.manager.open("prj1", None, create=True)
        self.assertTrue(isinstance(prj, project.Project))
        self.assertEqual(prj.filepath, self.tmp.child("prj1"))
        self.assertTrue(prj.filepath.child(".project").exists())

    def test_create(self):
        self.assertRaises(errors.InvalidNameError, self.manager.create,
                          "../cucu", None)
        path = self.tmp.child("prj")
        path.makedirs()
        self.assertRaises(errors.ProjectExistsError, self.manager.create,
                          path.basename(), None)
        prj = self.manager.create("prj2", None, False)
        self.assertEqual(self.manager.restored, [])
        self.assertEqual(settings.get("current_project"), "new_project")
        prj = self.manager.create("prj3", None)
        self.assertEqual(self.manager.restored, [prj])
