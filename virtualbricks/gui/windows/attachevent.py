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
Dialog to attach events to the start and the stop of a brick.
"""

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gtk

from virtualbricks.gui import widgets
from virtualbricks.gui.windows.base import _, destroy_on_exit, Window


class AttachEventDialog(Window):
    """
    Attach an event to the start (``pon_vbevent``) and to the stop
    (``poff_vbevent``) of a brick. The two lists show the configured events.
    """

    def __init__(self, brick, factory):
        Window.__init__(self)
        self.brick = brick
        events = (e for e in factory.iter_events() if e.configured())
        self.events_store.set_data_source(events)
        # event start
        event_start = factory.get_event_by_name(brick.get("pon_vbevent"))
        self.start_view.set_selected_value(event_start)
        self.start_view.set_cells_data_func()
        # event stop
        event_stop = factory.get_event_by_name(brick.get("poff_vbevent"))
        self.stop_view.set_selected_value(event_stop)
        self.stop_view.set_cells_data_func()

    def build_ui(self) -> None:
        """Create the widgets, formerly in ``attachevent.ui``."""

        # events_store (widgets.List)
        # Custom widget from glade-catalog.xml
        self.events_store = widgets.List()

        # dialog (Gtk.Dialog)
        self.dialog = Gtk.Dialog(
            width_request=800,
            height_request=430,
            can_focus=False,
            border_width=5,
            title=_(
                (
                    "Virtualbricks-Events to attach to the start/stop Brick "
                    "Events"
                ),
            ),
            resizable=False,
            modal=True,
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
        button2 = Gtk.Button(
            label="gtk-cancel",
            visible=True,
            can_focus=True,
            receives_default=True,
            use_stock=True,
        )
        self.dialog.add_action_widget(
            button2,
            Gtk.ResponseType.CANCEL,
        )
        # add_action_widget() packs the button at the end and aligns it to
        # the baseline, restore the Glade packing and alignment.
        button2.set_valign(Gtk.Align.FILL)
        dialog_action_area1.child_set(
            button2,
            pack_type=Gtk.PackType.START,
            expand=False,
            fill=False,
        )
        button1 = Gtk.Button(
            label="gtk-ok",
            visible=True,
            can_focus=True,
            can_default=True,
            receives_default=True,
            use_stock=True,
        )
        self.dialog.add_action_widget(
            button1,
            Gtk.ResponseType.OK,
        )
        button1.set_valign(Gtk.Align.FILL)
        dialog_action_area1.child_set(
            button1,
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
        table1 = Gtk.Grid(visible=True, can_focus=False, column_spacing=5)
        label1 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("<b>Start event selection</b>"),
            use_markup=True,
        )
        table1.attach(label1, 0, 0, 1, 1)
        label2 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("<b>Stop event selection</b>"),
            use_markup=True,
        )
        table1.attach(label2, 1, 0, 1, 1)
        sw_start = Gtk.ScrolledWindow(
            visible=True,
            can_focus=True,
            margin_top=2,
            hexpand=True,
            vexpand=True,
        )
        # Custom widget from glade-catalog.xml
        self.start_view = widgets.TreeView(
            visible=True,
            can_focus=True,
            model=self.events_store,
        )
        tvc_start_name = Gtk.TreeViewColumn.new()
        tvc_start_name.set_properties(title=_("Name"))
        # Custom widget from glade-catalog.xml
        crt1 = widgets.CellRendererFormattable(
            format_string="n",
            formatting_enabled=True,
        )
        tvc_start_name.pack_start(crt1, False)
        self.start_view.append_column(tvc_start_name)
        tvc_start_params = Gtk.TreeViewColumn.new()
        tvc_start_params.set_properties(title=_("Parameters"))
        # Custom widget from glade-catalog.xml
        crt2 = widgets.CellRendererFormattable(
            format_string="p",
            formatting_enabled=True,
        )
        tvc_start_params.pack_start(crt2, False)
        self.start_view.append_column(tvc_start_params)
        sw_start.add(self.start_view)
        table1.attach(sw_start, 0, 1, 1, 1)
        sv_stop = Gtk.ScrolledWindow(
            visible=True,
            can_focus=True,
            hexpand=True,
            vexpand=True,
        )
        # Custom widget from glade-catalog.xml
        self.stop_view = widgets.TreeView(
            visible=True,
            can_focus=True,
            model=self.events_store,
        )
        tvc_stop_name = Gtk.TreeViewColumn.new()
        tvc_stop_name.set_properties(title=_("Name"))
        # Custom widget from glade-catalog.xml
        crt3 = widgets.CellRendererFormattable(
            format_string="n",
            formatting_enabled=True,
        )
        tvc_stop_name.pack_start(crt3, False)
        self.stop_view.append_column(tvc_stop_name)
        tvc_stop_params = Gtk.TreeViewColumn.new()
        tvc_stop_params.set_properties(title=_("Parameters"))
        # Custom widget from glade-catalog.xml
        crt4 = widgets.CellRendererFormattable(
            format_string="p",
            formatting_enabled=True,
        )
        tvc_stop_params.pack_start(crt4, False)
        self.stop_view.append_column(tvc_stop_params)
        sv_stop.add(self.stop_view)
        table1.attach(sv_stop, 1, 1, 1, 1)
        clear_start_button = Gtk.Button(
            label=_("Assing nothing"),
            visible=True,
            can_focus=True,
            receives_default=True,
        )
        table1.attach(clear_start_button, 0, 2, 1, 1)
        clear_stop_button = Gtk.Button(
            label=_("Assign nothing"),
            visible=True,
            can_focus=True,
            receives_default=True,
        )
        table1.attach(clear_stop_button, 1, 2, 1, 1)
        dialog_vbox1.pack_start(table1, True, True, 0)

        # Need the complete widget tree:
        # default and focus widgets.
        button1.grab_default()

        # Signals
        self.dialog.connect(
            "response",
            self.on_dialog_response,
        )
        self.start_view.connect(
            "button-press-event",
            self.on_treeview_button_press_event,
        )
        self.stop_view.connect(
            "button-press-event",
            self.on_treeview_button_press_event,
        )
        clear_start_button.connect(
            "clicked",
            self.on_clear_start_button_clicked,
        )
        clear_stop_button.connect(
            "clicked",
            self.on_clear_stop_button_clicked,
        )

    def get_root_widget(self) -> Gtk.Dialog:
        return self.dialog

    def on_clear_start_button_clicked(self, button):
        self.start_view.set_selected_value(widgets.SELECT_NONE)
        return True

    def on_clear_stop_button_clicked(self, button):
        self.stop_view.set_selected_value(widgets.SELECT_NONE)
        return True

    def on_treeview_button_press_event(self, treeview, event):
        if event.button == 1:
            path = treeview.get_path_at_pos(int(event.x), int(event.y))
            if path is None:
                treeview.set_selected_value(widgets.SELECT_NONE)
                return True

    @destroy_on_exit
    def on_dialog_response(self, dialog, response_id):
        if response_id == Gtk.ResponseType.OK:
            event_start = self.start_view.get_selected_value()
            event_stop = self.stop_view.get_selected_value()
            cfg = {
                "pon_vbevent": event_start.name if event_start else "",
                "poff_vbevent": event_stop.name if event_stop else "",
            }
            self.brick.set(cfg)
        return True
