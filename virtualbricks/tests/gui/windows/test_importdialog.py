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


"""The import of a project: the paths of the machine and the images."""

from twisted.python import filepath

from virtualbricks import config
from virtualbricks.tests.gui import GuiTestCase, has_display

if has_display:
    from gi.repository import Gtk

    from virtualbricks.gui.windows import importdialog


class TestImportMachinePaths(GuiTestCase):

    def setUp(self):
        super().setUp()
        self.ours = self.folder("bin")
        config.set_app("qemupath", self.ours)
        config.set_app("vdepath", self.ours)
        self.dialog = importdialog.ImportDialog(self.factory)
        self.addCleanup(self.dialog.get_root_widget().destroy)
        self.humble = importdialog._HumbleImport()

    def imported(self, **project_settings):
        prj = self.manager.get_project("imported").create()
        data = prj.read_document()
        data["settings"].update(project_settings)
        prj.write_document(data)
        self.dialog.project = prj
        return prj

    def checks(self):
        return {
            key: (check.get_visible(), check.get_active(), check.get_label())
            for key, check in self.dialog.machine_path_checks.items()
        }

    def test_paths_that_are_not_here(self):
        self.imported(qemupath="/opt/elsewhere/qemu", vdepath=self.ours)
        self.humble.show_machine_paths(self.dialog)
        self.assertEqual(
            self.checks(),
            {
                "qemupath": (
                    True,
                    True,
                    f"Use qemupath of this machine, {self.ours}, instead of "
                    "/opt/elsewhere/qemu",
                ),
                "vdepath": (False, False, None),
            },
        )

    def test_paths_that_are_here_too(self):
        other = self.folder("other-bin")
        self.imported(vdepath=other)
        self.humble.show_machine_paths(self.dialog)
        visible, active, _ = self.checks()["vdepath"]
        self.assertEqual((visible, active), (True, False))

    def test_no_settings(self):
        prj = self.imported()
        data = prj.read_document()
        del data["settings"]
        prj.write_document(data)
        self.humble.show_machine_paths(self.dialog)
        self.assertEqual(
            [visible for visible, _, _ in self.checks().values()],
            [False, False],
        )

    def test_use_machine_paths(self):
        entry = {}
        self.humble.use_machine_paths(entry, ["vdepath"])
        self.assertEqual(entry, {"settings": {"vdepath": self.ours}})

    def test_confirm_page(self):
        self.imported(qemupath="/opt/elsewhere/qemu")
        self.dialog.set_project_name("lab")
        self.humble.step_3(self.dialog)
        self.assertTrue(
            self.dialog.machine_path_checks["qemupath"].get_visible()
        )
        self.assertEqual(self.dialog.project_name_label.get_text(), "lab")

    def test_extract(self):
        prj = self.imported()
        data = prj.read_document()
        data["images"] = {"deb": {"path": "/i/deb.qcow2", "description": ""}}
        prj.write_document(data)
        self.assertIs(self.humble.extract_cb(prj, self.dialog), prj)
        self.assertEqual(self.dialog.images, {"deb": "/i/deb.qcow2"})

    def test_apply(self):
        self.imported(
            qemupath="/opt/elsewhere/qemu", vdepath="/opt/elsewhere/vde"
        )
        self.dialog.set_project_name("lab")
        self.humble.show_machine_paths(self.dialog)
        # the user keeps the path of vde of the other machine
        self.dialog.machine_path_checks["vdepath"].set_active(False)
        waited = []

        class ProgressBar:
            def __init__(self, assistant):
                pass

            def wait_for(self, deferred):
                waited.append(deferred)

        self.patch(importdialog, "ProgressBar", ProgressBar)
        self.dialog.on_assistant_apply(self.dialog.get_root_widget())
        self.successResultOf(waited[0])
        data = config.load_toml(self.manager.get_project("lab").project_file)
        self.assertEqual(data["settings"]["qemupath"], self.ours)
        self.assertEqual(data["settings"]["vdepath"], "/opt/elsewhere/vde")


class TestImportImages(GuiTestCase):

    def test_remap(self):
        entry = {
            "images": {
                "deb": {"path": "/old/deb.qcow2", "description": ""},
                "arch": {"path": "/old/arch.qcow2", "description": ""},
            }
        }
        store = Gtk.ListStore(str, object)
        store.append(("arch", filepath.FilePath("/new/arch.qcow2")))
        saved = {"deb": filepath.FilePath("/new/deb.qcow2")}
        importdialog._HumbleImport().remap_images(entry, store, saved)
        self.assertEqual(entry["images"]["deb"]["path"], "/new/deb.qcow2")
        self.assertEqual(entry["images"]["arch"]["path"], "/new/arch.qcow2")
        self.assertEqual(sorted(saved), ["arch", "deb"])
