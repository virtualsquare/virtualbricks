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


"""The dialog that saves the project with another name."""

from virtualbricks.tests.gui import GuiTestCase, has_display

if has_display:

    from virtualbricks.gui.windows import saveprojectasdialog


class TestSaveProjectAs(GuiTestCase):

    def setUp(self):
        super().setUp()
        self.patch(saveprojectasdialog, "project_manager", self.manager)
        self.manager.get_project("lab").create().open(self.factory)
        self.manager.get_project("other").create()
        self.dialog = saveprojectasdialog.SaveProjectAsDialog(self.factory)
        self.addCleanup(self.dialog.get_root_widget().destroy)

    def check(self, name):
        entry = self.dialog.project_name_entry
        entry.set_text(name)
        self.dialog.on_project_name_entry_changed(entry)
        return self.dialog.ok_button.get_sensitive(), entry.get_tooltip_text()

    def test_names(self):
        self.assertEqual(self.check("copy"), (True, None))
        self.assertEqual(
            self.check("lab")[1],
            "New project name is the same as previous name",
        )
        # a name is a directory of the workspace
        self.assertEqual(
            self.check("../copy"), (False, "Invalid project name")
        )
        self.assertEqual(self.check("a/b"), (False, "Invalid project name"))
        self.assertEqual(
            self.check("other"),
            (False, "A project with the same name already exists"),
        )
        self.assertEqual(self.check(""), (False, None))
