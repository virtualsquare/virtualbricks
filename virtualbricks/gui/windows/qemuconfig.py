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
Configuration panel of the virtual machines.
"""

import os
import string

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gtk, Pango

from twisted.logger import Logger

from virtualbricks import config, qemu, tools
from virtualbricks.gui import graphics, widgets
from virtualbricks.gui.interfaces import IMenu
from virtualbricks.spawn import getQemuOutput
from virtualbricks.tools import dispose
from virtualbricks.bricks.virtualmachine import get_usb_devices
from virtualbricks.gui.windows.base import (
    _,
    ConfigController,
    SensitiveControl,
    State,
    StateManager,
)
from virtualbricks.gui.windows.confirmdialog import DeleteLinkConfirmDialog
from virtualbricks.gui.windows.createimagedialog import CreateImageDialog
from virtualbricks.gui.windows.disklibrary import DisksLibraryWindow
from virtualbricks.gui.windows.ethernetdialog import AddEthernetDialog
from virtualbricks.gui.windows.loadimagedialog import LoadImageDialog
from virtualbricks.gui.windows.usbdev import UsbDevDialog

logger = Logger()

qemu_version_parsing_error = "Error while parsing qemu version"
retrieve_qemu_version_error = "Error while retrieving qemu version."
usb_access = "Cannot access /dev/bus/usb. Check user privileges."
no_kvm = (
    "No KVM support found on the system. Check your active "
    "configuration. KVM will stay disabled."
)
retr_usb = "Error while retrieving usb devices."


def get_selection(treeview):
    selection = treeview.get_selection()
    if selection is not None:
        model, iter = selection.get_selected()
        if iter is not None:
            return model.get_value(iter, 0)


def get_element_at_click(treeview, event):
    pthinfo = treeview.get_path_at_pos(int(event.x), int(event.y))
    if pthinfo is not None:
        path, col, cellx, celly = pthinfo
        treeview.grab_focus()
        treeview.set_cursor(path, col, 0)
        model = treeview.get_model()
        obj = model.get_value(model.get_iter(path), 0)
        return obj


def _set_vlan(column, cell_renderer, model, itr, data=None):
    vlan = model.get_path(itr)[0]
    cell_renderer.set_property("text", str(vlan))


def _set_connection(column, cell_renderer, model, iter, data=None):
    link = model.get_value(iter, 0)
    if link.mode == "hostonly":
        conn = "Host"
    elif link.sock:
        conn = link.sock.brick.name
    elif link.mode == "sock" and config.get("femaleplugs"):
        conn = "Vde socket (female plug)"
    else:
        conn = "None"
    cell_renderer.set_property("text", conn)


def _set_model(column, cell_renderer, model, iter, data=None):
    link = model.get_value(iter, 0)
    cell_renderer.set_property("text", link.model)


def _set_mac(column, cell_renderer, model, iter, data=None):
    link = model.get_value(iter, 0)
    cell_renderer.set_property("text", link.mac)


class ImageFormatter(string.Formatter):

    def format(self, format_string, image):
        if image is None:
            return ""
        return format(image, format_string)


BOOT_DEVICE = (
    ("", "hd1"),
    ("a", "floppy"),
    ("d", "cdrom"),
)
SOUND_DEVICE = (
    ("", "no audio"),
    ("pcspk", "PC speaker"),
    ("sb16", "Creative Sound Blaster 16"),
    ("ac97", "Intel 82801AA AC97 Audio"),
    ("es1370", "ENSONIQ AudioPCI ES1370"),
)
MOUNT_DEVICE = (
    ("", "No"),
    ("/dev/cdrom", "cdrom"),
)


class ImagesBindingList(widgets.ImagesBindingList):

    def __iter__(self):
        yield None
        for image in widgets.ImagesBindingList.__iter__(self):
            yield image


class QemuConfigController(ConfigController):
    """
    Configuration panel of the virtual machines (Qemu brick): system, disks,
    network cards, graphics, devices, kernel and advanced options, one tab
    each.
    """

    config_to_widget_mapping = (
        ("snapshot", "snapshot_check"),
        ("deviceen", "device_radio"),
        ("cdromen", "cdrom_image_radio"),
        ("use_virtio", "virtio_check"),
        ("privatehda", "hda_private_check"),
        ("privatehdb", "hdb_private_check"),
        ("privatehdc", "hdc_private_check"),
        ("privatehdd", "hdd_private_check"),
        ("privatefda", "fda_private_check"),
        ("privatefdb", "fdb_private_check"),
        ("privatemtdblock", "mtdblock_private_check"),
        ("kvm", "kvm_check"),
        ("kvmsm", "kvmsm_check"),
        ("novga", "novga_check"),
        ("vga", "vga_check"),
        ("vnc", "vnc_check"),
        ("sdl", "sdl_check"),
        ("portrait", "portrait_check"),
        ("usbmode", "usb_check"),
        ("rtc", "rtc_check"),
        ("tdf", "tdf_check"),
        ("serial", "serial_check"),
        ("kernelenbl", "kernel_check"),
        ("initrdenbl", "initrd_check"),
        ("gdb", "gdb_check"),
    )
    config_to_filechooser_mapping = (
        ("cdrom", "cdrom_chooser"),
        ("kernel", "kernel_chooser"),
        ("initrd", "initrd_chooser"),
        ("icon", "icon_chooser"),
    )
    config_to_spinint_mapping = (
        ("smp", "smp_spin"),
        ("ram", "ram_spin"),
        ("kvmsmem", "kvmsmem_spin"),
        ("vncN", "vnc_display_spin"),
        ("gdbport", "gdb_port_spin"),
    )

    state_manager = None
    __images_list = None

    def build_ui(self) -> None:
        """Create the widgets, formerly in ``qemuconfig.ui``."""

        # adjustment1 (Gtk.Adjustment)
        adjustment1 = Gtk.Adjustment(
            lower=1,
            upper=64,
            value=1,
            step_increment=1,
            page_increment=8,
        )

        # adjustment2 (Gtk.Adjustment)
        adjustment2 = Gtk.Adjustment(
            upper=500,
            value=1,
            step_increment=1,
            page_increment=10,
        )

        # adjustment3 (Gtk.Adjustment)
        adjustment3 = Gtk.Adjustment(
            lower=1,
            upper=99999,
            value=128,
            step_increment=1,
            page_increment=10,
        )

        # adjustment4 (Gtk.Adjustment)
        adjustment4 = Gtk.Adjustment(
            upper=99999,
            value=1,
            step_increment=1,
            page_increment=10,
        )

        # adjustment5 (Gtk.Adjustment)
        adjustment5 = Gtk.Adjustment(
            lower=1,
            upper=65535,
            value=1234,
            step_increment=1,
            page_increment=10,
        )

        # argv0_store (widgets.List)
        # Custom widget from glade-catalog.xml
        self.argv0_store = widgets.List()
        self.argv0_store.set_properties(value_member="value")

        # boot_store (widgets.List)
        # Custom widget from glade-catalog.xml
        self.boot_store = widgets.List()
        self.boot_store.set_properties(value_member="value")

        # cpu_store (widgets.List)
        # Custom widget from glade-catalog.xml
        self.cpu_store = widgets.List()
        self.cpu_store.set_properties(value_member="value")

        # device_store (widgets.List)
        # Custom widget from glade-catalog.xml
        self.device_store = widgets.List()
        self.device_store.set_properties(value_member="value")

        # images_store (widgets.List)
        # Custom widget from glade-catalog.xml
        self.images_store = widgets.List()

        # machine_store (widgets.List)
        # Custom widget from glade-catalog.xml
        self.machine_store = widgets.List()
        self.machine_store.set_properties(value_member="value")

        # sound_store (widgets.List)
        # Custom widget from glade-catalog.xml
        self.sound_store = widgets.List()
        self.sound_store.set_properties(value_member="value")

        # plugs_store (Gtk.ListStore)
        self.plugs_store = Gtk.ListStore(object)

        # panel (Gtk.Box)
        self.panel = Gtk.Box(
            visible=True,
            can_focus=False,
            orientation=Gtk.Orientation.VERTICAL,
        )
        notebook_imgsettings = Gtk.Notebook(visible=True, can_focus=True)
        table1 = Gtk.Grid(
            visible=True,
            can_focus=False,
            row_spacing=5,
            column_spacing=5,
        )
        vbox1 = Gtk.Box(
            visible=True,
            can_focus=False,
            orientation=Gtk.Orientation.VERTICAL,
        )
        frame1 = Gtk.Frame(visible=True, can_focus=False, label_xalign=0)
        vbox2 = Gtk.Box(
            visible=True,
            can_focus=False,
            orientation=Gtk.Orientation.VERTICAL,
        )
        hbox1 = Gtk.Box(visible=True, can_focus=False, spacing=6)
        label1 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("boot as device"),
            xalign=0,
        )
        hbox1.pack_start(label1, False, True, 0)
        # Custom widget from glade-catalog.xml
        self.boot_combo = widgets.ComboBox(
            width_request=150,
            visible=True,
            can_focus=False,
            model=self.boot_store,
            active=0,
        )
        # Custom widget from glade-catalog.xml
        self.boot_cell = widgets.CellRendererFormattable(
            display_member="label"
        )
        self.boot_combo.pack_start(self.boot_cell, False)
        hbox1.pack_start(self.boot_combo, True, True, 0)
        vbox2.pack_start(hbox1, False, True, 0)
        self.snapshot_check = Gtk.CheckButton(
            label=_("Snapshot mode"),
            visible=True,
            can_focus=True,
            receives_default=False,
            has_tooltip=True,
            tooltip_text=_(
                "write to temporary files instead of disk image files",
            ),
            use_underline=True,
            xalign=0.5,
            draw_indicator=True,
        )
        vbox2.pack_start(self.snapshot_check, False, True, 0)
        frame1.add(vbox2)
        label2 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("<b>boot options</b>"),
            use_markup=True,
        )
        frame1.set_label_widget(label2)
        vbox1.pack_start(frame1, False, False, 0)
        frame2 = Gtk.Frame(visible=True, can_focus=False, label_xalign=0)
        table2 = Gtk.Grid(
            visible=True,
            can_focus=False,
            margin_top=3,
            margin_bottom=3,
            row_spacing=3,
            column_spacing=6,
        )
        nocdrom_radiobutton = Gtk.RadioButton(
            label=_("no cdrom"),
            visible=True,
            can_focus=True,
            receives_default=False,
            has_tooltip=True,
            tooltip_text=_("don´t use any cdrom device"),
            relief=Gtk.ReliefStyle.NONE,
            use_underline=True,
            xalign=0.5,
            active=True,
            draw_indicator=True,
        )
        table2.attach(nocdrom_radiobutton, 0, 0, 1, 1)
        self.device_radio = Gtk.RadioButton(
            label=_("mount cdrom"),
            visible=True,
            can_focus=True,
            receives_default=False,
            has_tooltip=True,
            tooltip_text=_("mount local cdrom Drive"),
            use_underline=True,
            xalign=0.5,
            draw_indicator=True,
            group=nocdrom_radiobutton,
        )
        table2.attach(self.device_radio, 0, 1, 1, 1)
        self.cdrom_image_radio = Gtk.RadioButton(
            label=_("use image as cdrom"),
            visible=True,
            can_focus=True,
            receives_default=False,
            has_tooltip=True,
            tooltip_text=_(
                (
                    "use one of the image files in the default folder as "
                    "cdrom device"
                ),
            ),
            use_underline=True,
            xalign=0.5,
            draw_indicator=True,
            group=nocdrom_radiobutton,
        )
        table2.attach(self.cdrom_image_radio, 0, 2, 1, 1)
        image1 = Gtk.Image(
            visible=True,
            can_focus=False,
            stock="gtk-cdrom",
        )
        table2.attach(image1, 1, 0, 1, 1)
        # Custom widget from glade-catalog.xml
        self.mount_combo = widgets.ComboBox(
            width_request=180,
            visible=True,
            can_focus=False,
            model=self.device_store,
            active=0,
        )
        # Custom widget from glade-catalog.xml
        self.mount_cell = widgets.CellRendererFormattable(
            display_member="label"
        )
        self.mount_combo.pack_start(self.mount_cell, False)
        table2.attach(self.mount_combo, 1, 1, 1, 1)
        self.cdrom_chooser = Gtk.FileChooserButton(
            visible=True, can_focus=False
        )
        table2.attach(self.cdrom_chooser, 1, 2, 1, 1)
        frame2.add(table2)
        label3 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("<b>cdrom device</b>"),
            use_markup=True,
        )
        frame2.set_label_widget(label3)
        vbox1.pack_start(frame2, False, False, 0)
        table1.attach(vbox1, 0, 0, 1, 1)
        vbox3 = Gtk.Box(
            visible=True,
            can_focus=False,
            orientation=Gtk.Orientation.VERTICAL,
        )
        frame3 = Gtk.Frame(visible=True, can_focus=False, label_xalign=0)
        vbox4 = Gtk.Box(
            visible=True,
            can_focus=False,
            margin_left=6,
            margin_right=6,
            margin_top=5,
            margin_bottom=5,
            orientation=Gtk.Orientation.VERTICAL,
        )
        hbox3 = Gtk.Box(visible=True, can_focus=False)
        image3 = Gtk.Image(
            visible=True,
            can_focus=False,
            stock="gtk-harddisk",
            icon_size=3,
        )
        hbox3.pack_start(image3, True, True, 0)
        label123 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("Select images for Qemu volumes"),
            xalign=0,
        )
        hbox3.pack_start(label123, True, True, 0)
        vbox4.pack_start(hbox3, False, True, 0)
        self.virtio_check = Gtk.CheckButton(
            label=_("Use virtio block devices"),
            visible=True,
            can_focus=True,
            receives_default=False,
            xalign=0.5,
            draw_indicator=True,
        )
        vbox4.pack_start(self.virtio_check, True, True, 0)
        table3 = Gtk.Grid(
            visible=True,
            can_focus=False,
            row_spacing=2,
            column_spacing=2,
            column_homogeneous=True,
        )
        label9 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("hda:"),
            xalign=0,
        )
        table3.attach(label9, 0, 0, 1, 1)
        label8 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("hdb:"),
            xalign=0,
        )
        table3.attach(label8, 0, 1, 1, 1)
        label7 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("hdc:"),
            xalign=0,
        )
        table3.attach(label7, 0, 2, 1, 1)
        label6 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("hdd:"),
            xalign=0,
        )
        table3.attach(label6, 0, 3, 1, 1)
        label5 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("fda:"),
            xalign=0,
        )
        table3.attach(label5, 0, 4, 1, 1)
        # Custom widget from glade-catalog.xml
        self.hda_combo = widgets.ComboBox(
            visible=True,
            can_focus=False,
            model=self.images_store,
            active=0,
        )
        # Custom widget from glade-catalog.xml
        self.hda_cell = widgets.CellRendererFormattable(
            format_string="n",
            formatting_enabled=True,
        )
        self.hda_combo.pack_start(self.hda_cell, False)
        table3.attach(self.hda_combo, 1, 0, 1, 1)
        # Custom widget from glade-catalog.xml
        self.hdb_combo = widgets.ComboBox(
            visible=True,
            can_focus=False,
            model=self.images_store,
            active=0,
        )
        # Custom widget from glade-catalog.xml
        self.hdb_cell = widgets.CellRendererFormattable(
            format_string="n",
            formatting_enabled=True,
        )
        self.hdb_combo.pack_start(self.hdb_cell, False)
        table3.attach(self.hdb_combo, 1, 1, 1, 1)
        # Custom widget from glade-catalog.xml
        self.hdc_combo = widgets.ComboBox(
            visible=True,
            can_focus=False,
            model=self.images_store,
            active=0,
        )
        # Custom widget from glade-catalog.xml
        self.hdc_cell = widgets.CellRendererFormattable(
            format_string="n",
            formatting_enabled=True,
        )
        self.hdc_combo.pack_start(self.hdc_cell, False)
        table3.attach(self.hdc_combo, 1, 2, 1, 1)
        # Custom widget from glade-catalog.xml
        self.hdd_combo = widgets.ComboBox(
            visible=True,
            can_focus=False,
            model=self.images_store,
            active=0,
        )
        # Custom widget from glade-catalog.xml
        self.hdd_cell = widgets.CellRendererFormattable(
            format_string="n",
            formatting_enabled=True,
        )
        self.hdd_combo.pack_start(self.hdd_cell, False)
        table3.attach(self.hdd_combo, 1, 3, 1, 1)
        # Custom widget from glade-catalog.xml
        self.fda_combo = widgets.ComboBox(
            visible=True,
            can_focus=False,
            model=self.images_store,
            active=0,
        )
        # Custom widget from glade-catalog.xml
        self.fda_cell = widgets.CellRendererFormattable(
            format_string="n",
            formatting_enabled=True,
        )
        self.fda_combo.pack_start(self.fda_cell, False)
        table3.attach(self.fda_combo, 1, 4, 1, 1)
        # Custom widget from glade-catalog.xml
        self.fdb_combo = widgets.ComboBox(
            visible=True,
            can_focus=False,
            model=self.images_store,
            active=0,
        )
        # Custom widget from glade-catalog.xml
        self.fdb_cell = widgets.CellRendererFormattable(
            format_string="n",
            formatting_enabled=True,
        )
        self.fdb_combo.pack_start(self.fdb_cell, False)
        table3.attach(self.fdb_combo, 1, 5, 1, 1)
        # Custom widget from glade-catalog.xml
        self.mtdblock_combo = widgets.ComboBox(
            visible=True,
            can_focus=False,
            model=self.images_store,
            active=0,
        )
        # Custom widget from glade-catalog.xml
        self.mtdblock_cell = widgets.CellRendererFormattable(
            format_string="n",
            formatting_enabled=True,
        )
        self.mtdblock_combo.pack_start(self.mtdblock_cell, False)
        table3.attach(self.mtdblock_combo, 1, 6, 1, 1)
        self.hda_private_check = Gtk.CheckButton(
            label=_("Private COW"),
            visible=True,
            can_focus=True,
            receives_default=False,
            xalign=0.5,
            draw_indicator=True,
        )
        table3.attach(self.hda_private_check, 2, 0, 1, 1)
        self.hdb_private_check = Gtk.CheckButton(
            label=_("Private COW"),
            visible=True,
            can_focus=True,
            receives_default=False,
            xalign=0.5,
            draw_indicator=True,
        )
        table3.attach(self.hdb_private_check, 2, 1, 1, 1)
        self.hdc_private_check = Gtk.CheckButton(
            label=_("Private COW"),
            visible=True,
            can_focus=True,
            receives_default=False,
            xalign=0.5,
            draw_indicator=True,
        )
        table3.attach(self.hdc_private_check, 2, 2, 1, 1)
        self.hdd_private_check = Gtk.CheckButton(
            label=_("Private COW"),
            visible=True,
            can_focus=True,
            receives_default=False,
            xalign=0.5,
            draw_indicator=True,
        )
        table3.attach(self.hdd_private_check, 2, 3, 1, 1)
        self.fda_private_check = Gtk.CheckButton(
            label=_("Private COW"),
            visible=True,
            can_focus=True,
            receives_default=False,
            xalign=0.5,
            draw_indicator=True,
        )
        table3.attach(self.fda_private_check, 2, 4, 1, 1)
        self.fdb_private_check = Gtk.CheckButton(
            label=_("Private COW"),
            visible=True,
            can_focus=True,
            receives_default=False,
            xalign=0.5,
            draw_indicator=True,
        )
        table3.attach(self.fdb_private_check, 2, 5, 1, 1)
        self.mtdblock_private_check = Gtk.CheckButton(
            label=_("Private COW"),
            visible=True,
            can_focus=True,
            receives_default=False,
            xalign=0.5,
            draw_indicator=True,
        )
        table3.attach(self.mtdblock_private_check, 2, 6, 1, 1)
        label4 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("fdb:"),
            xalign=0,
        )
        table3.attach(label4, 0, 5, 1, 1)
        label10 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("mtdblock:"),
            xalign=0,
        )
        table3.attach(label10, 0, 6, 1, 1)
        vbox4.pack_start(table3, False, True, 0)
        frame3.add(vbox4)
        label11 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("<b>additional media</b>"),
            use_markup=True,
        )
        frame3.set_label_widget(label11)
        vbox3.pack_start(frame3, False, True, 0)
        frame4 = Gtk.Frame(visible=True, can_focus=False, label_xalign=0)
        hbuttonbox1 = Gtk.ButtonBox(
            visible=True,
            can_focus=False,
            margin_left=6,
            margin_right=6,
            margin_top=6,
            margin_bottom=6,
            spacing=5,
            layout_style=Gtk.ButtonBoxStyle.CENTER,
        )
        newimage_button = Gtk.Button(
            label=_("New image\nfrom file"),
            visible=True,
            can_focus=True,
            receives_default=True,
        )
        hbuttonbox1.pack_start(newimage_button, False, False, 0)
        configimage_button = Gtk.Button(
            label=_("Configure \ndisk images"),
            visible=True,
            can_focus=True,
            receives_default=True,
        )
        hbuttonbox1.pack_start(configimage_button, False, False, 0)
        newempty_button = Gtk.Button(
            label=_("New (empty)\ndisk image"),
            visible=True,
            can_focus=True,
            receives_default=True,
        )
        hbuttonbox1.pack_start(newempty_button, False, False, 0)
        frame4.add(hbuttonbox1)
        label32 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("<b>disk images</b>"),
            use_markup=True,
        )
        frame4.set_label_widget(label32)
        vbox3.pack_start(frame4, False, True, 0)
        table1.attach(vbox3, 1, 0, 1, 1)
        hbox1b = Gtk.Box(visible=True, can_focus=False)
        image11 = Gtk.Image(
            visible=True,
            can_focus=False,
            stock="gtk-floppy",
        )
        hbox1b.pack_start(image11, True, True, 0)
        label12 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("Drives"),
        )
        hbox1b.pack_start(label12, True, True, 0)
        notebook_imgsettings.append_page(table1, hbox1b)
        hbox4 = Gtk.Box(
            visible=True,
            can_focus=False,
            spacing=6,
            homogeneous=True,
        )
        vbox17 = Gtk.Box(
            visible=True,
            can_focus=False,
            orientation=Gtk.Orientation.VERTICAL,
            spacing=6,
        )
        frame5 = Gtk.Frame(visible=True, can_focus=False, label_xalign=0)
        vbox5 = Gtk.Box(
            visible=True,
            can_focus=False,
            margin_right=3,
            margin_bottom=3,
            orientation=Gtk.Orientation.VERTICAL,
            spacing=3,
        )
        hbox13 = Gtk.Box(visible=True, can_focus=False)
        label13 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("Architecture:"),
            use_markup=True,
            xalign=0,
        )
        hbox13.pack_start(label13, False, False, 0)
        image12 = Gtk.Image(
            visible=True,
            can_focus=False,
            xalign=1,
            stock="gtk-convert",
        )
        hbox13.pack_start(image12, True, True, 0)
        vbox5.pack_start(hbox13, False, True, 0)
        # Custom widget from glade-catalog.xml
        self.argv0_combo = widgets.ComboBox(
            visible=True,
            can_focus=False,
            model=self.argv0_store,
        )
        # Custom widget from glade-catalog.xml
        self.argv0_cell = widgets.CellRendererFormattable(
            display_member="label"
        )
        self.argv0_combo.pack_start(self.argv0_cell, False)
        vbox5.pack_start(self.argv0_combo, True, True, 0)
        label14 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("CPU Type:"),
            use_markup=True,
            xalign=0,
        )
        vbox5.pack_start(label14, False, False, 0)
        # Custom widget from glade-catalog.xml
        self.cpu_combo = widgets.ComboBox(
            visible=True,
            can_focus=False,
            model=self.cpu_store,
        )
        # Custom widget from glade-catalog.xml
        self.cpu_cell = widgets.CellRendererFormattable(display_member="label")
        self.cpu_combo.pack_start(self.cpu_cell, False)
        vbox5.pack_start(self.cpu_combo, False, False, 0)
        label15 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("Machine type:"),
            use_markup=True,
            xalign=0,
        )
        vbox5.pack_start(label15, False, False, 0)
        # Custom widget from glade-catalog.xml
        self.machine_combo = widgets.ComboBox(
            visible=True,
            can_focus=False,
            model=self.machine_store,
        )
        # Custom widget from glade-catalog.xml
        self.machine_cell = widgets.CellRendererFormattable(
            display_member="label"
        )
        self.machine_combo.pack_start(self.machine_cell, False)
        vbox5.pack_start(self.machine_combo, False, False, 0)
        hbox14 = Gtk.Box(visible=True, can_focus=False)
        self.kvm_check = Gtk.CheckButton(
            label=_("KVM"),
            visible=True,
            can_focus=True,
            receives_default=False,
            xalign=0.5,
            draw_indicator=True,
        )
        hbox14.pack_start(self.kvm_check, False, False, 0)
        label16 = Gtk.Label(
            visible=True,
            can_focus=False,
            xpad=3,
            label=_("Number of CPUs:"),
            xalign=1,
        )
        hbox14.pack_start(label16, True, True, 2)
        self.smp_spin = Gtk.SpinButton(
            visible=True,
            can_focus=True,
            max_length=2,
            primary_icon_activatable=False,
            secondary_icon_activatable=False,
            adjustment=adjustment1,
            numeric=True,
            update_policy=Gtk.SpinButtonUpdatePolicy.IF_VALID,
        )
        hbox14.pack_start(self.smp_spin, False, False, 0)
        vbox5.pack_start(hbox14, False, False, 0)
        vbox5.reorder_child(hbox14, 7)
        frame5.add(vbox5)
        label103 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("<b>System and machine</b>"),
            use_markup=True,
        )
        frame5.set_label_widget(label103)
        vbox17.pack_start(frame5, False, True, 0)
        frame9 = Gtk.Frame(visible=True, can_focus=False, label_xalign=0)
        vbox12 = Gtk.Box(
            visible=True,
            can_focus=False,
            margin_left=3,
            margin_right=3,
            margin_top=3,
            margin_bottom=3,
            orientation=Gtk.Orientation.VERTICAL,
            spacing=3,
        )
        hbox21 = Gtk.Box(visible=True, can_focus=False)
        label22 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("Emulated Soundcard:"),
        )
        hbox21.pack_start(label22, False, False, 0)
        image15 = Gtk.Image(
            visible=True,
            can_focus=False,
            stock="gnome-stock-volume",
        )
        hbox21.pack_start(image15, True, True, 0)
        vbox12.pack_start(hbox21, False, True, 0)
        # Custom widget from glade-catalog.xml
        self.sound_combo = widgets.ComboBox(
            width_request=220,
            visible=True,
            can_focus=False,
            model=self.sound_store,
            active=0,
        )
        # Custom widget from glade-catalog.xml
        self.sound_cell = widgets.CellRendererFormattable(
            display_member="label"
        )
        self.sound_combo.pack_start(self.sound_cell, False)
        vbox12.pack_start(self.sound_combo, False, False, 0)
        frame9.add(vbox12)
        label23 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("<b>Audio Device Settings</b>"),
            use_markup=True,
        )
        frame9.set_label_widget(label23)
        vbox17.pack_start(frame9, False, True, 0)
        frame10 = Gtk.Frame(visible=True, can_focus=False, label_xalign=0)
        vbox13 = Gtk.Box(
            visible=True,
            can_focus=False,
            margin_left=3,
            margin_right=3,
            margin_top=3,
            margin_bottom=6,
            orientation=Gtk.Orientation.VERTICAL,
            spacing=3,
        )
        hbox = Gtk.Box(visible=True, can_focus=False, spacing=3)
        label24 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("Used RAM:"),
            xalign=0,
        )
        hbox.pack_start(label24, False, True, 3)
        self.ram_spin = Gtk.SpinButton(
            visible=True,
            can_focus=True,
            primary_icon_activatable=False,
            secondary_icon_activatable=False,
            adjustment=adjustment3,
            climb_rate=1,
            numeric=True,
        )
        hbox.pack_start(self.ram_spin, False, True, 0)
        label25 = Gtk.Label(visible=True, can_focus=False, label=_("MB"))
        hbox.pack_start(label25, False, True, 0)
        vbox13.pack_start(hbox, False, True, 0)
        hbox211 = Gtk.Box(visible=True, can_focus=False, spacing=3)
        self.kvmsm_check = Gtk.CheckButton(
            label=_("KVM Shadow Memory:"),
            visible=True,
            can_focus=True,
            receives_default=False,
            xalign=0.5,
            draw_indicator=True,
        )
        hbox211.pack_start(self.kvmsm_check, False, False, 0)
        self.kvmsmem_spin = Gtk.SpinButton(
            visible=True,
            can_focus=True,
            primary_icon_activatable=False,
            secondary_icon_activatable=False,
            adjustment=adjustment4,
            climb_rate=1,
            numeric=True,
        )
        hbox211.pack_start(self.kvmsmem_spin, False, True, 0)
        lbl_kvmsm = Gtk.Label(visible=True, can_focus=False, label=_("MB"))
        hbox211.pack_start(lbl_kvmsm, False, True, 0)
        vbox13.pack_start(hbox211, True, True, 0)
        frame10.add(vbox13)
        label27 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("<b>Memory Settings</b>"),
            use_markup=True,
        )
        frame10.set_label_widget(label27)
        vbox17.pack_start(frame10, False, True, 0)
        hbox4.pack_start(vbox17, False, True, 0)
        vbox18 = Gtk.Box(
            visible=True,
            can_focus=False,
            orientation=Gtk.Orientation.VERTICAL,
            spacing=6,
        )
        frame6 = Gtk.Frame(visible=True, can_focus=False, label_xalign=0)
        vbox8 = Gtk.Box(
            visible=True,
            can_focus=False,
            margin_left=3,
            margin_right=6,
            margin_top=6,
            margin_bottom=6,
            orientation=Gtk.Orientation.VERTICAL,
        )
        hbox16 = Gtk.Box(visible=True, can_focus=False)
        self.novga_check = Gtk.CheckButton(
            label=_("disable graphical output"),
            visible=True,
            can_focus=True,
            receives_default=False,
            use_underline=True,
            xalign=0.5,
            draw_indicator=True,
        )
        hbox16.pack_start(self.novga_check, True, True, 0)
        image13 = Gtk.Image(
            visible=True,
            can_focus=False,
            stock="gtk-fullscreen",
        )
        hbox16.pack_start(image13, False, False, 0)
        vbox8.pack_start(hbox16, False, True, 0)
        self.vga_check = Gtk.CheckButton(
            label=_("Use VGA instead of Default"),
            visible=True,
            can_focus=True,
            receives_default=False,
            use_underline=True,
            xalign=0.5,
            draw_indicator=True,
        )
        vbox8.pack_start(self.vga_check, False, False, 0)
        hbox17 = Gtk.Box(visible=True, can_focus=False)
        self.vnc_check = Gtk.CheckButton(
            label=_("Start in vncserver"),
            visible=True,
            can_focus=True,
            receives_default=False,
            use_underline=True,
            xalign=0.5,
            draw_indicator=True,
        )
        hbox17.pack_start(self.vnc_check, False, False, 0)
        self.vnc_display_label = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("on Display: "),
        )
        hbox17.pack_start(self.vnc_display_label, False, False, 0)
        self.vnc_display_spin = Gtk.SpinButton(
            visible=True,
            can_focus=True,
            primary_icon_activatable=False,
            secondary_icon_activatable=False,
            adjustment=adjustment2,
            climb_rate=1,
            numeric=True,
        )
        hbox17.pack_start(self.vnc_display_spin, False, True, 0)
        vbox8.pack_start(hbox17, False, True, 0)
        self.sdl_check = Gtk.CheckButton(
            label=_("SDL"),
            visible=True,
            can_focus=True,
            receives_default=False,
            xalign=0.5,
            draw_indicator=True,
        )
        vbox8.pack_start(self.sdl_check, True, True, 0)
        self.portrait_check = Gtk.CheckButton(
            label=_("Portrait"),
            visible=True,
            can_focus=True,
            receives_default=False,
            xalign=0.5,
            draw_indicator=True,
        )
        vbox8.pack_start(self.portrait_check, True, True, 0)
        frame6.add(vbox8)
        label18 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("<b>Display Options</b>"),
            use_markup=True,
        )
        frame6.set_label_widget(label18)
        vbox18.pack_start(frame6, False, True, 0)
        frame7 = Gtk.Frame(visible=True, can_focus=False, label_xalign=0)
        hbox18 = Gtk.Box(
            visible=True,
            can_focus=False,
            margin_left=3,
            margin_right=6,
            margin_top=6,
            margin_bottom=6,
            spacing=6,
        )
        self.usb_check = Gtk.CheckButton(
            label=_("enable usb"),
            visible=True,
            can_focus=True,
            receives_default=False,
            use_underline=True,
            xalign=0.5,
            draw_indicator=True,
        )
        hbox18.pack_start(self.usb_check, True, True, 0)
        self.bind_button = Gtk.Button(
            label=_("Bind devices"),
            visible=True,
            can_focus=True,
            receives_default=True,
        )
        hbox18.pack_start(self.bind_button, False, True, 0)
        image14 = Gtk.Image(
            visible=True,
            can_focus=False,
            stock="gtk-preferences",
        )
        hbox18.pack_start(image14, False, True, 0)
        frame7.add(hbox18)
        label19 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("<b>USB settings</b>"),
            use_markup=True,
        )
        frame7.set_label_widget(label19)
        vbox18.pack_start(frame7, False, True, 0)
        frame8 = Gtk.Frame(visible=True, can_focus=False, label_xalign=0)
        vbox10 = Gtk.Box(
            visible=True,
            can_focus=False,
            margin_left=3,
            margin_right=6,
            margin_top=6,
            margin_bottom=6,
            orientation=Gtk.Orientation.VERTICAL,
            spacing=3,
        )
        self.rtc_check = Gtk.CheckButton(
            label=_("Set realtime clock to local time"),
            visible=True,
            can_focus=True,
            receives_default=False,
            use_underline=True,
            xalign=0.5,
            draw_indicator=True,
        )
        vbox10.pack_start(self.rtc_check, False, True, 0)
        self.tdf_check = Gtk.CheckButton(
            label=_("Guest time drift compensation (TDF)"),
            visible=True,
            can_focus=True,
            receives_default=False,
            xalign=0.5,
            draw_indicator=True,
        )
        vbox10.pack_start(self.tdf_check, False, True, 0)
        hbox20 = Gtk.Box(visible=True, can_focus=False, spacing=6)
        label20 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("Keyboard:"),
        )
        hbox20.pack_start(label20, False, False, 0)
        self.keyboard_entry = Gtk.Entry(
            visible=True,
            can_focus=True,
            max_length=5,
            primary_icon_activatable=False,
            secondary_icon_activatable=False,
        )
        hbox20.pack_start(self.keyboard_entry, True, True, 0)
        vbox10.pack_start(hbox20, False, True, 0)
        self.serial_check = Gtk.CheckButton(
            label=_("Serial"),
            visible=True,
            can_focus=True,
            receives_default=False,
            xalign=0.5,
            draw_indicator=True,
        )
        vbox10.pack_start(self.serial_check, False, True, 0)
        frame8.add(vbox10)
        label21 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("<b>Extra Settings</b>"),
            use_markup=True,
        )
        frame8.set_label_widget(label21)
        vbox18.pack_start(frame8, False, True, 0)
        hbox4.pack_start(vbox18, False, True, 0)
        hbox2b = Gtk.Box(visible=True, can_focus=False)
        image16 = Gtk.Image(
            visible=True,
            can_focus=False,
            stock="gtk-execute",
        )
        hbox2b.pack_start(image16, True, True, 0)
        label28 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("System"),
        )
        hbox2b.pack_start(label28, True, True, 0)
        notebook_imgsettings.append_page(hbox4, hbox2b)
        vbox14 = Gtk.Box(
            visible=True,
            can_focus=False,
            orientation=Gtk.Orientation.VERTICAL,
        )
        label29 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("<b>Network cards</b>"),
            use_markup=True,
            xalign=0,
        )
        vbox14.pack_start(label29, False, True, 0)
        scrolledwindow1 = Gtk.ScrolledWindow(visible=True, can_focus=True)
        network_cards_view = Gtk.TreeView(
            visible=True,
            can_focus=True,
            model=self.plugs_store,
        )
        self.vlan_column = Gtk.TreeViewColumn.new()
        self.vlan_column.set_properties(
            title=_("Nic"),
            clickable=True,
            reorderable=True,
            sort_column_id=0,
        )
        self.vlan_cell = Gtk.CellRendererText()
        self.vlan_column.pack_start(self.vlan_cell, False)
        network_cards_view.append_column(self.vlan_column)
        self.connection_column = Gtk.TreeViewColumn.new()
        self.connection_column.set_properties(
            title=_("Connection"),
            clickable=True,
            reorderable=True,
            sort_column_id=1,
        )
        self.connection_cell = Gtk.CellRendererText()
        self.connection_column.pack_start(
            self.connection_cell,
            False,
        )
        network_cards_view.append_column(
            self.connection_column,
        )
        self.model_column = Gtk.TreeViewColumn.new()
        self.model_column.set_properties(
            title=_("Model"),
            clickable=True,
            reorderable=True,
            sort_column_id=2,
        )
        self.model_cell = Gtk.CellRendererText()
        self.model_column.pack_start(self.model_cell, False)
        network_cards_view.append_column(self.model_column)
        self.mac_column = Gtk.TreeViewColumn.new()
        self.mac_column.set_properties(
            title=_("MAC address"),
            clickable=True,
            reorderable=True,
            sort_column_id=3,
        )
        self.mac_cell = Gtk.CellRendererText()
        self.mac_column.pack_start(self.mac_cell, False)
        network_cards_view.append_column(self.mac_column)
        scrolledwindow1.add(network_cards_view)
        vbox14.pack_start(scrolledwindow1, True, True, 0)
        addplug_button = Gtk.Button(
            visible=True,
            can_focus=True,
            receives_default=True,
            has_tooltip=True,
            tooltip_text=_("Set up a new network card"),
        )
        alignment10 = Gtk.Alignment(
            visible=True,
            can_focus=False,
            xalign=0,
            xscale=0,
            yscale=0,
        )
        hbox26 = Gtk.Box(visible=True, can_focus=False, spacing=2)
        image17 = Gtk.Image(
            visible=True,
            can_focus=False,
            stock="gtk-add",
        )
        hbox26.pack_start(image17, False, False, 0)
        label30 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("Add Network card"),
            use_underline=True,
            justify=Gtk.Justification.CENTER,
            ellipsize=Pango.EllipsizeMode.START,
        )
        hbox26.pack_start(label30, False, False, 0)
        alignment10.add(hbox26)
        addplug_button.add(alignment10)
        vbox14.pack_end(addplug_button, False, True, 0)
        hbox3b = Gtk.Box(visible=True, can_focus=False)
        image18 = Gtk.Image(
            visible=True,
            can_focus=False,
            stock="gtk-network",
        )
        hbox3b.pack_start(image18, True, True, 0)
        label31 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("Network"),
        )
        hbox3b.pack_start(label31, True, True, 0)
        notebook_imgsettings.append_page(vbox14, hbox3b)
        frame11 = Gtk.Frame(visible=True, can_focus=False, label_xalign=0)
        table6 = Gtk.Grid(
            visible=True,
            can_focus=False,
            margin_left=3,
            margin_right=6,
            margin_top=6,
            margin_bottom=6,
            row_spacing=2,
            column_spacing=6,
            column_homogeneous=True,
        )
        self.kernel_check = Gtk.CheckButton(
            label=_("Use a custom kernel"),
            visible=True,
            can_focus=True,
            receives_default=False,
            xalign=0.5,
            draw_indicator=True,
        )
        table6.attach(self.kernel_check, 0, 0, 1, 1)
        self.initrd_check = Gtk.CheckButton(
            label=_("Specify initial ramdisk"),
            visible=True,
            can_focus=True,
            receives_default=False,
            xalign=0.5,
            draw_indicator=True,
        )
        table6.attach(self.initrd_check, 0, 1, 1, 1)
        label_32 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("Parameters to append to command line:"),
            xalign=0.10000000149011612,
        )
        table6.attach(label_32, 0, 2, 1, 1)
        self.gdb_check = Gtk.CheckButton(
            label=_("Enable kernel debugging"),
            visible=True,
            can_focus=True,
            receives_default=False,
            xalign=1,
            draw_indicator=True,
        )
        table6.attach(self.gdb_check, 0, 3, 1, 1)
        self.kernel_chooser = Gtk.FileChooserButton(
            width_request=200,
            visible=True,
            can_focus=False,
        )
        table6.attach(self.kernel_chooser, 1, 0, 1, 1)
        self.initrd_chooser = Gtk.FileChooserButton(
            width_request=200,
            visible=True,
            can_focus=False,
        )
        table6.attach(self.initrd_chooser, 1, 1, 1, 1)
        self.kernel_options_entry = Gtk.Entry(
            visible=True,
            can_focus=True,
            primary_icon_activatable=False,
            secondary_icon_activatable=False,
        )
        table6.attach(self.kernel_options_entry, 1, 2, 1, 1)
        hbox30 = Gtk.Box(visible=True, can_focus=False, spacing=6)
        self.gdb_port_label = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("GNU debugger TCP port:"),
            xalign=0,
        )
        hbox30.pack_start(self.gdb_port_label, False, True, 0)
        self.gdb_port_spin = Gtk.SpinButton(
            visible=True,
            can_focus=True,
            primary_icon_activatable=False,
            secondary_icon_activatable=False,
            adjustment=adjustment5,
        )
        hbox30.pack_start(self.gdb_port_spin, True, True, 0)
        table6.attach(hbox30, 1, 3, 1, 1)
        frame11.add(table6)
        label34 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("<b>Booting Linux</b>"),
            use_markup=True,
        )
        frame11.set_label_widget(label34)
        hbox4b = Gtk.Box(visible=True, can_focus=False)
        image21 = Gtk.Image(
            visible=True,
            can_focus=False,
            stock="gtk-properties",
        )
        hbox4b.pack_start(image21, True, True, 0)
        label35 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("Customize Linux Boot"),
        )
        hbox4b.pack_start(label35, True, True, 0)
        notebook_imgsettings.append_page(frame11, hbox4b)
        frame12 = Gtk.Frame(can_focus=False, label_xalign=0)
        table4 = Gtk.Grid(
            visible=True,
            can_focus=False,
            margin_left=6,
            margin_right=6,
            margin_top=6,
            margin_bottom=6,
            row_spacing=6,
        )
        self.icon_image = Gtk.Image(
            visible=True,
            can_focus=False,
            xalign=0,
            stock="gtk-missing-image",
        )
        table4.attach(self.icon_image, 0, 1, 1, 1)
        hbox33 = Gtk.Box(visible=True, can_focus=False, spacing=2)
        self.icon_chooser = Gtk.FileChooserButton(
            width_request=200,
            visible=True,
            can_focus=False,
        )
        hbox33.pack_start(self.icon_chooser, True, True, 0)
        setdefaulticon_button = Gtk.Button(
            visible=True,
            can_focus=True,
            receives_default=True,
        )
        image22 = Gtk.Image(
            visible=True,
            can_focus=False,
            stock="gtk-delete",
            icon_size=2,
        )
        setdefaulticon_button.add(image22)
        hbox33.pack_start(setdefaulticon_button, False, False, 0)
        table4.attach(hbox33, 0, 0, 1, 1)
        frame12.add(table4)
        label36 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("<b>Virtual Machine Icon</b>"),
            use_markup=True,
        )
        frame12.set_label_widget(label36)
        hbox5b = Gtk.Box(can_focus=False)
        image23 = Gtk.Image(
            visible=True,
            can_focus=False,
            stock="gtk-edit",
        )
        hbox5b.pack_start(image23, True, True, 0)
        label37 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("Others"),
        )
        hbox5b.pack_start(label37, True, True, 0)
        notebook_imgsettings.append_page(frame12, hbox5b)
        self.panel.pack_start(notebook_imgsettings, True, True, 0)

        # Signals
        newimage_button.connect(
            "clicked",
            self.on_newimage_button_clicked,
        )
        configimage_button.connect(
            "clicked",
            self.on_configimage_button_clicked,
        )
        newempty_button.connect(
            "clicked",
            self.on_newempty_button_clicked,
        )
        self.argv0_combo.connect("changed", self.on_argv0_combo_changed)
        self.bind_button.connect("clicked", self.on_bind_button_clicked)
        network_cards_view.connect(
            "button-release-event",
            self.on_network_cards_view_button_release_event,
        )
        network_cards_view.connect(
            "key-press-event",
            self.on_network_cards_view_key_press_event,
        )
        addplug_button.connect("clicked", self.on_addplug_button_clicked)
        self.icon_chooser.connect(
            "file-set",
            self.on_icon_chooser_file_set,
        )
        setdefaulticon_button.connect(
            "clicked",
            self.on_setdefaulticon_button_clicked,
        )

    def get_root_widget(self) -> Gtk.Box:
        return self.panel

    def setup_netwoks_cards(self):
        vmplugs = self.plugs_store
        vmplugs.clear()
        for plug in self.original.plugs:
            vmplugs.append((plug,))

        if config.get("femaleplugs"):
            for sock in self.original.socks:
                vmplugs.append((sock,))

        vlan_c = self.vlan_column
        vlan_cr = self.vlan_cell
        vlan_c.set_cell_data_func(vlan_cr, _set_vlan)
        connection_c = self.connection_column
        connection_cr = self.connection_cell
        connection_c.set_cell_data_func(connection_cr, _set_connection)
        model_c = self.model_column
        model_cr = self.model_cell
        model_c.set_cell_data_func(model_cr, _set_model)
        mac_c = self.mac_column
        mac_cr = self.mac_cell
        mac_c.set_cell_data_func(mac_cr, _set_mac)

    def get_config_view(self, gui):

        def install_qemu_version(version):
            qemu.parse_and_install(version)
            container = panel.get_parent()
            container.remove(panel)
            container.pack_start(self._get_config_view(gui), True, True, 0)

        def log_retrieve_error(failure):
            logger.failure(retrieve_qemu_version_error, failure)
            return failure

        def close_panel(failure):
            logger.failure(qemu_version_parsing_error, failure)
            gui.curtain_down()

        panel = Gtk.Alignment()
        label = Gtk.Label("Loading configuration...")
        panel.add(label)
        d = getQemuOutput("qemu-system-x86_64", ["-version"])
        d.addCallbacks(install_qemu_version, log_retrieve_error)
        d.addErrback(close_panel)
        panel.show_all()
        return panel

    def _get_config_view(self, gui):
        self.gui = gui
        self.usb_devices = list(self.original.config.usbdevlist)

        self.state_manager = StateManager()
        self.state_manager.add_checkbutton_active(
            self.device_radio,
            _("Mount cdrom option not active"),
            self.mount_combo,
        )
        self.state_manager.add_checkbutton_active(
            self.cdrom_image_radio,
            _("File image option not active"),
            self.cdrom_chooser,
        )
        self.state_manager.add_checkbutton_not_active(
            self.novga_check,
            _("Graphical output disabled"),
            self.vnc_check,
            self.vnc_display_spin,
            self.vnc_display_label,
        )
        self.state_manager.add_checkbutton_not_active(
            self.vnc_check, _("VNC enabled"), self.novga_check
        )
        self.state_manager.add_checkbutton_active(
            self.kernel_check,
            _("Custom kernel selction option disabled"),
            self.kernel_chooser,
        )
        self.state_manager.add_checkbutton_active(
            self.initrd_check, _("Initrd option disabled"), self.initrd_chooser
        )
        self.state_manager.add_checkbutton_active(
            self.gdb_check,
            _("Kernel debugging disabled"),
            self.gdb_port_spin,
            self.gdb_port_label,
        )

        # usb options
        def usb_check():
            active = self.usb_check.get_active()
            if active and not os.access("/dev/bus/usb", os.W_OK):
                self.usb_check.set_active(False)
                logger.error(usb_access)
                return False
            return active

        usbstate = State()
        tooltip = _("USB disabled or /dev/bus/usb not accessible")
        usbstate.add_control(SensitiveControl(self.bind_button, tooltip))
        usbstate.add_prerequisite(usb_check)
        self.usb_check.connect("toggled", lambda cb: usbstate.check())
        usbstate.check()

        # kvm options
        def _check_kvm():
            if self.kvm_check.get_active():
                supported = tools.check_kvm()
                if not supported:
                    self.kvm_check.set_active(False)
                    logger.error(no_kvm)
                return supported
            return False

        kvmstate = State()
        kvmstate.add_prerequisite(_check_kvm)
        self.kvm_check.connect("toggled", lambda cb: kvmstate.check())
        kvmstate.check()

        # argv0/cpu/machine comboboxes
        exes = qemu.get_executables()
        self.argv0_store.set_data_source(
            map(widgets.ListEntry.from_tuple, exes)
        )
        self.argv0_combo.set_selected_value(self.original.config.argv0)
        self.argv0_combo.set_cell_data_func(
            self.argv0_cell, self.argv0_cell.set_text
        )
        self.cpu_combo.set_cell_data_func(
            self.cpu_cell, self.cpu_cell.set_text
        )
        self.machine_combo.set_cell_data_func(
            self.machine_cell, self.machine_cell.set_text
        )

        # boot/sound/mount comboboxes
        boots = map(widgets.ListEntry.from_tuple, BOOT_DEVICE)
        self.boot_store.set_data_source(boots)
        self.boot_combo.set_selected_value(self.original.config.boot)
        self.boot_combo.set_cell_data_func(
            self.boot_cell, self.boot_cell.set_text
        )
        sounds = map(widgets.ListEntry.from_tuple, SOUND_DEVICE)
        self.sound_store.set_data_source(sounds)
        self.sound_combo.set_selected_value(self.original.config.soundhw)
        self.sound_combo.set_cell_data_func(
            self.sound_cell, self.sound_cell.set_text
        )
        devices = map(widgets.ListEntry.from_tuple, MOUNT_DEVICE)
        self.device_store.set_data_source(devices)
        self.mount_combo.set_selected_value(self.original.config.device)
        self.mount_combo.set_cell_data_func(
            self.mount_cell, self.mount_cell.set_text
        )

        # harddisks
        self.__images_list = ImagesBindingList(gui.factory)
        formatter = ImageFormatter()
        self.images_store.set_data_source(self.__images_list)
        self.hda_combo.set_selected_value(self.original.disk("hda").image)
        self.hda_combo.set_cell_data_func(
            self.hda_cell, self.hda_cell.set_text
        )
        self.hda_cell.set_property("formatter", formatter)
        self.hdb_combo.set_selected_value(self.original.disk("hdb").image)
        self.hdb_combo.set_cell_data_func(
            self.hdb_cell, self.hdb_cell.set_text
        )
        self.hdb_cell.set_property("formatter", formatter)
        self.hdc_combo.set_selected_value(self.original.disk("hdc").image)
        self.hdc_combo.set_cell_data_func(
            self.hdc_cell, self.hdc_cell.set_text
        )
        self.hdc_cell.set_property("formatter", formatter)
        self.hdd_combo.set_selected_value(self.original.disk("hdd").image)
        self.hdd_combo.set_cell_data_func(
            self.hdd_cell, self.hdd_cell.set_text
        )
        self.hdd_cell.set_property("formatter", formatter)
        self.fda_combo.set_selected_value(self.original.disk("fda").image)
        self.fda_combo.set_cell_data_func(
            self.fda_cell, self.fda_cell.set_text
        )
        self.fda_cell.set_property("formatter", formatter)
        self.fdb_combo.set_selected_value(self.original.disk("fdb").image)
        self.fdb_combo.set_cell_data_func(
            self.fdb_cell, self.fdb_cell.set_text
        )
        self.fdb_cell.set_property("formatter", formatter)
        self.mtdblock_combo.set_selected_value(
            self.original.disk("mtdblock").image
        )
        self.mtdblock_cell.set_property("formatter", formatter)
        self.mtdblock_combo.set_cell_data_func(
            self.mtdblock_cell, self.mtdblock_cell.set_text
        )

        cfg = self.original.config
        for pname, wname in self.config_to_widget_mapping:
            getattr(self, wname).set_active(getattr(cfg, pname))
        for pname, wname in self.config_to_spinint_mapping:
            getattr(self, wname).set_value(getattr(cfg, pname))
        for pname, wname in self.config_to_filechooser_mapping:
            if getattr(cfg, pname):
                getattr(self, wname).set_filename(getattr(cfg, pname))
        self.setup_netwoks_cards()
        self.keyboard_entry.set_text(cfg.keyboard)
        self.kernel_options_entry.set_text(cfg.kopt)
        return self.panel

    def configure_brick(self, gui):
        cfg = {}

        # argv0/cpu/machine comboboxes
        cfg["argv0"] = self.argv0_combo.get_selected_value() or ""
        cfg["cpu"] = self.cpu_combo.get_selected_value() or ""
        cfg["machine"] = self.machine_combo.get_selected_value() or ""

        # boot/sound/mount comboboxes
        cfg["boot"] = self.boot_combo.get_selected_value()
        cfg["soundhw"] = self.sound_combo.get_selected_value()
        cfg["device"] = self.mount_combo.get_selected_value()

        # harddisks
        self.original.set_image("hda", self.hda_combo.get_selected_value())
        self.original.set_image("hdb", self.hdb_combo.get_selected_value())
        self.original.set_image("hdc", self.hdc_combo.get_selected_value())
        self.original.set_image("hdd", self.hdd_combo.get_selected_value())
        self.original.set_image("fda", self.fda_combo.get_selected_value())
        self.original.set_image("fdb", self.fdb_combo.get_selected_value())
        self.original.set_image(
            "mtdblock", self.mtdblock_combo.get_selected_value()
        )

        for config_name, widget_name in self.config_to_widget_mapping:
            cfg[config_name] = getattr(self, widget_name).get_active()
        for pname, wname in self.config_to_spinint_mapping:
            cfg[pname] = getattr(self, wname).get_value_as_int()
        for pname, wname in self.config_to_filechooser_mapping:
            filename = getattr(self, wname).get_filename()
            if filename:
                cfg[pname] = filename
        cfg["keyboard"] = self.keyboard_entry.get_text()
        cfg["kopt"] = self.kernel_options_entry.get_text()
        if self.usb_check.get_active():
            devs = list(set(self.usb_devices))
        else:
            devs = []
        cfg["usbdevlist"] = devs
        self.original.update_usbdevlist(devs)
        self.original.set(cfg)

    def __dispose__(self):
        if self.__images_list is not None:
            dispose(self.__images_list)
            self.__images_list = None

    # signals

    def on_newimage_button_clicked(self, button):
        LoadImageDialog(self.gui.brickfactory).show(self.gui.window)

    def on_configimage_button_clicked(self, button):
        DisksLibraryWindow(self.original.factory).show()

    def on_newempty_button_clicked(self, button):
        CreateImageDialog(self.gui, self.gui.brickfactory).show(
            self.gui.window
        )

    def on_argv0_combo_changed(self, combobox):
        arch = self.argv0_combo.get_selected_value()
        if arch:
            cpus = map(widgets.ListEntry.from_tuple, qemu.get_cpus(arch))
            self.cpu_store.set_data_source(cpus)
            machines = map(
                widgets.ListEntry.from_tuple, qemu.get_machines(arch)
            )
            self.machine_store.set_data_source(machines)

    def on_bind_button_clicked(self, button):

        def show_usb_devices_dialog(found_usb_devices):
            dialog = UsbDevDialog(found_usb_devices, self.usb_devices)
            dialog.show(self.gui.window)

        deferred = get_usb_devices()
        deferred.addCallback(show_usb_devices_dialog)
        deferred.addErrback(lambda f: logger.failure(retr_usb, f))
        self.gui.user_wait_action(deferred)

    def _remove_link(self, link):
        # if link.brick.proc and link.hotdel:
        #     # XXX: why checking hotdel? is a method it is always true or raise
        #     # an exception if it is not defined
        #     link.hotdel()
        self.original.remove_plug(link)
        model = self.plugs_store
        itr = model.get_iter_first()
        while itr:
            plug = model.get_value(itr, 0)
            if plug is link:
                model.remove(itr)
                break
            itr = model.iter_next(itr)

    def ask_remove_link(self, link):
        DeleteLinkConfirmDialog(self, link).show(self.gui.window)

    def on_network_cards_view_key_press_event(self, treeview, event):
        if Gdk.keyval_from_name("Delete") == event.keyval:
            link = get_selection(treeview)
            if link is not None:
                self.ask_remove_link(link)
                return True

    def on_network_cards_view_button_release_event(self, treeview, event):
        if event.button == 3:
            link = get_element_at_click(treeview, event)
            if link:
                IMenu(link).popup(event.button, event.time, self, self.gui)
                return True

    def on_addplug_button_clicked(self, button):
        model = self.plugs_store
        AddEthernetDialog(self.gui.brickfactory, self.original, model).show(
            self.gui.window
        )

    def on_setdefaulticon_button_clicked(self, button):
        self.icon_image.set_from_pixbuf(graphics.pixbuf_for_brick_type("qemu"))

    def on_icon_chooser_file_set(self, filechooser):
        raise NotImplementedError(
            "QemuConfigController.on_icon_filechooser_file_set"
        )
