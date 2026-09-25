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


"""The settings dialog, with the tabs of the project settings."""

import os


from virtualbricks import locations
from virtualbricks.config import (
    get_app_setting,
    load_toml,
    set_app_setting,
    set_setting,
)
from virtualbricks.tests.gui import FakeGui, GuiTestCase, has_display

if has_display:
    from gi.repository import Gtk

    from virtualbricks.gui.windows import settings as settings_window


class TestSettingsDialog(GuiTestCase):

    def setUp(self):
        super().setUp()
        self.app_bin = self.folder("app-bin")
        self.project_bin = self.folder("project-bin")
        set_app_setting("qemupath", self.app_bin)
        set_app_setting("vdepath", self.app_bin)

    def dialog(self):
        dialog = settings_window.SettingsDialog(FakeGui(self.factory))
        self.addCleanup(dialog.dialog.destroy)
        return dialog

    def open_project(self):
        prj = self.manager.get_project("lab").create()
        prj.open(self.factory)
        set_setting("qemupath", self.project_bin)
        set_setting("femaleplugs", True)
        set_setting("cowfmt", "cow")
        return prj

    def test_tabs(self):
        children = self.dialog().dialog.get_content_area().get_children()
        [notebook] = [c for c in children if isinstance(c, Gtk.Notebook)]
        labels = [
            notebook.get_tab_label_text(notebook.get_nth_page(i))
            for i in range(notebook.get_n_pages())
        ]
        self.assertEqual(
            labels, ["Application", "This project", "New projects"]
        )

    def test_no_open_project(self):
        dialog = self.dialog()
        widgets = dialog.project_widgets
        self.assertFalse(widgets.grid.get_sensitive())
        self.assertEqual(
            widgets.qemupath_chooser.get_current_folder(), self.app_bin
        )
        self.assertEqual(dialog.term_entry.get_text(), get_app_setting("term"))
        self.assertEqual(
            settings_window.combobox_get_active_value(
                dialog.new_project_widgets.cowfmt_combo, 0
            ),
            "qcow2",
        )

    def test_open_project(self):
        self.open_project()
        dialog = self.dialog()
        widgets = dialog.project_widgets
        self.assertTrue(widgets.grid.get_sensitive())
        self.assertEqual(
            widgets.qemupath_chooser.get_current_folder(), self.project_bin
        )
        self.assertTrue(widgets.femaleplugs_switch.get_active())
        self.assertEqual(
            settings_window.combobox_get_active_value(widgets.cowfmt_combo, 0),
            "cow",
        )
        new = dialog.new_project_widgets
        self.assertEqual(
            new.qemupath_chooser.get_current_folder(), self.app_bin
        )
        self.assertFalse(new.femaleplugs_switch.get_active())

    def test_ok_stores_every_tab(self):
        prj = self.open_project()
        saved = []
        self.patch(self.manager, "save_current", saved.append)
        dialog = self.dialog()
        dialog.term_entry.set_text("/usr/bin/foot")
        dialog.systray_switch.set_active(False)
        dialog.project_widgets.erroronloop_switch.set_active(True)
        dialog.new_project_widgets.vdepath_chooser.set_current_folder(
            self.project_bin
        )
        settings_window.combobox_set_active_value(
            dialog.new_project_widgets.cowfmt_combo, "qcow", 0
        )
        dialog.on_dialog_response(dialog.dialog, Gtk.ResponseType.OK)
        self.assertEqual(get_app_setting("term"), "/usr/bin/foot")
        self.assertIs(get_app_setting("systray"), False)
        # the project tab changed the project only
        self.assertIs(prj.project_settings.erroronloop, True)
        self.assertIs(get_app_setting("erroronloop"), False)
        self.assertEqual(prj.project_settings.qemupath, self.project_bin)
        # the new projects tab changed the application settings only
        self.assertEqual(get_app_setting("vdepath"), self.project_bin)
        self.assertEqual(get_app_setting("cowfmt"), "qcow")
        self.assertEqual(prj.project_settings.cowfmt, "cow")
        self.assertEqual(saved, [self.factory])
        self.assertEqual(dialog.virtualbricks_gui.systray, ["stop"])
        self.assertEqual(self.ksm, [False])
        self.assertEqual(
            load_toml(locations.settings_file())["term"],
            "/usr/bin/foot",
        )

    def test_ok_without_a_project(self):
        dialog = self.dialog()
        dialog.project_widgets.femaleplugs_switch.set_active(True)
        dialog.on_dialog_response(dialog.dialog, Gtk.ResponseType.OK)
        self.assertIs(get_app_setting("femaleplugs"), False)
        self.assertEqual(dialog.virtualbricks_gui.systray, ["start"])

    def test_cancel(self):
        dialog = self.dialog()
        dialog.term_entry.set_text("/usr/bin/foot")
        dialog.on_dialog_response(dialog.dialog, Gtk.ResponseType.CANCEL)
        self.assertEqual(get_app_setting("term"), "/usr/bin/xterm")
        self.assertFalse(os.path.exists(locations.settings_file()))

    def test_unset_widgets_keep_the_values(self):
        widgets = settings_window.ProjectSettingsWidgets("note")
        values = {}
        widgets.store(values.__setitem__)
        self.assertEqual(values, {"femaleplugs": False, "erroronloop": False})
