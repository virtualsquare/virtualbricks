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

"""The way to the user guide: Yelp, the HTML, or the website."""

import os

from twisted.trial import unittest

from virtualbricks.tests import FakeLogger
from virtualbricks.tests.gui import has_display

if has_display:
    from gi.repository import Gio, GLib, Gtk

    from virtualbricks.gui import help
    from virtualbricks.gui.help import find_html, help_uri, show_help


class HelpTestCase(unittest.TestCase):

    if not has_display:  # pragma: no cover
        skip = "GTK can't open a display"

    def touch(self, *parts):
        path = os.path.join(*parts)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8"):
            pass
        return path


class TestHelpUri(HelpTestCase):

    def test_yelp(self):
        self.assertEqual(
            help_uri("settings", True, "/html"), "help:virtualbricks/settings"
        )
        self.assertEqual(help_uri(None, True, None), "help:virtualbricks")

    def test_html(self):
        self.assertEqual(
            help_uri("settings", False, "/usr/share/virtualbricks/help/C"),
            "file:///usr/share/virtualbricks/help/C/settings.html",
        )
        self.assertEqual(help_uri(None, False, "/h"), "file:///h/index.html")

    def test_website(self):
        self.assertEqual(
            help_uri("first-lab", False, None),
            "https://www.virtualbricks.it/help/C/first-lab.html",
        )
        self.assertEqual(
            help_uri(None, False, None),
            "https://www.virtualbricks.it/help/C/index.html",
        )


class TestYelpFindsIt(HelpTestCase):

    def setUp(self):
        self.handler = object()
        self.patch(
            Gio.AppInfo,
            "get_default_for_uri_scheme",
            lambda scheme: self.handler if scheme == "help" else None,
        )
        self.data = self.mktemp()
        self.empty = self.mktemp()

    def test_the_pages_there(self):
        self.touch(self.data, "help", "C", "virtualbricks", "index.page")
        self.assertTrue(help.yelp_finds_it([self.empty, self.data]))

    def test_no_pages(self):
        self.touch(self.data, "help", "C", "gedit", "index.page")
        self.assertFalse(help.yelp_finds_it([self.empty, self.data]))

    def test_no_yelp(self):
        self.touch(self.data, "help", "C", "virtualbricks", "index.page")
        self.handler = None
        self.assertFalse(help.yelp_finds_it([self.data]))


class TestFindHtml(HelpTestCase):

    def setUp(self):
        self.source = self.mktemp()
        self.patch(help, "SOURCE_HTML", self.source)
        self.venv = self.mktemp()
        self.user = self.mktemp()

    def installed(self, prefix):
        folder = os.path.join(prefix, "share", "virtualbricks", "help", "C")
        self.touch(folder, "index.html")
        return folder

    def test_installed(self):
        folder = self.installed(self.user)
        self.assertEqual(find_html([self.venv, self.user]), folder)

    def test_the_first_prefix(self):
        folder = self.installed(self.venv)
        self.installed(self.user)
        self.assertEqual(find_html([self.venv, self.user]), folder)

    def test_the_sources_first(self):
        self.touch(self.source, "index.html")
        self.installed(self.venv)
        self.assertEqual(find_html([self.venv]), self.source)

    def test_none(self):
        self.assertIsNone(find_html([self.venv, self.user]))


class TestShowHelp(HelpTestCase):

    def setUp(self):
        self.patch(help, "yelp_finds_it", lambda: False)
        self.patch(help, "find_html", lambda: "/h")
        self.opened = []
        self.patch(
            Gtk,
            "show_uri_on_window",
            lambda window, uri, time: self.opened.append((window, uri)),
        )

    def test_a_page(self):
        window = Gtk.Window()
        self.addCleanup(window.destroy)
        show_help(window, "settings")
        self.assertEqual(self.opened, [(window, "file:///h/settings.html")])

    def test_the_index(self):
        show_help(None)
        self.assertEqual(self.opened, [(None, "file:///h/index.html")])

    def test_yelp(self):
        self.patch(help, "yelp_finds_it", lambda: True)
        show_help(None, "bricks")
        self.assertEqual(self.opened, [(None, "help:virtualbricks/bricks")])

    def test_an_error(self):
        logger = FakeLogger()
        self.patch(help, "logger", logger)

        def fail(window, uri, time):
            raise GLib.Error("no browser")

        self.patch(Gtk, "show_uri_on_window", fail)
        show_help(None)
        self.assertEqual(
            logger.formatted(),
            ["Cannot open the help, file:///h/index.html: no browser"],
        )
