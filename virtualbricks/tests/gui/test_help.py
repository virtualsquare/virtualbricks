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

import importlib
import os
import pkgutil

from twisted.trial import unittest

from virtualbricks.tests import FakeLogger
from virtualbricks.tests.gui import GuiTestCase, has_display
from virtualbricks.tests.test_help import page_names

if has_display:
    from gi.repository import Gdk, Gio, GLib, Gtk

    from virtualbricks import gui
    from virtualbricks.gui import help
    from virtualbricks.gui.dialogs.base import Window
    from virtualbricks.gui.help import (
        find_html,
        find_pages,
        find_yelp,
        html_uri,
        launch_context,
        page_about,
        show_help,
        yelp_uri,
    )
    from virtualbricks.gui.mainwindow.bricks.config.panel import Panel
    from virtualbricks.gui.mainwindow.tab import Tab


class HelpTestCase(unittest.TestCase):

    if not has_display:  # pragma: no cover
        skip = "GTK can't open a display"

    def touch(self, *parts):
        path = os.path.join(*parts)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8"):
            pass
        return path


def file_uri(*parts):
    return "file://" + os.path.abspath(os.path.join(*parts))


class TestHtmlUri(HelpTestCase):

    def test_html(self):
        self.assertEqual(
            html_uri("settings", "/usr/share/virtualbricks/help/C"),
            "file:///usr/share/virtualbricks/help/C/settings.html",
        )
        self.assertEqual(html_uri(None, "/h"), "file:///h/index.html")

    def test_website(self):
        self.assertEqual(
            html_uri("first-lab", None),
            "https://www.virtualbricks.it/help/C/first-lab.html",
        )
        self.assertEqual(
            html_uri(None, None),
            "https://www.virtualbricks.it/help/C/index.html",
        )


class TestFindYelp(HelpTestCase):

    def setUp(self):
        # the program of each scheme
        self.programs = {}
        self.patch(
            Gio.AppInfo,
            "get_default_for_uri_scheme",
            lambda scheme: self.programs.get(scheme),
        )

    def test_the_program_of_help_links(self):
        yelp = object()
        self.programs["help"] = yelp
        self.programs["ghelp"] = object()
        self.assertIs(find_yelp(), yelp)

    def test_none(self):
        self.programs["ghelp"] = object()
        self.assertIsNone(find_yelp())


class TestYelpFindsIt(HelpTestCase):

    def setUp(self):
        self.data = self.mktemp()
        self.empty = self.mktemp()

    def test_the_pages_there(self):
        self.touch(self.data, "help", "C", "virtualbricks", "index.page")
        self.assertTrue(help.yelp_finds_it([self.empty, self.data]))

    def test_no_pages(self):
        self.touch(self.data, "help", "C", "gedit", "index.page")
        self.assertFalse(help.yelp_finds_it([self.empty, self.data]))


class TestFindPages(HelpTestCase):

    def setUp(self):
        self.source = self.mktemp()
        self.patch(help, "SOURCE_PAGES", self.source)
        self.venv = self.mktemp()
        self.user = self.mktemp()

    def installed(self, prefix):
        folder = os.path.join(prefix, "share", "help", "C", "virtualbricks")
        self.touch(folder, "index.page")
        return folder

    def test_installed(self):
        folder = self.installed(self.user)
        self.assertEqual(find_pages([self.venv, self.user]), folder)

    def test_the_first_prefix(self):
        folder = self.installed(self.venv)
        self.installed(self.user)
        self.assertEqual(find_pages([self.venv, self.user]), folder)

    def test_the_sources_first(self):
        self.touch(self.source, "index.page")
        self.installed(self.venv)
        self.assertEqual(find_pages([self.venv]), self.source)

    def test_none(self):
        self.touch(
            self.venv, "share", "virtualbricks", "help", "C", "index.html"
        )
        self.assertIsNone(find_pages([self.venv, self.user]))


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


class TestYelpUri(HelpTestCase):
    """help: where Yelp finds the pages, else the file of the page."""

    def setUp(self):
        self.data = self.mktemp()
        self.source = self.mktemp()
        self.patch(help, "SOURCE_PAGES", self.source)
        self.venv = self.mktemp()

    def uri(self, page):
        return yelp_uri(page, [self.data], [self.venv])

    def test_installed(self):
        self.touch(self.data, "help", "C", "virtualbricks", "index.page")
        # before the sources
        self.touch(self.source, "index.page")
        self.assertEqual(self.uri("settings"), "help:virtualbricks/settings")
        self.assertEqual(self.uri(None), "help:virtualbricks")

    def test_the_sources(self):
        self.touch(self.source, "index.page")
        self.assertEqual(
            self.uri("settings"), file_uri(self.source, "settings.page")
        )
        self.assertEqual(self.uri(None), file_uri(self.source, "index.page"))

    def test_installed_where_yelp_doesnt_look(self):
        folder = os.path.join(self.venv, "share", "help", "C", "virtualbricks")
        self.touch(folder, "index.page")
        self.assertEqual(self.uri("bricks"), file_uri(folder, "bricks.page"))

    def test_no_pages(self):
        self.assertIsNone(self.uri("settings"))


class FakeYelp:
    """Yelp's desktop entry: the links it opens, with their context."""

    def __init__(self, error=None):
        self.error = error
        self.opened = []

    def launch_uris(self, uris, context):
        if self.error is not None:
            raise GLib.Error(self.error)
        self.opened.append((uris, context))


class TestShowHelp(HelpTestCase):

    def setUp(self):
        self.yelp = None
        self.patch(help, "find_yelp", lambda: self.yelp)
        # where Yelp looks for the pages, and the folder of their files
        self.installed = False
        self.pages = None
        self.patch(
            help, "yelp_finds_it", lambda data_dirs=None: self.installed
        )
        self.patch(help, "find_pages", lambda prefixes=None: self.pages)
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
        self.yelp = FakeYelp()
        self.installed = True
        show_help(None, "bricks")
        [(uris, context)] = self.yelp.opened
        self.assertEqual(uris, ["help:virtualbricks/bricks"])
        self.assertIsInstance(context, Gdk.AppLaunchContext)
        self.assertEqual(self.opened, [])

    def test_yelp_with_the_files(self):
        self.yelp = FakeYelp()
        self.pages = "/p"
        show_help(None, "bricks")
        [(uris, context)] = self.yelp.opened
        self.assertEqual(uris, ["file:///p/bricks.page"])
        self.assertEqual(self.opened, [])

    def test_yelp_without_the_pages(self):
        self.yelp = FakeYelp()
        show_help(None, "bricks")
        self.assertEqual(self.yelp.opened, [])
        self.assertEqual(self.opened, [(None, "file:///h/bricks.html")])

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

    def test_an_error_of_yelp(self):
        logger = FakeLogger()
        self.patch(help, "logger", logger)
        self.yelp = FakeYelp("no yelp")
        self.installed = True
        show_help(None)
        self.assertEqual(
            logger.formatted(),
            ["Cannot open the help, help:virtualbricks: no yelp"],
        )
        self.assertEqual(self.opened, [])


class TestLaunchContext(HelpTestCase):

    def test_the_display_of_the_window(self):
        window = Gtk.Window()
        self.addCleanup(window.destroy)
        context = launch_context(window)
        self.assertIsInstance(context, Gdk.AppLaunchContext)
        self.assertEqual(context.props.display, window.get_display())

    def test_without_a_window(self):
        context = launch_context(None)
        self.assertEqual(context.props.display, Gdk.Display.get_default())


class TestPageAbout(GuiTestCase):

    def test_each_kind(self):
        factory = self.factory
        self.assertEqual(
            page_about(factory.new_brick("switch", "sw")), "bricks"
        )
        self.assertEqual(page_about(factory.new_brick("qemu", "vm")), "bricks")
        self.assertEqual(page_about(factory.new_event("ev")), "events")
        self.assertEqual(page_about(self.image("disk")), "images")


def subclasses(base):
    """The subclasses of base in the modules of virtualbricks.gui."""

    for module in pkgutil.walk_packages(gui.__path__, "virtualbricks.gui."):
        importlib.import_module(module.name)
    found, todo = [], [base]
    while todo:
        for cls in todo.pop().__subclasses__():
            todo.append(cls)
            if cls.__module__.startswith("virtualbricks.gui."):
                found.append(cls)
    return found


class TestTheNamedPages(HelpTestCase):
    """
    The windows, the tabs and the panels name a page of the guide, which F1
    opens.
    """

    def named(self, base):
        """
        The page that each subclass of base names: None if it doesn't, a
        property if it says which.
        """

        # the property of base that says None; a panel names "bricks"
        unnamed = vars(base)["help_page"]
        if not isinstance(unnamed, property):
            unnamed = object()
        pages = {}
        for cls in subclasses(base):
            page = getattr(cls, "HELP_PAGE", None) or cls.help_page
            pages[cls.__name__] = None if page is unnamed else page
        return pages

    def test_a_page_of_the_guide(self):
        names = set(page_names())
        for base in (Window, Tab, Panel):
            for cls, page in self.named(base).items():
                if isinstance(page, str):
                    self.assertIn(page, names, cls)

    def test_every_window(self):
        pages = self.named(Window)
        # About opens the index
        self.assertEqual(
            [cls for cls, page in pages.items() if page is None],
            ["AboutDialog"],
        )
        self.assertEqual(pages["SettingsWindow"], "settings")
        self.assertEqual(pages["LoggingWindow"], "problems")
        self.assertIsInstance(pages["MainWindow"], property)

    def test_every_tab(self):
        pages = self.named(Tab)
        self.assertEqual(
            {
                cls: page
                for cls, page in pages.items()
                if not isinstance(page, property)
            },
            {
                "BricksTab": "bricks",
                "EventsTab": "events",
                "ImagesTab": "images",
                "TopologyTab": "topology",
                "ReadmeTab": "readme",
            },
        )

    def test_every_panel(self):
        pages = self.named(Panel)
        self.assertEqual(pages["VirtualMachinePanel"], "machines")
        self.assertEqual(pages["EventEditor"], "events")
        self.assertEqual(pages["ImageDetails"], "images")
        self.assertEqual(pages["SwitchPanel"], "bricks")
