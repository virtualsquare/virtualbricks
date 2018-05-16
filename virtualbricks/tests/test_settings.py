# Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
# Copyright (C) 2018 Virtualbricks team

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

from virtualbricks import _settings
from virtualbricks.tests import unittest


class TestSettings(unittest.TestCase):

    def test_create_settings_if_not_exists(self):
        """
        If the settings file does not exist, create it with reasonable values.
        """

        filename = self.mktemp()
        self.assertFalse(os.path.isfile(filename))
        s = _settings.Settings(filename)
        s.load()
        self.assertTrue(os.path.isfile(filename))


OLD_CONFIG_FILE = """
[Main]
alt-term = /usr/bin/gnome-terminal
term = /usr/bin/xterm
baseimages = /home/user/.virtualbricks
femaleplugs = False
vdepath = /usr/bin
python = True
current_project = /home/user/.virtualbricks/.virtualbricks.vbl
sudo = /usr/bin/gksu
erroronloop = False
qemupath = /usr/bin
kvm = True
cdroms =
ksm = False
systray = True
bricksdirectory = /home/kapo/.virtualbricks
projects = 1
"""

class TestNewSettingsV1(unittest.TestCase):
    """
    Test the compatibility with the old settings format.
    All these tests are relative to the virtualbricks 1.0 settings file format.
    """

    def setUp(self):
        self.filename = self.mktemp()
        with open(self.filename, "w") as fp:
            fp.write(OLD_CONFIG_FILE)

    def test_cowfmt(self):
        """
        cowfmt is a new option, don't raise an exception if it is not found.
        """

        s = _settings.Settings(self.filename)
        s.load()
        self.assertEqual(s.get("cowfmt"), "qcow2")
    test_cowfmt.skip = 'dirty reactor error'

    def test_workspace(self):
        """
        workspace is a new option, don't raise an exception if it is not found.
        """

        s = _settings.Settings(self.filename)
        s.load()
        self.assertEqual(s.get("workspace"), _settings.DEFAULT_WORKSPACE)
    test_cowfmt.skip = 'dirty reactor error'

    def test_show_missing(self):
        """
        show_missing is a new option, don't raise an exception if it is not found.
        """

        s = _settings.Settings(self.filename)
        s.load()
        self.assertEqual(s.get("show_missing"), True)
    test_cowfmt.skip = 'dirty reactor error'
