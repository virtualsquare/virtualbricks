# -*- test-case-name: virtualbricks.tests.gui.mainwindow.events.test_newevent -*-
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
The window of New Event: a name and a delay, then the settings of the new
event in the Events tab, to add its actions.

The name is checked as it is typed, and the message appears under the
field; Create waits until the name is good. Cancel in the settings keeps the
event, without actions.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from gi.repository import Gtk, Pango

from virtualbricks import errors
from virtualbricks.engine import Engine
from virtualbricks.gui.dialogs.base import Window
from virtualbricks.gui.mainwindow.events.eventeditor import delay_button
from virtualbricks.gui.pango import pango_attr_list
from virtualbricks.i18n import _

# The name suggested, and the delay, in seconds.
NAME = "new_event"
DELAY = 10
MARGIN = 18
GAP = 6


@dataclass(frozen=True)
class NewEvent:
    name: str
    delay: int


OnCreateNewEventCallback = Callable[[NewEvent], None]


class NewEventDialog(Window):
    """
    Ask a name and a delay, the name checked against the project of engine;
    Create gives them to on_create_new_event.
    """

    def __init__(
        self, engine: Engine, on_create_new_event: OnCreateNewEventCallback
    ) -> None:
        self.engine = engine
        self.on_create_new_event = on_create_new_event
        self.build_ui()

    def build_ui(self) -> None:
        self.dialog = Gtk.Dialog(
            title=_("New Event"),
            use_header_bar=True,
            modal=True,
            destroy_with_parent=True,
            default_width=360,
        )
        self.dialog.add_button(_("Cancel"), Gtk.ResponseType.CANCEL)
        self.create_button = self.dialog.add_button(
            _("Create"), Gtk.ResponseType.OK
        )
        self.create_button.get_style_context().add_class("suggested-action")
        self.dialog.set_default_response(Gtk.ResponseType.OK)

        grid = Gtk.Grid(
            visible=True, row_spacing=GAP, column_spacing=12, margin=MARGIN
        )
        bold = pango_attr_list(Pango.attr_weight_new(Pango.Weight.BOLD))
        name_label = Gtk.Label(
            visible=True, label=_("Name"), xalign=0.0, attributes=bold
        )
        self.name_entry = Gtk.Entry(
            visible=True, hexpand=True, activates_default=True
        )
        name_label.set_mnemonic_widget(self.name_entry)
        self.name_message = Gtk.Label(xalign=0.0, wrap=True, no_show_all=True)
        self.name_message.get_style_context().add_class("dim-label")

        # one sentence for the translators, around the number
        wait, _sep, seconds = _("Wait {delay} seconds").partition("{delay}")
        wait_label = Gtk.Label(
            visible=True, label=wait.strip(), xalign=0.0, attributes=bold
        )
        self.delay = delay_button(DELAY)
        self.delay.set_activates_default(True)
        wait_label.set_mnemonic_widget(self.delay)
        delay = Gtk.Box(visible=True, spacing=GAP)
        delay.pack_start(self.delay, False, False, 0)
        delay.pack_start(
            Gtk.Label(visible=True, label=seconds.strip()), False, False, 0
        )

        grid.attach(name_label, 0, 0, 1, 1)
        grid.attach(self.name_entry, 1, 0, 1, 1)
        grid.attach(self.name_message, 1, 1, 1, 1)
        grid.attach(wait_label, 0, 2, 1, 1)
        grid.attach(delay, 1, 2, 1, 1)
        self.dialog.get_content_area().pack_start(grid, True, True, 0)

        # initial data
        self.name_entry.set_text(self.engine.factory.unused_name(NAME))
        self.check(self.name_entry.get_text())

        # signals
        self.name_entry.connect("changed", self.on_name_changed)
        self.dialog.connect("response", self.on_response)

    def get_root_widget(self) -> Gtk.Dialog:
        return self.dialog

    # The name

    def check(self, event_name: str) -> None:
        """Say what is wrong with the name, if anything, and wait for it."""

        message = None
        try:
            self.engine.factory.check_name(event_name)
        except errors.InvalidNameError as exc:
            message = str(exc)
        self.name_message.set_text(message or "")
        self.name_message.set_visible(message is not None)
        self.create_button.set_sensitive(message is None)

    def on_name_changed(self, entry: Gtk.Entry) -> None:
        self.check(entry.get_text())

    # The action

    def on_response(self, dialog: Gtk.Dialog, response_id: int) -> None:
        new_event = None
        if response_id == Gtk.ResponseType.OK:
            if not self.create_button.get_sensitive():
                # Create waits for a good name
                return
            self.delay.update()
            new_event = NewEvent(
                self.name_entry.get_text(), self.delay.get_value_as_int()
            )

        dialog.destroy()
        if new_event is not None:
            self.on_create_new_event(new_event)
