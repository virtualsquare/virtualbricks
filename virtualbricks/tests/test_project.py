from twisted.trial import unittest
from twisted.python import filepath

from virtualbricks import settings, project, configfile, errors


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
        prj = pm.create(name, factory)
        self.addCleanup(pm.close)
        return prj

    def test_new_project(self):
        f = FactoryStub()
        pm = self.create_project_manager()
        self.assertRaises(errors.InvalidNameError, pm.create, "../t", f)
        self.assertRaises(errors.InvalidNameError, pm.create, "/test", f)
        prj = pm.create("test", f)
        self.addCleanup(pm.close)
        self.assertTrue(prj.filepath.child(".project").isfile())
        self.assertRaises(errors.InvalidNameError, pm.create, "test", f)

    def restore_home(self):
        settings.VIRTUALBRICKS_HOME = settings.DEFAULT_HOME

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

    def test_restore_project_set_virtualbricks_home(self):
        self.addCleanup(self.restore_home)
        self.assertEqual(settings.VIRTUALBRICKS_HOME,
                         settings.DEFAULT_HOME)
        self.patch(configfile, "restore", lambda fa, fi: None)
        prj = self.create_project("test", FactoryStub())
        self.assertEqual(prj.path, settings.VIRTUALBRICKS_HOME)
        self.assertNotEqual(settings.VIRTUALBRICKS_HOME,
                            settings.DEFAULT_HOME)

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
