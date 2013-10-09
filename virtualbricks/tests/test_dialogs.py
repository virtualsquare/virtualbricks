import itertools

import gtk
from twisted.python import filepath

from virtualbricks import project
from virtualbricks.gui import dialogs
from virtualbricks.tests import unittest, GtkTestCase


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
        self.assertTreeModelEqual(tree1, tree2)

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
        self.assertTreeModelEqual(tree1, tree2)

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
        self.assertTreeModelEqual(tree1, tree2)

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
        ritr = tree2.append(None, (False, True, gtk.STOCK_DIRECTORY,
                                   self.prjpath.basename(), self.prjpath))
        Ai = tree2.append(ritr, (False, True, gtk.STOCK_DIRECTORY,
                                  A.basename(), A))
        tree2.append(Ai, (False, True, gtk.STOCK_FILE, a.basename(), a))
        tree2.append(ritr, (False, True, gtk.STOCK_FILE, b.basename(), b))
        self.assertTreeModelEqual(tree1, tree2)

    def test_export(self):
        self.patch(project.manager, "export", self.export)
        model = gtk.TreeStore(bool, bool, str, str, object)
        self.dialog.include_images = True
        self.dialog.image_files = [filepath.FilePath("/images/a")]
        ancestor = filepath.FilePath("/")
        self.dialog.export(model, ancestor, "test.tgz")

    def export(self, filename, files, images):
        for name in itertools.chain(files, images):
            self.assertIsInstance(name, str)


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
