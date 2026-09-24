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
Dialog to create a new brick.
"""

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gtk

from twisted.logger import Logger

from virtualbricks import errors
from virtualbricks.errors import InvalidNameError, NameAlreadyInUseError
from virtualbricks.gui.windows.base import (
    _,
    _Dialog,
    destroy_on_exit,
    load_pixbuf,
)


logger = Logger()

brick_invalid_name = "Cannot create brick: Invalid name."
created = "Created successfully"


class NewBrickDialog(_Dialog):
    """
    Create a new brick: the type is chosen with a radio button for each brick
    type, the name of the radio button is the type.
    """

    def __init__(self, factory):
        """
        :type brickfactory: virtualbricks.brickfactory.BrickFactory
        :rtype: None
        """

        self._factory = factory
        self.build_ui()
        self._type = 'switch'

    def build_ui(self) -> None:
        """Create the widgets, formerly in ``newbrick.ui``."""

        # captureInterfaceImage (Gtk.Image)
        # Glade image "capture.png" (virtualbricks/gui/data)
        capture_interface_image = Gtk.Image(
            visible=True,
            can_focus=False,
            pixbuf=load_pixbuf("capture.png"),
        )

        # netemuImage (Gtk.Image)
        # Glade image "netemu.png" (virtualbricks/gui/data)
        netemu_image = Gtk.Image(
            visible=True,
            can_focus=False,
            pixbuf=load_pixbuf("netemu.png"),
        )

        # routerImage (Gtk.Image)
        # Glade image "router.png" (virtualbricks/gui/data)
        router_image = Gtk.Image(
            visible=True,
            can_focus=False,
            pixbuf=load_pixbuf("router.png"),
        )

        # switchImage (Gtk.Image)
        # Glade image "switch.png" (virtualbricks/gui/data)
        switch_image = Gtk.Image(
            visible=True,
            can_focus=False,
            pixbuf=load_pixbuf("switch.png"),
        )

        # switchWrapperImage (Gtk.Image)
        # Glade image "switchwrapper.png" (virtualbricks/gui/data)
        switch_wrapper_image = Gtk.Image(
            visible=True,
            can_focus=False,
            pixbuf=load_pixbuf("switchwrapper.png"),
        )

        # tapImage (Gtk.Image)
        # Glade image "tap.png" (virtualbricks/gui/data)
        tap_image = Gtk.Image(
            visible=True,
            can_focus=False,
            pixbuf=load_pixbuf("tap.png"),
        )

        # tunnelClientImage (Gtk.Image)
        # Glade image "tunnelconnect.png" (virtualbricks/gui/data)
        tunnel_client_image = Gtk.Image(
            visible=True,
            can_focus=False,
            pixbuf=load_pixbuf("tunnelconnect.png"),
        )

        # tunnelServerImage (Gtk.Image)
        # Glade image "tunnellisten.png" (virtualbricks/gui/data)
        tunnel_server_image = Gtk.Image(
            visible=True,
            can_focus=False,
            pixbuf=load_pixbuf("tunnellisten.png"),
        )

        # virtualMachineImage (Gtk.Image)
        # Glade image "qemu.png" (virtualbricks/gui/data)
        virtual_machine_image = Gtk.Image(
            visible=True,
            can_focus=False,
            pixbuf=load_pixbuf("qemu.png"),
        )

        # wireImage (Gtk.Image)
        # Glade image "wire.png" (virtualbricks/gui/data)
        wire_image = Gtk.Image(
            visible=True,
            can_focus=False,
            pixbuf=load_pixbuf("wire.png"),
        )

        # dialog (Gtk.Dialog)
        self.dialog = Gtk.Dialog(
            name="NewBrickDialog",
            can_focus=False,
            resizable=False,
            modal=True,
            destroy_with_parent=True,
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
        self.dialog.add_action_widget(
            self.ok_button,
            Gtk.ResponseType.OK,
        )
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
            spacing=5,
        )
        grid1 = Gtk.Grid(
            visible=True,
            can_focus=False,
            row_spacing=5,
            column_spacing=4,
        )
        switch_radio_button = Gtk.RadioButton(
            label="Switch",
            name="switch",
            visible=True,
            can_focus=False,
            receives_default=False,
            image=switch_image,
            image_position=Gtk.PositionType.TOP,
            always_show_image=True,
            active=True,
            draw_indicator=False,
        )
        grid1.attach(switch_radio_button, 0, 0, 1, 1)
        wire_radio_button = Gtk.RadioButton(
            label="Wire",
            name="wire",
            visible=True,
            can_focus=False,
            receives_default=False,
            image=wire_image,
            image_position=Gtk.PositionType.TOP,
            always_show_image=True,
            draw_indicator=False,
            group=switch_radio_button,
        )
        grid1.attach(wire_radio_button, 1, 0, 1, 1)
        virtual_machine_radio_button = Gtk.RadioButton(
            label="Virtual Machine",
            name="vm",
            visible=True,
            can_focus=False,
            receives_default=False,
            image=virtual_machine_image,
            image_position=Gtk.PositionType.TOP,
            always_show_image=True,
            draw_indicator=False,
            group=switch_radio_button,
        )
        grid1.attach(virtual_machine_radio_button, 1, 1, 1, 1)
        netemu_radio_button = Gtk.RadioButton(
            label="Netemu",
            name="netemu",
            visible=True,
            can_focus=False,
            receives_default=False,
            image=netemu_image,
            image_position=Gtk.PositionType.TOP,
            always_show_image=True,
            draw_indicator=False,
            group=switch_radio_button,
        )
        grid1.attach(netemu_radio_button, 2, 0, 1, 1)
        tap_radio_button = Gtk.RadioButton(
            label=_("Tap"),
            name="tap",
            visible=True,
            can_focus=False,
            receives_default=False,
            image=tap_image,
            image_position=Gtk.PositionType.TOP,
            always_show_image=True,
            draw_indicator=False,
            group=switch_radio_button,
        )
        grid1.attach(tap_radio_button, 3, 0, 1, 1)
        switch_wrapper_radio_button = Gtk.RadioButton(
            label="Switch Wrapper",
            name="switchwrapper",
            visible=True,
            can_focus=False,
            receives_default=False,
            image=switch_wrapper_image,
            image_position=Gtk.PositionType.TOP,
            always_show_image=True,
            draw_indicator=False,
            group=switch_radio_button,
        )
        grid1.attach(switch_wrapper_radio_button, 4, 0, 1, 1)
        router_radio_button = Gtk.RadioButton(
            label="Router",
            name="router",
            visible=True,
            can_focus=False,
            receives_default=False,
            image=router_image,
            image_position=Gtk.PositionType.TOP,
            always_show_image=True,
            draw_indicator=False,
            group=switch_radio_button,
        )
        grid1.attach(router_radio_button, 4, 1, 1, 1)
        capture_interface_radio_button = Gtk.RadioButton(
            label="Capture Interface",
            name="capture",
            visible=True,
            can_focus=False,
            receives_default=False,
            image=capture_interface_image,
            image_position=Gtk.PositionType.TOP,
            always_show_image=True,
            draw_indicator=False,
            group=switch_radio_button,
        )
        grid1.attach(capture_interface_radio_button, 3, 1, 1, 1)
        tunnel_server_radio_button = Gtk.RadioButton(
            label="Tunnel Server",
            name="tunnelserver",
            visible=True,
            can_focus=False,
            receives_default=False,
            image=tunnel_server_image,
            image_position=Gtk.PositionType.TOP,
            always_show_image=True,
            draw_indicator=False,
            group=switch_radio_button,
        )
        grid1.attach(tunnel_server_radio_button, 2, 1, 1, 1)
        tunnel_client_radio_button = Gtk.RadioButton(
            label="Tunnel Client",
            name="tunnelclient",
            visible=True,
            can_focus=False,
            receives_default=False,
            image=tunnel_client_image,
            image_position=Gtk.PositionType.TOP,
            always_show_image=True,
            draw_indicator=False,
            group=switch_radio_button,
        )
        grid1.attach(tunnel_client_radio_button, 0, 1, 1, 1)
        box1.pack_start(grid1, False, True, 0)
        self.brick_name_entry = Gtk.Entry(
            visible=True,
            can_focus=True,
            activates_default=True,
            placeholder_text=_("Brick name"),
        )
        box1.pack_start(self.brick_name_entry, True, True, 0)
        content_area.pack_start(box1, False, True, 0)

        # Need the complete widget tree:
        # default and focus widgets.
        self.ok_button.grab_default()
        self.brick_name_entry.grab_focus()

        # Signals
        self.dialog.connect(
            "response",
            self.on_dialog_response,
        )
        switch_radio_button.connect("toggled", self.on_radiobutton_toggled)
        wire_radio_button.connect("toggled", self.on_radiobutton_toggled)
        virtual_machine_radio_button.connect(
            "toggled",
            self.on_radiobutton_toggled,
        )
        netemu_radio_button.connect("toggled", self.on_radiobutton_toggled)
        tap_radio_button.connect("toggled", self.on_radiobutton_toggled)
        switch_wrapper_radio_button.connect(
            "toggled",
            self.on_radiobutton_toggled,
        )
        router_radio_button.connect("toggled", self.on_radiobutton_toggled)
        capture_interface_radio_button.connect(
            "toggled",
            self.on_radiobutton_toggled,
        )
        tunnel_server_radio_button.connect(
            "toggled",
            self.on_radiobutton_toggled,
        )
        tunnel_client_radio_button.connect(
            "toggled",
            self.on_radiobutton_toggled,
        )
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

    def on_radiobutton_toggled(self, radiobutton):
        """
        :type radiobutton: Gtk.RadioButton
        :rtype: bool
        """

        if radiobutton.get_active():
            self._type = radiobutton.get_name()
        return True

    def on_brick_name_entry_changed(self, entry):
        """
        Set the status of the entry based on brick name validity.

        :type entry: Gtk.Entry
        :rtype: bool
        """

        brick_name = entry.get_text()
        if not brick_name:
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
        """
        :type dialog: Gtk.Dialog
        :type response_id: Gtk.ResponseType
        :rtype: bool
        """

        if response_id == Gtk.ResponseType.OK:
            name = self.brick_name_entry.get_text()
            try:
                self._factory.new_brick(self._type, name)
            except errors.InvalidNameError:
                # TODO: report the name
                logger.error(brick_invalid_name)
            else:
                logger.debug(created)
        return True
