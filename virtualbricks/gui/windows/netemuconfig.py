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
Configuration panel of the Netemu brick.
"""

from copy import deepcopy

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

from virtualbricks.gui import help, widgets
from virtualbricks.tools import dispose
from virtualbricks.gui.windows.base import (
    _,
    _PlugMixin,
    ConfigController,
    StateManager,
)


class NetemuConfigController(_PlugMixin, ConfigController):
    """
    Configuration panel of the Netemu brick: buffer size, delay, loss and
    bandwidth of both directions, and the states of the Markov chain with their
    transition weights.
    """

    state_manager = None
    help = help.Help()
    config_to_checkbutton_mapping = (
        ("chanbufsizesymm", "chanbufsize_check"),
        ("delaysymm", "delay_check"),
        ("losssymm", "loss_check"),
        ("bandwidthsymm", "bandwidth_check"),
    )
    config_to_spinint_mapping = (
        ("chanbufsizer", "chanbufsizer_spin"),
        ("chanbufsize", "chanbufsize_spin"),
        ("delayr", "delayr_spin"),
        ("delay", "delay_spin"),
        ("bandwidthr", "bandwidthr_spin"),
        ("bandwidth", "bandwidth_spin"),
    )
    config_to_spinfloat_mapping = (
        ("lossr", "lossr_spin"),
        ("loss", "loss_spin"),
    )
    help_buttons = (
        "chanbufsize_help_button",
        "delay_help_button",
        "loss_help_button",
        "bandwidth_help_button",
    )

    def build_ui(self) -> None:
        """Create the widgets, formerly in ``netemuconfig.ui``."""

        # adjustment1 (Gtk.Adjustment)
        adjustment1 = Gtk.Adjustment(
            upper=1073741824,
            value=75000,
            step_increment=1000,
            page_increment=10000,
        )

        # adjustment2 (Gtk.Adjustment)
        adjustment2 = Gtk.Adjustment(
            upper=1073741824,
            value=75000,
            step_increment=1000,
            page_increment=10000,
        )

        # adjustment3 (Gtk.Adjustment)
        adjustment3 = Gtk.Adjustment(
            upper=1073741824,
            step_increment=10,
            page_increment=100,
        )

        # adjustment4 (Gtk.Adjustment)
        adjustment4 = Gtk.Adjustment(
            upper=1073741824,
            step_increment=10,
            page_increment=100,
        )

        # adjustment5 (Gtk.Adjustment)
        adjustment5 = Gtk.Adjustment(
            upper=100,
            step_increment=1,
            page_increment=10,
        )

        # adjustment6 (Gtk.Adjustment)
        adjustment6 = Gtk.Adjustment(
            upper=100,
            step_increment=1,
            page_increment=10,
        )

        # adjustment7 (Gtk.Adjustment)
        adjustment7 = Gtk.Adjustment(
            upper=1073741824,
            value=125000,
            step_increment=5000,
            page_increment=25000,
        )

        # adjustment8 (Gtk.Adjustment)
        adjustment8 = Gtk.Adjustment(
            upper=1073741824,
            value=125000,
            step_increment=5000,
            page_increment=25000,
        )

        # probability_adjustment (Gtk.Adjustment)
        self.probability_adjustment = Gtk.Adjustment(
            upper=100,
            step_increment=1,
            page_increment=10,
        )

        # timeAdjustment (Gtk.Adjustment)
        time_adjustment = Gtk.Adjustment(
            upper=1073741824,
            value=100,
            step_increment=1,
            page_increment=10,
        )

        # states_store (widgets.List)
        # Custom widget from glade-catalog.xml
        self.states_store = widgets.List()
        self.states_store.set_properties(value_member="value")

        # other_states_store (widgets.List)
        # Custom widget from glade-catalog.xml
        self.other_states_store = widgets.List()
        self.other_states_store.set_properties(value_member="value")

        # panel (Gtk.Grid)
        self.panel = Gtk.Grid(
            visible=True,
            can_focus=False,
            column_spacing=5,
        )
        hbox = Gtk.Box(visible=True, can_focus=False, spacing=6)
        self.sock0_combo = Gtk.ComboBox(visible=True, can_focus=False)
        sock0_cellrenderer = Gtk.CellRendererText()
        self.sock0_combo.pack_start(sock0_cellrenderer, False)
        hbox.pack_start(self.sock0_combo, True, True, 0)
        label8 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("<=== connect ===>"),
        )
        hbox.pack_start(label8, False, True, 0)
        self.sock1_combo = Gtk.ComboBox(visible=True, can_focus=False)
        sock1_cellrenderer = Gtk.CellRendererText()
        self.sock1_combo.pack_start(sock1_cellrenderer, False)
        hbox.pack_start(self.sock1_combo, True, True, 0)
        self.panel.attach(hbox, 0, 0, 5, 1)
        hseparator2 = Gtk.Separator(visible=True, can_focus=False)
        self.panel.attach(hseparator2, 0, 1, 5, 1)
        hboxspace = Gtk.Box(visible=True, can_focus=False, spacing=5)
        labelspace = Gtk.Label(visible=True, can_focus=False, label=_(""))
        hboxspace.pack_start(labelspace, False, False, 0)
        self.panel.attach(hboxspace, 0, 2, 1, 1)
        hbox_m = Gtk.Box(visible=True, can_focus=False, spacing=5)
        label100 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("Markov state"),
        )
        hbox_m.pack_start(label100, False, False, 0)
        self.panel.attach(hbox_m, 0, 3, 1, 1)
        # Custom widget from glade-catalog.xml
        self.state_combo = widgets.ComboBox(
            width_request=150,
            visible=True,
            can_focus=False,
            model=self.states_store,
            active=0,
        )
        # Custom widget from glade-catalog.xml
        self.state_cell = widgets.CellRendererFormattable(display_member="label")
        self.state_combo.pack_start(self.state_cell, False)
        self.panel.attach(self.state_combo, 1, 3, 1, 1)
        hboxspace0 = Gtk.Box(visible=True, can_focus=False)
        labelspace0 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_(""),
        )
        hboxspace0.pack_start(labelspace0, False, False, 0)
        self.panel.attach(hboxspace0, 0, 4, 1, 1)
        hboxspace1 = Gtk.Box(visible=True, can_focus=False)
        label_channel = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("Channel configuration"),
        )
        hboxspace1.pack_start(label_channel, False, False, 0)
        self.panel.attach(hboxspace1, 0, 5, 1, 1)
        self.add_state_button = Gtk.Button(
            label="Add state",
            visible=True,
            can_focus=True,
            receives_default=True,
            use_stock=True,
            focus_on_click=False,
        )
        self.panel.attach(self.add_state_button, 0, 19, 1, 1)
        self.edit_state_button = Gtk.Button(
            label="Change name",
            visible=True,
            can_focus=True,
            receives_default=True,
            use_stock=True,
            focus_on_click=False,
        )
        self.panel.attach(self.edit_state_button, 2, 17, 1, 1)
        self.remove_state_button = Gtk.Button(
            label="Remove state",
            visible=True,
            can_focus=True,
            receives_default=True,
            use_stock=True,
            focus_on_click=False,
        )
        self.panel.attach(self.remove_state_button, 0, 20, 1, 1)
        hseparator100 = Gtk.Separator(visible=True, can_focus=False)
        self.panel.attach(hseparator100, 0, 4, 5, 1)
        hbox1 = Gtk.Box(visible=True, can_focus=False, spacing=5)
        label6 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("Forward link"),
        )
        hbox1.pack_start(label6, False, False, 0)
        arrow1 = Gtk.Arrow(visible=True, can_focus=False, xalign=0)
        hbox1.pack_start(arrow1, True, True, 0)
        self.panel.attach(hbox1, 1, 6, 1, 1)
        hbox2 = Gtk.Box(visible=True, can_focus=False, spacing=5)
        arrow2 = Gtk.Arrow(
            visible=True,
            can_focus=False,
            xalign=1,
            arrow_type=Gtk.ArrowType.LEFT,
            shadow_type=Gtk.ShadowType.NONE,
        )
        hbox2.pack_start(arrow2, True, True, 0)
        label7 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("Reverse link"),
            xalign=0,
        )
        hbox2.pack_start(label7, False, False, 0)
        self.panel.attach(hbox2, 2, 6, 1, 1)
        label5 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("Asymmetric"),
        )
        self.panel.attach(label5, 3, 6, 1, 1)
        label1 = Gtk.Label(
            visible=True,
            can_focus=False,
            tooltip_text=_(
                (
                    "Maximum size of the packet queue. Exceeding packets are "
                    "discarded."
                ),
            ),
            label=_("buffer length (Byte; 0=no limit)"),
            xalign=0,
        )
        self.panel.attach(label1, 0, 7, 1, 1)
        label2 = Gtk.Label(
            visible=True,
            can_focus=False,
            tooltip_text=_(
                (
                    "Extra delay (in milliseconds). This delay is added to "
                    "the real communication delay. Packets are temporarily "
                    "stored and resent after the delay."
                ),
            ),
            label=_("propagation delay (one way; ms)"),
            xalign=0,
        )
        self.panel.attach(label2, 0, 8, 1, 1)
        label3 = Gtk.Label(
            visible=True,
            can_focus=False,
            tooltip_text=_("Percentage of loss as a floating point number."),
            label=_("loss rate (in %, [0,100] real)"),
            xalign=0,
        )
        self.panel.attach(label3, 0, 9, 1, 1)
        label4 = Gtk.Label(
            visible=True,
            can_focus=False,
            tooltip_text=_(
                (
                    "Sender is not prevented from sending packets, delivery "
                    "is delayed to limit the bandwidth to the desired value "
                    "(like a bottleneck along the path)."
                ),
            ),
            label=_("bandwidth (Byte/s; 0=no limit)"),
            xalign=0,
        )
        self.panel.attach(label4, 0, 10, 1, 1)
        self.chanbufsize_spin = Gtk.SpinButton(
            visible=True,
            can_focus=True,
            invisible_char=ord("●"),
            primary_icon_activatable=False,
            secondary_icon_activatable=False,
            adjustment=adjustment1,
            numeric=True,
        )
        self.panel.attach(
            self.chanbufsize_spin,
            1,
            7,
            1,
            1,
        )
        self.chanbufsizer_spin = Gtk.SpinButton(
            visible=True,
            sensitive=False,
            can_focus=True,
            invisible_char=ord("●"),
            primary_icon_activatable=False,
            secondary_icon_activatable=False,
            adjustment=adjustment2,
            numeric=True,
        )
        self.panel.attach(
            self.chanbufsizer_spin,
            2,
            7,
            1,
            1,
        )
        self.delay_spin = Gtk.SpinButton(
            visible=True,
            can_focus=True,
            invisible_char=ord("●"),
            primary_icon_activatable=False,
            secondary_icon_activatable=False,
            adjustment=adjustment3,
            numeric=True,
        )
        self.panel.attach(self.delay_spin, 1, 8, 1, 1)
        self.delayr_spin = Gtk.SpinButton(
            visible=True,
            sensitive=False,
            can_focus=True,
            invisible_char=ord("●"),
            primary_icon_activatable=False,
            secondary_icon_activatable=False,
            adjustment=adjustment4,
            numeric=True,
        )
        self.panel.attach(self.delayr_spin, 2, 8, 1, 1)
        self.loss_spin = Gtk.SpinButton(
            visible=True,
            can_focus=True,
            invisible_char=ord("●"),
            primary_icon_activatable=False,
            secondary_icon_activatable=False,
            adjustment=adjustment5,
            digits=2,
            numeric=True,
        )
        self.panel.attach(self.loss_spin, 1, 9, 1, 1)
        self.lossr_spin = Gtk.SpinButton(
            visible=True,
            sensitive=False,
            can_focus=True,
            invisible_char=ord("●"),
            primary_icon_activatable=False,
            secondary_icon_activatable=False,
            adjustment=adjustment6,
            digits=2,
            numeric=True,
        )
        self.panel.attach(self.lossr_spin, 2, 9, 1, 1)
        self.bandwidth_spin = Gtk.SpinButton(
            visible=True,
            can_focus=True,
            invisible_char=ord("●"),
            primary_icon_activatable=False,
            secondary_icon_activatable=False,
            adjustment=adjustment7,
            numeric=True,
        )
        self.panel.attach(self.bandwidth_spin, 1, 10, 1, 1)
        self.bandwidthr_spin = Gtk.SpinButton(
            visible=True,
            sensitive=False,
            can_focus=True,
            invisible_char=ord("●"),
            primary_icon_activatable=False,
            secondary_icon_activatable=False,
            adjustment=adjustment8,
            numeric=True,
        )
        self.panel.attach(
            self.bandwidthr_spin,
            2,
            10,
            1,
            1,
        )
        self.chanbufsize_help_button = Gtk.Button(
            label="gtk-help",
            visible=True,
            can_focus=True,
            receives_default=True,
            use_stock=True,
            focus_on_click=False,
        )
        self.panel.attach(
            self.chanbufsize_help_button,
            4,
            7,
            1,
            1,
        )
        self.delay_help_button = Gtk.Button(
            label="gtk-help",
            visible=True,
            can_focus=True,
            receives_default=True,
            use_stock=True,
            focus_on_click=False,
        )
        self.panel.attach(self.delay_help_button, 4, 8, 1, 1)
        self.loss_help_button = Gtk.Button(
            label="gtk-help",
            visible=True,
            can_focus=True,
            receives_default=True,
            use_stock=True,
            focus_on_click=False,
        )
        self.panel.attach(self.loss_help_button, 4, 9, 1, 1)
        self.bandwidth_help_button = Gtk.Button(
            label="gtk-help",
            visible=True,
            can_focus=True,
            receives_default=True,
            use_stock=True,
            focus_on_click=False,
        )
        self.panel.attach(
            self.bandwidth_help_button,
            4,
            10,
            1,
            1,
        )
        hseparator1 = Gtk.Separator(visible=True, can_focus=False)
        self.panel.attach(hseparator1, 0, 11, 5, 1)
        hbuttonbox1 = Gtk.ButtonBox(
            visible=True,
            can_focus=False,
            layout_style=Gtk.ButtonBoxStyle.END,
        )
        reset_button = Gtk.Button(
            label="Default values",
            visible=True,
            can_focus=True,
            receives_default=True,
            use_stock=True,
            focus_on_click=False,
        )
        hbuttonbox1.pack_start(reset_button, False, False, 0)
        self.panel.attach(hbuttonbox1, 0, 11, 5, 1)
        self.chanbufsize_check = Gtk.CheckButton(
            visible=True,
            can_focus=True,
            receives_default=False,
            halign=Gtk.Align.CENTER,
            focus_on_click=False,
            xalign=0.5,
            draw_indicator=True,
        )
        self.panel.attach(
            self.chanbufsize_check,
            3,
            7,
            1,
            1,
        )
        self.delay_check = Gtk.CheckButton(
            visible=True,
            can_focus=True,
            receives_default=False,
            halign=Gtk.Align.CENTER,
            focus_on_click=False,
            xalign=0.5,
            draw_indicator=True,
        )
        self.panel.attach(self.delay_check, 3, 8, 1, 1)
        self.loss_check = Gtk.CheckButton(
            visible=True,
            can_focus=True,
            receives_default=False,
            halign=Gtk.Align.CENTER,
            focus_on_click=False,
            xalign=0.5,
            draw_indicator=True,
        )
        self.panel.attach(self.loss_check, 3, 9, 1, 1)
        self.bandwidth_check = Gtk.CheckButton(
            visible=True,
            can_focus=True,
            receives_default=False,
            halign=Gtk.Align.CENTER,
            focus_on_click=False,
            xalign=0.5,
            draw_indicator=True,
        )
        self.panel.attach(
            self.bandwidth_check,
            3,
            10,
            1,
            1,
        )
        hboxspace2 = Gtk.Box(visible=True, can_focus=False)
        labelspace2 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_(""),
        )
        hboxspace2.pack_start(labelspace2, False, False, 0)
        self.panel.attach(hboxspace2, 0, 12, 1, 1)
        hboxspace3 = Gtk.Box(visible=True, can_focus=False)
        labelspace3 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("Markov configuration"),
        )
        hboxspace3.pack_start(labelspace3, False, False, 0)
        self.panel.attach(hboxspace3, 0, 13, 1, 1)
        hboxspace4 = Gtk.Box(visible=True, can_focus=False)
        self.state_label = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_(""),
            xalign=1,
        )
        hboxspace4.pack_start(self.state_label, True, True, 0)
        hboxspace4.reorder_child(self.state_label, 1)
        self.panel.attach(hboxspace4, 0, 15, 1, 1)
        hbuttonbox10 = Gtk.ButtonBox(
            visible=True,
            can_focus=False,
            layout_style=Gtk.ButtonBoxStyle.END,
        )
        save_button = Gtk.Button(
            label="Save channel configuration",
            visible=True,
            can_focus=True,
            receives_default=True,
            use_stock=True,
            focus_on_click=False,
        )
        hbuttonbox10.add(save_button)
        self.panel.attach(hbuttonbox10, 0, 11, 1, 1)
        label12 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("Changing state probability"),
        )
        self.panel.attach(label12, 3, 14, 1, 1)
        label11 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("========>"),
        )
        self.panel.attach(label11, 1, 15, 1, 1)
        # Custom widget from glade-catalog.xml
        self.weight_combo = widgets.ComboBox(
            width_request=150,
            visible=True,
            can_focus=False,
            model=self.other_states_store,
            active=0,
        )
        # Custom widget from glade-catalog.xml
        self.weight_cell = widgets.CellRendererFormattable(display_member="label")
        self.weight_combo.pack_start(self.weight_cell, False)
        self.panel.attach(self.weight_combo, 2, 15, 1, 1)
        self.weight_spin = Gtk.SpinButton(
            visible=True,
            can_focus=True,
            invisible_char=ord("●"),
            primary_icon_activatable=False,
            secondary_icon_activatable=False,
            adjustment=self.probability_adjustment,
            digits=2,
            numeric=True,
        )
        self.panel.attach(self.weight_spin, 3, 15, 1, 1)
        self.update_weight_button = Gtk.Button(
            label="Save",
            visible=True,
            can_focus=True,
            receives_default=True,
            use_stock=True,
            focus_on_click=False,
        )
        self.panel.attach(self.update_weight_button, 4, 15, 1, 1)
        hboxspace6 = Gtk.Box(visible=True, can_focus=False)
        label_name = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("State name"),
            xalign=1,
        )
        hboxspace6.pack_start(label_name, True, True, 0)
        self.panel.attach(hboxspace6, 0, 17, 1, 1)
        self.state_name_entry = Gtk.Entry(
            visible=True,
            can_focus=True,
            invisible_char=ord("●"),
            primary_icon_activatable=False,
            secondary_icon_activatable=False,
        )
        self.panel.attach(self.state_name_entry, 1, 17, 1, 1)
        hboxspace7 = Gtk.Box(visible=True, can_focus=False)
        labelspace7 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_(""),
        )
        hboxspace7.pack_start(labelspace7, False, False, 0)
        self.panel.attach(hboxspace7, 0, 16, 1, 1)
        hboxspace8 = Gtk.Box(visible=True, can_focus=False)
        labelspace8 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_(""),
        )
        hboxspace8.pack_start(labelspace8, False, False, 0)
        self.panel.attach(hboxspace8, 0, 18, 1, 1)
        time_label = Gtk.Label(
            label="Transition period (ms)",
            visible=True,
            can_focus=True,
            xalign=1,
        )
        self.panel.attach(time_label, 2, 3, 1, 1)
        self.time_spin = Gtk.SpinButton(
            visible=True,
            can_focus=True,
            invisible_char=ord("●"),
            primary_icon_activatable=False,
            secondary_icon_activatable=False,
            adjustment=time_adjustment,
            numeric=True,
        )
        self.panel.attach(self.time_spin, 3, 3, 1, 1)
        # TODO: empty Glade placeholder, nothing to create.
        # TODO: empty Glade placeholder, nothing to create.

        # Signals
        self.state_combo.connect("changed", self.on_state_combo_changed)
        reset_button.connect("clicked", self.on_reset_button_clicked)
        save_button.connect("clicked", self.on_save_button_clicked)
        self.weight_combo.connect("changed", self.on_weight_combo_changed)

    def get_root_widget(self) -> Gtk.Grid:
        return self.panel

    def get_config_view(self, gui):

        # when creating a new item, the set function is not called
        if self.original.markov_manager is None:
            self.original.init_markov()

        # original parameters
        self.temp = deepcopy(self.original.markov_manager)
        self.tempStates = self.temp.states
        self.tempWeights = self.temp.weights

        self.update(False, self.original.currentState)

        self.state_manager = manager = StateManager()
        params = ("chanbufsize", "delay", "loss", "bandwidth")
        for param in params:
            checkbutton = getattr(self, param + "_check")
            checkbutton.set_active(not self.original.get(param + "symm"))
            tooltip = _("Disabled because set symmetric")
            spinbutton = getattr(self, param + "r_spin")
            manager.add_checkbutton_active(checkbutton, tooltip, spinbutton)

        self.time_spin.set_value(self.original.transPeriod)

        # setup help buttons
        for button in self.help_buttons:
            getattr(self, button).connect(
                "clicked",
                self.help.on_help_button_clicked,
            )

        # markov buttons
        self.add_state_button.connect("clicked", self.on_add_state)
        self.edit_state_button.connect("clicked", self.on_edit_state)
        self.remove_state_button.connect("clicked", self.on_remove_state)
        self.update_weight_button.connect("clicked", self.on_update_weight)

        # setup plugs
        for i, wname in enumerate(("sock0_combo", "sock1_combo")):
            combo = getattr(self, wname)
            self.configure_sock_combobox(
                combo,
                gui.brickfactory.socks.filter_new(),
                self.original,
                self.original.plugs[i],
                gui
            )

        return self.panel

    def getconfig(self, cfg):
        for config_name, widget_name in self.config_to_checkbutton_mapping:
            cfg[config_name] = not getattr(self, widget_name).get_active()
        for pname, wname in self.config_to_spinint_mapping:
            cfg[pname] = getattr(self, wname).get_value_as_int()
        for pname, wname in self.config_to_spinfloat_mapping:
            cfg[pname] = getattr(self, wname).get_value()

    def configure_brick(self, gui):
        cfg = {}
        self.getconfig(cfg)
        cfg["name"] = self.state_name_entry.get_text()
        self.original.set(cfg)

        # configure plug
        for i, wname in enumerate(("sock0_combo", "sock1_combo")):
            self.connect_plug(self.original.plugs[i], getattr(self, wname))

    def on_reset_button_clicked(self, button):
        self.chanbufsize_spin.set_value(75000)
        self.chanbufsizer_spin.set_value(75000)
        self.delay_spin.set_value(0)
        self.delayr_spin.set_value(0)
        self.loss_spin.set_value(0)
        self.lossr_spin.set_value(0)
        self.bandwidth_spin.set_value(125000)
        self.bandwidthr_spin.set_value(125000)

    # save all parameters, calling this function has the same effect of calling each save function then communicating with the emulator
    def on_ok_button_clicked(self, button, gui):

        self.original.markov_manager.states = self.tempStates
        self.original.markov_manager.weights = self.tempWeights

        transPeriod = self.time_spin.get_value_as_int()
        if transPeriod is not None:
            self.original.transPeriod = transPeriod

        index = self.state_combo.get_selected_value()
        if index is not None:
            self.original.config = self.tempStates[index]
            self.getconfig(self.original.config)
            self.original.config["name"] = self.state_name_entry.get_text()

            self.original.currentState = index

            otherIndex = self.weight_combo.get_selected_value()
            if otherIndex is not None:
                self.original.markov_manager.weights[index][otherIndex] = float(self.weight_spin.get_value_as_int())
        else:
            self.original.config = self.tempStates[0]
            self.original.currentState = 0

        self.original.update()

        # configure plug
        for i, wname in enumerate(("sock0_combo", "sock1_combo")):
            self.connect_plug(self.original.plugs[i], getattr(self, wname))

        dispose(self)
        gui.curtain_down()

    # save channel configuration
    def on_save_button_clicked(self, button):
        index = self.state_combo.get_selected_value()
        if index is not None:
            self.getconfig(self.tempStates[index])

    # update the gui without user intervention
    # parameters:
    #   noCombo: if true, the comboboxes representating the states are not updated
    #   index: the index of the state list

    def update(self, noCombo, index):
        for pname, wname in self.config_to_checkbutton_mapping:
            getattr(self, wname).set_active(not self.tempStates[index][pname])
        for pname, wname in self.config_to_spinint_mapping:
            getattr(self, wname).set_value(self.tempStates[index][pname])
        for pname, wname in self.config_to_spinfloat_mapping:
            getattr(self, wname).set_value(self.tempStates[index][pname])

        self.state_label.set_text("Selected state: " + str(index))
        self.state_name_entry.set_text(self.tempStates[index]["name"])

        states = list()
        exstates = list()
        for i, state in enumerate(self.tempStates):
            states.append(widgets.ListEntry(i, str(i) + " (" + state["name"] + ")"))
            if i != index:
                exstates.append(widgets.ListEntry(i, str(i) + " (" + state["name"] + ")"))

        self.other_states_store.set_data_source(exstates)

        if len(exstates):
            self.weight_combo.set_selected_value(exstates[0].value)
            self.weight_combo.set_cell_data_func(self.weight_cell, self.weight_cell.set_text)
            self.weight_spin.set_editable(True)
            self.update_weight_button.set_sensitive(True)
            self.time_spin.set_editable(True)
        else:
            self.weight_spin.set_value(0.0)
            self.weight_spin.set_editable(False)
            self.update_weight_button.set_sensitive(False)
            self.time_spin.set_editable(False)

        if noCombo:
            return

        self.states_store.set_data_source(states)
        self.state_combo.set_selected_value(index)
        self.state_combo.set_cell_data_func(self.state_cell, self.state_cell.set_text)

    def on_add_state(self, button):
        index = self.state_combo.get_selected_value()
        if index is not None:
            self.temp.add(index + 1)
            self.update(False, index + 1)

    def on_remove_state(self, button):
        index = self.state_combo.get_selected_value()
        if index is not None:
            self.temp.remove(index)
            self.update(False, min(index, len(self.tempStates) - 1))

    def on_edit_state(self, button):
        index = self.state_combo.get_selected_value()
        if index is not None:
            text = self.state_name_entry.get_text()
            if text is None:
                return

            # no name duplicates
            for state in self.tempStates:
                if state["name"] == text:
                    return

            self.tempStates[index]["name"] = text
            self.update(False, index)

    def on_update_weight(self, button):
        index = self.state_combo.get_selected_value()
        if index is not None:
            otherIndex = self.weight_combo.get_selected_value()
            if otherIndex is not None:
                self.tempWeights[index][otherIndex] = float(self.weight_spin.get_value_as_int())

    def on_state_combo_changed(self, combobox):
        index = self.state_combo.get_selected_value()
        if index is not None:
            self.update(True, index)

    def on_weight_combo_changed(self, combobox):
        index = self.weight_combo.get_selected_value()
        if index is not None:
            otherIndex = self.state_combo.get_selected_value()
            if otherIndex is not None and otherIndex < len(self.tempWeights):
                value = self.tempWeights[otherIndex][index]
                maxWeight = 100
                for weight in self.tempWeights[otherIndex]:
                    maxWeight -= weight
                maxWeight += value
                self.probability_adjustment.set_upper(maxWeight)
                self.weight_spin.set_value(value)
