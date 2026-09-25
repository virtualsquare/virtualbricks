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

"""Running a program as root: sudo -A or sudo -n."""

import os
import shutil

from twisted.trial import unittest

from virtualbricks.sudo import askpass_configured, sudo_command


class TestAskpass(unittest.TestCase):

    def conf(self, text):
        path = self.mktemp()
        with open(path, "w") as fp:
            fp.write(text)
        return path

    def test_the_variable(self):
        missing = self.mktemp()
        environ = {"SUDO_ASKPASS": "/usr/bin/ssh-askpass"}
        self.assertTrue(askpass_configured(environ, missing))
        self.assertFalse(askpass_configured({"SUDO_ASKPASS": ""}, missing))
        self.assertFalse(askpass_configured({}, missing))

    def test_the_environment_of_the_process(self):
        self.patch(os, "environ", {"SUDO_ASKPASS": "/usr/bin/ssh-askpass"})
        self.assertTrue(askpass_configured(sudo_conf=self.mktemp()))

    def test_sudo_conf(self):
        for text in (
            "Path askpass /usr/bin/ssh-askpass\n",
            "# Sudo askpass:\n  path   AskPass /usr/bin/ksshaskpass\n",
        ):
            self.assertTrue(askpass_configured({}, self.conf(text)), text)

    def test_sudo_conf_without_askpass(self):
        for text in (
            "",
            "#Path askpass /usr/bin/ssh-askpass\n",
            "Path noexec /usr/libexec/sudo/sudo_noexec.so\n",
            "Path askpass\n",
        ):
            self.assertFalse(askpass_configured({}, self.conf(text)), text)


class TestSudoCommand(unittest.TestCase):

    def setUp(self):
        self.patch(shutil, "which", lambda name: f"/usr/bin/{name}")
        self.no_conf = self.mktemp()

    def test_with_a_helper(self):
        environ = {"SUDO_ASKPASS": "/usr/bin/ssh-askpass"}
        self.assertEqual(
            sudo_command(environ, self.no_conf), ["/usr/bin/sudo", "-A", "--"]
        )

    def test_without_a_helper(self):
        self.assertEqual(
            sudo_command({}, self.no_conf), ["/usr/bin/sudo", "-n", "--"]
        )

    def test_sudo_not_found(self):
        self.patch(shutil, "which", lambda name: None)
        self.assertEqual(sudo_command({}, self.no_conf)[0], "sudo")
