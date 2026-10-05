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

"""Delete a brick or an event, and what goes with it."""

import os

from virtualbricks.bricks.eventaction import StartAction, StopAction
from virtualbricks.config.workspace import OpenProject
from virtualbricks.engine import LocalEngine
from virtualbricks.tests import FakeLogger, FakeTrash
from virtualbricks.tests.gui import GuiTestCase, has_display, untranslated
from virtualbricks.tests.gui.dialogs.test_imagedialogs import (
    FakeWorkspace,
    texts,
)

if has_display:
    from gi.repository import Gtk

    from virtualbricks.gui import imageinfo
    from virtualbricks.gui.dialogs import deletedialog
    from virtualbricks.gui.dialogs.deletedialog import DeleteDialog


class FakeMachine:
    """The machine of the bricks, as another one tells of its files."""

    def __init__(self, sizes, trash=True):
        self.sizes = sizes
        self.trash = trash

    def exists(self, path):
        return path in self.sizes

    def taken(self, path):
        return self.sizes.get(path)

    def can_trash(self, path):
        return self.trash


class DeleteTestCase(GuiTestCase):
    """sw1, with vm1 (eth0) and w1 plugged into it; the events boot and halt."""

    def setUp(self):
        super().setUp()
        untranslated(self)
        self.logger = FakeLogger()
        self.patch(deletedialog, "logger", self.logger)
        self.trash = FakeTrash()
        self.workspace = FakeWorkspace(self.folder("workspace"), self.trash)
        # the private copies are in the open project
        self.lab = self.folder(os.path.join("workspace", "lab"))
        self.manager.current = OpenProject(self.lab, None)
        self.engine = LocalEngine(self.factory, workspace=self.workspace)
        self.factory.runtime_dir = "/run/vb"
        self.sw1 = self.factory.new_brick("switch", "sw1")
        self.vm1 = self.factory.new_brick("qemu", "vm1")
        self.vm1.connect(self.sw1.socks[0])
        self.w1 = self.factory.new_brick("wire", "w1")
        self.w1.plugs[0].connect(self.sw1.socks[0])
        self.boot = self.factory.new_event("boot")
        self.halt = self.factory.new_event("halt")
        self.destroyed = []

    def dialog(self, item):
        dialog = DeleteDialog(self.engine, item)
        dialog.dialog.connect("destroy", self.destroyed.append)
        self.addCleanup(dialog.dialog.destroy)
        return dialog

    def lines(self, item):
        return texts(self.dialog(item).dialog)

    def actions(self, event, *actions):
        event.update_config({"actions": list(actions)})

    def machine(self, name, *copies, private=("hda",)):
        """A machine with private disks, and the files of copies."""

        vm = self.factory.new_brick("qemu", name)
        vm.update_config({f"{device}_private": True for device in private})
        paths = []
        for device in copies:
            path = vm.disk(device).get_cow_path()
            with open(path, "wb") as fp:
                fp.write(b"x" * 5000)
            paths.append(path)
        return vm, paths

    def size(self, *paths):
        return imageinfo.human_size(
            sum(self.engine.machine.taken(path) for path in paths)
        )


class TestWhatItSays(DeleteTestCase):

    def test_a_switch(self):
        self.actions(self.boot, StartAction("sw1"))
        dialog = self.dialog(self.sw1)
        self.assertEqual(dialog.dialog.get_title(), "Delete Brick")
        self.assertEqual(dialog.delete_button.get_label(), "Delete")
        style = dialog.delete_button.get_style_context()
        self.assertTrue(style.has_class("destructive-action"))
        self.assertEqual(
            texts(dialog.dialog),
            [
                "Delete the brick sw1?",
                "vm1 (eth0) and w1 will be plugged into nothing.",
                "The event boot will no longer start sw1.",
            ],
        )

    def test_the_card_of_a_machine(self):
        sw2 = self.factory.new_brick("switch", "sw2")
        self.vm1.connect(sw2.socks[0])
        self.assertEqual(
            self.lines(sw2)[1], "vm1 (eth1) will be plugged into nothing."
        )

    def test_events_that_start_or_stop_it(self):
        self.actions(self.halt, StopAction("sw1"))
        self.assertEqual(
            self.lines(self.sw1)[2], "The event halt will no longer stop sw1."
        )
        self.actions(self.boot, StartAction("sw1"), StopAction("vm1"))
        self.assertEqual(
            self.lines(self.sw1)[2],
            "The events boot and halt will no longer start or stop sw1.",
        )

    def test_nothing_else(self):
        w2 = self.factory.new_brick("wire", "w2")
        self.assertEqual(
            self.lines(w2), ["Delete the brick w2?", "Nothing else uses it."]
        )

    def test_an_event(self):
        self.actions(self.halt, StopAction("boot"))
        self.sw1.update_config({"on_start": "boot"})
        self.vm1.update_config({"on_start": "boot", "on_stop": "boot"})
        self.patch(self.boot, "is_running", lambda: True)
        dialog = self.dialog(self.boot)
        self.assertEqual(dialog.dialog.get_title(), "Delete Event")
        self.assertEqual(
            texts(dialog.dialog),
            [
                "Delete the event boot?",
                "The event halt will no longer stop boot.",
                "sw1 and vm1 will no longer run boot when they start.",
                "vm1 will no longer run boot when it stops.",
                "It is waiting: it stops, and its actions don't run.",
            ],
        )

    def test_the_private_copies(self):
        # hdb has no copy yet, and hdc's copy is of a disk no longer private
        vm, paths = self.machine("vm2", "hda", "hdc", private=("hda", "hdb"))
        self.assertEqual(
            self.lines(vm)[-1],
            "Its private copy goes to the trash, with the changes it keeps:"
            f" vm2_hda.cow, {self.size(paths[0])}.",
        )
        vm.update_config({"hdc_private": True})
        self.assertEqual(
            self.lines(vm)[-1],
            "Its private copies go to the trash, with the changes they keep:"
            f" vm2_hda.cow and vm2_hdc.cow, {self.size(*paths)}.",
        )

    def test_without_a_trash(self):
        self.workspace.trasher = None
        vm, paths = self.machine("vm2", "hda")
        self.assertEqual(
            self.lines(vm)[-1],
            "Its private copy is deleted for good, with the changes it keeps:"
            f" vm2_hda.cow, {self.size(*paths)}. There is no trash.",
        )

    def test_the_machine_of_the_bricks(self):
        # over a connection, what the Virtualbricks there said of the files
        vm, _ = self.machine("vm2")
        path = vm.disk("hda").get_cow_path()
        self.engine.machine = FakeMachine({path: 2.3e9})
        self.assertEqual(
            self.lines(vm)[-1],
            "Its private copy goes to the trash, with the changes it keeps:"
            " vm2_hda.cow, 2.3 GB.",
        )


class TestTheDelete(DeleteTestCase):

    def test_a_switch(self):
        self.actions(self.boot, StartAction("sw1"), StartAction("vm1"))
        self.dialog(self.sw1).dialog.response(Gtk.ResponseType.OK)
        self.assertIsNone(self.factory.get_brick("sw1"))
        self.assertIsNone(self.vm1.plugs[0].sock)
        self.assertEqual(self.boot.config.actions, [StartAction("vm1")])
        self.assertEqual(len(self.destroyed), 1)

    def test_an_event(self):
        self.sw1.update_config({"on_start": "boot"})
        self.dialog(self.boot).dialog.response(Gtk.ResponseType.OK)
        self.assertIsNone(self.factory.get_event("boot"))
        self.assertEqual(self.sw1.config.on_start, "")

    def test_cancel(self):
        self.dialog(self.sw1).dialog.response(Gtk.ResponseType.CANCEL)
        self.assertIs(self.factory.get_brick("sw1"), self.sw1)
        self.assertEqual(len(self.destroyed), 1)

    def test_the_copies_go_first(self):
        # the machine names them; over a connection too
        vm, paths = self.machine("vm2", "hda", "hdb", private=("hda", "hdb"))
        calls = []
        start_over, remove = self.engine.start_over, self.engine.remove

        def starting_over(machine, device):
            calls.append(("start over", device, machine.name))
            return start_over(machine, device)

        def removing(item):
            calls.append(("remove", item.name))
            return remove(item)

        self.patch(self.engine, "start_over", starting_over)
        self.patch(self.engine, "remove", removing)
        self.dialog(vm).dialog.response(Gtk.ResponseType.OK)
        self.assertEqual(
            calls,
            [
                ("start over", "hda", "vm2"),
                ("start over", "hdb", "vm2"),
                ("remove", "vm2"),
            ],
        )
        self.assertEqual(self.trash.trashed, paths)
        self.assertIsNone(self.factory.get_brick("vm2"))

    def test_a_copy_that_stays(self):
        self.trash.error = PermissionError(13, "Permission denied")
        vm, paths = self.machine("vm2", "hda")
        self.dialog(vm).dialog.response(Gtk.ResponseType.OK)
        # said, and the machine goes anyway
        self.assertEqual(
            self.logger.formatted(),
            [
                "Cannot discard vm2's private copy of hda:"
                " [Errno 13] Permission denied"
            ],
        )
        self.assertIsNone(self.factory.get_brick("vm2"))

    def test_a_refusal(self):
        # it started while the dialog was open
        dialog = self.dialog(self.sw1)
        self.patch(self.sw1, "is_running", lambda: True)
        dialog.dialog.response(Gtk.ResponseType.OK)
        self.assertIs(self.factory.get_brick("sw1"), self.sw1)
        self.assertEqual(self.logger.levels(), ["error"])
        self.assertEqual(len(self.destroyed), 1)
