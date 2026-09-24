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
Dialog to create a new event.
"""

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gtk

from virtualbricks import console
from virtualbricks.gui.windows.base import _, load_pixbuf, VALIDKEY, Window
from virtualbricks.gui.windows.brickselection import BrickSelectionDialog
from virtualbricks.gui.windows.eventcommand import ShellCommandDialog


class NewEventDialog(Window):
    """
    Create a new event: name, delay and type. The next dialog depends on the
    type.
    """

    def __init__(self, gui):
        Window.__init__(self)
        self.gui = gui

    def build_ui(self) -> None:
        """Create the widgets, formerly in ``newevent.ui``."""

        # image1 (Gtk.Image)
        # Glade image "event.png" (virtualbricks/gui/data)
        image1 = Gtk.Image(
            visible=True,
            can_focus=False,
            pixbuf=load_pixbuf("event.png"),
        )

        # image2 (Gtk.Image)
        # Glade image "event.png" (virtualbricks/gui/data)
        image2 = Gtk.Image(
            visible=True,
            can_focus=False,
            pixbuf=load_pixbuf("event.png"),
        )

        # image3 (Gtk.Image)
        # Glade image "event.png" (virtualbricks/gui/data)
        image3 = Gtk.Image(
            visible=True,
            can_focus=False,
            pixbuf=load_pixbuf("event.png"),
        )

        # image4 (Gtk.Image)
        # Glade image "event.png" (virtualbricks/gui/data)
        image4 = Gtk.Image(
            visible=True,
            can_focus=False,
            pixbuf=load_pixbuf("event.png"),
        )

        # image5 (Gtk.Image)
        # Glade image "event.png" (virtualbricks/gui/data)
        image5 = Gtk.Image(
            visible=True,
            can_focus=False,
            pixbuf=load_pixbuf("event.png"),
        )

        # dialog (Gtk.Dialog)
        self.dialog = Gtk.Dialog(
            can_focus=False,
            border_width=5,
            resizable=False,
            modal=True,
            window_position=Gtk.WindowPosition.CENTER_ALWAYS,
            type_hint=Gdk.WindowTypeHint.DIALOG,
        )
        dialog_vbox1 = self.dialog.get_content_area()
        dialog_vbox1.set_properties(
            visible=True,
            can_focus=False,
            spacing=2,
        )
        dialog_action_area1 = self.dialog.get_action_area()
        dialog_action_area1.set_properties(
            visible=True,
            can_focus=False,
            layout_style=Gtk.ButtonBoxStyle.END,
        )
        cancel_button = Gtk.Button(
            label="gtk-cancel",
            visible=True,
            can_focus=True,
            receives_default=True,
            use_stock=True,
        )
        self.dialog.add_action_widget(
            cancel_button,
            Gtk.ResponseType.CANCEL,
        )
        # add_action_widget() packs the button at the end and aligns it to
        # the baseline, restore the Glade packing and alignment.
        cancel_button.set_valign(Gtk.Align.FILL)
        dialog_action_area1.child_set(
            cancel_button,
            pack_type=Gtk.PackType.START,
            expand=False,
            fill=False,
        )
        dialog_action_area1.set_child_secondary(cancel_button, True)
        ok_button = Gtk.Button(
            label="gtk-ok",
            visible=True,
            can_focus=True,
            can_default=True,
            receives_default=True,
            use_stock=True,
        )
        self.dialog.add_action_widget(
            ok_button,
            Gtk.ResponseType.OK,
        )
        ok_button.set_valign(Gtk.Align.FILL)
        dialog_action_area1.child_set(
            ok_button,
            pack_type=Gtk.PackType.START,
            expand=False,
            fill=False,
        )
        dialog_vbox1.child_set(
            dialog_action_area1,
            expand=False,
            fill=True,
            pack_type=Gtk.PackType.END,
        )
        vbox1 = Gtk.Box(
            visible=True,
            can_focus=False,
            orientation=Gtk.Orientation.VERTICAL,
            homogeneous=True,
        )
        hbox1 = Gtk.Box(visible=True, can_focus=False, homogeneous=True)
        self.start_radio = Gtk.RadioButton(
            label=_("Brick start"),
            visible=True,
            can_focus=True,
            receives_default=False,
            image=image1,
            xalign=0.5,
            image_position=Gtk.PositionType.TOP,
            active=True,
            draw_indicator=True,
        )
        hbox1.pack_start(self.start_radio, True, False, 0)
        self.stop_radio = Gtk.RadioButton(
            label=_("Brick stop"),
            visible=True,
            can_focus=True,
            receives_default=False,
            image=image2,
            xalign=0.5,
            image_position=Gtk.PositionType.TOP,
            draw_indicator=True,
            group=self.start_radio,
        )
        hbox1.pack_start(self.stop_radio, True, False, 0)
        self.config_radio = Gtk.RadioButton(
            label=_("Brick config"),
            visible=True,
            sensitive=False,
            can_focus=True,
            receives_default=False,
            image=image3,
            xalign=0.5,
            image_position=Gtk.PositionType.TOP,
            draw_indicator=True,
            group=self.start_radio,
        )
        hbox1.pack_start(self.config_radio, True, False, 0)
        vbox1.pack_start(hbox1, False, True, 0)
        hbox2 = Gtk.Box(visible=True, can_focus=False, homogeneous=True)
        self.shell_radio = Gtk.RadioButton(
            label=_("Free shell command"),
            visible=True,
            can_focus=True,
            receives_default=False,
            image=image4,
            xalign=0.5,
            image_position=Gtk.PositionType.TOP,
            draw_indicator=True,
            group=self.start_radio,
        )
        hbox2.pack_start(self.shell_radio, True, False, 0)
        self.collation_radio = Gtk.RadioButton(
            label=_("Events collation"),
            visible=True,
            can_focus=True,
            receives_default=False,
            image=image5,
            xalign=0.5,
            image_position=Gtk.PositionType.TOP,
            draw_indicator=True,
            group=self.start_radio,
        )
        hbox2.pack_start(self.collation_radio, True, False, 0)
        vbox1.pack_start(hbox2, False, True, 0)
        dialog_vbox1.pack_start(vbox1, False, True, 0)
        grid1 = Gtk.Grid(visible=True, can_focus=False, column_spacing=6)
        label1 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("Event name:"),
            xalign=0,
        )
        grid1.attach(label1, 0, 0, 1, 1)
        self.name_entry = Gtk.Entry(
            visible=True,
            can_focus=True,
            primary_icon_activatable=False,
            secondary_icon_activatable=False,
        )
        grid1.attach(self.name_entry, 1, 0, 1, 1)
        label2 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("Delay:"),
            xalign=0,
        )
        grid1.attach(label2, 0, 1, 1, 1)
        self.delay_entry = Gtk.Entry(
            visible=True,
            can_focus=True,
            text=_("10"),
            primary_icon_activatable=False,
            secondary_icon_activatable=False,
        )
        grid1.attach(self.delay_entry, 1, 1, 1, 1)
        dialog_vbox1.pack_start(grid1, True, True, 0)

        # Need the complete widget tree:
        # default and focus widgets.
        ok_button.grab_default()

        # Signals
        self.dialog.connect(
            "response",
            self.on_dialog_response,
        )
        self.name_entry.connect(
            "key-press-event",
            self.on_name_entry_key_press_event,
        )
        self.delay_entry.connect(
            "key-press-event",
            self.on_delay_entry_key_press_event,
        )

    def get_root_widget(self) -> Gtk.Dialog:
        return self.dialog

    def on_delay_entry_key_press_event(self, entry, event):
        if Gdk.keyval_name(event.keyval) not in VALIDKEY:
            return True
        elif Gdk.keyval_name(event.keyval) == "Return":
            self.get_root_widget().response(Gtk.ResponseType.OK)
            return True

    def on_name_entry_key_press_event(self, entry, event):
        if Gdk.keyval_name(event.keyval) == "Return":
            self.get_root_widget().response(Gtk.ResponseType.OK)
            return True

    def get_event_type(self):
        for name in "start", "stop", "config", "shell", "collation":
            button = getattr(self, name + "_radio")
            if button.get_active():
                return name
        return "shell"  # this condition show not be reached

    def on_dialog_response(self, dialog, response_id):
        try:
            if response_id == Gtk.ResponseType.OK:
                name = self.name_entry.get_text()
                delay = self.delay_entry.get_text()
                type = self.get_event_type()
                event = self.gui.brickfactory.new_event(name)
                event.set({"delay": int(delay)})
                if type in ("start", "stop", "collation"):
                    action = "off" if type == "stop" else "on"
                    bricks = self.gui.brickfactory.bricks
                    dialog_n = BrickSelectionDialog(event, action, bricks)
                elif type == "shell":
                    action = console.VbShellCommand("new switch myswitch")
                    event.set({"actions": [action]})
                    dialog_n = ShellCommandDialog(event)
                else:
                    raise RuntimeError("Invalid event type %s" % type)
                dialog_n.show(self.gui.window)
        finally:
            dialog.destroy()
