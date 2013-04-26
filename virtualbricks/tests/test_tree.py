import gtk

from virtualbricks.gui import tree
from virtualbricks.tests import unittest


class GladefileStub:

    def get_widget(self, name):
        return gtk.TreeView()


class GuiStub:

    gladefile = GladefileStub()


class TestVBTree(unittest.TestCase):

    def test_custom_model(self):
        model = gtk.ListStore(str)
        vbtree = tree.VBTree(GuiStub(), None, model, [str], ["test"])

