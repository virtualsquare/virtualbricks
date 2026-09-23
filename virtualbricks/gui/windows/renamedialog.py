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
Dialog to rename a brick or an event.
"""

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gtk

from virtualbricks import errors, log
from virtualbricks.errors import InvalidNameError, NameAlreadyInUseError
from virtualbricks.gui.windows.base import _, _Dialog, destroy_on_exit


logger = log.Logger()

invalid_name = log.Event("Invalid name {name}")


class RenameDialog(_Dialog):
    """
    Rename a brick or an event. The OK button is sensitive only when the name
    is valid and not in use.
    """

    def __init__(self, brickfactory, brick):
        """
        :type brickfactory: virtualbricks.brickfactory.BrickFactory
        :type brick: Union[virtualbricks.bricks.Brick,
            virtualbricks.events.Event]
        :rtype: None
        """

        self._factory = brickfactory
        self._brick = brick
        self._prev_name = brick.name
        self.build_ui()
        self.brick_name_entry.set_text(brick.name)

    def build_ui(self) -> None:
        """Create the widgets, formerly in ``renamedialog.ui``."""

        # dialog (Gtk.Dialog)
        self.dialog = Gtk.Dialog(
            width_request=320,
            can_focus=False,
            title=_("Virtualbricks - Rename brick"),
            modal=True,
            window_position=Gtk.WindowPosition.CENTER_ON_PARENT,
            type_hint=Gdk.WindowTypeHint.DIALOG,
        )
        # TODO: empty Glade placeholder, nothing to create.
        content_area = self.dialog.get_content_area()
        content_area.set_properties(
            can_focus=False,
            orientation=Gtk.Orientation.VERTICAL,
            spacing=2,
        )
        action_area = self.dialog.get_action_area()
        action_area.set_properties(
            can_focus=False,
            layout_style=Gtk.ButtonBoxStyle.END,
        )
        cancel_button = Gtk.Button(
            label=_("Cancel"),
            visible=True,
            can_focus=True,
            receives_default=True,
        )
        self.dialog.add_action_widget(
            cancel_button,
            Gtk.ResponseType.CANCEL,
        )
        # add_action_widget() packs the button at the end and aligns it to
        # the baseline, restore the Glade packing and alignment.
        cancel_button.set_valign(Gtk.Align.FILL)
        action_area.child_set(
            cancel_button,
            pack_type=Gtk.PackType.START,
            expand=True,
            fill=True,
        )
        self.ok_button = Gtk.Button(
            label=_("OK"),
            visible=True,
            sensitive=False,
            can_focus=True,
            can_default=True,
            receives_default=True,
            always_show_image=True,
        )
        self.dialog.add_action_widget(self.ok_button, Gtk.ResponseType.OK)
        self.ok_button.set_valign(Gtk.Align.FILL)
        action_area.child_set(
            self.ok_button,
            pack_type=Gtk.PackType.START,
            expand=True,
            fill=True,
        )
        content_area.child_set(action_area, expand=False, fill=False)
        box1 = Gtk.Box(
            visible=True,
            can_focus=False,
            orientation=Gtk.Orientation.VERTICAL,
        )
        label1 = Gtk.Label(
            visible=True,
            can_focus=False,
            halign=Gtk.Align.START,
            margin_top=5,
            margin_bottom=5,
            label=_("Chose a new name"),
        )
        box1.pack_start(label1, False, True, 0)
        self.brick_name_entry = Gtk.Entry(
            visible=True,
            can_focus=True,
            activates_default=True,
            placeholder_text=_("Brick name"),
        )
        box1.pack_start(self.brick_name_entry, False, True, 0)
        content_area.pack_start(box1, False, True, 0)

        # Need the complete widget tree:
        # default and focus widgets.
        self.ok_button.grab_default()
        self.brick_name_entry.grab_focus()

        # Signals
        self.dialog.connect("response", self.on_dialog_response)
        self.brick_name_entry.connect("changed", self.on_brick_name_entry_changed)

    def get_root_widget(self) -> Gtk.Dialog:
        return self.dialog

    def _set_error(self, tooltip):
        """
        :type tooltip: str
        :rtype: None
        """

        style_context = self.brick_name_entry.get_style_context()
        style_context.add_class('error')
        self.brick_name_entry.set_tooltip_markup(tooltip)
        self.ok_button.set_sensitive(False)

    def _reset_error(self):
        """
        :rtype: None
        """

        style_context = self.brick_name_entry.get_style_context()
        style_context.remove_class('error')
        self.brick_name_entry.set_tooltip_text(None)
        self.ok_button.set_sensitive(True)

    def on_brick_name_entry_changed(self, entry):
        """
        Set the status of the entry based on brick name validity.

        :type entry: Gtk.Entry
        :rtype: bool
        """

        brick_name = entry.get_text()
        if not brick_name or brick_name == self._prev_name:
            self._reset_error()
            self.ok_button.set_sensitive(False)
            return
        try:
            self._factory.normalize_name(brick_name)
            self._reset_error()
        except NameAlreadyInUseError:
            tooltip = (
                f'Name <span weight="bold">{brick_name}</span>'
                ' is already in use'
            )
            self._set_error(tooltip)
        except InvalidNameError as exc:
            self._set_error(str(exc))
        return True

    @destroy_on_exit
    def on_dialog_response(self, dialog, response_id):
        if response_id == Gtk.ResponseType.OK:
            name = self.brick_name_entry.get_text()
            try:
                self._brick.rename(name)
                # TODO: add debugging log
                # logger.debug(renamed)
            except errors.InvalidNameError:
                # TODO: check the difference between invalid_name and
                # brick_invalid_name
                logger.error(invalid_name, name=name)
        return True
