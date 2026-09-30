# Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
# Copyright (C) 2019 Virtualbricks team

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

"""A path of the machine of the bricks, completed from its folders."""

from twisted.internet import defer
from twisted.trial import unittest

from virtualbricks.tests.gui import has_display

if has_display:
    from gi.repository import Gtk

    from virtualbricks.gui.pathentry import PathCompletion


class FolderThere:
    """engine.folder() of the machine of the bricks: asked, answered later."""

    def __init__(self):
        self.asked = []

    def folder(self, path):
        answer = defer.Deferred()
        self.asked.append((path, answer))
        return answer

    def answer(self, entries, more=False, which=-1):
        self.asked[which][1].callback((entries, more))


class TestPathCompletion(unittest.TestCase):

    if not has_display:  # pragma: no cover
        skip = "GTK can't open a display"

    def setUp(self):
        self.engine = FolderThere()
        self.entry = Gtk.Entry()
        self.addCleanup(self.entry.destroy)
        self.completion = PathCompletion(self.engine, self.entry)

    def asked(self):
        return [path for path, _answer in self.engine.asked]

    def offered(self):
        return [row[0] for row in self.completion.store]

    def test_once_a_folder(self):
        self.entry.set_text("lab")
        self.assertEqual(self.asked(), [])
        self.entry.set_text("/lab/")
        self.engine.answer(["/lab/frr.qcow2", "/lab/images/"])
        self.assertEqual(self.offered(), ["/lab/frr.qcow2", "/lab/images/"])
        # the completion picks among those
        self.entry.set_text("/lab/fr")
        self.assertEqual(self.asked(), ["/lab/"])
        # another folder
        self.entry.set_text("/lab/images/")
        self.assertEqual(self.asked(), ["/lab/", "/lab/images/"])
        self.assertIs(self.entry.get_completion(), self.completion.completion)

    def test_a_folder_with_more(self):
        self.entry.set_text("/usr/lib/")
        self.engine.answer(["/usr/lib/a/"], more=True)
        self.entry.set_text("/usr/lib/py")
        self.assertEqual(self.asked(), ["/usr/lib/", "/usr/lib/py"])
        self.engine.answer(["/usr/lib/python3/"])
        self.assertEqual(self.offered(), ["/usr/lib/python3/"])
        # all there now
        self.entry.set_text("/usr/lib/pyt")
        self.assertEqual(len(self.asked()), 2)

    def test_an_answer_too_late(self):
        self.entry.set_text("/lab/")
        self.entry.set_text("/srv/")
        self.engine.answer(["/lab/frr.qcow2"], which=0)
        self.assertEqual(self.offered(), [])
        self.engine.answer(["/srv/labs/"], which=1)
        self.assertEqual(self.offered(), ["/srv/labs/"])

    def test_no_answer(self):
        self.entry.set_text("/lab/")
        self.engine.asked[0][1].errback(RuntimeError("lost"))
        self.assertEqual(self.offered(), [])

    def test_folders_only(self):
        entry = Gtk.Entry()
        self.addCleanup(entry.destroy)
        completion = PathCompletion(self.engine, entry, folders=True)
        entry.set_text("/lab/")
        self.engine.answer(["/lab/frr.qcow2", "/lab/images/"])
        self.assertEqual(
            [row[0] for row in completion.store], ["/lab/images/"]
        )
