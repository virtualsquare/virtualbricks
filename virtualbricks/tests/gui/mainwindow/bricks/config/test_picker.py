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

"""The picker: what is chosen, a list with a search, the choice kept."""

from virtualbricks.tests.gui import GuiTestCase, has_display, untranslated

if has_display:
    from virtualbricks.gui.mainwindow.bricks.config.picker import (
        Option,
        Picker,
    )

OPTIONS = [
    Option(
        "pc-q35-7.0",
        "pc-q35-7.0",
        "Standard PC (Q35 + ICH9, 2009) (deprecated)",
    ),
    Option("q35", "q35", "Standard PC (Q35 + ICH9, 2009)"),
    Option("isapc", "isapc", "ISA-only PC"),
]


class TestAPicker(GuiTestCase):

    def setUp(self):
        super().setUp()
        untranslated(self)
        self.chosen = []
        self.picker = Picker("q35", self.chosen.append, "not in QEMU 10.0.13")
        self.addCleanup(self.picker.destroy)

    def names(self):
        return [row.option.name for row in self.picker.list.get_children()]

    def test_before_the_options(self):
        self.assertEqual(self.names(), ["q35"])
        self.assertEqual(self.picker.name.get_text(), "q35")
        self.assertEqual(self.picker.words.get_text(), "not in QEMU 10.0.13")

    def test_the_options(self):
        self.picker.set_options(OPTIONS)
        # the deprecated last
        self.assertEqual(self.names(), ["q35", "isapc", "pc-q35-7.0"])
        rows = self.picker.list.get_children()
        self.assertEqual(
            [row.get_child().get_children()[0].get_opacity() for row in rows],
            [1.0, 0.0, 0.0],
        )
        self.assertEqual(
            self.picker.words.get_text(), "Standard PC (Q35 + ICH9, 2009)"
        )
        self.assertTrue(
            rows[2].name.get_style_context().has_class("dim-label")
        )

    def test_a_choice_it_hasnt(self):
        self.picker.set_options(OPTIONS[2:])
        self.assertEqual(self.names(), ["q35", "isapc"])
        self.assertEqual(
            self.picker.list.get_children()[0].option,
            Option("q35", "q35", "not in QEMU 10.0.13"),
        )

    def test_choose(self):
        self.picker.set_options(OPTIONS)
        rows = self.picker.list.get_children()
        self.picker.list.emit("row-activated", rows[1])
        self.assertEqual(self.chosen, ["isapc"])
        self.assertEqual(self.picker.value, "isapc")
        self.assertEqual(self.picker.name.get_text(), "isapc")

    def test_search(self):
        self.picker.set_options(OPTIONS)
        rows = self.picker.list.get_children()
        self.picker.search.set_text("ich9")
        self.assertEqual(
            [self.picker._matches(row) for row in rows], [True, False, True]
        )
        self.picker.search.set_text("ISA")
        self.assertEqual(
            [self.picker._matches(row) for row in rows], [False, True, False]
        )
