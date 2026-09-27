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
Yes/No confirmation dialogs.
"""

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gtk, Pango

from virtualbricks.config import images
from virtualbricks.gui.windows.base import (
    _,
    _Dialog,
    pango_attr_list,
)
from virtualbricks.i18n import ngettext


class _ConfirmDialog(_Dialog):
    """
    A question with Yes and No buttons: a primary text and an optional
    secondary text. The subclasses handle the response.
    """

    def build_ui(self) -> None:
        """Create the widgets, formerly in ``confirmdialog.ui``."""

        # dialog (Gtk.Dialog)
        self.dialog = Gtk.Dialog(
            can_focus=False,
            resizable=False,
            modal=True,
            window_position=Gtk.WindowPosition.CENTER_ON_PARENT,
            destroy_with_parent=True,
            type_hint=Gdk.WindowTypeHint.DIALOG,
            skip_taskbar_hint=True,
            skip_pager_hint=True,
        )
        # TODO: empty Glade placeholder, nothing to create.
        content_area = self.dialog.get_content_area()
        content_area.set_properties(
            can_focus=False,
            orientation=Gtk.Orientation.VERTICAL,
            spacing=10,
        )
        action_area = self.dialog.get_action_area()
        action_area.set_properties(
            can_focus=False,
            layout_style=Gtk.ButtonBoxStyle.END,
        )
        button1 = Gtk.Button(
            label=_("No"),
            visible=True,
            can_focus=True,
            can_default=True,
            receives_default=True,
        )
        self.dialog.add_action_widget(button1, Gtk.ResponseType.NO)
        # add_action_widget() packs the button at the end and aligns it to
        # the baseline, restore the Glade packing and alignment.
        button1.set_valign(Gtk.Align.FILL)
        action_area.child_set(
            button1,
            pack_type=Gtk.PackType.START,
            expand=True,
            fill=True,
        )
        button2 = Gtk.Button(
            label=_("Yes"),
            visible=True,
            can_focus=True,
            receives_default=True,
        )
        self.dialog.add_action_widget(
            button2,
            Gtk.ResponseType.YES,
        )
        button2.set_valign(Gtk.Align.FILL)
        action_area.child_set(
            button2,
            pack_type=Gtk.PackType.START,
            expand=True,
            fill=True,
        )
        content_area.child_set(action_area, expand=False, fill=False)
        grid1 = Gtk.Grid(
            visible=True,
            can_focus=False,
            margin_left=30,
            margin_right=30,
            margin_top=20,
            margin_bottom=20,
            row_spacing=10,
        )
        self.primary_label = Gtk.Label(
            can_focus=False,
            halign=Gtk.Align.CENTER,
            valign=Gtk.Align.START,
            margin_top=6,
            margin_bottom=6,
            hexpand=True,
            wrap=True,
            max_width_chars=60,
            attributes=pango_attr_list(
                Pango.attr_weight_new(Pango.Weight.BOLD),
            ),
        )
        self.primary_label.get_style_context().add_class("title")
        grid1.attach(self.primary_label, 0, 0, 1, 1)
        self.secondary_label = Gtk.Label(
            can_focus=False,
            halign=Gtk.Align.CENTER,
            valign=Gtk.Align.START,
            margin_bottom=2,
            vexpand=True,
            wrap=True,
            max_width_chars=60,
        )
        grid1.attach(self.secondary_label, 0, 1, 1, 1)
        content_area.pack_start(grid1, False, True, 0)
        content_area.reorder_child(grid1, 0)

        # Need the complete widget tree:
        # default and focus widgets.
        button1.grab_focus()
        button1.grab_default()

        # Signals
        self.dialog.connect("response", self.on_dialog_response)

    def get_root_widget(self) -> Gtk.Dialog:
        return self.dialog

    def on_dialog_response(
        self,
        dialog: Gtk.Dialog,
        response_id: int,
        data=None,
    ) -> None:
        """
        Handler of the "response" signal of GtkDialog.

        Implemented by the subclasses.
        """

        pass

    def set_primary_text(self, text, markup=False):
        """
        Set the text for the primary label.

        :type text: str
        :type markup: bool
        """

        if text is not None:
            self.primary_label.show()
            if markup:
                self.primary_label.set_markup(text)
            else:
                self.primary_label.set_text(text)
        else:
            self.primary_label.hide()

    def set_secondary_text(self, text, markup=False):
        """
        Set the text for the primary label.

        :type text: Optional[str]
        :type markup: bool
        """

        if text is not None:
            self.secondary_label.show()
            if markup:
                self.secondary_label.set_markup(text)
            else:
                self.secondary_label.set_text(text)
        else:
            self.secondary_label.hide()


class DeleteBrickConfirmDialog(_ConfirmDialog):
    """
    Ask to delete a brick.
    """

    def __init__(self, brickfactory, brick):
        self._brickfactory = brickfactory
        self._brick = brick
        self.build_ui()
        qst_fmt = _("Do you really want to delete {brick} ({type})?")
        question = qst_fmt.format(brick=brick.name, type=brick.get_type())
        self.set_primary_text(question)

    def on_dialog_response(self, dialog, response_id):
        if response_id == Gtk.ResponseType.YES:
            self._brickfactory.del_brick(self._brick)
        dialog.destroy()


class DeleteEventConfirmDialog(_ConfirmDialog):
    """
    Ask to delete an event.
    """

    def __init__(self, brickfactory, event):
        self._brickfactory = brickfactory
        self._event = event
        self.build_ui()
        qst_fmt = _("Do you really want to delete {event} ({type})?")
        question = qst_fmt.format(event=event.name, type=event.get_type())
        self.set_primary_text(question)
        if event.scheduled is not None:
            self.set_secondary_text(
                _("The event is in use, it will be stopped before.")
            )

    def on_dialog_response(self, dialog, response_id):
        if response_id == Gtk.ResponseType.YES:
            self._brickfactory.del_event(self._event)
        dialog.destroy()


class RemoveImageConfirmDialog(_ConfirmDialog):
    """
    Ask to remove a disk image from the library, saying which disks lose it.
    The file stays.
    """

    def __init__(self, brickfactory, image):
        self._brickfactory = brickfactory
        self._image = image
        self.build_ui()
        self.set_primary_text(
            _("Remove the image {name}?").format(name=image.get_name())
        )
        uses = images.uses(brickfactory, image)
        disks = [
            _("{vm} ({device})").format(
                vm=use.vm.get_name(), device=use.device
            )
            for use in uses
        ]
        if disks:
            if len(disks) == 1:
                listed = disks[0]
            else:
                listed = _("{first} and {last}").format(
                    first=", ".join(disks[:-1]), last=disks[-1]
                )
            lose = ngettext(
                "The disk {disks} will have no image.",
                "The disks {disks} will have no image.",
                len(disks),
            ).format(disks=listed)
            copies = sum(1 for use in uses if use.private)
            if copies:
                lose += " " + ngettext(
                    "The private copy stays.",
                    "The private copies stay.",
                    copies,
                )
        else:
            lose = _("No disk uses it.")
        stays = _("The file stays: {path}").format(path=image.get_path())
        self.set_secondary_text(f"{lose}\n\n{stays}")

    def on_dialog_response(self, dialog, response_id):
        if response_id == Gtk.ResponseType.YES:
            self._brickfactory.remove_disk_image(self._image)
        dialog.destroy()


class DeleteLinkConfirmDialog(_ConfirmDialog):
    """
    Ask to delete a network interface of a virtual machine.
    """

    def __init__(self, qemu_config_controller, link):
        self._qemu_config_controller = qemu_config_controller
        self._link = link
        self.build_ui()
        question = _("Do you really want to delete the network interface?")
        self.set_primary_text(question)

    def on_dialog_response(self, dialog, response_id):
        if response_id == Gtk.ResponseType.YES:
            self._qemu_config_controller._remove_link(self._link)
        dialog.destroy()
