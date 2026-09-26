# -*- test-case-name: virtualbricks.tests.gui.mainwindow.test_tab -*-
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
A tab of the main window, and what the window tells its tabs.

A tab is the widget of its page, and a :class:`Tab` too: the window puts it
in its notebook under its title, and tells it when a project opens, is
saved, or Virtualbricks quits, and when it shows or another tab does.
"""

from __future__ import annotations


class Tab:
    """
    What a tab hears from the main window; each hook does nothing unless the
    tab needs it.
    """

    # the label of the tab, with the underline of its mnemonic
    title = ""

    def on_open(self) -> None:
        """A project opened: another one, a new one or an imported one."""

    def on_save(self) -> None:
        """The project is about to be saved."""

    def on_quit(self) -> None:
        """Virtualbricks is about to quit."""

    def on_shown(self) -> None:
        """The tab is about to show."""

    def on_left(self) -> None:
        """Another tab is about to show instead."""


def tabs(notebook) -> list[Tab]:
    """The tabs of a notebook, in their order."""

    return [page for page in notebook.get_children() if isinstance(page, Tab)]


def switch(notebook, page) -> None:
    """
    Tell the tab that shows and the one that goes: for the switch-page
    signal of a notebook, before the notebook switches.
    """

    # -1 while it has no page yet, which get_nth_page reads as the last one
    index = notebook.get_current_page()
    current = notebook.get_nth_page(index) if index >= 0 else None
    if isinstance(current, Tab):
        current.on_left()
    if isinstance(page, Tab):
        page.on_shown()
