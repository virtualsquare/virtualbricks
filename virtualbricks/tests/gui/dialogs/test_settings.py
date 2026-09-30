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

from twisted.internet import defer


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

    def test_one_page_here(self):
        # the rows of the machine of the bricks under those of the windows
        dialog = self.dialog()
        grid = dialog.terminal_entry.get_parent()
        self.assertIs(dialog.enable_ksm_switch.get_parent(), grid)
        self.assertEqual(
            grid.child_get_property(dialog.enable_ksm_switch, "top-attach"), 3
        )
        self.assertIsNone(dialog.workspace_label)

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


class SettingsThere:
    """The settings of the Virtualbricks there, as its copy has them."""

    def __init__(self, values):
        self.values = values

    def setting(self, name):
        return self.values[name]


class OpenThere:
    name = "ospf"


class WorkspaceThere:
    path = "/srv/labs"
    current = OpenThere()


class EngineThere:
    """The engine of windows over a connection: what it sends there."""

    local = False
    where = "lab.example"

    def __init__(self, values):
        self.machine = SettingsThere(values)
        self.workspace = WorkspaceThere()
        self.sent = []

    def set_settings(self, values):
        self.sent.append(("settings", values))
        return defer.succeed(None)

    def set_ksm(self, enable):
        self.sent.append(("ksm", enable))
        return defer.succeed(enable)


class TestOverAConnection(GuiTestCase):
    """This computer, the machine there, the project there (19 R10)."""

    def setUp(self):
        super().setUp()
        self.engine = EngineThere(
            {
                "kernel_samepage_merging": False,
                "audio_driver": "pipewire",
                "vde_path": "/opt/vde/bin",
                "qemu_path": "/opt/qemu/bin",
                "allow_female_plugs": True,
                "log_link_loops": False,
                "cow_format": "qcow2",
            }
        )
        gui = FakeGui(self.factory)
        gui.engine = self.engine
        self.dialog = settings_window.SettingsDialog(gui)
        self.addCleanup(self.dialog.dialog.destroy)

    def test_three_pages(self):
        children = self.dialog.dialog.get_content_area().get_children()
        [notebook] = [c for c in children if isinstance(c, Gtk.Notebook)]
        labels = [
            notebook.get_tab_label_text(notebook.get_nth_page(i))
            for i in range(notebook.get_n_pages())
        ]
        self.assertEqual(
            labels, ["This computer", "lab.example", "This project"]
        )
        self.assertEqual(self.dialog.workspace_label.get_text(), "/srv/labs")

    def test_the_settings_there(self):
        dialog = self.dialog
        self.assertEqual(dialog.audio_driver_entry.get_text(), "pipewire")
        widgets = dialog.project_widgets
        self.assertTrue(widgets.grid.get_sensitive())
        # typed: a chooser shows the folders of this computer
        self.assertIsInstance(widgets.qemu_path_chooser, Gtk.Entry)
        self.assertEqual(widgets.qemu_path_chooser.get_text(), "/opt/qemu/bin")
        self.assertTrue(widgets.female_plugs_switch.get_active())
        # those of the windows are this computer's
        self.assertEqual(
            dialog.terminal_entry.get_text(), get_setting("terminal")
        )

    def test_ksm_there(self):
        # KSM runs there, not here
        self.engine.machine.values["kernel_samepage_merging"] = True
        gui = FakeGui(self.factory)
        gui.engine = self.engine
        dialog = settings_window.SettingsDialog(gui)
        self.addCleanup(dialog.dialog.destroy)
        self.assertTrue(dialog.enable_ksm_switch.get_active())

    def test_ok(self):
        dialog = self.dialog
        audio_here = get_setting("audio_driver")
        dialog.terminal_entry.set_text("/usr/bin/foot")
        dialog.audio_driver_entry.set_text("pa")
        dialog.project_widgets.qemu_path_chooser.set_text("/usr/local/bin")
        dialog.on_dialog_response(dialog.dialog, Gtk.ResponseType.OK)
        # here
        self.assertEqual(get_setting("terminal"), "/usr/bin/foot")
        self.assertEqual(get_setting("audio_driver"), audio_here)
        # there
        [(kind, values), ksm] = self.engine.sent
        self.assertEqual(kind, "settings")
        self.assertEqual(values["audio_driver"], "pa")
        self.assertEqual(values["qemu_path"], "/usr/local/bin")
        self.assertEqual(values["vde_path"], "/opt/vde/bin")
        self.assertNotIn("terminal", values)
        self.assertEqual(ksm, ("ksm", False))
