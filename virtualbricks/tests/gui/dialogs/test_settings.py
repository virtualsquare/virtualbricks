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
from virtualbricks.config.settings import get_setting, set_setting
from virtualbricks.config.tomlfile import load_toml
from virtualbricks.tests.gui import FakeGui, GuiTestCase, has_display

if has_display:
    from gi.repository import Gtk

    from virtualbricks.gui.dialogs import settings as settings_window


class TestSettingsDialog(GuiTestCase):

    def setUp(self):
        super().setUp()
        self.project_bin = self.folder("project-bin")

    def dialog(self):
        dialog = settings_window.SettingsDialog(FakeGui(self.factory))
        self.addCleanup(dialog.dialog.destroy)
        return dialog

    def open_project(self):
        self.manager.create("lab")
        self.manager.open("lab", self.factory)
        prj = self.manager.current
        set_setting("qemu_path", self.project_bin)
        set_setting("allow_female_plugs", True)
        set_setting("cow_format", "cow")
        return prj

    def test_tabs(self):
        children = self.dialog().dialog.get_content_area().get_children()
        [notebook] = [c for c in children if isinstance(c, Gtk.Notebook)]
        labels = [
            notebook.get_tab_label_text(notebook.get_nth_page(i))
            for i in range(notebook.get_n_pages())
        ]
        self.assertEqual(labels, ["Application", "This project"])

    def test_no_open_project(self):
        dialog = self.dialog()
        widgets = dialog.project_widgets
        # the defaults, which can't be changed
        self.assertFalse(widgets.grid.get_sensitive())
        self.assertEqual(
            widgets.qemu_path_chooser.get_current_folder(), "/usr/bin"
        )
        self.assertEqual(
            settings_window.combobox_get_active_value(
                widgets.cow_format_combo, 0
            ),
            "qcow2",
        )
        self.assertEqual(
            dialog.terminal_entry.get_text(), get_setting("terminal")
        )

    def test_open_project(self):
        self.open_project()
        dialog = self.dialog()
        widgets = dialog.project_widgets
        self.assertTrue(widgets.grid.get_sensitive())
        self.assertEqual(
            widgets.qemu_path_chooser.get_current_folder(), self.project_bin
        )
        self.assertTrue(widgets.female_plugs_switch.get_active())
        self.assertEqual(
            settings_window.combobox_get_active_value(
                widgets.cow_format_combo, 0
            ),
            "cow",
        )

    def test_ok_stores_both_tabs(self):
        prj = self.open_project()
        saved = []
        self.patch(self.manager, "save", saved.append)
        dialog = self.dialog()
        dialog.terminal_entry.set_text("/usr/bin/foot")
        dialog.tray_icon_switch.set_active(False)
        dialog.project_widgets.link_loops_switch.set_active(True)
        dialog.on_dialog_response(dialog.dialog, Gtk.ResponseType.OK)
        self.assertEqual(get_setting("terminal"), "/usr/bin/foot")
        self.assertIs(get_setting("tray_icon"), False)
        self.assertIs(prj.settings.log_link_loops, True)
        self.assertEqual(prj.settings.qemu_path, self.project_bin)
        self.assertEqual(saved, [self.factory])
        self.assertEqual(dialog.virtualbricks_gui.systray, ["stop"])
        self.assertEqual(self.ksm, [False])
        data = load_toml(locations.settings_file())
        self.assertEqual(data["terminal"], "/usr/bin/foot")
        # the settings of the project are in the project only
        self.assertNotIn("log_link_loops", data)

    def test_ok_without_a_project(self):
        dialog = self.dialog()
        dialog.project_widgets.female_plugs_switch.set_active(True)
        dialog.on_dialog_response(dialog.dialog, Gtk.ResponseType.OK)
        self.assertIs(get_setting("allow_female_plugs"), False)
        self.assertEqual(dialog.virtualbricks_gui.systray, ["start"])

    def test_cancel(self):
        dialog = self.dialog()
        dialog.terminal_entry.set_text("/usr/bin/foot")
        dialog.on_dialog_response(dialog.dialog, Gtk.ResponseType.CANCEL)
        self.assertEqual(get_setting("terminal"), "/usr/bin/xterm")
        self.assertFalse(os.path.exists(locations.settings_file()))

    def test_unset_widgets_keep_the_values(self):
        widgets = settings_window.ProjectSettingsWidgets("note")
        values = {}
        widgets.store(values.__setitem__)
        self.assertEqual(
            values, {"allow_female_plugs": False, "log_link_loops": False}
        )
