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


"""The launcher: the lock, the logging, the options."""

import os

from twisted.python import usage
from twisted.trial import unittest

from virtualbricks import app, locations
from virtualbricks.tests import isolate


class TestLock(unittest.TestCase):

    def setUp(self):
        isolate(self)

    def test_global_lock(self):
        application = app._LockedApplication({})
        self.assertEqual(application.lock.name, locations.LOCK_FILE)


class TestWorkspace(unittest.TestCase):

    def setUp(self):
        self.root = isolate(self)

    def parse(self, *args):
        options = app.Options()
        options.parseOptions(list(args))
        return options["workspace"]

    def test_the_setting_without_it(self):
        self.assertIsNone(self.parse())

    def test_an_absolute_path(self):
        self.assertEqual(self.parse("--workspace", "/srv/labs/"), "/srv/labs")
        self.assertEqual(self.parse("--workspace=/srv/labs"), "/srv/labs")

    def test_home_and_the_current_folder(self):
        self.assertEqual(
            self.parse("--workspace", "~/labs"),
            os.path.join(self.root, "labs"),
        )
        self.assertEqual(
            self.parse("--workspace", "labs"),
            os.path.join(os.getcwd(), "labs"),
        )

    def test_not_a_folder(self):
        path = os.path.join(self.root, "file")
        open(path, "w").close()
        error = self.assertRaises(
            usage.UsageError, self.parse, "--workspace", path
        )
        self.assertEqual(str(error), f"--workspace: {path} is not a folder")
        self.assertRaises(usage.UsageError, self.parse, "--workspace", "")
