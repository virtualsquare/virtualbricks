# -*- test-case-name: virtualbricks.tests.gui.test_help -*-
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

"""
The user guide: Yelp shows its pages wherever they are, the browser its
HTML where there is no Yelp.

:func:`show_help` opens a page of the guide, or its index, the first way
that works:

1. in Yelp, the program the desktop opens ``help:`` links with, when
   there is one:

   - ``help:virtualbricks/PAGE``, when the pages are installed where Yelp
     looks for them: in ``help/C/virtualbricks/`` of the user's data folder
     or of a data folder of the system;
   - else the file of the page, ``file:///.../PAGE.page``: the one of the
     sources, as in a checkout, else the one installed under
     ``sys.prefix``, the user base or ``sys.base_prefix``, as in a
     virtualenv, whose data folder Yelp doesn't know;

2. else, or without the pages, the HTML of the page, in the browser: the
   one of the sources, else the one installed under those prefixes, as
   :func:`virtualbricks.i18n.find_localedir` finds the translations, so
   that a virtualenv has its own;
3. else the copy of the website.

A page is named as its file in ``help/C/``, without ``.page``. A failure to
open is logged. The windows, the tabs and the panels of the settings name
their page in ``help_page``, which F1 opens: see
:class:`virtualbricks.gui.dialogs.base.Window`.
"""

from __future__ import annotations

import site
import sys
from collections.abc import Sequence
from os.path import abspath, dirname, isfile, join

from gi.repository import Gdk, Gio, GLib, Gtk
from twisted.logger import Logger

from virtualbricks.bricks.event import is_event
from virtualbricks.bricks.virtualmachine import is_disk_image

logger = Logger()
cannot_open_help = "Cannot open the help, {uri}: {error}"

# The guide is help:virtualbricks.
ID = "virtualbricks"
# The pages, under a data folder, where Yelp looks for them.
PAGES = join("help", "C", ID)
# The guide in the sources: its pages, and their HTML, which help/build.py
# writes.
SOURCES = join(dirname(dirname(dirname(abspath(__file__)))), "help")
SOURCE_PAGES = join(SOURCES, "C")
SOURCE_HTML = join(SOURCES, "html", "C")
# The pages and the HTML once installed, under a prefix.
INSTALLED_PAGES = join("share", PAGES)
INSTALLED_HTML = join("share", "virtualbricks", "help", "C")
WEBSITE = "https://www.virtualbricks.it/help/C/"


def find_yelp() -> Gio.AppInfo | None:
    """
    Yelp: the program the desktop opens help: links with, whatever it is;
    None if there is none.
    """

    return Gio.AppInfo.get_default_for_uri_scheme("help")


def yelp_finds_it(data_dirs: Sequence[str] | None = None) -> bool:
    """
    Whether the pages are where Yelp looks for help:virtualbricks: in one of
    data_dirs, by default those of the user and of the system.
    """

    if data_dirs is None:
        data_dirs = [GLib.get_user_data_dir(), *GLib.get_system_data_dirs()]
    return any(
        isfile(join(folder, PAGES, "index.page")) for folder in data_dirs
    )


def _find(
    source: str, installed: str, index: str, prefixes: Sequence[str] | None
) -> str | None:
    """
    The folder source if it has the file index, else installed under the
    first of prefixes that has it, by default sys.prefix, the user base and
    sys.base_prefix; None if none has.
    """

    if prefixes is None:
        prefixes = (sys.prefix, site.getuserbase(), sys.base_prefix)
    folders = [source, *(join(prefix, installed) for prefix in prefixes)]
    for folder in folders:
        if isfile(join(folder, index)):
            return folder
    return None


def find_pages(prefixes: Sequence[str] | None = None) -> str | None:
    """
    The folder of the pages of the guide, for Yelp to read as files: the
    sources', else the one under the first of prefixes that has it; None if
    none has.
    """

    return _find(SOURCE_PAGES, INSTALLED_PAGES, "index.page", prefixes)


def find_html(prefixes: Sequence[str] | None = None) -> str | None:
    """
    The folder of the HTML of the guide: the sources', else the one under
    the first of prefixes that has it; None if none has.
    """

    return _find(SOURCE_HTML, INSTALLED_HTML, "index.html", prefixes)


def yelp_uri(
    page: str | None,
    data_dirs: Sequence[str] | None = None,
    prefixes: Sequence[str] | None = None,
) -> str | None:
    """
    The URI of page, or of the index if None, for Yelp: a help: link where
    Yelp finds the pages (yelp_finds_it(data_dirs)), else the file of the
    page (find_pages(prefixes)); None if there are no pages.
    """

    if yelp_finds_it(data_dirs):
        return f"help:{ID}/{page}" if page else f"help:{ID}"
    folder = find_pages(prefixes)
    if folder is None:
        return None
    path = join(folder, f"{page or 'index'}.page")
    return Gio.File.new_for_path(path).get_uri()


def html_uri(page: str | None, html: str | None) -> str:
    """
    The URI of page, or of the index if None, for the browser: in the
    folder html, else on the website.
    """

    name = f"{page or 'index'}.html"
    if html is not None:
        return Gio.File.new_for_path(join(html, name)).get_uri()
    return WEBSITE + name


def page_about(item: object) -> str:
    """The page about item: a brick, an event or a disk image."""

    if is_disk_image(item):
        return "images"
    if is_event(item):
        return "events"
    return "bricks"


def show_help(window: Gtk.Window | None, page: str | None = None) -> None:
    """
    Open page of the guide, or its index, for window: in Yelp, if there is
    one and the pages, else in the browser.
    """

    yelp = find_yelp()
    uri = yelp_uri(page) if yelp is not None else None
    try:
        if yelp is not None and uri is not None:
            yelp.launch_uris([uri], launch_context(window))
        else:
            uri = html_uri(page, find_html())
            Gtk.show_uri_on_window(window, uri, Gdk.CURRENT_TIME)
    except GLib.Error as exc:
        logger.error(cannot_open_help, uri=uri, error=exc.message)


def launch_context(window: Gtk.Window | None) -> Gdk.AppLaunchContext | None:
    """
    The context of a program opened for window: its display, and the time
    of now, so that its window comes in front.
    """

    display: Gdk.Display | None
    if window is not None:
        display = window.get_display()
    else:
        display = Gdk.Display.get_default()
    if display is None:
        return None
    context = display.get_app_launch_context()
    context.set_timestamp(Gdk.CURRENT_TIME)
    return context
