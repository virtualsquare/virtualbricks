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

The tabs share the helpers after it: a button with an icon, and for the
lists of the Bricks and the Events tabs, their menu and the sensitivity of
their toolbars.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from virtualbricks.gui.interfaces import IMenu  # noqa: E402


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


def icon_button(button, icon, name):
    """An icon, with a name for the tooltip and the screen readers."""

    button.set_image(Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.BUTTON))
    button.set_tooltip_text(name)
    button.get_accessible().set_name(name)
    return button


# The lists of the bricks and the events


def state_add_selection(manager, treeview, prerequisite, tooltip, *widgets):
    """Make widgets sensitive while prerequisite() is true, on a selection."""

    state = manager._build_state(tooltip, *widgets)
    state.add_prerequisite(prerequisite)
    selection = treeview.get_selection()
    selection.connect("changed", lambda s: state.check())
    state.check()
    return state


def popup_menu(view, event, gui, open_menu=None) -> bool | None:
    """
    For the button-release-event of a list: the right button opens the menu
    of the row under it, with open_menu(value, event) if given. True if it's
    the right button, on a row or not.
    """

    if event.button != 3:
        return None
    found = view.get_path_at_pos(int(event.x), int(event.y))
    if found is not None:
        path, column, _x, _y = found
        view.grab_focus()
        view.set_cursor(path, column, False)
        model = view.get_model()
        value = model.get_value(model.get_iter(path), 0)
        if open_menu is None:
            IMenu(value).popup(event.button, event.time, gui)
        else:
            open_menu(value, event)
    return True
