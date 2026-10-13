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
The user guide: Yelp shows it where it finds its pages, the browser its
HTML everywhere else.

:func:`show_help` opens a page of the guide, or its index, the first way of
three that works:

1. ``help:virtualbricks/PAGE``, when a program handles the ``help:`` scheme,
   as Yelp does, and the pages are where Yelp looks: in ``help/C/`` of the
   user's data folder or of a data folder of the system;
2. else the HTML of the pages, in the browser: the one of the sources, else
   the one installed under ``sys.prefix``, the user base or
   ``sys.base_prefix``, as :func:`virtualbricks.i18n.find_localedir` finds
   the translations, so that a virtualenv has its own;
3. else the copy of the website.

A page is named as its file in ``help/C/``, without ``.page``. A failure to
open is logged.
"""

from __future__ import annotations

import site
import sys
from collections.abc import Sequence
from os.path import abspath, dirname, isfile, join

from gi.repository import Gdk, Gio, GLib, Gtk
from twisted.logger import Logger

logger = Logger()
cannot_open_help = "Cannot open the help, {uri}: {error}"

# The guide is help:virtualbricks.
ID = "virtualbricks"
# The pages, under a data folder, where Yelp looks for them.
PAGES = join("help", "C", ID)
# The HTML of the sources, which help/build.py writes.
SOURCE_HTML = join(
    dirname(dirname(dirname(abspath(__file__)))), "help", "html", "C"
)
# The HTML once installed, under a prefix.
INSTALLED_HTML = join("share", "virtualbricks", "help", "C")
WEBSITE = "https://www.virtualbricks.it/help/C/"


def yelp_finds_it(data_dirs: Sequence[str] | None = None) -> bool:
    """
    Whether a program handles help:, and the pages are in one of data_dirs,
    by default those of the user and of the system.
    """

    if Gio.AppInfo.get_default_for_uri_scheme("help") is None:
        return False
    if data_dirs is None:
        data_dirs = [GLib.get_user_data_dir(), *GLib.get_system_data_dirs()]
    return any(
        isfile(join(folder, PAGES, "index.page")) for folder in data_dirs
    )


def find_html(prefixes: Sequence[str] | None = None) -> str | None:
    """
    The folder of the HTML of the guide: the sources', else the one under
    the first of prefixes that has it; None if none has.
    """

    if prefixes is None:
        prefixes = (sys.prefix, site.getuserbase(), sys.base_prefix)
    folders = [
        SOURCE_HTML,
        *(join(prefix, INSTALLED_HTML) for prefix in prefixes),
    ]
    for folder in folders:
        if isfile(join(folder, "index.html")):
            return folder
    return None


def help_uri(page: str | None, yelp: bool, html: str | None) -> str:
    """
    The URI of page, or of the index if None: in Yelp if yelp, else in the
    folder html, else on the website.
    """

    if yelp:
        return f"help:{ID}/{page}" if page else f"help:{ID}"
    name = f"{page or 'index'}.html"
    if html is not None:
        return Gio.File.new_for_path(join(html, name)).get_uri()
    return WEBSITE + name


def show_help(window: Gtk.Window | None, page: str | None = None) -> None:
    """Open page of the guide, or its index, for window."""

    uri = help_uri(page, yelp_finds_it(), find_html())
    try:
        Gtk.show_uri_on_window(window, uri, Gdk.CURRENT_TIME)
    except GLib.Error as exc:
        logger.error(cannot_open_help, uri=uri, error=exc.message)
