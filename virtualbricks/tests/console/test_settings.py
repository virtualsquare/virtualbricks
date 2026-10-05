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

"""The commands of the settings."""

from virtualbricks import locations
from virtualbricks.config.settings import get_setting
from virtualbricks.config.tomlfile import load_toml
from virtualbricks.tests.console import ConsoleTestCase


class TestSettings(ConsoleTestCase):

    def test_show(self):
        lines = self.run_line("setting show")
        self.assertEqual(lines[0], "# Virtualbricks")
        self.assertIn('terminal = "x-terminal-emulator"', lines)
        self.assertEqual(lines[lines.index("") + 1], "# This project")
        self.assertIn('qemu_path = "/usr/bin"', lines)
        self.assertEqual(
            self.run_line("setting show tray_icon"), ["tray_icon = true"]
        )
        self.assertEqual(
            self.fails("setting show nope"),
            "No setting nope: setting show lists them",
        )

    def test_set(self):
        self.assertEqual(
            self.run_line("setting set tray_icon=false qemu_path=/opt/qemu"),
            [],
        )
        self.assertFalse(get_setting("tray_icon"))
        self.assertEqual(get_setting("qemu_path"), "/opt/qemu")
        # settings.toml has the settings of Virtualbricks
        written = load_toml(locations.settings_file())
        self.assertFalse(written["tray_icon"])

    def test_all_or_none(self):
        self.assertEqual(
            self.fails("setting set tray_icon=false log_link_loops=qed"),
            "log_link_loops: 'qed' is not true or false",
        )
        self.assertTrue(get_setting("tray_icon"))
        self.assertEqual(
            self.fails("setting set nope=1"),
            "No setting nope: setting show lists them",
        )

    def test_unset(self):
        self.run_line("setting set tray_icon=false qemu_path=/opt/qemu")
        self.assertEqual(
            self.run_line("setting unset tray_icon qemu_path"), []
        )
        self.assertTrue(get_setting("tray_icon"))
        self.assertEqual(get_setting("qemu_path"), "/usr/bin")
