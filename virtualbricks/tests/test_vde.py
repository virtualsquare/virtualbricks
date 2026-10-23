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


"""Finding the VDE programs."""

import os

from twisted.trial import unittest

from virtualbricks.config import settings
from virtualbricks.tests import isolate, reset_settings
from virtualbricks.vde import which


class TestWhich(unittest.TestCase):
    """The folder of vde_path, and one on PATH, with no programs yet."""

    def setUp(self):
        isolate(self)
        reset_settings(self)
        self.vde = self.folder("vde")
        self.bin = self.folder("bin")
        settings.use_project(settings.ProjectSettings(vde_path=self.vde))
        os.environ["PATH"] = self.bin

    def folder(self, name):
        path = os.path.abspath(self.mktemp() + "-" + name)
        os.makedirs(path)
        return path

    def program(self, folder, name, mode=0o755):
        path = os.path.join(folder, name)
        with open(path, "w") as fp:
            fp.write("#!/bin/sh\n")
        os.chmod(path, mode)
        return path

    def test_in_vde_path(self):
        path = self.program(self.vde, "vdeterm")
        self.program(self.bin, "vdeterm")
        self.assertEqual(which("vdeterm"), path)

    def test_on_path(self):
        path = self.program(self.bin, "vdeterm")
        self.assertEqual(which("vdeterm"), path)

    def test_a_path(self):
        """A program given by its path is itself, where it is."""

        path = self.program(self.folder("opt"), "vde_switch")
        self.program(self.vde, "vde_switch")
        self.assertEqual(which(path), path)

    def test_not_executable(self):
        self.program(self.vde, "vdeterm", mode=0o644)
        path = self.program(self.bin, "vdeterm")
        self.assertEqual(which("vdeterm"), path)

    def test_none(self):
        self.program(self.vde, "vdeterm", mode=0o644)
        self.assertRaises(FileNotFoundError, which, "vdeterm")
