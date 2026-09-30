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

    def test_workspace_key(self):
        # eight letters and digits of base32, the same at every call
        key = locations.workspace_key("/home/alice/labs")
        self.assertRegex(key, r"\A[a-z2-7]{8}\Z")
        self.assertEqual(key, locations.workspace_key("/home/alice/labs"))
        self.assertNotEqual(key, locations.workspace_key("/home/alice/lab"))
        self.assertEqual(
            locations.workspace_key("/home/alice/labs/"),
            locations.workspace_key("/home/alice/./labs"),
        )

    def test_workspace_key_of_a_link(self):
        # the folder, whatever path names it
        root = os.path.abspath(self.mktemp())
        os.makedirs(os.path.join(root, "labs"))
        os.symlink("labs", os.path.join(root, "link"))
        self.assertEqual(
            locations.workspace_key(os.path.join(root, "link")),
            locations.workspace_key(os.path.join(root, "labs")),
        )

    def test_workspace_runtime_dir(self):
        self.env["XDG_RUNTIME_DIR"] = "/run/user/1000"
        key = locations.workspace_key("/home/alice/labs")
        self.assertEqual(
            locations.workspace_runtime_dir("/home/alice/labs"),
            f"/run/user/1000/virtualbricks/{key}",
        )

    def test_user_lock_file(self):
        # beside the runtime directories of the projects, named as none can be
        self.env["XDG_RUNTIME_DIR"] = "/run/user/1000"
        self.assertEqual(
            locations.user_lock_file(), "/run/user/1000/virtualbricks/.lock"
        )

    def test_control_socket(self):
        # beside the runtime directories of the projects, and its lock too
        self.env["XDG_RUNTIME_DIR"] = "/run/user/1000"
        socket = locations.control_socket()
        self.assertEqual(socket, "/run/user/1000/virtualbricks/.control")
        self.assertEqual(
            locations.control_lock_file(socket),
            "/run/user/1000/virtualbricks/.control.lock",
        )
        self.assertEqual(
            locations.control_lock_file("/home/alice/lab.sock"),
            "/home/alice/lab.sock.lock",
        )

    def test_short_path(self):
        self.assertEqual(
            locations.short_path("/home/alice/vm/a.img"), "~/vm/a.img"
        )
        self.assertEqual(locations.short_path("/home/alice"), "~")
        # a folder whose name starts as the home's
        self.assertEqual(
            locations.short_path("/home/alice2/a"), "/home/alice2/a"
        )
        self.assertEqual(locations.short_path("/srv/a.img"), "/srv/a.img")

    def test_workspace_lock_file(self):
        self.assertEqual(
            locations.workspace_lock_file("/home/alice/labs"),
            "/home/alice/labs/.virtualbricks.lock",
        )

    def test_token_file(self):
        # beside the settings
        self.env["XDG_CONFIG_HOME"] = "/home/alice/.config"
        self.assertEqual(
            locations.token_file(), "/home/alice/.config/virtualbricks/token"
        )

    def test_brick_name_room(self):
        # 107 bytes: the runtime directory, "/", the name, ".ctl/.<pid>-<n>"
        runtime_dir = "/run/user/1000/virtualbricks/lab"
        self.assertEqual(locations.brick_name_room(runtime_dir), 55)
        self.assertEqual(locations.brick_name_room("/" + "è" * 50), -14)

    def test_ensure_private_dir(self):
        path = os.path.join(self.mktemp(), "a", "b")
        self.assertEqual(locations.ensure_private_dir(path), path)
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o700)
        # a second call is fine
        locations.ensure_private_dir(path)
