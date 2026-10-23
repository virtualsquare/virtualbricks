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


def checked(accessible) -> bool:
    return accessible.get_state_set().contains(Atspi.StateType.CHECKED)


def selected(accessible) -> bool:
    return accessible.get_state_set().contains(Atspi.StateType.SELECTED)


def editable(accessible) -> bool:
    return accessible.get_state_set().contains(Atspi.StateType.EDITABLE)


def active(accessible) -> bool:
    """Whether the window has the focus: the keys go to it."""

    return accessible.get_state_set().contains(Atspi.StateType.ACTIVE)


def vertical(accessible) -> bool:
    return accessible.get_state_set().contains(Atspi.StateType.VERTICAL)


def find(root, role, name=None):
    """
    The first widget of role (as "button", "label") under root that
    shows, with name if given.
    """

    for accessible in find_all(root, role, name):
        return accessible
    return None


def label(accessible) -> str:
    """
    The name of the widget, or else that of the label of it, as an entry
    after a label whose mnemonic it is: a screen reader says that.
    """

    name = accessible.get_name()
    if name:
        return name
    for relation in accessible.get_relation_set():
        if relation.get_relation_type() == Atspi.RelationType.LABELLED_BY:
            return " ".join(
                relation.get_target(i).get_name()
                for i in range(relation.get_n_targets())
            )
    return ""


def text(accessible) -> str:
    """The text of the widget, as that typed in an entry."""

    return Atspi.Text.get_text(accessible, 0, -1)


def selection(accessible) -> tuple[int, int] | None:
    """The first and the last offset of the text selected; None if none."""

    if not Atspi.Text.get_n_selections(accessible):
        return None
    chosen = Atspi.Text.get_selection(accessible, 0)
    return chosen.start_offset, chosen.end_offset


def offset(accessible, index) -> int:
    """
    The offset of the character index of the text of the widget, as AT-SPI
    counts them: a text view of GTK 3 leaves its images out of its text, but
    counts them in the offsets of its characters.
    """

    count = Atspi.Text.get_character_count(accessible)
    low, high = index, count
    # the first offset with index characters of text before it
    while low < high:
        middle = (low + high) // 2
        if len(Atspi.Text.get_text(accessible, 0, middle)) < index:
            low = middle + 1
        else:
            high = middle
    # then the images before the character
    while low < count and not Atspi.Text.get_text(accessible, low, low + 1):
        low += 1
    return low


def text_extents(accessible, start, end):
    """
    Where the characters start to end of the widget, offsets of AT-SPI, are
    on the screen: x, y, width, height.
    """

    rect = Atspi.Text.get_range_extents(
        accessible, start, end, Atspi.CoordType.SCREEN
    )
    return rect.x, rect.y, rect.width, rect.height


def runs(accessible):
    """
    The text of the widget, in runs of characters of the same attributes:
    the text of each, and those of its attributes that aren't the default,
    as {"weight": "700"}.
    """

    count = Atspi.Text.get_character_count(accessible)
    found = []
    start = 0
    while start < count:
        attributes, start, end = Atspi.Text.get_attribute_run(
            accessible, start, False
        )
        found.append((Atspi.Text.get_text(accessible, start, end), attributes))
        start = max(end, start + 1)
    return found


def write(accessible, text):
    """
    Write text in the widget at its cursor, as an assistive tool does: GTK
    inserts it as if typed there.
    """

    offset = Atspi.Text.get_caret_offset(accessible)
    # its length in bytes
    Atspi.EditableText.insert_text(
        accessible, offset, text, len(text.encode())
    )


def erase(accessible):
    """
    Erase the text of the widget, as a user who selects it all and deletes
    it.
    """

    Atspi.EditableText.delete_text(
        accessible, 0, Atspi.Text.get_character_count(accessible)
    )


def find_all(root, role, name=None):
    """
    The widgets of role under root that show, with name if given: theirs,
    or that of their label.
    """

    try:
        if not showing(root) and root.get_role() != Atspi.Role.APPLICATION:
            return
        if root.get_role_name() == role and (
            name is None or label(root) == name
        ):
            yield root
        for i in range(root.get_child_count()):
            child = root.get_child_at_index(i)
            if child is not None:
                yield from find_all(child, role, name)
    except GLib.Error:
        # gone while looked at
        return


def position(accessible):
    """Where a scroll bar is: its value, its least and its most."""

    value = accessible.get_value_iface()
    return (
        value.get_current_value(),
        value.get_minimum_value(),
        value.get_maximum_value(),
    )


def index(accessible) -> int:
    """Its place among the children of its parent."""

    return accessible.get_index_in_parent()


def extents(accessible):
    """Where the widget is on the screen: x, y, width, height."""

    rect = accessible.get_component_iface().get_extents(Atspi.CoordType.SCREEN)
    return rect.x, rect.y, rect.width, rect.height


def center(accessible):
    """The middle of the widget on the screen."""

    x, y, width, height = extents(accessible)
    return x + width // 2, y + height // 2


def describe(root, depth=0):
    """The tree of the widgets that show under root, one a line."""

    try:
        if not showing(root) and root.get_role() != Atspi.Role.APPLICATION:
            return []
        lines = ["  " * depth + f"[{root.get_role_name()}] {label(root)!r}"]
        for i in range(root.get_child_count()):
            child = root.get_child_at_index(i)
            if child is not None:
                lines.extend(describe(child, depth + 1))
        return lines
    except GLib.Error:
        return []
