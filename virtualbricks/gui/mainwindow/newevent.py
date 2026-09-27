# -*- test-case-name: virtualbricks.tests.gui.mainwindow.test_newevent -*-
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
The window of New Event: a name and a delay, then the settings of the new
event in the Events tab, to add its actions.

The name is checked as it is typed, and the message appears under the
field; Create waits until the name is good. Cancel in the settings keeps the
event, without actions.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Pango  # noqa: E402

from virtualbricks import errors  # noqa: E402
from virtualbricks.gui.mainwindow.eventeditor import delay_button  # noqa: E402
from virtualbricks.gui.windows.base import pango_attr_list  # noqa: E402
from virtualbricks.i18n import _  # noqa: E402

# The name suggested, and the delay, in seconds.
NAME = "new_event"
DELAY = 10
MARGIN = 18
GAP = 6


class NewEventDialog:
    """
    Ask a name and a delay, create the event and show its settings.

    gui is the main window, which has the factory and shows the settings.
    """

    def __init__(self, gui):
        self.gui = gui
        self.factory = gui.brickfactory
        self.build_ui()
        self.name_entry.set_text(self.factory.next_name(NAME))
        self.check()

    def build_ui(self):
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

        self.name_entry.connect("changed", self.on_name_changed)
        self.dialog.connect("response", self.on_response)

    def get_root_widget(self):
        return self.dialog

    def show(self, parent=None):
        if parent is not None:
            self.dialog.set_transient_for(parent)
        self.dialog.show()

    # The name

    def check(self):
        """Say what is wrong with the name, if anything, and wait for it."""

        message = None
        try:
            self.factory.normalize_name(self.name_entry.get_text())
        except errors.NameAlreadyInUseError as exc:
            message = _("The name “{name}” is in use").format(name=exc.name)
        except errors.InvalidNameError as exc:
            message = str(exc)
        self.name_message.set_text(message or "")
        self.name_message.set_visible(message is not None)
        self.create_button.set_sensitive(message is None)

    def on_name_changed(self, entry):
        self.check()

    # The action

    def on_response(self, dialog, response_id):
        if response_id != Gtk.ResponseType.OK:
            dialog.destroy()
            return
        if not self.create_button.get_sensitive():
            return
        # a number typed and not yet taken
        self.delay.update()
        event = self.factory.new_event(self.name_entry.get_text())
        event.set({"delay": self.delay.get_value_as_int()})
        dialog.destroy()
        self.gui.curtain_up(event)
