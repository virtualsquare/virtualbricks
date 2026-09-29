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

"""The virtualbricks command: with the windows, or without."""

import sys

from twisted.trial import unittest

from virtualbricks import app, brickfactory
from virtualbricks.scripts import virtualbricks
from virtualbricks.tests import isolate


class TestRun(unittest.TestCase):

    def setUp(self):
        isolate(self)
        self.ran = []
        self.patch(
            app,
            "run_app",
            lambda application, config: self.ran.append(
                (application(config), config)
            ),
        )

    def test_without_the_windows(self):
        self.patch(sys, "argv", ["virtualbricks", "--no-gui", "--noterm"])
        virtualbricks.run()
        [(locked, config)] = self.ran
        self.assertTrue(config["no-gui"])
        self.assertIs(locked.factory, virtualbricks.make_plain_application)
        plain = locked.factory(config)
        self.assertIs(type(plain), brickfactory.Application)
