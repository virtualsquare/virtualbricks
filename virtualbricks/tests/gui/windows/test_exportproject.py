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


"""The export of a project."""

import os

from virtualbricks import locations
from virtualbricks.tests.gui import GuiTestCase, has_display

if has_display:

    from virtualbricks.gui.windows import exportproject


class TestExport(GuiTestCase):

    def test_files(self):
        prj = self.manager.get_project("lab").create()
        for name in ("README", "notes.txt", locations.LEGACY_PROJECT_FILE):
            with open(os.path.join(prj.path, name), "w"):
                pass
        image = self.image("deb")
        dialog = exportproject.ExportProjectDialog(None, prj.path, [image])
        self.addCleanup(dialog.get_root_widget().destroy)
        dialog.build_path_tree(dialog.files_store, dialog.prjpath)
        calls = []

        def export(*args):
            calls.append(args)

        dialog.export(dialog.files_store, dialog.prjpath, "/out.vbp", export)
        filename, directory, files, images = calls[0]
        self.assertEqual((filename, directory), ("/out.vbp", prj.path))
        self.assertEqual(
            sorted(files), ["README", "notes.txt", "project.toml"]
        )
        self.assertEqual(images, [])
        dialog.include_images = True
        dialog.export(dialog.files_store, dialog.prjpath, "/out.vbp", export)
        self.assertEqual(calls[1][3], [("deb", image.path)])
