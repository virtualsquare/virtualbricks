# -*- test-case-name: virtualbricks.tests.gui.mainwindow.events.test_eventmenu -*-
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
The menu of an event, in the Events tab.

``menu()`` makes the ``Gio.Menu`` of an event, and ``EventActions`` the
group of actions its items call, under the prefix ``event``. The menu has
Start or Stop, Run Now, Configure, Rename, Duplicate and Delete. Run Now
runs the actions at once, to try an event out; a wait goes on.
"""

from __future__ import annotations

import functools

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gio, Gtk  # noqa: E402

from virtualbricks.gui.mainwindow import tab  # noqa: E402
from virtualbricks.bricks import eventinfo  # noqa: E402
from virtualbricks.bricks.eventinfo import State  # noqa: E402
from virtualbricks.gui.mainwindow.tab import (  # noqa: E402
    menu_item,
    menu_of,
    menu_section,
)
from virtualbricks.gui.dialogs.renamedialog import RenameDialog  # noqa: E402
from virtualbricks.i18n import _  # noqa: E402
from virtualbricks.base import is_running  # noqa: E402

GROUP = "event"

_item = functools.partial(menu_item, GROUP)


def menu(event, keys=False) -> Gio.Menu:
    """
    The menu of event. keys shows the keys of the Events tab next to the
    items: Enter, F2 and Delete.
    """

    def key(name):
        return name if keys else None

    return menu_of(
        menu_section(
            _item(_("Stop") if is_running(event) else _("Start"), "startstop"),
            _item(_("Run Now"), "run-now"),
            _item(_("Configure…"), "configure", keys=key("Return")),
        ),
        menu_section(
            _item(_("Rename…"), "rename", keys=key("F2")),
            _item(_("Duplicate"), "duplicate"),
        ),
        menu_section(_item(_("Delete…"), "delete", keys=key("Delete"))),
    )


class EventActions(Gio.SimpleActionGroup):
    """What the items of the menu of an event do."""

    def __init__(self, gui, event) -> None:
        super().__init__()
        self.gui = gui
        self.event = event
        for name, callback in (
            ("startstop", self.startstop),
            ("run-now", self.run_now),
            ("configure", self.configure),
            ("rename", self.rename),
            ("duplicate", self.duplicate),
            ("delete", self.delete),
        ):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", lambda a, p, call=callback: call())
            self.add_action(action)
        self.update()

    def update(self) -> None:
        """The actions that the event allows now."""

        state = eventinfo.state(self.event)
        enabled = {
            "startstop": state is not State.NOT_CONFIGURED,
            "run-now": bool(self.event.config.actions),
            "rename": state is not State.WAITING,
        }
        for name, value in enabled.items():
            self.lookup_action(name).set_enabled(value)

    def startstop(self) -> None:
        self.event.toggle()

    def run_now(self) -> None:
        self.event.run_actions()

    def configure(self) -> None:
        self.gui.curtain_up(self.event)

    def rename(self) -> None:
        RenameDialog(self.gui.brickfactory, self.event).show(self.gui.window)

    def duplicate(self) -> None:
        self.gui.brickfactory.dup_event(self.event)

    def delete(self) -> None:
        self.gui.ask_remove_event(self.event)


def popup(widget, event, gui, the_event, keys=False) -> Gtk.Menu:
    """
    Open the menu of the_event: at the pointer, for a click on widget, or
    under widget when event is None, as for the Menu key. Keep the menu that
    it returns while it shows.
    """

    return tab.popup(
        widget,
        event,
        menu(the_event, keys),
        GROUP,
        EventActions(gui, the_event),
    )
