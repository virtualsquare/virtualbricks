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

import gtk
from twisted.internet import defer
from twisted.python import filepath

from virtualbricks import project
from virtualbricks.virtualmachines import UsbDevice
from virtualbricks.gui import dialogs
from virtualbricks.tests import (unittest, GtkTestCase, failureResultOf,
                                 successResultOf, stubs)


class Object:
    pass


class UsbDevWindowStub(dialogs.UsbDevWindow):

    def __init__(self, treeview, usbdev):
        self.view = treeview
        self.vm = Object()
        self.vm.config = {"usbdevlist": usbdev}

    def get_object(self, name):
        return self.view


OUTPUT = """
Bus 003 Device 002: ID 0a5c:2110 Broadcom Corp. Bluetooth Controller
Bus 004 Device 002: ID 4168:1010
Bus 001 Device 001: ID 1d6b:0002 Linux Foundation 2.0 root hub
Bus 002 Device 001: ID 1d6b:0002 Linux Foundation 2.0 root hub
Bus 003 Device 001: ID 1d6b:0001 Linux Foundation 1.1 root hub
Bus 004 Device 001: ID 1d6b:0001 Linux Foundation 1.1 root hub
Bus 005 Device 001: ID 1d6b:0001 Linux Foundation 1.1 root hub
Bus 006 Device 001: ID 1d6b:0001 Linux Foundation 1.1 root hub
Bus 007 Device 001: ID 1d6b:0001 Linux Foundation 1.1 root hub
"""


class TestUsbDevWindow(unittest.TestCase):

    def setUp(self):
        self.dlg = dialogs.UsbDevWindow([])
        self.dlg.lDevs.set_data_source(self.dlg.parse_lsusb(OUTPUT.strip()))

    def get_selected_values(self):
        return self.dlg.tvDevices.get_selected_values()

    def set_selected_values(self, lst):
        self.dlg.tvDevices.set_selected_values(lst)

    def test_select_empty(self):
        self.assertEquals(self.get_selected_values(), ())

    def test_select_one(self):
        self.set_selected_values([UsbDevice("0a5c:2110")])
        self.assertEquals(self.get_selected_values(),
                          (UsbDevice("0a5c:2110"),))

    def test_select_mores(self):
        self.set_selected_values([UsbDevice("1d6b:0001")])
        self.assertEquals(self.get_selected_values(),
                          (UsbDevice("1d6b:0001"),) * 5)


class WindowStub(object):

    def __init__(self, _, prjpath, disk_images):
        super(WindowStub, self).__init__(_, prjpath, disk_images)


class ExportProjectDialog(WindowStub, dialogs.ExportProjectDialog):

    pass

MODEL = {
    (0, 1, gtk.STOCK_DIRECTORY, "root", None): {
        (0, 1, gtk.STOCK_DIRECTORY, "A", None): {
            (0, 1, gtk.STOCK_FILE, "a", None): {},
            (0, 1, gtk.STOCK_FILE, "b", None): {},
            (0, 1, gtk.STOCK_FILE, "c", None): {},
        },
        (0, 1, gtk.STOCK_DIRECTORY, "B", None): {
            (0, 1, gtk.STOCK_FILE, "a", None): {},
            (0, 1, gtk.STOCK_FILE, "b", None): {},
            (0, 1, gtk.STOCK_FILE, "c", None): {},
        },
        (0, 1, gtk.STOCK_DIRECTORY, "C", None): {
            (0, 1, gtk.STOCK_FILE, "a", None): {},
            (0, 1, gtk.STOCK_FILE, "b", None): {},
            (0, 1, gtk.STOCK_FILE, "c", None): {},
        }
    }
}


def build_model():
    model = gtk.TreeStore(bool, bool, str, str, object)
    root = MODEL.keys()[0]
    insert_children(model, None, root, MODEL[root])
    return model


def insert_children(model, ancestor, row, children):
    parent = model.append(ancestor, row)
    for node in sorted(children):
        insert_children(model, parent, node, children[node])


class TestExportDialog(GtkTestCase):

    def setUp(self):
        self.prjpath = filepath.FilePath(self.mktemp())
        self.dialog = ExportProjectDialog(None, self.prjpath, [])

    def toggle(self, path, model):
        self.dialog.on_selected_cellrenderer_toggled(None, path, model)

    def test_selected_toggled(self):
        """Toggle a node and all descendants should be checked."""

        tree1 = build_model()
        self.toggle("0:0", tree1)
        tree2 = build_model()
        tree2[0, 0][0] = 1
        tree2[0, 0, 0][0] = 1
        tree2[0, 0, 1][0] = 1
        tree2[0, 0, 2][0] = 1
        self.assert_tree_model_equal(tree1, tree2)

    def test_selected_toggled_all_children(self):
        """Selecting all children select the parent too."""

        tree1 = build_model()
        self.toggle("0:0:0", tree1)
        self.toggle("0:0:1", tree1)
        self.toggle("0:0:2", tree1)
        tree2 = build_model()
        tree2[0, 0][0] = 1
        tree2[0, 0, 0][0] = 1
        tree2[0, 0, 1][0] = 1
        tree2[0, 0, 2][0] = 1
        self.assert_tree_model_equal(tree1, tree2)

    def test_selected_toggled_root(self):
        """Selecting root select all nodes."""

        tree1 = build_model()
        self.toggle("0", tree1)
        tree2 = build_model()
        tree2[0, ][0] = 1
        tree2[0, 0][0] = 1
        tree2[0, 0, 0][0] = 1
        tree2[0, 0, 1][0] = 1
        tree2[0, 0, 2][0] = 1
        tree2[0, 1][0] = 1
        tree2[0, 1, 0][0] = 1
        tree2[0, 1, 1][0] = 1
        tree2[0, 1, 2][0] = 1
        tree2[0, 2][0] = 1
        tree2[0, 2, 0][0] = 1
        tree2[0, 2, 1][0] = 1
        tree2[0, 2, 2][0] = 1
        self.assert_tree_model_equal(tree1, tree2)

    def create_file(self, parent, name, isdir=False):
        child = parent.child(name)
        if isdir:
            child.makedirs()
        else:
            child.touch()
        return child

    def test_build_tree_path(self):
        """
        Internal files and required files should not be presented to the users.
        """

        self.prjpath.makedirs()
        A = self.create_file(self.prjpath, "A", True)
        a = self.create_file(A, "a")
        b = self.create_file(self.prjpath, "b")
        self.create_file(self.prjpath, ".project")
        self.create_file(self.prjpath, "vde.dot")
        self.create_file(self.prjpath, "vde_topology.plain")
        tree1 = gtk.TreeStore(bool, bool, str, str, object)
        tree2 = gtk.TreeStore(bool, bool, str, str, object)
        self.dialog.build_path_tree(tree1, self.prjpath)
        ritr = tree2.append(None, (True, True, gtk.STOCK_DIRECTORY,
                                   self.prjpath.basename(), self.prjpath))
        Ai = tree2.append(ritr, (True, True, gtk.STOCK_DIRECTORY,
                                  A.basename(), A))
        tree2.append(Ai, (True, True, gtk.STOCK_FILE, a.basename(), a))
        tree2.append(ritr, (True, True, gtk.STOCK_FILE, b.basename(), b))
        self.assert_tree_model_equal(tree1, tree2)

    # def test_build_tree_path_dont_recurse_internal_dirs(self):
    #     self.todo = "not implemented"
    #     raise NotImplementedError()

    def test_export(self):
        model = gtk.TreeStore(bool, bool, str, str, object)
        self.dialog.include_images = True
        self.dialog.image_files = [("a", filepath.FilePath("/images/a"))]
        ancestor = filepath.FilePath("/")
        self.dialog.export(model, ancestor, "test.tgz", self.export)

    def export(self, filename, files, images):
        for name in files:
            self.assertIsInstance(name, str)
        for name, path in images:
            self.assertIsInstance(name, str)
            self.assertIsInstance(path, str)


class Container:

    def __init__(self, children=None, **kwds):
        self.children = children or []
        self.__dict__.update(kwds)

    def foreach(self, function, data):
        function(self, data)
        for child in self.children:
            child.foreach(function, data)

    def get_data(self, name):
        return self.__dict__.get(name, None)


class TestImageMapDialog(unittest.TestCase):

    def test_accumulate_data(self):
        c1 = Container(data="a")
        c2 = Container(data="b")
        root = Container((c1, c2))
        lst = dialogs.accumulate_data(root, "data")
        expected = [("a", c1), ("b", c2)]
        self.assertEqual(lst, expected)


class ImportDialogStub:

    project = None
    images = None
    archive_path = None
    destroied = False

    def __init__(self, project_name=None, archive=None, overwrite=False,
                 page=0):
        self.project_name = project_name
        self.archive = archive
        self.curr_page = page
        self.overwrite = overwrite
        self.page_complete = {}

    def set_page_complete(self, page=None, complete=True):
        self.page_complete[page or self.curr_page] = complete

    def get_current_page(self):
        return self.curr_page

    def goto_next_page(self):
        self.curr_page += 1

    def get_project_name(self):
        return self.project_name

    def set_project_name(self, name):
        self.project_name = name

    def get_archive_path(self):
        return self.archive

    def set_archive(self, path):
        self.archive = path

    def get_overwrite(self):
        return self.overwrite

    def set_overwrite(self, value):
        self.overwrite = bool(value)

    def destroy(self):
        assert not self.destroied, "Dialog already destroied"
        self.destroied = True

    def get_object(self, name):
        return None


class TestHumbleImport(GtkTestCase):

    project_name = "test"
    archive = "/import/project.vbp"
    overwrite = False
    page = 0
    extract_args = None

    def setUp(self):
        self.manager = project.ProjectManager(self.mktemp())
        self.humble = dialogs._HumbleImport()
        self.dialog = ImportDialogStub(self.project_name, self.archive,
                                       self.overwrite, self.page)

    def assert_page_complete(self, page, msg=None):
        if msg is None:
            msg = "Page %s is not set as complete" % page
        self.assertIn(page, self.dialog.page_complete, msg)
        self.assertTrue(self.dialog.page_complete[page], msg)

    def assert_page_not_complete(self, page, msg=None):
        if msg is None:
            msg = "Page %s is set as complete" % page
        if page in self.dialog.page_complete:
            self.assertFalse(self.dialog.page_complete[page], msg)

    def assert_current_page(self, num, msg=None):
        curr = self.dialog.get_current_page()
        if not msg:
            msg = ("Wrong assistant current page. Actual page is {0}, "
                   "expected {1}".format(curr, num))
        self.assertEqual(num, curr, msg)

    def extract(self, *args):
        self.extract_args = args
        prj = self.manager.get_project(self.dialog.project_name)
        prj.create()
        return defer.succeed(prj)

    def assert_extract_not_called(self, msg=None):
        if not msg:
            msg = ("extract callback called with the following arguments: "
                   "%s" % (self.extract_args, ))
        self.assertIs(self.extract_args, None, msg)

    def assert_extract_called_with(self, args, msg=None):
        if not msg:
            msg = ("extract callback called with the following "
                   "arguments:\n%s\n, expected:\n%s" % (self.extract_args,
                                                        args))
        self.assertIsNot(self.extract_args, None,
                         "extract callback not called")
        self.assertEqual(self.extract_args, args, msg)

    def assert_project_exists(self, name, msg=None):
        if not msg:
            msg = "Project %s does not exists" % name
        self.assertTrue(self.manager.get_project(name).exists(), msg)

    def assert_project_does_not_exists(self, name, msg=None):
        if not msg:
            msg = "Project %s does exists" % name
        self.assertFalse(self.manager.get_project(name).exists(), msg)


class TestImportStep1(TestHumbleImport):

    page = 1

    def setUp(self):
        TestHumbleImport.setUp(self)
        self.model = gtk.ListStore(str, object, bool)
        self.ipath = filepath.FilePath(self.manager.path).child("vimages")

    def test_same_archive_dont_extract(self):
        """If the archive is not changed, don't extract it again."""

        self.humble.step_1(self.dialog, self.model, self.ipath, self.extract)
        self.extract_args = None
        self.humble.step_1(self.dialog, self.model, self.ipath, self.extract)
        self.assert_extract_not_called()

    def test_extract_args(self):
        """
        The extract function is called with a temporary name and the path of
        the archive.
        """

        self.humble.step_1(self.dialog, self.model, self.ipath, self.extract)
        self.assertNotEqual(self.extract_args[0],
                            self.dialog.get_project_name())
        self.assertEqual(self.extract_args[1], self.dialog.get_archive_path())

    def test_project_delete(self):
        """
        Step1 -> next -> extract -> step2 -> back -> step1 -> change archive ->
        next -> step 2

        The user has changed the archive so delete the extracted project.
        """

        self.dialog.set_project_name("test_delete")
        self.dialog.set_archive("/test_delete.vbp")
        self.humble.step_1(self.dialog, self.model, self.ipath, self.extract)
        self.assert_project_exists("test_delete")
        self.dialog.set_archive("/test.vbp")
        self.dialog.set_project_name("test")
        self.humble.step_1(self.dialog, self.model, self.ipath, self.extract)
        self.assert_project_does_not_exists("test_delete")

    def test_import_error(self):
        """If the import fails, destroy the assistant."""

        extract = lambda *a: defer.fail(RuntimeError())
        d = self.humble.step_1(self.dialog, self.model, self.ipath, extract)
        failureResultOf(self, d, RuntimeError)
        self.flushLoggedErrors(RuntimeError)
        self.assertTrue(self.dialog.destroied)

    def test_fill_model(self):
        """Found some image, fill the model set the page as complete."""

        def extract(name, path):
            prj = self.manager.get_project(name)
            prj.create()
            # fake some image
            fp = filepath.FilePath(prj.path).child(".images")
            fp.makedirs()
            fp.child("debian7.img").touch()
            fp.child("ubuntu.img").touch()
            self.extract_args = (name, path)
            return defer.succeed(prj)

        successResultOf(self, self.humble.step_1(self.dialog, self.model,
                                                 self.ipath, extract))
        model = gtk.ListStore(str, object, bool)
        model.append(("debian7.img", self.ipath.child("debian7.img"), True))
        model.append(("ubuntu.img", self.ipath.child("ubuntu.img"), True))
        model1s = gtk.TreeModelSort(self.model)
        model1s.set_sort_column_id(0, gtk.SORT_ASCENDING)
        model2s = gtk.TreeModelSort(model)
        model2s.set_sort_column_id(0, gtk.SORT_ASCENDING)
        self.assert_tree_model_equal(model1s, model2s)


# class TestHumbleImportStep2(TestHumbleImport):

#     page = 2

#     def setUp(self):
#         TestHumbleImport.setUp(self)
#         self.model = gtk.ListStore(str, object, bool)
#         self.ipath = self.manager.project_path("vimages")
#         # self.dialog.project = self.project = self.manager.create("test")
#         # self.dialog.images = {}

    # def test_step_2_commit_page(self):
    #     """No images are extracted, go to the next page."""

    #     self.humble.step_2(self.dialog, self.model, self.ipath)
    #     self.assert_page_commit()
    #     self.assert_current_page(3)

# class TestHumbleImportStep3(TestHumbleImport):

    # page = 3

    # def setUp(self):
    #     TestHumbleImport.setUp(self)
    #     self.dialog.images = {}
    #     self.store1 = gtk.ListStore(str, object, bool)
    #     self.store2 = gtk.ListStore(str, object)

    # def test_no_images(self):
    #     """
    #     If the project does not require any image it should be importable.
    #     """

    #     self.assertEqual(len(self.dialog.images), 0)
    #     self.humble.step_3(self.dialog, self.store1, self.store2)
    #     self.assert_page_complete(3)

    # def test_simple(self):
    #     """
    #     The archive does not include images and the project uses one. The
    #     assistant is stopped to this step.
    #     """

    #     self.dialog.images["test_image"] = "/vimages/test.img"
    #     self.humble.step_3(self.dialog, self.store1, self.store2)
    #     self.assert_page_not_complete(3)

    # def test_one_image_mapped(self):
    #     """The archive include one image used by the project."""

    #     self.dialog.images["test_image"] = ""
    #     self.store1.append(("test_image", "/vimages/test.img", True))
    #     self.humble.step_3(self.dialog, self.store1, self.store2)
    #     self.assert_page_complete(3)

    # def test_one_image_not_mapped(self):
    #     """The project require one image but is not mapped."""

    #     self.dialog.images["test_image"] = ""
    #     self.humble.step_3(self.dialog, self.store1, self.store2)
    #     self.assert_page_not_complete(3)


# class TestHumbleImportStep4(TestHumbleImport):

    # page = 4

    # def setUp(self):
    #     TestHumbleImport.setUp(self)
    #     self.dialog.images = {}
    #     self.store1 = gtk.ListStore(str, object, bool)
    #     self.store2 = gtk.ListStore(str, object)
    #     self.dialog.project = self.project = self.manager.create("test")

    # def test_no_come_back(self):
    #     """Step 4 does not permit to come back."""

    #     self.humble.step_4(self.dialog, self.store1, self.store2)
    #     self.assert_page_commit()

    # def make_src_dest(self, *names):
    #     source = filepath.FilePath(self.mktemp())
    #     source.makedirs()
    #     dest = filepath.FilePath(self.mktemp())
    #     dest.makedirs()
    #     ret = [source, dest]
    #     for name in names:
    #         src = source.child(name)
    #         src.touch()
    #         dst = dest.child(name)
    #         ret.extend((src, dst))
    #     return ret

    # def test_save_images(self):
    #     """Move the selected images."""

    #     NAME1, NAME2 = "image1", "image2"
    #     src, _, _, dimg1, _, dimg2 = self.make_src_dest(NAME1, NAME2)
    #     self.store1.append((NAME1, dimg1, True))
    #     self.store1.append((NAME2, dimg2, False))
    #     d = self.humble.save_images(self.store1, src)
    #     self.assertEqual(d, {NAME1: dimg1})

    # def test_remap_images(self):
    #     """Remap the images """


class AssistantStub:

    def __init__(self):
        self.completed = {}
        self.current_page = 0
        self.pages = []

    def get_nth_page(self, num):
        try:
            return self.pages[num]
        except IndexError:
            return None

    def get_current_page(self):
        return self.current_page

    def set_page_complete(self, page, complete):
        self.completed[page] = complete


class ImportDialog(dialogs.ImportDialog):

    assistant = None

class TestImportDialog(unittest.TestCase):

    def setUp(self):
        self.factory = stubs.FactoryStub()
        self.dialog = ImportDialog(self.factory)
        self.dialog.assistant = self.assistant = AssistantStub()

    def assert_page_complete(self, page, msg=None):
        if not msg:
            msg = "Page is not set as completed."
        self.assertIn(page, self.assistant.completed, msg)
        self.assertTrue(self.assistant.completed[page], msg)

    def test_set_page_complete(self):
        page = object()
        self.assistant.pages = [page]
        self.dialog.set_page_complete()
        self.assert_page_complete(page)
