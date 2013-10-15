import os
import functools

import gtk
from twisted.internet import defer
from twisted.python import filepath

from virtualbricks import project
from virtualbricks.gui import dialogs
from virtualbricks.tests import unittest, GtkTestCase, test_project


def gtk_null_iterations():
    return int(os.environ.get("VIRTUALBRICKS_GTK_ITERATIONS", 1000))


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

    def get_rows(self, usbdev):
        model = gtk.ListStore(str, str)
        view = gtk.TreeView(model)
        w = UsbDevWindowStub(view, usbdev)
        w._populate_model(model, OUTPUT.strip())
        selection = view.get_selection()
        _, rows = selection.get_selected_rows()
        return map(list, map(model.__getitem__, rows))

    def test_populate_model(self):
        self.assertEquals(self.get_rows([]), [])
        self.assertEquals(self.get_rows(["0a5c:2110"]),
                [["0a5c:2110", "Broadcom Corp. Bluetooth Controller"]])
        self.assertEquals(self.get_rows(["1d6b:0001"]),
                          [["1d6b:0001", "Linux Foundation 1.1 root hub"],
                           ["1d6b:0001", "Linux Foundation 1.1 root hub"],
                           ["1d6b:0001", "Linux Foundation 1.1 root hub"],
                           ["1d6b:0001", "Linux Foundation 1.1 root hub"],
                           ["1d6b:0001", "Linux Foundation 1.1 root hub"]])


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
        self.patch(project.manager, "export", self.export)
        model = gtk.TreeStore(bool, bool, str, str, object)
        self.dialog.include_images = True
        self.dialog.image_files = [("a", filepath.FilePath("/images/a"))]
        ancestor = filepath.FilePath("/")
        self.dialog.export(model, ancestor, "test.tgz")

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


def ignore(func, *args, **kwds):
    @functools.wraps(func)
    def wrapper(_):
        return func(*args, **kwds)
    return wrapper


def sort_model(model, iter1, iter2, column):
    return cmp(model[iter1][column], model[iter2][column])


class TestImportDialog(test_project.TestBase, GtkTestCase):

    def setUp(self):
        test_project.TestBase.setUp(self)
        self.dialog = dialogs.ImportDialog()
        self.assistant = self.dialog.widget

    def get_page(self, num):
        return self.assistant.get_nth_page(num)

    def block_prepare_signal(method):
        @functools.wraps(method)
        def wrapper(self):
            def cb(passthru):
                self.assistant.handler_unblock_by_func(
                    self.dialog.on_ImportDialog_prepare)
                return passthru
            self.assistant.handler_block_by_func(
                self.dialog.on_ImportDialog_prepare)
            return defer.maybeDeferred(method, self).addBoth(cb)
        return wrapper

    def go(self, name):
        return self.dialog.get_object(name)

    def get_archive(self):
        return self.go("filechooserbutton").get_filename()

    def set_archive(self, name):
        return self.go("filechooserbutton").set_filename(name)

    def set_project_name(self, name):
        self.go("prjname_entry").set_text(name)

    def get_project_name(self):
        return self.go("prjname_entry").get_text()

    def set_open_project(self, flag):
        self.go("opencheckbutton").set_active(flag)

    def set_overwrite_project(self, flag):
        self.go("overwritecheckbutton").set_active(flag)

    def test_initial_status_page_0(self):
        self.assert_not_visible(self.go("overwritecheckbutton"))
        self.assert_not_visible(self.go("warn_label"))
        self.assert_page_not_complete(self.assistant, 0)

    def test_project_exists(self):
        """
        If the project exists a warning and an option to overwrite are showed.
        """

        TESTNAME = "test"
        self.manager.create(TESTNAME)
        self.set_project_name(TESTNAME)
        self.assert_visible(self.go("overwritecheckbutton"))
        self.assert_visible(self.go("warn_label"))
        self.assert_page_not_complete(self.assistant, 0)

    def test_project_exists_overwrite(self):
        """If the overwrite checkbutton is active, the label is not shown."""

        TESTNAME = "test"
        self.manager.create(TESTNAME)
        self.set_project_name(TESTNAME)
        self.set_overwrite_project(True)
        self.assert_visible(self.go("overwritecheckbutton"))
        self.assert_not_visible(self.go("warn_label"))
        self.assert_page_complete(self.assistant, 0)

    def assert_not_fail(self, deferred):
        def eb(fail):
            self.fail("Operation failed unexpectedly. Error message: %s." %
                      fail.getErrorMessage())
            return fail
        return deferred.addErrback(eb)

    def step_1(self):
        self.patch(project, "manager", self.manager)
        self.set_project_name("test")
        self.assertEqual(self.get_project_name(), "test")
        self.set_overwrite_project(True)
        archive = os.path.join(os.path.dirname(__file__), "test.vbp")
        self.assertTrue(self.set_archive(archive))
        num_iter = gtk_null_iterations()
        for i in xrange(num_iter):  # :/
            gtk.main_iteration(False)
        self.assertIsNot(self.get_archive(), None,
                         "Archive project not set. This is a problem of gtk "
                         "2.24.10 and who knows what others versions. It this "
                         "assertion fails, increase the number of iterations "
                         "the gtk loop performes before the check. Actual "
                         "number of iterations: %s, try setting the "
                         "VIRTUALBRICKS_GTK_ITERATIONS environment variable "
                         "to with %s" % (num_iter, num_iter * 10))
        return self.dialog.step_1(self.assistant, self.get_page(1))

    def step_1_cb(self, _):
        # these values are hard coded in test.vbp
        self.assertEqual(self.dialog.get_project_name(), "test")
        self.assertEqual(self.dialog.get_open(), False)
        self.assertIsNot(self.dialog.project, None)
        self.assertEqual(self.dialog.imported_images, set())
        self.assertEqual(self.dialog.project_images, {"vtatpa.martin.qcow2":
                "/home/marco/.virtualenvs/virtualbricks/src/vb-debug/tmp/"
                "vtatpa.martin.qcow2"})
        self.assert_page_complete(self.assistant, 1)
        self.assert_current_page(self.assistant, 2)

    @block_prepare_signal
    def test_step_1(self):
        self.assistant.set_current_page(1)
        return self.assert_not_fail(self.step_1()).addCallback(self.step_1_cb)

    def get_imported_project_model(self):
        TEST_IMAGE1 = "test_image"
        TEST_IMAGE2 = "test_image2"
        IMG1 = "1.img"
        imported_images = set((TEST_IMAGE1, TEST_IMAGE2))
        project_images = {TEST_IMAGE1: "/" + IMG1}
        model = gtk.ListStore(str, object, bool)
        model.append((TEST_IMAGE1, self.vimages.child(IMG1), True))
        model.append((TEST_IMAGE2, self.vimages.child(TEST_IMAGE2), True))
        return imported_images, project_images, model

    @block_prepare_signal
    def test_step_2(self):
        self.dialog.project = self.manager.create("test")
        iimgs, pimgs, model = self.get_imported_project_model()
        self.dialog.imported_images = iimgs
        self.dialog.project_images = pimgs
        self.assertFalse(self.dialog.step2)
        cur_page = self.assistant.get_current_page()
        self.dialog.step_2(self.assistant, self.get_page(2))
        self.assertTrue(self.dialog.step2)
        self.assert_current_page(self.assistant, cur_page)
        model2 = self.go("liststore1")
        model2.set_default_sort_func(sort_model, 0)
        self.assert_tree_model_equal(model, model2)

    @block_prepare_signal
    def test_step_3(self):
        cur_page = self.assistant.get_current_page()
        iimgs, pimgs, _ = self.get_imported_project_model()
        self.dialog.project_images = pimgs
        self.dialog.step_3(self.assistant, self.get_page(3))
        self.assert_current_page(self.assistant, cur_page)
        model = gtk.ListStore(str, object)
        model.append(("test_image", None))
        self.assert_tree_model_equal(self.go("liststore2"), model)
        self.assert_page_not_complete(self.assistant, 3)

    @block_prepare_signal
    def test_step_4(self):
        cur_page = self.assistant.get_current_page()
        # self.dialog.step_4(self.assistant, self.get_page(4))
        self.assert_current_page(self.assistant, cur_page)
