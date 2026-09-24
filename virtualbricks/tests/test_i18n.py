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
import site
import sys

from virtualbricks import i18n
from virtualbricks.tests import unittest


class TestFindLocaledir(unittest.TestCase):

    def setUp(self):
        self.prefix = self.mktemp()
        self.other = self.mktemp()
        self.patch(os, "environ", dict(os.environ, LANGUAGE="it"))
        self.patch(sys, "prefix", self.prefix)
        self.patch(sys, "base_prefix", self.other)
        self.patch(site, "getuserbase", lambda: self.other)
        self.source = self.mktemp()
        self.patch(i18n, "SOURCE_LOCALEDIR", self.source)

    def make_localedir(self, localedir):
        catalog = os.path.join(
            localedir, "it", "LC_MESSAGES", "virtualbricks.mo"
        )
        os.makedirs(os.path.dirname(catalog))
        open(catalog, "w").close()
        return localedir

    def make_catalog(self, prefix):
        return self.make_localedir(os.path.join(prefix, "share", "locale"))

    def test_no_catalog(self):
        self.assertIsNone(i18n.find_localedir())

    def test_sys_prefix_wins_over_base_prefix(self):
        """
        Inside a virtualenv the catalogs are installed under sys.prefix, not
        under the sys.base_prefix used as default by gettext.
        """

        expected = self.make_catalog(self.prefix)
        self.make_catalog(self.other)
        self.assertEqual(i18n.find_localedir(), expected)

    def test_fallback_to_user_base(self):
        expected = self.make_catalog(self.other)
        self.assertEqual(i18n.find_localedir(), expected)

    def test_source_tree_wins_over_installed(self):
        """
        Running from a checkout uses its catalogs, not a stale installed copy.
        """

        expected = self.make_localedir(self.source)
        self.make_catalog(self.prefix)
        self.assertEqual(i18n.find_localedir(), expected)
