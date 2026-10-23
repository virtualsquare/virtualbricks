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

"""The trash of the desktop that the GUI gives to the workspace."""

import os

from gi.repository import Gio, GLib
from twisted.trial import unittest

from virtualbricks import errors
from virtualbricks.gui.trash import DesktopTrash


class TestDesktopTrash(unittest.TestCase):

    def fake_file(self, error):
        class File:
            def trash(self, cancellable):
                raise GLib.Error.new_literal(
                    Gio.io_error_quark(), "cannot", error
                )

        self.patch(Gio.File, "new_for_path", staticmethod(lambda p: File()))

    def test_not_supported(self):
        self.fake_file(Gio.IOErrorEnum.NOT_SUPPORTED)
        self.assertRaises(
            errors.TrashNotSupportedError, DesktopTrash().trash, "/lab"
        )

    def test_other_errors(self):
        self.fake_file(Gio.IOErrorEnum.PERMISSION_DENIED)
        self.assertRaises(OSError, DesktopTrash().trash, "/lab")

    def test_can_trash(self):
        trash = DesktopTrash()
        self.assertFalse(trash.can_trash(self.mktemp()))
        path = os.path.abspath(self.mktemp())
        os.makedirs(path)
        # it depends on the file system; asking changes nothing
        self.assertIsInstance(trash.can_trash(path), bool)
        self.assertTrue(os.path.isdir(path))
