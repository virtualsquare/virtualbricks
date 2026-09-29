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

"""Finding the QEMU programs and running qemu-img."""

import os

from twisted.trial import unittest

from virtualbricks.config import settings
from virtualbricks.errors import CommandError
from virtualbricks.qemu.run import qemu_img, which
from virtualbricks.tests import isolate, reset_settings


class RunTestCase(unittest.TestCase):
    """The folder of qemu_path, and one on PATH, with no programs yet."""

    def setUp(self):
        isolate(self)
        reset_settings(self)
        self.qemu = self.folder("qemu")
        self.bin = self.folder("bin")
        settings.use_project(settings.ProjectSettings(qemu_path=self.qemu))
        os.environ["PATH"] = self.bin

    def folder(self, name):
        path = os.path.abspath(self.mktemp() + "-" + name)
        os.makedirs(path)
        return path

    def program(self, folder, name, script="", mode=0o755):
        path = os.path.join(folder, name)
        with open(path, "w") as fp:
            fp.write("#!/bin/sh\n" + script)
        os.chmod(path, mode)
        return path


class TestWhich(RunTestCase):
    def test_in_qemu_path(self):
        path = self.program(self.qemu, "qemu-img")
        self.program(self.bin, "qemu-img")
        self.assertEqual(which("qemu-img"), path)

    def test_on_path(self):
        path = self.program(self.bin, "qemu-img")
        self.assertEqual(which("qemu-img"), path)

    def test_a_path(self):
        """A program given by its path is itself, where it is."""

        path = self.program(self.folder("opt"), "qemu-system-x86_64")
        self.program(self.qemu, "qemu-system-x86_64")
        self.assertEqual(which(path), path)

    def test_not_executable(self):
        self.program(self.qemu, "qemu-img", mode=0o644)
        path = self.program(self.bin, "qemu-img")
        self.assertEqual(which("qemu-img"), path)

    def test_none(self):
        self.program(self.qemu, "qemu-img", mode=0o644)
        self.assertRaises(FileNotFoundError, which, "qemu-img")


class TestQemuImg(RunTestCase):
    def test_output(self):
        self.program(self.qemu, "qemu-img", 'echo "$@"\n')
        deferred = qemu_img(["info", "--output=json", "/lab/deb.qcow2"])
        deferred.addCallback(
            self.assertEqual, "info --output=json /lab/deb.qcow2\n"
        )
        return deferred

    def test_fails(self):
        self.program(self.qemu, "qemu-img", "echo broken >&2\nexit 3\n")
        deferred = self.assertFailure(qemu_img(["info"]), CommandError)

        def check(error):
            self.assertEqual(error.exit_code, 3)
            self.assertEqual(error.stderr, "broken\n")

        return deferred.addCallback(check)

    def test_no_qemu_img(self):
        self.assertRaises(FileNotFoundError, qemu_img, ["info"])
