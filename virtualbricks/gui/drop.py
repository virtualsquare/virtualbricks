# -*- test-case-name: virtualbricks.tests.gui.test_drop -*-
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
Files dropped on a window, from the file manager: the main window and the
Projects window import the archives dropped on them.

A widget that takes drops of its own, as a text entry, takes them first: GTK
offers a drop to the widget under the pointer, then to the ones around it.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable, Sequence

from gi.repository import Gdk, Gio, Gtk

from virtualbricks.i18n import _

# the paths of the files of this computer dropped, and the rest
OnFiles = Callable[[list[str], list[str]], object]


def take_files(widget: Gtk.Widget, on_files: OnFiles) -> None:
    """
    Let files be dropped on widget, and on what it holds; on_files gets
    them, as files_of() sorts them.
    """

    widget.drag_dest_set(Gtk.DestDefaults.ALL, [], Gdk.DragAction.COPY)
    widget.drag_dest_add_uri_targets()
    widget.connect("drag-data-received", received, on_files)


def received(
    widget: Gtk.Widget,
    context: Gdk.DragContext,
    x: int,
    y: int,
    data: Gtk.SelectionData,
    info: int,
    time: int,
    on_files: OnFiles,
) -> None:
    on_files(*files_of(data.get_uris()))


def files_of(uris: Iterable[str]) -> tuple[list[str], list[str]]:
    """
    The paths of the files of uris on this computer, and the rest, as paths
    or URIs: folders, files gone, and places elsewhere, as a web link.
    """

    files = []
    others = []
    for uri in uris:
        path = Gio.File.new_for_uri(uri).get_path()
        if path is not None and os.path.isfile(path):
            files.append(path)
        else:
            others.append(path or uri)
    return files, others


def refusal(others: Sequence[str]) -> str:
    """Why others, dropped, aren't imported."""

    return _(
        "Only the files of this computer can be imported, not {names}"
    ).format(names=", ".join(others))
