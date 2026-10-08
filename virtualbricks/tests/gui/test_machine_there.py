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

"""
The files that the windows show are those of the machine of the bricks, as
engine.machine knows them, not those of this one (page 19 §8): an image
whose file is there, and not here, isn't missing.
"""

import os
import time

from twisted.internet import defer

from virtualbricks.bricks.virtualmachine import ImageDraft, VirtualMachineDraft
from virtualbricks.config import images
from virtualbricks.config.workspace import OpenProject
from virtualbricks.console import ampcommands
from virtualbricks.engine import LocalEngine, LocalMachine
from virtualbricks.tests import FakeLogger
from virtualbricks.tests.config.test_images import INFO
from virtualbricks.tests.gui import GuiTestCase, has_display, untranslated

if has_display:
    from gi.repository import Gtk

    from virtualbricks.gui.dialogs import imagedialogs
    from virtualbricks.gui.dialogs.addimage import (
        ExistingImageDialog,
        NewDiskDialog,
    )
    from virtualbricks.gui.dialogs.imagedialogs import (
        FindFileDialog,
        RemoveImageDialog,
        StartOverDialog,
    )
    from virtualbricks.gui.form import Form
    from virtualbricks.gui.mainwindow.bricks.config.vm.disks import (
        DisksSection,
    )
    from virtualbricks.gui.mainwindow.bricks.config.vm.imagepicker import (
        ImagePicker,
    )
    from virtualbricks.gui.mainwindow.images import imagemenu
    from virtualbricks.gui.mainwindow.images.imagedetails import ImageDetails
    from virtualbricks.gui.mainwindow.images.tab import ImagesTab

# Thursday 24 September 2026, 17:47:09, local time
CHANGED = time.mktime((2026, 9, 24, 17, 47, 9, 0, 0, -1))


def texts(box):
    """The labels of a box, those of the boxes in it too."""

    found = []
    for child in box.get_children():
        if isinstance(child, Gtk.Label):
            found.append(child.get_text())
        elif isinstance(child, Gtk.Box):
            found.extend(texts(child))
    return found


class WorkspaceThere:
    """The workspace of the Virtualbricks there."""

    path = "/lab"
    current = None


class KnownInfos:
    """What qemu-img says there of the files, known already."""

    def __init__(self, infos):
        self.infos = infos

    def get(self, path):
        return self.infos.get(path)

    def read(self, path):
        return defer.succeed(self.infos[path])


class MachineThere(LocalMachine):
    """The machine of the bricks, when it isn't this one: its files."""

    def __init__(self, workspace, taken):
        super().__init__(workspace)
        # the files there, and the space each takes
        self.files = taken
        self.infos = KnownInfos(
            {path: images.parse_info(INFO) for path in taken}
        )
        self.others = {}

    def exists(self, path):
        return path in self.files

    def taken(self, path):
        return self.files.get(path)

    def changed(self, path):
        return CHANGED if path in self.files else None

    def other_projects(self, path):
        return self.others.get(path, [])

    def can_trash(self, path):
        return False

    def image_folder(self):
        return "/lab/shared_images"


class FakeGui:
    def __init__(self, engine):
        self.brickfactory = engine.factory
        self.engine = engine
        self.window = None

    def curtain_up(self, image):
        pass


class ThereTestCase(GuiTestCase):
    """
    The image frr, whose file is there only, and the image here, whose file
    is here only; r1 has a private copy there.
    """

    def setUp(self):
        super().setUp()
        untranslated(self)
        self.manager.current = OpenProject("/lab/ospf", None)
        self.frr = self.factory.new_image("frr", "/lab/frr.qcow2")
        self.here = self.image("here")
        self.r1 = self.factory.new_brick("qemu", "r1")
        self.r1.update_config({"hda_image": "frr", "hda_private": True})
        self.machine = MachineThere(
            self.manager,
            {self.frr.path: 1900000000, "/lab/ospf/r1_hda.cow": 8192},
        )
        self.engine = LocalEngine(self.factory)
        self.engine.machine = self.machine
        self.gui = FakeGui(self.engine)


class TestTheImagesTab(ThereTestCase):

    def setUp(self):
        super().setUp()
        self.tab = ImagesTab(self.gui, self.factory)
        self.addCleanup(self.tab.destroy)
        self.addCleanup(lambda: self.tab.on_quit())

    def test_the_rows(self):
        row = self.tab.list.row_of(self.frr)
        self.assertEqual(row.state_label.get_text(), "Not in use")
        self.assertEqual(
            row.detail.get_text(),
            "qcow2 · 4.0 GB disk · 1.9 GB on disk · r1, private copy",
        )
        row = self.tab.list.row_of(self.here)
        self.assertTrue(row.warning.get_visible())
        self.assertIn("isn't there", row.detail.get_text())

    def test_the_menu(self):
        row = self.tab.list.row_of(self.here)
        model = row.menu_model()
        first = model.get_item_link(0, "section")
        self.assertEqual(
            first.get_item_attribute_value(0, "label").unpack(),
            "Find the File…",
        )
        actions = imagemenu.ImageActions(self.gui, self.frr)
        self.assertFalse(actions.lookup_action("find-file").get_enabled())
        self.assertTrue(actions.lookup_action("show").get_enabled())

    def test_the_popup(self):
        self.patch(Gtk.Menu, "popup_at_widget", lambda *args: None)
        widget = Gtk.Button()
        self.addCleanup(widget.destroy)
        for image, first in (
            (self.frr, "Details…"),
            (self.here, "Find the File…"),
        ):
            menu = imagemenu.popup(widget, None, self.gui, image)
            self.addCleanup(menu.destroy)
            self.assertEqual(menu.get_children()[0].get_label(), first)


class LaterInfos:
    """What qemu-img says there, known once ImageFacts answers."""

    def __init__(self, machine):
        self.machine = machine
        self.reading = defer.Deferred()

    def get(self, path):
        return None

    def read(self, path):
        return self.reading

    def answer(self, path, others):
        self.machine.others[path] = others
        self.reading.callback(images.parse_info(INFO))


class TestTheDetails(ThereTestCase):

    def test_the_facts(self):
        self.machine.others[self.frr.path] = [("ripv2", "debian")]
        details = ImageDetails(
            ImageDraft(self.frr, self.factory), self.machine
        )
        self.addCleanup(details.panel.destroy)
        rows = {}
        for child in details.facts.get_children():
            row = details.facts.child_get_property(child, "top-attach")
            rows.setdefault(row, []).append(child.get_text())
        facts = {texts[-1]: texts[0] for texts in rows.values()}
        self.assertEqual(
            facts["Changed"], time.strftime("%x %X", time.localtime(CHANGED))
        )
        self.assertEqual(
            details.others.get_text(),
            "The project ripv2, as debian uses the same file.",
        )
        texts = [child.get_text() for child in details.uses.get_children()]
        self.assertIn("private copy r1_hda.cow, 8.2 KB", texts)

    def test_the_other_projects_later(self):
        # over a connection, ImageFacts says them with the facts
        infos = self.machine.infos = LaterInfos(self.machine)
        details = ImageDetails(
            ImageDraft(self.frr, self.factory), self.machine
        )
        self.addCleanup(details.panel.destroy)
        self.assertFalse(details.others.get_visible())
        infos.answer(self.frr.path, [("ripv2", "debian")])
        self.assertTrue(details.others.get_visible())
        self.assertIn("ripv2", details.others.get_text())


class TestTheDisks(ThereTestCase):

    def test_a_disk(self):
        section = DisksSection(self.r1, self.engine)
        self.addCleanup(section.destroy)
        row = section.row("hda")
        self.assertEqual(
            row.line.get_text(),
            "r1's changes are kept in r1_hda.cow, 8.2 KB, in the project;"
            " frr stays as it is.",
        )
        # its changes there, which the menu of the disk can save
        self.assertTrue(row.keeps_changes())
        self.assertEqual(
            row.picker.facts_label.get_text(),
            "qcow2 · 4.0 GB disk · 1.9 GB on disk",
        )

    def test_the_picker(self):
        picker = ImagePicker(self.engine, self.r1, self.frr)
        self.addCleanup(picker.destroy)
        picker.fill()
        options = {option.image: option for option in picker.options()}
        self.assertTrue(options[self.frr].get_sensitive())
        self.assertEqual(options[self.frr].words.get_text(), "qcow2 · 4.0 GB")
        self.assertFalse(options[self.here].get_sensitive())
        self.assertEqual(
            options[self.here].words.get_text(), "The file isn't there"
        )


class TestTheDialogs(ThereTestCase):
    """The dialogs of the files, over a connection."""

    def setUp(self):
        super().setUp()
        self.engine.local = False

    def test_remove_an_image(self):
        infos = self.machine.infos = LaterInfos(self.machine)
        self.frr.set_path("/lab/shared_images/frr.qcow2")
        self.machine.files[self.frr.path] = 5000
        dialog = RemoveImageDialog(self.engine, self.frr)
        self.addCleanup(dialog.dialog.destroy)
        # what the other projects there do with the file comes first
        self.assertEqual(texts(dialog.file_box), ["Looking at the file…"])
        self.assertFalse(dialog.remove_button.get_sensitive())
        infos.answer(self.frr.path, [])
        self.assertTrue(dialog.remove_button.get_sensitive())
        self.assertEqual(
            dialog.file_check.get_label(),
            "Also delete the file (5.0 KB): there is no trash",
        )

    def test_remove_an_image_others_use(self):
        infos = self.machine.infos = LaterInfos(self.machine)
        self.frr.set_path("/lab/shared_images/frr.qcow2")
        self.machine.files[self.frr.path] = 5000
        dialog = RemoveImageDialog(self.engine, self.frr)
        self.addCleanup(dialog.dialog.destroy)
        infos.answer(self.frr.path, [("ospf", "frr")])
        self.assertIsNone(dialog.file_check)
        self.assertEqual(
            texts(dialog.file_box),
            ["The project ospf uses the file too: it stays."],
        )

    def test_the_file_stays_there(self):
        # the Virtualbricks there refuses: the log says why
        logger = FakeLogger()
        self.patch(imagedialogs, "logger", logger)
        self.frr.set_path("/lab/shared_images/frr.qcow2")
        self.machine.files[self.frr.path] = 5000
        self.engine.remove = lambda image: defer.succeed(None)
        self.engine.discard_file = lambda path: defer.fail(
            ampcommands.BadArgument("The project ospf uses the file")
        )
        infos = self.machine.infos = LaterInfos(self.machine)
        dialog = RemoveImageDialog(self.engine, self.frr)
        self.addCleanup(dialog.dialog.destroy)
        infos.answer(self.frr.path, [])
        dialog.file_check.set_active(True)
        self.successResultOf(dialog.remove())
        self.assertEqual(
            logger.formatted(),
            [
                "Cannot remove the file /lab/shared_images/frr.qcow2: The project"
                " ospf uses the file"
            ],
        )

    def test_start_over(self):
        dialog = StartOverDialog(self.engine, self.r1, "hda")
        self.addCleanup(dialog.dialog.destroy)
        self.assertIn(
            "r1_hda.cow is deleted for good, with the changes it keeps,"
            " 8.2 KB: there is no trash. The next start makes an empty one.",
            texts(dialog.dialog.get_content_area()),
        )

    def test_a_new_disk(self):
        dialog = NewDiskDialog(self.engine)
        self.addCleanup(dialog.dialog.destroy)
        self.assertIsNone(dialog.folder_chooser)
        dialog.name_entry.set_text("pc")
        self.assertEqual(dialog.target(), "/lab/shared_images/pc.qcow2")
        self.assertTrue(dialog.create_button.get_sensitive())
        # a file there already
        self.machine.files["/lab/shared_images/pc.qcow2"] = 10
        self.assertFalse(dialog.check())
        self.assertIn("is there already", dialog.file_label.get_text())


class TestTypedPaths(ThereTestCase):
    """Over a connection, a path is typed, completed from there (19 R9)."""

    def setUp(self):
        super().setUp()
        self.engine.local = False
        self.asked = []
        self.engine.folder = lambda path: (
            self.asked.append(path) or defer.succeed(([], False))
        )
        self.read = []

        def image_info(path):
            self.read.append(path)
            return defer.succeed(images.parse_info(INFO))

        self.engine.image_info = image_info
        self.engine.workspace = WorkspaceThere()

    def test_what_a_file_says_here(self):
        # a file of the same path here, which isn't the one there
        path = os.path.join(self.folder("disks"), "frr.qcow2")
        with open(path + ".md", "w") as fp:
            fp.write("Not the one there")
        dialog = ExistingImageDialog(self.engine)
        self.addCleanup(dialog.dialog.destroy)
        dialog.file_entry.set_text(path)
        dialog.file_entry.emit("activate")
        buffer = dialog.description_view.get_buffer()
        self.assertEqual(buffer.get_char_count(), 0)

    def test_add_an_image(self):
        dialog = ExistingImageDialog(self.engine)
        self.addCleanup(dialog.dialog.destroy)
        self.assertIsNone(dialog.file_chooser)
        entry = dialog.file_entry
        entry.set_text("/lab/shared_images/")
        self.assertEqual(self.asked, ["/lab/shared_images/"])
        entry.set_text("/lab/shared_images/frr.qcow2")
        entry.emit("activate")
        self.assertEqual(self.read, ["/lab/shared_images/frr.qcow2"])
        # the same again: read once
        dialog.on_file_left(entry, None)
        self.assertEqual(self.read, ["/lab/shared_images/frr.qcow2"])
        self.assertEqual(dialog.name_entry.get_text(), "frr")
        # what a file beside it says is here only
        buffer = dialog.description_view.get_buffer()
        self.assertEqual(buffer.get_char_count(), 0)
        # inside the workspace there
        self.assertFalse(dialog.outside())

    def test_a_new_disk_elsewhere(self):
        dialog = NewDiskDialog(self.engine)
        self.addCleanup(dialog.dialog.destroy)
        self.assertEqual(dialog.folder_entry.get_text(), "/lab/shared_images")
        dialog.folder_entry.set_text("/srv/disks/")
        self.assertEqual(self.asked[-1], "/srv/disks/")
        dialog.name_entry.set_text("pc")
        self.assertEqual(dialog.target(), "/srv/disks/pc.qcow2")

    def test_find_the_file(self):
        # a file of that name in the shared images here: not the one there
        folder = os.path.join(self.manager.path, "shared_images")
        os.makedirs(folder)
        with open(os.path.join(folder, "here.qcow2"), "w"):
            pass
        dialog = FindFileDialog(self.engine, self.here)
        self.addCleanup(dialog.dialog.destroy)
        self.assertIsNone(dialog.found())
        self.assertFalse(dialog.use_button.get_sensitive())
        dialog.file_chooser.set_text("/lab/shared_images/here.qcow2")
        self.assertEqual(dialog.chosen, "/lab/shared_images/here.qcow2")
        self.assertTrue(dialog.use_button.get_sensitive())
        dialog.file_chooser.set_text("")
        self.assertFalse(dialog.use_button.get_sensitive())

    def test_a_path_of_a_panel(self):
        form = Form(VirtualMachineDraft(self.r1), lambda: None, self.engine)
        form.section("System")
        entry = form.path("kernel", "The kernel to boot")
        # no Browse button
        self.assertEqual(entry.get_parent().get_children(), [entry])
        self.assertIsNotNone(entry.get_completion())
        entry.set_text("/boot/")
        self.assertEqual(self.asked, ["/boot/"])

    def test_a_path_here(self):
        self.engine.local = True
        form = Form(VirtualMachineDraft(self.r1), lambda: None, self.engine)
        form.section("System")
        entry = form.path("kernel", "The kernel to boot")
        [_entry, button] = entry.get_parent().get_children()
        self.assertIsNone(entry.get_completion())
