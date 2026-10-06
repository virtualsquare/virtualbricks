# -*- test-case-name: virtualbricks.tests.gui.test_pathentry -*-
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

"""
A path of the machine of the bricks, typed in an entry: over a connection,
a file chooser shows the files of this computer, so the path rows of the
windows are entries that complete from the folders there (page 19 R9).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

if TYPE_CHECKING:  # pragma: no cover
    from virtualbricks.engine import Engine


class PathCompletion:
    """
    Complete what entry holds with the entries of its folder, which
    engine.folder() gives: asked once for a folder, and again as the typing
    goes on only if the folder has more than it gave. folders keeps only the
    folders, for an entry of a folder.
    """

    def __init__(
        self, engine: Engine, entry: Gtk.Entry, folders: bool = False
    ) -> None:
        self.engine = engine
        self.entry = entry
        self.folders = folders
        self.store = Gtk.ListStore(str)
        self.completion = Gtk.EntryCompletion(
            model=self.store, text_column=0, minimum_key_length=0
        )
        entry.set_completion(self.completion)
        # the folder asked last, what was asked, and whether it had more
        self.folder: str | None = None
        self.asked: str | None = None
        self.more = False
        entry.connect("changed", self.on_changed)

    def on_changed(self, entry: Gtk.Entry) -> None:
        text = entry.get_text()
        folder = text[: text.rfind("/") + 1]
        if not folder:
            return
        if folder != self.folder:
            self.ask(folder, folder)
        elif self.more and text != self.asked:
            # the folder has more than it gave: those that start so
            self.ask(folder, text)

    def ask(self, folder: str, path: str) -> None:
        self.folder, self.asked = folder, path
        asking = self.engine.folder(path)
        asking.addCallbacks(
            self.fill, lambda failure: None, callbackArgs=(path,)
        )

    def fill(self, answer: tuple[list[str], bool], asked: str) -> None:
        if asked != self.asked:
            # an answer too late
            return
        entries, self.more = answer
        self.store.clear()
        for path in entries:
            if not self.folders or path.endswith("/"):
                self.store.append([path])
        if self.entry.has_focus():
            self.completion.complete()
