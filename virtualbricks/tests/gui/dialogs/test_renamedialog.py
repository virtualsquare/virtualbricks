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

"""Rename a brick, an event or an image."""

import errno

from twisted.internet import defer

from virtualbricks.console import ampwire
from virtualbricks.engine import LocalEngine
from virtualbricks.tests.gui import GuiTestCase, has_display

if has_display:
    from gi.repository import Gtk

    from virtualbricks.gui.dialogs.renamedialog import RenameDialog


class RenameTestCase(GuiTestCase):

    def setUp(self):
        super().setUp()
        self.factory.runtime_dir = "/run/vb"
        self.engine = LocalEngine(self.factory)
        self.sw1 = self.factory.new_brick("switch", "sw1")
        self.vm1 = self.factory.new_brick("qemu", "vm1")
        self.boot = self.factory.new_event("boot")
        self.image = self.factory.new_image("deb", "/lab/deb.qcow2")
        self.destroyed = []

    def dialog(self, item):
        dialog = RenameDialog(self.engine, item)
        dialog.dialog.connect("destroy", self.destroyed.append)
        self.addCleanup(dialog.dialog.destroy)
        return dialog

    def type(self, dialog, name):
        """Whether Rename is sensitive, and the line under the field."""

        dialog.name_entry.set_text(name)
        return dialog.rename_button.get_sensitive(), (
            dialog.name_message.get_text()
            if dialog.name_message.get_visible()
            else None
        )

    def ok(self, dialog):
        dialog.dialog.response(Gtk.ResponseType.OK)

    def error(self, dialog):
        """The red line of a refusal, if it shows."""

        label = dialog.error_label
        return label.get_text() if label.get_visible() else None


class TestTheDialog(RenameTestCase):

    def test_the_title_says_what(self):
        for item, title in (
            (self.sw1, "Rename Brick"),
            (self.vm1, "Rename Brick"),
            (self.boot, "Rename Event"),
            (self.image, "Rename Image"),
        ):
            dialog = self.dialog(item)
            header = dialog.dialog.get_header_bar()
            self.assertEqual(header.get_title(), title)
            self.assertEqual(header.get_subtitle(), item.name)

    def test_the_name_selected(self):
        # typing replaces it; Rename waits for another
        dialog = self.dialog(self.sw1)
        self.assertEqual(dialog.name_entry.get_text(), "sw1")
        self.assertEqual(dialog.name_entry.get_selection_bounds(), (0, 3))
        self.assertFalse(dialog.rename_button.get_sensitive())
        self.assertFalse(dialog.name_message.get_visible())

    def test_as_you_type(self):
        dialog = self.dialog(self.sw1)
        self.assertEqual(self.type(dialog, ""), (False, None))
        self.assertEqual(self.type(dialog, "core"), (True, None))
        self.assertEqual(
            self.type(dialog, "lab sw"), (True, "It will be named lab_sw")
        )
        # the old name, written another way
        self.assertEqual(self.type(dialog, " sw1 "), (False, None))
        for name, message in (
            ("vm1", "vm1 is the name of a brick"),
            ("boot", "boot is the name of an event"),
            ("deb", "deb is the name of an image"),
            ("1sw", "A name starts with a letter"),
            (
                "sw/1",
                "A name has only letters, digits, underscores (_), hyphens"
                " (-) and dots (.)",
            ),
        ):
            self.assertEqual(self.type(dialog, name), (False, message), name)

    def test_a_brick_has_sockets_and_a_kind(self):
        # its name goes in the paths of its sockets; an event's doesn't
        long = "x" * 120
        usable, message = self.type(self.dialog(self.sw1), long)
        self.assertFalse(usable)
        self.assertTrue(message.startswith("The name is 120 bytes long"))
        self.assertEqual(self.type(self.dialog(self.boot), long), (True, None))
        tap = self.factory.new_brick("tap", "tap1")
        usable, message = self.type(self.dialog(tap), "t" * 16)
        self.assertFalse(usable)
        self.assertIsNotNone(message)


class TestTheRename(RenameTestCase):

    def test_rename(self):
        dialog = self.dialog(self.sw1)
        self.type(dialog, "core switch")
        self.ok(dialog)
        self.assertEqual(self.sw1.name, "core_switch")
        self.assertEqual(len(self.destroyed), 1)

    def test_an_event_and_an_image(self):
        for item, name in ((self.boot, "start"), (self.image, "debian")):
            dialog = self.dialog(item)
            self.type(dialog, name)
            self.ok(dialog)
            self.assertEqual(item.name, name)
        self.assertIs(self.factory.get_event("start"), self.boot)
        self.assertIs(self.factory.get_image("debian"), self.image)

    def test_enter_waits_for_a_name(self):
        # nothing is asked, here or over a connection
        asked = []
        self.patch(self.engine, "rename", lambda *args: asked.append(args))
        dialog = self.dialog(self.sw1)
        self.type(dialog, "vm1")
        self.ok(dialog)
        self.assertEqual(asked, [])
        self.assertEqual(self.destroyed, [])

    def test_cancel(self):
        dialog = self.dialog(self.sw1)
        self.type(dialog, "core")
        dialog.dialog.response(Gtk.ResponseType.CANCEL)
        self.assertEqual(self.sw1.name, "sw1")
        self.assertEqual(len(self.destroyed), 1)

    def test_once_while_it_is_asked(self):
        answer = defer.Deferred()
        self.patch(self.engine, "rename", lambda item, name: answer)
        dialog = self.dialog(self.sw1)
        self.type(dialog, "core")
        self.ok(dialog)
        self.assertFalse(dialog.rename_button.get_sensitive())
        self.assertEqual(self.destroyed, [])
        answer.callback("sw1")
        self.assertEqual(len(self.destroyed), 1)


class TestARefusal(RenameTestCase):

    def refuse(self, error):
        self.patch(self.engine, "rename", lambda item, name: defer.fail(error))

    def test_the_private_copies(self):
        self.refuse(
            PermissionError(
                errno.EACCES, "Permission denied", "/lab/vm1_hda.cow"
            )
        )
        dialog = self.dialog(self.vm1)
        self.type(dialog, "core")
        self.ok(dialog)
        # it stays, with the reason, and Rename can be tried again
        self.assertEqual(self.destroyed, [])
        self.assertEqual(
            self.error(dialog),
            "Cannot rename the private copy vm1_hda.cow: Permission denied",
        )
        self.assertTrue(dialog.rename_button.get_sensitive())
        # until something else is typed
        self.type(dialog, "core2")
        self.assertIsNone(self.error(dialog))

    def test_over_a_connection(self):
        self.refuse(ampwire.CommandFailed("lab.example refused it"))
        dialog = self.dialog(self.sw1)
        self.type(dialog, "core")
        self.ok(dialog)
        self.assertEqual(self.error(dialog), "lab.example refused it")

    def test_a_name_taken_meanwhile(self):
        dialog = self.dialog(self.sw1)
        self.type(dialog, "core")
        self.factory.new_brick("switch", "core")
        self.ok(dialog)
        self.assertEqual(self.destroyed, [])
        # the line under the field says it; no red line
        self.assertEqual(
            (
                dialog.rename_button.get_sensitive(),
                dialog.name_message.get_text(),
            ),
            (False, "core is the name of a brick"),
        )
        self.assertIsNone(self.error(dialog))
