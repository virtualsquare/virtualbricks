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

"""The panel of a switch wrapper."""

from virtualbricks.tests.gui import GuiTestCase, has_display, untranslated

if has_display:
    from virtualbricks.gui.mainwindow.bricks.config import new_panel
    from virtualbricks.gui.mainwindow.bricks.config.switchwrapperconfig import (
        SwitchWrapperPanel,
    )


class TestTheSwitchWrapperPanel(GuiTestCase):

    def test_its_folder(self):
        untranslated(self)
        wrapper = self.factory.new_brick("switchwrapper", "sww")
        wrapper.update_config({"socket_path": "/run/vde/sw"})
        panel = new_panel(wrapper)
        self.addCleanup(panel.widget.destroy)
        self.assertIsInstance(panel, SwitchWrapperPanel)
        self.assertEqual(list(panel.form.rows), ["socket_path"])
        row = panel.form.rows["socket_path"]
        self.assertEqual(row.title.get_text(), "Control folder")
        entry = row.title.get_mnemonic_widget()
        self.assertEqual(entry.get_text(), "/run/vde/sw")
        entry.set_text("/run/vde/other")
        self.assertEqual(
            panel.draft.changes(), {"socket_path": "/run/vde/other"}
        )
