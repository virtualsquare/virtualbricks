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
Dialogs to add or edit a network interface of a virtual machine.
"""

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gtk

from twisted.logger import Logger

from virtualbricks import tools
from virtualbricks.bricks import virtualmachine
from virtualbricks.config import settings
from virtualbricks.gui.windows.base import _, Window

logger = Logger()

invalid_mac = "MAC address {mac} is not valid, generating " "a random one"
not_implemented = "Not implemented"


class BaseEthernetDialog(Window):
    """
    Network interface of a virtual machine: the sock to connect to, the network
    card model and the MAC address.
    """

    def __init__(self, factory, brick):
        Window.__init__(self)
        self.factory = factory
        self.brick = brick

    def build_ui(self) -> None:
        """Create the widgets, formerly in ``ethernetdialog.ui``."""

        # nic_model_store (Gtk.ListStore)
        self.nic_model_store = Gtk.ListStore(str)
        self.nic_model_store.append([_("rtl8139")])
        self.nic_model_store.append([_("e1000")])
        self.nic_model_store.append([_("virtio-net-pci")])
        self.nic_model_store.append([_("i82551")])
        self.nic_model_store.append([_("i82557b")])
        self.nic_model_store.append([_("i82559er")])
        self.nic_model_store.append([_("ne2k_pci")])
        self.nic_model_store.append([_("pcnet")])
        self.nic_model_store.append([_("ne2k_isa")])

        # sock_store (Gtk.ListStore)
        self.sock_store = Gtk.ListStore(str, object)

        # dialog (Gtk.Dialog)
        self.dialog = Gtk.Dialog(
            can_focus=False,
            border_width=5,
            modal=True,
            window_position=Gtk.WindowPosition.CENTER,
            type_hint=Gdk.WindowTypeHint.DIALOG,
        )
        vbox1 = self.dialog.get_content_area()
        vbox1.set_properties(visible=True, can_focus=False, spacing=16)
        dialog_action_area1 = self.dialog.get_action_area()
        dialog_action_area1.set_properties(
            visible=True,
            can_focus=False,
            layout_style=Gtk.ButtonBoxStyle.END,
        )
        button3 = Gtk.Button(
            label="gtk-cancel",
            visible=True,
            can_focus=True,
            receives_default=True,
            use_stock=True,
        )
        self.dialog.add_action_widget(
            button3,
            Gtk.ResponseType.CANCEL,
        )
        # add_action_widget() packs the button at the end and aligns it to
        # the baseline, restore the Glade packing and alignment.
        button3.set_valign(Gtk.Align.FILL)
        dialog_action_area1.child_set(
            button3,
            pack_type=Gtk.PackType.START,
            expand=False,
            fill=False,
        )
        self.ok_button = Gtk.Button(
            label="gtk-add",
            visible=True,
            can_focus=True,
            receives_default=True,
            use_stock=True,
        )
        self.dialog.add_action_widget(
            self.ok_button,
            Gtk.ResponseType.OK,
        )
        self.ok_button.set_valign(Gtk.Align.FILL)
        dialog_action_area1.child_set(
            self.ok_button,
            pack_type=Gtk.PackType.START,
            expand=False,
            fill=False,
        )
        vbox1.child_set(
            dialog_action_area1,
            expand=False,
            fill=True,
            pack_type=Gtk.PackType.END,
        )
        self.title_label = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("<b>New ethernet interface</b>"),
            use_markup=True,
        )
        vbox1.pack_start(self.title_label, False, True, 0)
        grid1 = Gtk.Grid(
            visible=True,
            can_focus=False,
            row_homogeneous=True,
        )
        label2 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("Model:"),
            xalign=0,
        )
        grid1.attach(label2, 0, 0, 1, 1)
        self.model_combo = Gtk.ComboBox(
            visible=True,
            can_focus=False,
            model=self.nic_model_store,
            active=0,
        )
        renderer2 = Gtk.CellRendererText()
        self.model_combo.pack_start(renderer2, False)
        self.model_combo.add_attribute(renderer2, "text", 0)
        grid1.attach(self.model_combo, 1, 0, 1, 1)
        label3 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("Connect to:"),
            xalign=0,
        )
        grid1.attach(label3, 0, 1, 1, 1)
        self.sock_combo = Gtk.ComboBox(
            visible=True,
            can_focus=False,
            model=self.sock_store,
        )
        renderer1 = Gtk.CellRendererText()
        self.sock_combo.pack_start(renderer1, False)
        self.sock_combo.add_attribute(renderer1, "text", 0)
        grid1.attach(self.sock_combo, 1, 1, 1, 1)
        box1 = Gtk.Box(visible=True, can_focus=False)
        label4 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("Mac address:"),
            xalign=0,
        )
        box1.pack_start(label4, True, True, 0)
        randomize_button = Gtk.Button(
            label=_("Randomize"),
            visible=True,
            can_focus=True,
            receives_default=True,
        )
        box1.pack_end(randomize_button, False, False, 6)
        grid1.attach(box1, 0, 2, 1, 1)
        self.mac_entry = Gtk.Entry(
            visible=True,
            can_focus=True,
            primary_icon_activatable=False,
            secondary_icon_activatable=False,
        )
        grid1.attach(self.mac_entry, 1, 2, 1, 1)
        vbox1.pack_start(grid1, False, True, 0)

        # Signals
        self.dialog.connect(
            "response",
            self.on_dialog_response,
        )
        randomize_button.connect(
            "clicked",
            self.on_randomize_button_clicked,
        )

    def get_root_widget(self) -> Gtk.Dialog:
        return self.dialog

    def is_valid(self, mac):
        return tools.mac_is_valid(mac)

    def setup(self):
        socks = self.sock_store
        socks.append(
            ("Host-only ad hoc network", virtualmachine.hostonly_sock)
        )
        if settings.get("femaleplugs"):
            socks.append(("Vde socket", "_sock"))
            for sock in self.factory.socks:
                socks.append((sock.nickname, sock))
        else:
            for sock in self.factory.socks:
                if sock.brick.get_type().startswith("Switch"):
                    socks.append((sock.nickname, sock))

    def on_randomize_button_clicked(self, button):
        self.mac_entry.set_text(tools.random_mac())

    def on_dialog_response(self, dialog, response_id):
        if response_id == Gtk.ResponseType.OK:
            combo = self.sock_combo
            sock = combo.get_model().get_value(combo.get_active_iter(), 1)
            combo = self.model_combo
            model = combo.get_model().get_value(combo.get_active_iter(), 0)
            mac = self.mac_entry.get_text()
            if not self.is_valid(mac):
                logger.error(invalid_mac, mac=mac)
                mac = tools.random_mac()
            self.do(sock, mac, model)
        dialog.destroy()


class AddEthernetDialog(BaseEthernetDialog):
    """
    Add a network interface.
    """

    def __init__(self, factory, brick, model):
        BaseEthernetDialog.__init__(self, factory, brick)
        self.model = model

    def show(self, parent=None):
        self.setup()
        self.sock_combo.set_active(0)
        BaseEthernetDialog.show(self, parent)

    def do(self, sock, mac, model):
        if sock == "_sock":
            link = self.brick.add_sock(mac, model)
        else:
            link = self.brick.add_plug(sock, mac, model)
        self.model.append((link,))


class EditEthernetDialog(BaseEthernetDialog):
    """
    Edit a network interface.
    """

    def __init__(self, factory, brick, plug):
        BaseEthernetDialog.__init__(self, factory, brick)
        self.plug = plug

    def show(self, parent=None):
        self.setup()
        self.title_label.set_label("<b>Edit ethernet interface</b>")
        self.ok_button.set_property("label", "gtk-ok")
        self.mac_entry.set_text(self.plug.mac)
        model = self.nic_model_store
        itr = model.get_iter_first()
        while itr:
            if model.get_value(itr, 0) == self.plug.model:
                self.model_combo.set_active_iter(itr)
                break
            itr = model.iter_next(itr)

        socks = self.sock_store
        if self.plug.mode == "sock" and settings.get("femaleplugs"):
            self.sock_combo.set_active(1)
        else:
            itr = socks.get_iter_first()
            while itr:
                if self.plug.sock is socks.get_value(itr, 1):
                    self.sock_combo.set_active_iter(itr)
                    break
                itr = socks.iter_next(itr)
        BaseEthernetDialog.show(self, parent)

    def do(self, sock, mac, model):
        if sock == "_sock":
            logger.error(not_implemented)
        else:
            if self.plug.configured():
                self.plug.disconnect()
            self.plug.connect(sock)
            if mac:
                self.plug.mac = mac
            if model:
                self.plug.model = model
