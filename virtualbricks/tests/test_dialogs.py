import copy
import itertools

import gtk

from virtualbricks.gui import dialogs
from virtualbricks.tests import unittest


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

    def __init__(self):
        pass


class ExportProjectDialog(WindowStub, dialogs.ExportProjectDialog):

    pass

MODEL = {
    0: ([0, 1, gtk.STOCK_DIRECTORY, "root", None], {
        0: ([0, 1, gtk.STOCK_DIRECTORY, "A", None], {
            0: ([0, 1, gtk.STOCK_FILE, "a", None], {}),
            1: ([0, 1, gtk.STOCK_FILE, "b", None], {}),
            2: ([0, 1, gtk.STOCK_FILE, "c", None], {}),
        }),
        1: ([0, 1, gtk.STOCK_DIRECTORY, "B", None], {
            0: ([0, 1, gtk.STOCK_FILE, "a", None], {}),
            1: ([0, 1, gtk.STOCK_FILE, "b", None], {}),
            2: ([0, 1, gtk.STOCK_FILE, "c", None], {}),
        }),
        2: ([0, 1, gtk.STOCK_DIRECTORY, "C", None], {
            0: ([0, 1, gtk.STOCK_FILE, "a", None], {}),
            1: ([0, 1, gtk.STOCK_FILE, "b", None], {}),
            2: ([0, 1, gtk.STOCK_FILE, "c", None], {}),
        })
    })
}


class TestExportDialog(unittest.TestCase):

    def setUp(self):
        self.dialog = ExportProjectDialog()
        self.model = self.build_model()

    def build_model(self):
        model = gtk.TreeStore(bool, bool, str, str, object)
        for idx in MODEL:
            self.insert_children(model, None, idx, MODEL[idx][0],
                                 MODEL[idx][1])
        return model

    def insert_children(self, model, ancestor, position, row, children):
        parent = model.insert(ancestor, position, row)
        for idx in sorted(children):
            self.insert_children(model, parent, idx, children[idx][0],
                                 children[idx][1])

    def assertTreeEqual(self, model, dct):
        self.assertSubtreeEqual(model, model.get_iter_root(), dct, 0)

    def assertSubtreeEqual(self, model, itr, dct, idx):
        self.assertIn(idx, dct)
        value, children = dct[idx]
        self.assertEqual(value, list(model[itr]))
        itrc = model.iter_children(itr)
        for i in itertools.count():
            if not itrc:
                break
            self.assertSubtreeEqual(model, itrc, children, i)
            itrc = model.iter_next(itrc)

    def toggle(self, path):
        self.dialog.on_selected_cellrenderer_toggled(None, path, self.model)

    def modify_dict(self, tree, *toggled):
        for index, value in toggled:
            itr = map(int, index.split(":"))
            field = itr.pop()
            node = tree
            for idx in itr:
                node = node[idx]
            node[field] = value

    def test_selected_toggled(self):
        """Toggle a node and all descendants should be checked."""

        self.toggle("0:0")
        dct = copy.deepcopy(MODEL)
        self.modify_dict(dct, ("0:1:0:0:0", 1), ("0:1:0:1:0:0:0", 1),
                         ("0:1:0:1:1:0:0", 1), ("0:1:0:1:2:0:0", 1))
        self.assertTreeEqual(self.model, dct)

    def test_selected_toggled_all_children(self):
        """Selecting all children select the parent too."""

        self.toggle("0:0:0")
        self.toggle("0:0:1")
        self.toggle("0:0:2")
        dct = copy.deepcopy(MODEL)
        self.modify_dict(dct, ("0:1:0:0:0", 1), ("0:1:0:1:0:0:0", 1),
                         ("0:1:0:1:1:0:0", 1), ("0:1:0:1:2:0:0", 1))
        self.assertTreeEqual(self.model, dct)

    def test_selected_toggled_root(self):
        """Selecting root select all nodes."""

        self.toggle("0")
        dct = copy.deepcopy(MODEL)
        self.modify_dict(dct, ("0:0:0", 1), ("0:1:0:0:0", 1), ("0:1:1:0:0", 1),
                         ("0:1:2:0:0", 1), ("0:1:0:1:0:0:0", 1),
                         ("0:1:0:1:1:0:0", 1), ("0:1:0:1:2:0:0", 1),
                         ("0:1:1:1:0:0:0", 1), ("0:1:1:1:1:0:0", 1),
                         ("0:1:1:1:2:0:0", 1), ("0:1:2:1:0:0:0", 1),
                         ("0:1:2:1:1:0:0", 1), ("0:1:2:1:2:0:0", 1))
        self.assertTreeEqual(self.model, dct)
