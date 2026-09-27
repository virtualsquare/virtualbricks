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


"""The library of the disk images."""

import json
import os

from twisted.internet import defer

from virtualbricks.config import images
from virtualbricks.config.images import RunningError
from virtualbricks.config.workspace import OpenProject
from virtualbricks.tests import FakeLogger
from virtualbricks.tests.gui import GuiTestCase, has_display

if has_display:
    from gi.repository import Gtk

    from virtualbricks.gui.windows import disklibrary

INFO = {"format": "qcow2", "virtual-size": 4e9, "actual-size": 1.9e9}


class TestDiskLibrary(GuiTestCase):

    def setUp(self):
        super().setUp()
        self.logger = FakeLogger()
        self.patch(disklibrary, "logger", self.logger)
        self.window = disklibrary.DisksLibraryWindow(self.factory)
        self.addCleanup(self.window.get_root_widget().destroy)

    def test_rename_updates_the_disks(self):
        image = self.image("deb")
        vm = self.factory.new_brick("qemu", "vm")
        vm.disk("hda").set_image(image)
        self.window._show_edit_screen(image)
        self.window.name_entry.set_text("debian")
        self.window.on_save_button_clicked(None)
        self.assertIs(self.factory.get_image_by_name("debian"), image)
        self.assertIsNone(self.factory.get_image_by_name("deb"))
        self.assertEqual(vm.config.hda, "debian")
        self.assertIsNone(self.window._disk_image)

    def test_invalid_name(self):
        image = self.image("deb")
        self.window._show_edit_screen(image)
        self.window.name_entry.set_text("1 bad")
        self.window.on_save_button_clicked(None)
        self.assertEqual(image.get_name(), "deb")
        self.assertEqual(self.logger.levels(), ["error"])
        # the form stays open to fix the name
        self.assertIs(self.window._disk_image, image)


class FakeDialog:
    def __init__(self, shown, *args):
        self.shown = shown
        self.args = args

    def show(self, parent):
        self.shown.append((self.args, parent))


class TestTheList(GuiTestCase):

    def setUp(self):
        super().setUp()
        self.manager.current = OpenProject(self.folder("lab"), None)
        self.logger = FakeLogger()
        self.patch(disklibrary, "logger", self.logger)
        self.infos = []
        self.failing = False
        self.patch(images.spawn, "qemu_img", self.qemu_img)
        self.frr = self.image("frr")
        self.window = disklibrary.DisksLibraryWindow(self.factory)
        self.addCleanup(self.window.get_root_widget().destroy)

    def qemu_img(self, args):
        self.infos.append(args[-1])
        if self.failing:
            return defer.fail(RuntimeError("qemu-img: not found"))
        return defer.succeed(json.dumps(INFO))

    def vm(self, name, device="hda", private=True):
        vm = self.factory.new_brick("qemu", name)
        vm.set({device: "frr", "private" + device: private})
        return vm

    def cell(self, set_cell, data=None):
        cell = Gtk.CellRendererText()
        model = self.window._tree_model
        set_cell(None, cell, model, model.get_iter_first(), data)
        return cell.props.text

    def test_the_disks(self):
        # all the disks, and those with a private copy
        self.vm("r1")
        self.vm("r2")
        self.vm("vm", "hdb", private=False)
        window = self.window
        self.assertEqual(self.cell(window.set_cell_used_by, self.factory), "3")
        self.assertEqual(self.cell(window.set_cell_cows, self.factory), "2")

    def test_the_disk_that_writes_the_image(self):
        vm = self.vm("vm", "hdb", private=False)
        self.assertEqual(self.cell(self.window.set_cell_master_brick), "")
        self.frr.acquire(vm.disk("hdb"))
        self.assertEqual(
            self.cell(self.window.set_cell_master_brick), "vm (hdb)"
        )

    def test_the_size(self):
        changed = []
        self.window._tree_model.connect(
            "row-changed", lambda model, path, itr: changed.append(path)
        )
        # read the first time the list asks
        self.assertEqual(
            self.cell(self.window.set_cell_size), "\N{HORIZONTAL ELLIPSIS}"
        )
        self.assertEqual(len(changed), 1)
        self.assertEqual(
            self.cell(self.window.set_cell_size), "4.0 GB disk, 1.9 GB on disk"
        )
        self.assertEqual(self.infos, [self.frr.get_path()])

    def test_a_missing_file(self):
        os.remove(self.frr.get_path())
        self.assertEqual(self.cell(self.window.set_cell_size), "File missing")
        self.assertEqual(self.infos, [])

    def test_a_file_that_cant_be_read(self):
        self.failing = True
        self.cell(self.window.set_cell_size)
        self.assertEqual(self.cell(self.window.set_cell_size), "Unknown")
        self.assertEqual(len(self.infos), 1)

    def test_remove_asks(self):
        shown = []
        self.patch(
            disklibrary,
            "RemoveImageConfirmDialog",
            lambda *args: FakeDialog(shown, *args),
        )
        self.window._show_edit_screen(self.frr)
        self.window.on_remove_button_clicked(None)
        self.assertEqual(
            shown, [((self.factory, self.frr), self.window.window)]
        )
        self.assertIs(self.factory.get_image_by_name("frr"), self.frr)
        # the edit screen goes with the image
        self.factory.remove_disk_image(self.frr)
        self.assertIsNone(self.window._disk_image)

    def save_with(self, path, relinked):
        calls = []

        def relink(factory, image, new):
            calls.append((factory, image, new))
            return relinked

        self.patch(disklibrary.images, "relink", relink)
        self.window._show_edit_screen(self.frr)
        self.window.path_chooser.get_filename = lambda: path
        self.window.on_save_button_clicked(None)
        return calls

    def test_a_new_file(self):
        calls = self.save_with("/new/frr.qcow2", defer.succeed(None))
        self.assertEqual(calls, [(self.factory, self.frr, "/new/frr.qcow2")])
        self.assertEqual(self.logger.events, [])

    def test_a_new_file_while_a_machine_runs(self):
        self.save_with("/new/frr.qcow2", defer.fail(RunningError(["r1"])))
        self.assertEqual(
            self.logger.formatted(),
            [
                "Cannot change the file of the image frr: stop the machines"
                " that use it first: r1"
            ],
        )

    def test_no_file_chosen(self):
        self.assertEqual(self.save_with(None, None), [])
