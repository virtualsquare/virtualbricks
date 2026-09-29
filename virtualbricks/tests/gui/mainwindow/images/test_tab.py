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

"""
The Images tab: the rows of the images and what qemu-img says of them, the
row above the list, the page of a project without images, the keys and the
details.
"""

import os

from twisted.internet import defer

from virtualbricks.qemu import run
from virtualbricks.config.workspace import OpenProject
from virtualbricks.tests.config.test_images import INFO, FakeQemuImg
from virtualbricks.tests.gui import GuiTestCase, has_display, untranslated
from virtualbricks.tests.gui.mainwindow.bricks.test_brickmenu import content

if has_display:
    from gi.repository import Gdk, Gtk

    from virtualbricks.gui.mainwindow.images import imagemenu, tab
    from virtualbricks.gui.mainwindow.images.imagedetails import ImageDetails
    from virtualbricks.gui.mainwindow.images.tab import ImagesTab, count


class LaterQemuImg(FakeQemuImg):
    """qemu-img that answers when told, as the real one does, later."""

    def __init__(self):
        super().__init__()
        self.pending = []

    def __call__(self, args):
        later = defer.Deferred()
        self.pending.append((args, later))
        return later

    def answer(self):
        pending, self.pending = self.pending, []
        for args, later in pending:
            super().__call__(args).chainDeferred(later)


class FakeGui:
    def __init__(self, factory):
        self.brickfactory = factory
        self.window = object()
        self.configured = []
        self.removed = []
        self.tab = None

    def curtain_up(self, image):
        self.configured.append(image)

    def curtain_down(self):
        self.tab.close_settings()

    def ask_remove_image(self, image):
        self.removed.append(image)


class FakeDialog:
    def __init__(self, shown, *args):
        self.shown = shown
        self.args = args

    def show(self, parent):
        self.shown.append((self.args, parent))


class ImagesTestCase(GuiTestCase):

    def setUp(self):
        super().setUp()
        untranslated(self)
        self.qemu_img = LaterQemuImg()
        self.patch(run, "qemu_img", self.qemu_img)
        # the private copies are in the open project
        self.manager.current = OpenProject(self.folder("lab"), None)
        self.frr = self.image("frr")
        self.qemu_img.infos[self.frr.get_path()] = INFO
        self.gui = FakeGui(self.factory)
        self.tab = ImagesTab(self.gui, self.factory)
        self.gui.tab = self.tab
        self.addCleanup(self.tab.destroy)
        self.addCleanup(lambda: self.tab.on_quit())
        self.qemu_img.answer()

    def vm(self, name, image=None, private=True, device="hda"):
        vm = self.factory.new_brick("qemu", name)
        vm.set(
            {
                f"{device}_image": (image or self.frr).get_name(),
                f"{device}_private": private,
            }
        )
        return vm

    def start(self, vm):
        vm.__isrunning__ = lambda: True
        vm.notify_changed()
        return vm

    def row(self, image=None):
        return self.tab.list.row_of(self.frr if image is None else image)

    def listed(self):
        return [
            row.item
            for row in self.tab.list.get_children()
            if self.tab.list._visible(row)
        ]

    def select(self, image):
        row = self.row(image)
        self.tab.list.select_row(row)
        return row

    def press(self, keyval):
        event = Gdk.Event.new(Gdk.EventType.KEY_PRESS)
        event.key.keyval = keyval
        event.key.window = self.tab.get_window()
        seat = Gdk.Display.get_default().get_default_seat()
        event.set_device(seat.get_keyboard())
        return self.tab.on_list_key_press(self.tab.list, event.key)

    def show(self):
        window = Gtk.OffscreenWindow()
        self.addCleanup(window.destroy)
        window.set_size_request(900, 400)
        window.add(self.tab)
        window.show()
        return window


class TestTheRows(ImagesTestCase):

    def test_an_image(self):
        row = self.row()
        self.assertEqual(row.name.get_text(), "frr")
        self.assertEqual(
            row.detail.get_text(),
            "qcow2 · 4.0 GB disk · 1.9 GB on disk · no disk uses it",
        )
        self.assertEqual(row.state_label.get_text(), "No disk")
        self.assertFalse(row.warning.get_visible())
        self.assertIsNone(row.state.get_tooltip_text())
        # an image doesn't start
        self.assertIsNone(row.startstop.get_parent())

    def test_before_qemu_img_answers(self):
        image = self.image("pc")
        self.qemu_img.infos[image.get_path()] = INFO
        self.assertEqual(self.row(image).detail.get_text(), "no disk uses it")
        self.qemu_img.answer()
        self.assertEqual(
            self.row(image).detail.get_text(),
            "qcow2 · 4.0 GB disk · 1.9 GB on disk · no disk uses it",
        )

    def test_read_once(self):
        self.vm("r1")
        self.vm("r2")
        self.assertEqual(self.qemu_img.pending, [])
        self.assertEqual(len(self.qemu_img.calls), 1)

    def test_a_file_that_qemu_img_cant_read(self):
        image = self.image("notes")
        self.qemu_img.failing.add((image.get_path(),))
        self.qemu_img.answer()
        self.assertEqual(self.row(image).detail.get_text(), "no disk uses it")
        self.assertEqual(len(self.qemu_img.calls), 2)

    def test_a_file_that_a_machine_keeps_changing(self):
        image = self.image("pc")
        self.qemu_img.infos[image.get_path()] = INFO
        # the machine writes while qemu-img reads
        with open(image.get_path(), "w") as fp:
            fp.write("changed")
        self.qemu_img.answer()
        self.assertIn("4.0 GB disk", self.row(image).detail.get_text())
        self.assertEqual(self.qemu_img.pending, [])

    def test_in_use(self):
        self.vm("r1")
        self.start(self.vm("r2"))
        self.vm("vm", private=False)
        row = self.row()
        self.assertEqual(
            row.detail.get_text(),
            "qcow2 · 4.0 GB disk · 1.9 GB on disk · r1 and r2, private copies"
            " · vm, the image itself",
        )
        self.assertEqual(row.state_label.get_text(), "In use")
        self.assertEqual(row.state.get_tooltip_text(), "r2 runs")

    def test_not_in_use(self):
        self.vm("r1")
        self.assertEqual(self.row().state_label.get_text(), "Not in use")

    def test_a_missing_file(self):
        image = self.factory.new_disk_image("old", "/gone/old.qcow2")
        row = self.row(image)
        self.assertEqual(
            row.detail.get_text(),
            "/gone/old.qcow2 isn't there · no disk uses it",
        )
        self.assertEqual(row.state_label.get_text(), "File missing")
        self.assertTrue(row.warning.get_visible())
        self.assertEqual(row.state.get_tooltip_text(), "Find the file of old")
        # nothing to read
        self.assertEqual(self.qemu_img.pending, [])

    def test_the_rows_follow_the_images(self):
        other = self.image("pc")
        self.assertEqual(self.listed(), [self.frr, other])
        self.factory.remove_disk_image(self.frr)
        self.assertEqual(self.listed(), [other])
        self.assertIsNone(self.row())

    def test_while_a_project_loads(self):
        # the machines of a project come before it's open, as at start-up
        self.manager.current = None
        self.manager.create("dtn")
        self.manager.open("dtn", self.factory)
        frr = self.image("frr")
        self.qemu_img.infos[frr.get_path()] = INFO
        # a machine read after another tells the tab
        self.vm("node1", frr)
        self.vm("node2", frr)
        self.manager.save(self.factory)
        self.manager.close(self.factory)
        self.assertIsNone(self.manager.current)
        self.manager.open("dtn", self.factory)
        frr = self.factory.get_image_by_name("frr")
        self.qemu_img.answer()
        self.assertEqual(
            self.row(frr).detail.get_text(),
            "qcow2 · 4.0 GB disk · 1.9 GB on disk · node1 and node2, private"
            " copies",
        )

    def test_the_rows_follow_the_bricks(self):
        vm = self.vm("r1")
        self.assertIn("r1, private copy", self.row().detail.get_text())
        self.factory.del_brick(vm)
        self.assertIn("no disk uses it", self.row().detail.get_text())


class TestTheRowAboveTheList(ImagesTestCase):

    def test_its_words(self):
        tab = self.tab
        self.assertEqual(tab.title, "_Images")
        self.assertEqual(tab.new_button.get_label(), "Add Image")
        self.assertEqual(tab.search.get_placeholder_text(), "Search images")
        self.assertEqual(tab.running_button.get_label(), "In use")
        self.assertEqual(tab.count.get_text(), "0 of 1 in use")
        self.start(self.vm("r1"))
        self.assertEqual(tab.count.get_text(), "1 of 1 in use")

    def test_the_count(self):
        self.assertEqual(count(self.tab.list, []), "0 of 0 in use")

    def test_no_start_all(self):
        for button in (self.tab.start_button, self.tab.stop_button):
            self.assertFalse(button.is_ancestor(self.tab))

    def test_add_image(self):
        popped = []
        self.patch(
            Gtk.Menu,
            "popup_at_widget",
            lambda menu, widget, *args: popped.append(widget),
        )
        shown = []
        for name in ("ExistingImageDialog", "NewDiskDialog"):
            self.patch(tab, name, lambda *a, n=name: FakeDialog(shown, n, *a))
        self.tab.new_button.clicked()
        self.assertEqual(popped, [self.tab.new_button])
        menu = self.tab._add_menu
        self.addCleanup(menu.destroy)
        items = menu.get_children()
        self.assertEqual(
            [item.get_label() for item in items],
            ["Existing Image…", "New Empty Disk…"],
        )
        for item in items:
            item.activate()
        self.assertEqual(
            shown,
            [
                (("ExistingImageDialog", self.factory), self.gui.window),
                (("NewDiskDialog", self.factory), self.gui.window),
            ],
        )

    def test_the_search(self):
        self.image("pc")
        self.tab.list.set_search("FR")
        self.assertEqual(self.listed(), [self.frr])
        self.tab.list.set_search("disk")
        self.assertEqual(
            self.tab.list.placeholder.get_text(), "No image matches “disk”"
        )

    def test_the_images_in_use(self):
        other = self.image("pc")
        self.tab.running_button.set_active(True)
        self.assertEqual(self.listed(), [])
        self.assertEqual(
            self.tab.list.placeholder.get_text(), "No image is in use"
        )
        self.start(self.vm("r1", other))
        self.assertEqual(self.listed(), [other])


class TestAProjectWithoutImages(ImagesTestCase):

    def setUp(self):
        super().setUp()
        self.factory.remove_disk_image(self.frr)

    def test_the_page(self):
        tab = self.tab
        self.assertIs(tab.pages.get_visible_child(), tab.empty)
        image, title, words = tab.empty.get_children()
        self.assertEqual(title.get_text(), "No Images Yet")
        self.assertEqual(
            words.get_text(),
            "A disk image is the disk a virtual machine starts from. Add one"
            " to give a machine its disk.",
        )
        self.assertIsNotNone(image.get_pixbuf())

    def test_add_under_its_button(self):
        popped = []
        self.patch(
            Gtk.Menu,
            "popup_at_widget",
            lambda menu, widget, *args: popped.append(widget),
        )
        self.tab.new_button.clicked()
        self.addCleanup(self.tab._add_menu.destroy)
        self.assertEqual(popped, [self.tab.new_button])


class TestTheKeysAndTheMouse(ImagesTestCase):

    def test_delete(self):
        self.select(self.frr)
        self.assertTrue(self.press(Gdk.KEY_Delete))
        self.assertEqual(self.gui.removed, [self.frr])

    def test_the_menu(self):
        shown = []
        self.patch(
            imagemenu, "popup", lambda *args: shown.append(args) or "menu"
        )
        row = self.select(self.frr)
        self.assertTrue(self.press(Gdk.KEY_Menu))
        self.assertEqual(
            shown, [(row.menu_button, None, self.gui, self.frr, True)]
        )

    def test_the_menu_of_a_row(self):
        row = self.row()
        # without the keys
        self.assertEqual(content(row.menu_model())[0], ["Details…"])
        self.assertIsInstance(row.actions, imagemenu.ImageActions)
        self.assertIs(row.actions.image, self.frr)
        self.assertIs(row.get_action_group("image"), row.actions)

    def test_a_double_click_shows_the_details(self):
        self.tab.list.emit("row-activated", self.row())
        self.assertEqual(self.gui.configured, [self.frr])


class TestTheDetails(ImagesTestCase):

    def test_the_details(self):
        tab = self.tab
        self.show()
        tab.configure(self.frr)
        self.assertIs(tab.get_visible_child(), tab.settings)
        head = tab.settings.get_children()[0]
        _image, text = head.get_children()
        name, words = text.get_children()
        self.assertEqual(name.get_text(), "frr")
        self.assertEqual(words.get_text(), "Disk image")
        details = tab._controller
        self.assertIsInstance(details, ImageDetails)
        # the facts that the list read
        self.assertIs(details.infos, tab.list.infos)
        self.assertEqual(len(self.qemu_img.calls), 1)
        details.name_entry.set_text("frr-debian")
        details.description_view.get_buffer().set_text("FRR on Debian.")
        tab.ok_button.clicked()
        self.assertIs(self.factory.get_image_by_name("frr-debian"), self.frr)
        self.assertEqual(self.frr.get_description(), "FRR on Debian.")
        self.assertIs(tab.get_visible_child(), tab.main_page)
        self.assertEqual(self.row().name.get_text(), "frr-debian")

    def test_cancel(self):
        self.tab.configure(self.frr)
        self.tab._controller.name_entry.set_text("frr-debian")
        self.tab.cancel_button.clicked()
        self.assertEqual(self.frr.get_name(), "frr")
        self.assertIsNone(self.tab.configuring)

    def test_removing_the_image(self):
        self.tab.configure(self.frr)
        self.factory.remove_disk_image(self.frr)
        self.assertIsNone(self.tab.configuring)
        self.assertIs(self.tab.get_visible_child(), self.tab.main_page)

    def test_after_quit(self):
        self.tab.on_quit()
        # the tab doesn't follow the bricks any more
        self.vm("r1")
        self.assertEqual(self.tab.count.get_text(), "0 of 1 in use")
        self.tab.on_quit = lambda: None
        self.assertTrue(os.path.exists(self.frr.get_path()))
