import gtk

from virtualbricks.gui import dialogs
from virtualbricks.tests import unittest


class Object:
    pass


class UsbDevWindowStub(dialogs.UsbDevWindow):

    def __init__(self, treeview, usbdev):
        self.view = treeview
        self.gui = Object()
        self.vm = Object()
        self.vm.cfg = Object()
        self.vm.cfg.usbdevlist = self.usbdev

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
        self.assertEquals(self.get_rows(""), [])
        self.assertEquals(self.get_rows("0a5c:2110"),
                [["0a5c:2110", "Broadcom Corp. Bluetooth Controller"]])
        self.assertEquals(self.get_rows("1d6b:0001"),
                          [["1d6b:0001", "Linux Foundation 1.1 root hub"],
                           ["1d6b:0001", "Linux Foundation 1.1 root hub"],
                           ["1d6b:0001", "Linux Foundation 1.1 root hub"],
                           ["1d6b:0001", "Linux Foundation 1.1 root hub"],
                           ["1d6b:0001", "Linux Foundation 1.1 root hub"]])

