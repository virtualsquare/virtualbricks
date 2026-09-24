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

import os
import stat
import tempfile

from twisted.trial import unittest

from virtualbricks import locations


class TestLocations(unittest.TestCase):

    def setUp(self):
        self.env = {"HOME": "/home/alice"}
        self.patch(os, "environ", self.env)

    def test_defaults(self):
        self.assertEqual(locations.home(), "/home/alice")
        self.assertEqual(
            locations.config_dir(), "/home/alice/.config/virtualbricks"
        )
        self.assertEqual(
            locations.state_dir(), "/home/alice/.local/state/virtualbricks"
        )
        self.assertEqual(
            locations.settings_file(),
            "/home/alice/.config/virtualbricks/settings.toml",
        )
        self.assertEqual(
            locations.state_file(),
            "/home/alice/.local/state/virtualbricks/state.toml",
        )
        self.assertEqual(
            locations.default_workspace(), "/home/alice/.virtualbricks"
        )
        self.assertEqual(
            locations.legacy_settings_file(), "/home/alice/.virtualbricks.conf"
        )

    def test_xdg_variables(self):
        self.env.update(XDG_CONFIG_HOME="/cfg", XDG_STATE_HOME="/st")
        self.assertEqual(locations.config_dir(), "/cfg/virtualbricks")
        self.assertEqual(locations.state_dir(), "/st/virtualbricks")

    def test_relative_xdg_variables_are_ignored(self):
        self.env.update(XDG_CONFIG_HOME="cfg", XDG_RUNTIME_DIR="run")
        self.assertEqual(
            locations.config_dir(), "/home/alice/.config/virtualbricks"
        )
        self.assertEqual(
            locations.runtime_dir(),
            os.path.join(
                tempfile.gettempdir(), f"virtualbricks-{os.getuid()}"
            ),
        )

    def test_runtime_dir(self):
        self.env["XDG_RUNTIME_DIR"] = "/run/user/1000"
        self.assertEqual(
            locations.runtime_dir(), "/run/user/1000/virtualbricks"
        )

    def test_runtime_dir_without_xdg(self):
        self.assertTrue(
            locations.runtime_dir().endswith(f"virtualbricks-{os.getuid()}")
        )

    def test_ensure_private_dir(self):
        path = os.path.join(self.mktemp(), "a", "b")
        self.assertEqual(locations.ensure_private_dir(path), path)
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o700)
        # a second call is fine
        locations.ensure_private_dir(path)
