# -*- test-case-name: virtualbricks.tests.gui.dialogs.test_renamedialog -*-
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
Rename a brick, an event or a disk image, as Rename Project does a project.

The name is selected, so typing replaces it. It is checked as you type: the
line under the field says why it can't be used, or what it becomes when
spaces turn into underscores, and Rename waits for a name that can be used.
A refusal keeps the dialog open with the reason, as a machine's private
copies that the project folder doesn't let rename.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk
from twisted.internet import defer
from twisted.python.failure import Failure

from virtualbricks import errors
from virtualbricks.brickfactory import normalize_name
from virtualbricks.bricks.event import is_event
from virtualbricks.bricks.virtualmachine import is_disk_image
from virtualbricks.console import ampcommands, ampwire
from virtualbricks.engine import Engine
from virtualbricks.gui.dialogs.base import Window, action_dialog, text_label
from virtualbricks.i18n import _

if TYPE_CHECKING:  # pragma: no cover
    from virtualbricks.remote.follower import Item


class RenameDialog(Window):
    """Ask a new name for a brick, an event or an image, and rename it."""

    def __init__(self, engine: Engine, item: Item) -> None:
        self.engine = engine
        # the names are checked on its factory
        self.factory = engine.factory
        self.item = item
        self.build_ui()
        self.name_entry.set_text(item.name)
        # after the name: the focus selects it
        self.name_entry.grab_focus()
        self.check()

    def build_ui(self) -> None:
        if is_disk_image(self.item):
            title = _("Rename Image")
        elif is_event(self.item):
            title = _("Rename Event")
        else:
            title = _("Rename Brick")
        self.dialog, self.rename_button, box = action_dialog(
            title, _("Rename")
        )
        self.dialog.get_header_bar().set_subtitle(self.item.name)
        self.dialog.set_default_response(Gtk.ResponseType.OK)
        self.name_entry = Gtk.Entry(visible=True, activates_default=True)
        # the screen readers say the label with the field
        name_label = text_label(_("New name"), bold=True)
        name_label.set_mnemonic_widget(self.name_entry)
        box.pack_start(name_label, False, False, 0)
        box.pack_start(self.name_entry, False, False, 0)
        self.name_message = text_label(dim=True, visible=False)
        box.pack_start(self.name_message, False, False, 0)
        self.error_label = text_label(visible=False, selectable=True)
        self.error_label.get_style_context().add_class("error")
        box.pack_start(self.error_label, False, False, 0)
        self.name_entry.connect("changed", self.on_name_changed)
        self.dialog.connect("response", self.on_response)

    def get_root_widget(self) -> Gtk.Dialog:
        return self.dialog

    # The name

    def problem(self, typed: str) -> tuple[bool, str | None]:
        """Whether typed can be the new name, and what to say of it."""

        if not typed:
            return False, None
        try:
            name = normalize_name(typed)
            if name == self.item.name:
                return False, None
            # only a brick has sockets, named after it, and a kind
            if is_disk_image(self.item) or is_event(self.item):
                self.factory.check_name(name)
            else:
                self.factory.check_brick_name(self.item.get_type(), name)
        except errors.InvalidNameError as exc:
            return False, str(exc)
        if name != typed:
            return True, _("It will be named {name}").format(name=name)
        return True, None

    def check(self) -> None:
        usable, message = self.problem(self.name_entry.get_text())
        self.name_message.set_text(message or "")
        self.name_message.set_visible(message is not None)
        self.rename_button.set_sensitive(usable)

    def on_name_changed(self, entry: Gtk.Entry) -> None:
        self.error_label.set_visible(False)
        self.check()

    # The rename

    def on_response(self, dialog: Gtk.Dialog, response_id: int) -> None:
        if response_id != Gtk.ResponseType.OK:
            dialog.destroy()
            return
        # Enter, with a name that can't be used
        if self.rename_button.get_sensitive():
            self.rename()

    def rename(self) -> defer.Deferred[Any]:
        # once, while it is asked
        self.rename_button.set_sensitive(False)
        renaming = self.engine.rename(self.item, self.name_entry.get_text())
        renaming.addCallbacks(self._renamed, self._refused)
        return renaming

    def _renamed(self, _old: object) -> None:
        self.dialog.destroy()

    def _refused(self, failure: Failure) -> None:
        # here, or there over a connection
        failure.trap(
            OSError,
            errors.Error,
            ampwire.CommandFailed,
            ampcommands.BadArgument,
        )
        self.check()
        # a name taken meanwhile: the line under the field says it
        if self.rename_button.get_sensitive():
            self.error_label.set_text(refusal(failure.value))
            self.error_label.set_visible(True)


def refusal(error: BaseException | None) -> str:
    """What the dialog says of an error of the rename."""

    if isinstance(error, OSError) and error.filename:
        # the only files renamed are a machine's private copies
        return _("Cannot rename the private copy {file}: {reason}").format(
            file=os.path.basename(error.filename),
            reason=error.strerror or error,
        )
    return str(error)
