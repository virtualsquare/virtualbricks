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


"""The application window: the startup migration."""

import os


from virtualbricks.config import locations
from virtualbricks.tests.gui import GuiTestCase, has_display
from virtualbricks.tests.migrate.fixtures import (
    CONFIG1,
    write_project,
    write_settings,
)

if has_display:

    from virtualbricks.gui import gui
    from virtualbricks.migrate import gui as migrate_gui


class TestStartupMigration(GuiTestCase):

    def setUp(self):
        super().setUp()
        self.shown = []
        self.patch(
            migrate_gui.MigrationWindow,
            "show",
            lambda window: self.shown.append(window),
        )
        self.app = gui.Application.__new__(gui.Application)

    def test_nothing_to_migrate(self):
        self.assertIsNone(self.app.migrate())
        self.assertEqual(self.shown, [])

    def test_show_the_migration(self):
        workspace = os.path.join(self.root, ".virtualbricks")
        write_settings(locations.legacy_settings_file(), workspace, "lab")
        write_project(workspace, "lab", CONFIG1)
        closed = self.app.migrate()
        window = self.shown[0]
        self.addCleanup(window.window.destroy)
        self.assertTrue(window.fixed)
        self.assertIs(closed, window.closed)
        self.assertEqual(
            [item.name for item in window.migration.items],
            [locations.LEGACY_SETTINGS_FILE, "lab"],
        )

    def test_start_sets_the_title(self):
        titles = []

        class VBGUI:
            def set_title(self):
                titles.append("set")

        self.app.gui = VBGUI()
        self.patch(
            gui.brickfactory.Application, "_start", lambda app, reactor: "quit"
        )
        self.assertEqual(self.app._start("reactor"), "quit")
        self.assertEqual(titles, ["set"])
