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

"""New Brick: the popover of the kinds of bricks."""

import os
from unittest import mock

from virtualbricks.bricks.tap import Tap
from virtualbricks.config import settings
from virtualbricks.engine import LocalEngine
from virtualbricks.programs import VDE_PROGRAMS
from virtualbricks.tests.gui import GuiTestCase, has_display

if has_display:
    from gi.repository import Gtk

    from virtualbricks.bricks.brickinfo import NEW_KINDS
    from virtualbricks.gui.mainwindow.bricks.newbrick import NewBrickPopover


def install(folder, name):
    path = os.path.join(folder, name)
    with open(path, "w") as fp:
        fp.write("#!/bin/sh\n")
    os.chmod(path, 0o755)


class NewBrickTestCase(GuiTestCase):

    def setUp(self):
        super().setUp()
        self.factory.runtime_dir = "/run/vb"
        self.vde = self.folder()
        qemu = self.folder()
        for name in VDE_PROGRAMS:
            install(self.vde, name)
        install(qemu, "qemu-system-i386")
        # the folders are settings of the open project
        settings.use_project(settings.ProjectSettings())
        settings.set_setting("vde_path", self.vde)
        settings.set_setting("qemu_path", qemu)
        # only the folders: this computer's PATH has programs of its own
        patcher = mock.patch.dict(os.environ, {"PATH": ""})
        patcher.start()
        self.addCleanup(patcher.stop)
        # the window goes after the popover
        self.window = Gtk.OffscreenWindow()
        self.addCleanup(self.window.destroy)
        self.button = Gtk.Button(label="New Brick")
        self.window.add(self.button)
        self.window.show_all()
        self.made = []
        self.popover = NewBrickPopover(
            LocalEngine(self.factory), self.made.append
        )
        self.addCleanup(self.popover.destroy)

    def folder(self):
        path = os.path.abspath(self.mktemp())
        os.makedirs(path)
        return path

    def row(self, type):
        return next(row for row in self.popover.rows if row.kind.type == type)

    def make(self, type):
        self.popover.on_row_activated(self.popover.list, self.row(type))
        return self.made[-1]


class TestTheRows(NewBrickTestCase):

    def test_a_row_per_kind(self):
        rows = self.popover.rows
        self.assertEqual([row.kind for row in rows], list(NEW_KINDS))
        self.assertEqual(self.popover.list.get_children(), rows)
        for row in rows:
            self.assertEqual(row.name.get_text(), row.kind.words)

    def test_a_title_over_each_group(self):
        titles = []
        for row in self.popover.rows:
            header = row.get_header()
            if header is None:
                titles.append(None)
                continue
            *line, title = header.get_children()
            # a line between the groups
            titles.append((title.get_text(), len(line)))
        self.assertEqual(
            titles,
            [("Machines and switches", 0), None, None, None]
            + [("Links", 1), None, None, None]
            + [("This computer", 1), None],
        )

    def test_what_a_kind_is(self):
        self.popover.refresh()
        for row in self.popover.rows:
            self.assertEqual(row.line.get_text(), row.kind.line)
            self.assertTrue(
                row.line.get_style_context().has_class("dim-label")
            )
            self.assertFalse(row.warning.get_visible())
            self.assertEqual(row.get_tooltip_text(), row.kind.about)
            self.assertTrue(row.get_sensitive())

    def test_what_a_kind_lacks(self):
        os.remove(os.path.join(self.vde, "vde_cryptcab"))
        self.popover.refresh()
        row = self.row("TunnelConnect")
        self.assertEqual(row.line.get_text(), "vde_cryptcab isn't installed")
        self.assertFalse(row.line.get_style_context().has_class("dim-label"))
        self.assertTrue(row.warning.get_visible())
        self.assertEqual(
            row.get_tooltip_text(),
            "vde_cryptcab isn't installed: the package vde2-cryptcab has it."
            " The brick can be made now, and starts once it is installed.\n\n"
            + row.kind.about,
        )
        # it can be made all the same
        self.assertTrue(row.get_sensitive())
        self.assertFalse(self.row("Switch").warning.get_visible())

    def test_no_room_for_a_name(self):
        self.factory.runtime_dir = "/" + "r" * 104
        self.popover.refresh()
        for row in self.popover.rows:
            self.assertFalse(row.get_sensitive())
            self.assertEqual(row.line.get_text(), row.kind.line)
            self.assertFalse(row.warning.get_visible())
            reason, about = row.get_tooltip_text().split("\n\n")
            self.assertTrue(reason.startswith("The name is "), reason)
            self.assertEqual(about, row.kind.about)


class TestOpenAndMake(NewBrickTestCase):

    def test_a_click_makes_a_brick(self):
        tap = self.make("Tap")
        self.assertIsInstance(tap, Tap)
        self.assertEqual(tap.name, "tap1")
        self.assertIs(self.factory.get_brick("tap1"), tap)
        self.assertEqual(self.make("Tap").name, "tap2")

    def test_under_the_button(self):
        self.popover.popup_at(self.button)
        self.assertIs(self.popover.get_relative_to(), self.button)
        self.assertTrue(self.popover.get_visible())
        self.assertIs(
            self.popover.list.get_selected_row(), self.popover.rows[0]
        )

    def test_on_the_kind_made_last(self):
        self.make("Tap")
        self.popover.popup_at(self.button)
        self.assertIs(self.popover.list.get_selected_row(), self.row("Tap"))

    def test_said_again_at_each_opening(self):
        self.popover.popup_at(self.button)
        self.assertFalse(self.row("Wire").warning.get_visible())
        self.popover.popdown()
        os.remove(os.path.join(self.vde, "dpipe"))
        self.popover.popup_at(self.button)
        self.assertTrue(self.row("Wire").warning.get_visible())
