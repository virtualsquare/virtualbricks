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

"""The menu of an image: its items, when they are enabled, what they do."""

from virtualbricks.engine import LocalEngine
from virtualbricks.tests.gui import GuiTestCase, has_display
from virtualbricks.tests.gui.mainwindow.bricks.test_brickmenu import (
    attribute,
    content,
)

if has_display:
    from gi.repository import Gdk, Gtk

    from virtualbricks.gui.mainwindow.images import imagemenu
    from virtualbricks.gui.mainwindow.images.imagemenu import (
        ImageActions,
        menu,
        popup,
    )


class FakeDialog:
    def __init__(self, shown, *args):
        self.shown = shown
        self.args = args

    def show(self, parent):
        self.shown.append((self.args, parent))


class ImageMenuTestCase(GuiTestCase):

    def setUp(self):
        super().setUp()
        self.engine = LocalEngine(self.factory)
        # what the dialogs open over: the main window
        self.window = object()
        # what Details shows
        self.configured = []
        self.there = self.image("frr")
        self.missing = self.factory.new_image("old", "/gone/old.qcow2")


class TestTheMenu(ImageMenuTestCase):

    def test_an_image(self):
        self.assertEqual(
            [
                section
                for section in content(menu(self.there, True))
                if section
            ],
            [["Details…"], ["Rename…", "Show in Files"], ["Remove…"]],
        )

    def test_a_missing_file(self):
        self.assertEqual(
            content(menu(self.missing, False))[0], ["Find the File…"]
        )

    def test_the_keys(self):
        model = menu(self.missing, False, keys=True)
        self.assertEqual(attribute(model, [1, 0], "accel"), "Return")
        self.assertEqual(attribute(model, [2, 0], "accel"), "F2")
        self.assertEqual(attribute(model, [3, 0], "accel"), "Delete")
        for path in ([0, 0], [2, 1]):
            self.assertIsNone(attribute(model, path, "accel"), path)
        self.assertIsNone(
            attribute(menu(self.missing, False), [1, 0], "accel")
        )

    def test_every_item_has_its_action(self):
        actions = set(
            ImageActions(
                self.engine, self.window, self.missing, self.configured.append
            ).list_actions()
        )
        model = menu(self.missing, False)
        used = set()
        for i in range(model.get_n_items()):
            section = model.get_item_link(i, "section")
            for j in range(section.get_n_items()):
                action = section.get_item_attribute_value(j, "action")
                used.add(action.unpack())
        self.assertEqual({name.partition(".")[2] for name in used}, actions)
        self.assertEqual({name.partition(".")[0] for name in used}, {"image"})


class TestWhatIsEnabled(ImageMenuTestCase):

    def enabled(self, image):
        actions = ImageActions(
            self.engine, self.window, image, self.configured.append
        )
        return sorted(
            name
            for name in actions.list_actions()
            if actions.get_action_enabled(name)
        )

    def test_an_image(self):
        self.assertEqual(
            self.enabled(self.there), ["details", "remove", "rename", "show"]
        )

    def test_a_missing_file(self):
        # nothing to show in Files
        self.assertEqual(
            self.enabled(self.missing),
            ["details", "find-file", "remove", "rename"],
        )

    def test_update(self):
        actions = ImageActions(
            self.engine, self.window, self.missing, self.configured.append
        )
        self.missing.set_path(self.there.path)
        actions.update()
        self.assertTrue(actions.get_action_enabled("show"))
        self.assertFalse(actions.get_action_enabled("find-file"))


class TestWhatTheyDo(ImageMenuTestCase):

    def test_details(self):
        actions = ImageActions(
            self.engine, self.window, self.there, self.configured.append
        )
        actions.activate_action("details", None)
        self.assertEqual(self.configured, [self.there])

    def test_dialogs(self):
        shown = []
        for name in ("RenameDialog", "FindFileDialog", "RemoveImageDialog"):
            self.patch(
                imagemenu, name, lambda *a, n=name: FakeDialog(shown, n, *a)
            )
        actions = ImageActions(
            self.engine, self.window, self.missing, self.configured.append
        )
        actions.activate_action("rename", None)
        actions.activate_action("find-file", None)
        actions.activate_action("remove", None)
        self.assertEqual(
            shown,
            [
                (
                    ("RenameDialog", self.engine, self.missing),
                    self.window,
                ),
                (
                    ("FindFileDialog", self.engine, self.missing),
                    self.window,
                ),
                (
                    ("RemoveImageDialog", self.engine, self.missing),
                    self.window,
                ),
            ],
        )

    def test_show_in_files(self):
        shown = []
        self.patch(
            imagemenu,
            "show_in_files",
            lambda parent, path: shown.append((parent, path)),
        )
        ImageActions(
            self.engine, self.window, self.there, self.configured.append
        ).activate_action("show", None)
        self.assertEqual(shown, [(self.window, self.there.path)])


class TestPopup(ImageMenuTestCase):

    def test_at_the_pointer(self):
        shown = []
        self.patch(
            Gtk.Menu,
            "popup_at_pointer",
            lambda menu, event: shown.append(event),
        )
        widget = Gtk.Button()
        self.addCleanup(widget.destroy)
        click = Gdk.Event.new(Gdk.EventType.BUTTON_PRESS)
        result = popup(
            widget,
            click,
            self.engine,
            self.window,
            self.missing,
            self.configured.append,
        )
        self.addCleanup(result.destroy)
        self.assertEqual(shown, [click])
        actions = result.get_action_group("image")
        self.assertIsInstance(actions, ImageActions)
        self.assertIs(actions.image, self.missing)
        labels = [
            child.get_label()
            for child in result.get_children()
            if not isinstance(child, Gtk.SeparatorMenuItem)
        ]
        self.assertEqual(labels[:2], ["Find the File…", "Details…"])
