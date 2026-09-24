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

import builtins
import gettext
import locale
import os
import sys

from twisted.trial import unittest

from virtualbricks import i18n
from virtualbricks.tests import isolate

BUILTINS = ("_", "gettext", "ngettext")


class I18nTestCase(unittest.TestCase):

    def setUp(self):
        isolate(self)
        # gettext.install() replaces the builtins: restore them afterwards
        for name in BUILTINS:
            self.patch(builtins, name, getattr(builtins, name))

    def language(self, language):
        self.patch(os, "environ", dict(os.environ, LANGUAGE=language))

    def catalog(self, prefix, language="it"):
        directory = os.path.join(prefix, "share", "locale")
        messages = os.path.join(directory, language, "LC_MESSAGES")
        os.makedirs(messages)
        with open(os.path.join(messages, f"{i18n.DOMAIN}.mo"), "wb") as fp:
            fp.write(b"")
        return directory


class TestImport(I18nTestCase):

    def test_builtins_are_installed(self):
        # installed when i18n was imported, before any call to install()
        for name in BUILTINS:
            self.assertTrue(callable(getattr(builtins, name)), name)
        self.assertEqual(i18n.NAMES, ["gettext", "ngettext"])

    def test_functions_use_the_builtins(self):
        self.patch(builtins, "gettext", lambda message: f"<{message}>")
        self.patch(
            builtins,
            "ngettext",
            lambda singular, plural, count: plural if count > 1 else singular,
        )
        self.assertEqual(i18n._("Cancel"), "<Cancel>")
        self.assertEqual(
            i18n.ngettext("a warning", "warnings", 1), "a warning"
        )
        self.assertEqual(i18n.ngettext("a warning", "warnings", 2), "warnings")

    def test_translations(self):
        self.language("it")
        gettext.install(i18n.DOMAIN, i18n.find_localedir(), names=i18n.NAMES)
        self.assertEqual(i18n._("Cancel"), "Annulla")
        self.assertEqual(builtins._("Cancel"), "Annulla")
        self.language("C")
        gettext.install(i18n.DOMAIN, i18n.find_localedir(), names=i18n.NAMES)
        self.assertEqual(i18n._("Cancel"), "Cancel")
        self.assertEqual(
            i18n.ngettext("{0} file", "{0} files", 2), "{0} files"
        )


class TestFindLocaledir(I18nTestCase):

    def test_source_checkout(self):
        self.language("it")
        self.assertEqual(i18n.find_localedir(), i18n.SOURCE_LOCALEDIR)

    def test_installed(self):
        self.language("it")
        self.patch(i18n, "SOURCE_LOCALEDIR", self.mktemp())
        prefix = os.path.abspath(self.mktemp())
        self.patch(sys, "prefix", prefix)
        self.assertIsNone(i18n.find_localedir())
        localedir = self.catalog(prefix)
        self.assertEqual(i18n.find_localedir(), localedir)

    def test_user_base(self):
        self.language("it")
        self.patch(i18n, "SOURCE_LOCALEDIR", self.mktemp())
        self.patch(sys, "prefix", self.mktemp())
        userbase = os.path.abspath(self.mktemp())
        self.patch(i18n.site, "getuserbase", lambda: userbase)
        localedir = self.catalog(userbase)
        self.assertEqual(i18n.find_localedir(), localedir)

    def test_no_catalog_for_the_language(self):
        self.language("C")
        self.assertIsNone(i18n.find_localedir())


class TestInstall(I18nTestCase):

    def setUp(self):
        super().setUp()
        self.calls = []
        self.patch(
            locale,
            "setlocale",
            lambda *args: self.calls.append(("locale", args)),
        )
        self.patch(
            gettext,
            "bindtextdomain",
            lambda *args: self.calls.append(("bind", args)),
        )

    def test_install(self):
        self.language("it")
        i18n.install()
        self.assertEqual(
            self.calls,
            [
                ("locale", (locale.LC_ALL, "")),
                ("bind", (i18n.DOMAIN, i18n.SOURCE_LOCALEDIR)),
            ],
        )
        self.assertEqual(builtins._("Cancel"), "Annulla")
        self.assertEqual(builtins.gettext("Cancel"), "Annulla")
        self.assertTrue(callable(builtins.ngettext))

    def test_install_without_catalogs(self):
        self.language("C")
        i18n.install()
        self.assertEqual(self.calls, [("locale", (locale.LC_ALL, ""))])
        self.assertEqual(builtins._("Cancel"), "Cancel")
