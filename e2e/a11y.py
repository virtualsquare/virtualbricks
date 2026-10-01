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
The eyes of the end-to-end tests: the widgets of the windows, as a screen
reader sees them, through AT-SPI.

GTK tells the accessibility bus of each widget: its role (a button, a
label, a frame), its name (the label, or the name given for the screen
readers), whether it shows, where it is on the screen. The session bus of
the tests must be in DBUS_SESSION_BUS_ADDRESS before the first call here.
"""

import time

import gi

gi.require_version("Atspi", "2.0")
from gi.repository import Atspi, GLib  # noqa: E402


def wait_for(get, what, timeout=10.0):
    """What get returns once it is true; AssertionError after timeout."""

    deadline = time.monotonic() + timeout
    while True:
        value = get()
        if value:
            return value
        if time.monotonic() > deadline:
            raise AssertionError(f"Not in {timeout} s: {what}")
        time.sleep(0.1)


def application(pid):
    """The application of the process pid on the desktop, or None."""

    desktop = Atspi.get_desktop(0)
    for i in range(desktop.get_child_count()):
        app = desktop.get_child_at_index(i)
        if app is not None and app.get_process_id() == pid:
            return app
    return None


def showing(accessible) -> bool:
    return accessible.get_state_set().contains(Atspi.StateType.SHOWING)


def sensitive(accessible) -> bool:
    return accessible.get_state_set().contains(Atspi.StateType.SENSITIVE)


def find(root, role, name=None):
    """
    The first widget of role (as "button", "label") under root that
    shows, with name if given.
    """

    for accessible in find_all(root, role, name):
        return accessible
    return None


def find_all(root, role, name=None):
    """The widgets of role under root that show, with name if given."""

    try:
        if not showing(root) and root.get_role() != Atspi.Role.APPLICATION:
            return
        if root.get_role_name() == role and name in (None, root.get_name()):
            yield root
        for i in range(root.get_child_count()):
            child = root.get_child_at_index(i)
            if child is not None:
                yield from find_all(child, role, name)
    except GLib.Error:
        # gone while looked at
        return


def center(accessible):
    """The middle of the widget on the screen."""

    rect = accessible.get_component_iface().get_extents(Atspi.CoordType.SCREEN)
    return rect.x + rect.width // 2, rect.y + rect.height // 2


def describe(root, depth=0):
    """The tree of the widgets that show under root, one a line."""

    try:
        if not showing(root) and root.get_role() != Atspi.Role.APPLICATION:
            return []
        lines = [
            "  " * depth + f"[{root.get_role_name()}] {root.get_name()!r}"
        ]
        for i in range(root.get_child_count()):
            child = root.get_child_at_index(i)
            if child is not None:
                lines.extend(describe(child, depth + 1))
        return lines
    except GLib.Error:
        return []
