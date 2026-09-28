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

"""The dialog of New Project, Rename Project and Duplicate Project."""

import os

from virtualbricks import locations
from virtualbricks.config.settings import current_project
from virtualbricks.config.tomlfile import dump_toml, load_toml
from virtualbricks.tests import FakeLogger
from virtualbricks.tests.gui import GuiTestCase, ProjectsGui, has_display

if has_display:
    from gi.repository import Gtk

    from virtualbricks.gui.dialogs import projectname


class NameTestCase(GuiTestCase):

    def setUp(self):
        super().setUp()
        self.gui = ProjectsGui(self.factory, self.manager)
        self.logger = FakeLogger()
        self.patch(projectname, "logger", self.logger)
        # a real one, 28 bytes, which leaves 18 bytes to the bricks of a
        # project with 40; never created
        runtime_dir = "/run/user/1000/virtualbricks"
        self.patch(locations, "runtime_dir", lambda: runtime_dir)
        self.patch(locations, "ensure_private_dir", lambda path: path)
        self.done = []

    def dialog(self, kind, original=None):
        dialog = projectname.ProjectNameDialog(self.gui, kind, original)
        dialog.on_done = self.done.append
        self.addCleanup(dialog.dialog.destroy)
        return dialog

    def type(self, dialog, name):
        dialog.name_entry.set_text(name)
        return dialog.ok_button.get_sensitive(), (
            dialog.name_message.get_text()
            if dialog.name_message.get_visible()
            else None
        )

    def ok(self, dialog):
        dialog.dialog.response(Gtk.ResponseType.OK)


class TestNew(NameTestCase):

    def test_new(self):
        dialog = self.dialog(projectname.NEW)
        self.assertEqual(dialog.dialog.get_title(), "New Project")
        self.assertEqual(dialog.name_entry.get_text(), "new_project")
        self.assertEqual(self.type(dialog, "ospf-lab"), (True, None))
        dialog.description_view.get_buffer().set_text("Three routers")
        self.ok(dialog)
        self.assertEqual(
            self.gui.calls, [("new", "ospf-lab", "Three routers")]
        )
        self.assertEqual(self.done, ["ospf-lab"])
        self.assertEqual(self.manager.current.name, "ospf-lab")
        self.assertEqual(self.logger.levels(), ["info"])

    def test_suggests_a_free_name(self):
        self.manager.create("new_project")
        dialog = self.dialog(projectname.NEW)
        self.assertEqual(dialog.name_entry.get_text(), "new_project-2")

    def test_bad_names(self):
        self.manager.create("lab")
        dialog = self.dialog(projectname.NEW)
        self.assertEqual(self.type(dialog, ""), (False, "The name is empty"))
        self.assertEqual(
            self.type(dialog, "lab"),
            (False, "A project with this name already exists"),
        )
        self.assertEqual(
            self.type(dialog, "x" * 41),
            (False, "The name is 41 bytes long, at most 40"),
        )
        # the main button waits for a good name
        self.ok(dialog)
        self.assertEqual(self.gui.calls, [])

    def test_cancel(self):
        dialog = self.dialog(projectname.NEW)
        dialog.dialog.response(Gtk.ResponseType.CANCEL)
        self.assertEqual(self.gui.calls, [])
        self.assertEqual(self.done, [])

    def test_a_failure_keeps_the_dialog(self):
        dialog = self.dialog(projectname.NEW)
        self.type(dialog, "lab")
        os.makedirs(self.manager.path)
        os.chmod(self.manager.path, 0o500)
        self.addCleanup(os.chmod, self.manager.path, 0o700)
        self.ok(dialog)
        self.assertTrue(dialog.error_label.get_visible())
        self.assertIn("Permission denied", dialog.error_label.get_text())
        self.assertEqual(self.done, [])
        # typing hides the error
        self.type(dialog, "lab2")
        self.assertFalse(dialog.error_label.get_visible())


class TestRename(NameTestCase):

    def setUp(self):
        super().setUp()
        self.manager.create("lab")
        self.manager.create("other")

    def test_rename(self):
        dialog = self.dialog(projectname.RENAME, "lab")
        self.assertEqual(dialog.dialog.get_title(), "Rename Project")
        self.assertEqual(dialog.name_entry.get_text(), "lab")
        # the same name: nothing to do
        self.assertFalse(dialog.ok_button.get_sensitive())
        self.assertEqual(
            self.type(dialog, "other"),
            (False, "A project with this name already exists"),
        )
        self.assertEqual(self.type(dialog, "ospf"), (True, None))
        self.ok(dialog)
        self.assertEqual(self.manager.names(), ["ospf", "other"])
        self.assertEqual(self.gui.calls, [("title",)])
        self.assertEqual(self.done, ["ospf"])

    def test_rename_the_open_project(self):
        self.manager.open("lab", self.factory)
        self.factory.new_brick("switch", "b" * 19)
        dialog = self.dialog(projectname.RENAME, "lab")
        # the bricks of the factory, not those of the file
        ok, message = self.type(dialog, "x" * 40)
        self.assertFalse(ok)
        self.assertIn("leaves", message)
        self.type(dialog, "ospf")
        self.ok(dialog)
        self.assertEqual(self.manager.current.name, "ospf")
        self.assertEqual(current_project(self.manager.path), "ospf")


class TestDuplicate(NameTestCase):

    def setUp(self):
        super().setUp()
        self.manager.create("lab")

    def test_duplicate_and_open(self):
        dialog = self.dialog(projectname.DUPLICATE, "lab")
        self.assertEqual(dialog.dialog.get_title(), "Duplicate Project")
        self.assertEqual(dialog.name_entry.get_text(), "lab-copy")
        self.assertEqual(
            self.type(dialog, "lab"),
            (False, "A project with this name already exists"),
        )
        self.type(dialog, "lab-copy")
        self.ok(dialog)
        self.assertEqual(self.manager.names(), ["lab", "lab-copy"])
        self.assertEqual(self.gui.calls, [("open", "lab-copy")])
        self.assertEqual(self.manager.current.name, "lab-copy")

    def test_duplicate_the_open_project(self):
        self.manager.open("lab", self.factory)
        self.factory.new_brick("switch", "sw")
        dialog = self.dialog(projectname.DUPLICATE, "lab")
        dialog.open_check.set_active(False)
        self.ok(dialog)
        # saved first, so the copy has the switch
        self.assertEqual(self.gui.calls, [("save",)])
        data = load_toml(self.manager._project_file("lab-copy"))
        self.assertIn("sw", data["bricks"])
        self.assertEqual(self.manager.current.name, "lab")

    def test_the_bricks_of_the_copy_must_fit(self):
        data = load_toml(self.manager._project_file("lab"))
        data["bricks"] = {"b" * 19: {"type": "switch"}}
        dump_toml(data, self.manager._project_file("lab"))
        dialog = self.dialog(projectname.DUPLICATE, "lab")
        ok, message = self.type(dialog, "x" * 40)
        self.assertFalse(ok)
        self.assertIn("leaves 18 bytes", message)

    def test_show(self):
        dialog = self.dialog(projectname.DUPLICATE, "lab")
        parent = Gtk.Window()
        self.addCleanup(parent.destroy)
        dialog.show(parent)
        self.assertIs(dialog.dialog.get_transient_for(), parent)
        self.assertEqual(dialog.dialog.get_header_bar().get_subtitle(), "lab")
