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

The tabs share the helpers after it: a button with an icon, and the menus
of the bricks and the events, their items and where they open.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402


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


def brick_signals(factory) -> tuple:
    """The factory's signals of the bricks: one added, removed, changed."""

    return factory.brick_added, factory.brick_removed, factory.brick_changed


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


# The menus of the bricks and the events


def menu_item(group, label, action, target=None, keys=None) -> Gio.MenuItem:
    """
    An item that activates the action of group, with a string target if
    there is one; keys, as Gtk.accelerator_parse() reads them, show next to
    it.
    """

    item = Gio.MenuItem.new(label, None)
    if target is None:
        item.set_detailed_action(f"{group}.{action}")
    else:
        item.set_action_and_target_value(
            f"{group}.{action}", GLib.Variant.new_string(target)
        )
    if keys is not None:
        item.set_attribute_value("accel", GLib.Variant.new_string(keys))
    return item


def menu_section(*items) -> Gio.Menu:
    """The items that aren't None, together."""

    section = Gio.Menu()
    for item in items:
        if item is not None:
            section.append_item(item)
    return section


def menu_of(*sections) -> Gio.Menu:
    """A menu of the sections that aren't empty."""

    result = Gio.Menu()
    for section in sections:
        if section.get_n_items():
            result.append_section(None, section)
    return result


def popup(widget, event, model, group, actions) -> Gtk.Menu:
    """
    Open the menu of model, with the actions of group: at the pointer, for
    a click on widget, or under widget when event is None, as for the Menu
    key. Keep the menu that it returns while it shows.
    """

    result = Gtk.Menu.new_from_model(model)
    result.insert_action_group(group, actions)
    result.attach_to_widget(widget, None)
    if event is None:
        result.popup_at_widget(
            widget, Gdk.Gravity.SOUTH_EAST, Gdk.Gravity.NORTH_EAST, None
        )
    else:
        result.popup_at_pointer(event)
    return result
