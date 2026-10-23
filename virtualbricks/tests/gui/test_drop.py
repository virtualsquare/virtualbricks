# Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
# Copyright (C) 2026 Virtualbricks team

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

"""Files dropped on a window."""

import os

from twisted.trial import unittest

from virtualbricks.tests.gui import has_display, untranslated

if has_display:
    from gi.repository import Gdk, Gio, GObject, Gtk

    from virtualbricks.gui import drop


class FakeSelection:
    """The data of a drop."""

    def __init__(self, uris):
        self.uris = uris

    def get_uris(self):
        return self.uris


def uri(path):
    return Gio.File.new_for_path(path).get_uri()


def takes_files(widget):
    """Whether files dropped on widget go to it."""

    targets = widget.drag_dest_get_target_list()
    if targets is None:
        return False
    found, _info = targets.find(Gdk.Atom.intern("text/uri-list", False))
    return found


class TestDrop(unittest.TestCase):

    if not has_display:  # pragma: no cover
        skip = "GTK can't open a display"

    def setUp(self):
        self.root = os.path.abspath(self.mktemp())
        os.makedirs(self.root)
        self.dropped = []

    def file(self, name):
        path = os.path.join(self.root, name)
        with open(path, "wb"):
            pass
        return path

    def on_files(self, files, others):
        self.dropped.append((files, others))

    def test_take_files(self):
        box = Gtk.Box()
        self.assertFalse(takes_files(box))
        drop.take_files(box, self.on_files)
        self.assertTrue(takes_files(box))
        signal = GObject.signal_lookup("drag-data-received", Gtk.Widget)
        self.assertTrue(
            GObject.signal_has_handler_pending(box, signal, 0, False)
        )

    def test_received(self):
        path = self.file("lab.vbp")
        drop.received(
            Gtk.Box(),
            None,
            0,
            0,
            FakeSelection([uri(path)]),
            0,
            0,
            self.on_files,
        )
        self.assertEqual(self.dropped, [([path], [])])

    def test_files_of(self):
        first, second = self.file("a.vbp"), self.file("b.tar.gz")
        folder = os.path.join(self.root, "labs")
        os.mkdir(folder)
        gone = os.path.join(self.root, "gone.vbp")
        link = "https://example.org/lab.vbp"
        self.assertEqual(
            drop.files_of(
                [uri(first), link, uri(folder), uri(gone), uri(second)]
            ),
            ([first, second], [link, folder, gone]),
        )

    def test_refusal(self):
        untranslated(self)
        self.assertEqual(
            drop.refusal(["https://example.org/lab.vbp", "/home/labs"]),
            "Only the files of this computer can be imported, not "
            "https://example.org/lab.vbp, /home/labs",
        )
