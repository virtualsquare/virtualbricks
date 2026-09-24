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
Preferences dialog.
"""

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gtk

from virtualbricks import log, settings, tools
from virtualbricks._settings import DEFAULT_CONF
from virtualbricks.errors import NoOptionError
from virtualbricks.gui.windows.base import _, _Dialog, destroy_on_exit


_MARKER = object()
logger = log.Logger()

apply_settings = log.Event("Apply settings...")


def settings_get_default(name, default=_MARKER):
    try:
        return settings.get(name)
    except NoOptionError as exc:
        if default is _MARKER:
            try:
                return DEFAULT_CONF[name]
            except KeyError:
                raise exc
        else:
            return default


def combobox_get_active_value(combobox, column, default=None):
    """
    Get current active value in combobox at the given column.

    :type combobox: Gtk.ComboBox
    :type column: int
    :type default: Any
    :rtype: Any
    """

    model = combobox.get_model()
    itr = combobox.get_active_iter()
    if itr:
        obj = model.get_value(itr, column)
        return obj
    else:
        return default


def combobox_set_active_value(combobox, value, column):
    """
    Set the current active value in the ComboBox to value if found.

    :type combobox: Gtk.ComboBox
    :type value: Any
    :type column: int
    :rtype: None
    """

    model = combobox.get_model()
    itr = model.get_iter_first()
    while itr:
        obj = model.get_value(itr, column)
        if obj == value:
            combobox.set_active_iter(itr)
            break
        itr = model.iter_next(itr)


class SettingsDialog(_Dialog):
    """
    The preferences of Virtualbricks: general, VDE and Qemu tabs.
    """

    def __init__(self, virtualbricks_gui):
        """
        :type virtualbricks_gui: virtualbricks.gui.gui.VBGUI
        """

        self._setting_ksm_deferred = None
        self.virtualbricks_gui = virtualbricks_gui
        self.build_ui()
        self.load_settings()

    def build_ui(self) -> None:
        """Create the widgets, formerly in ``settings.ui``."""

        # cowFormatListStore (Gtk.ListStore)
        cow_format_list_store = Gtk.ListStore(str)
        cow_format_list_store.append(["cow"])
        cow_format_list_store.append(["qcow"])
        cow_format_list_store.append(["qcow2"])

        # dialog (Gtk.Dialog)
        self.dialog = Gtk.Dialog(
            width_request=600,
            height_request=400,
            can_focus=False,
            title=_("Virtualbricks Settings"),
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
        button1 = Gtk.Button(
            label=_("Cancel"),
            visible=True,
            can_focus=True,
            receives_default=True,
        )
        self.dialog.add_action_widget(
            button1,
            Gtk.ResponseType.CANCEL,
        )
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
            label=_("OK"),
            visible=True,
            can_focus=True,
            receives_default=True,
            always_show_image=True,
        )
        self.dialog.add_action_widget(
            button2,
            Gtk.ResponseType.OK,
        )
        button2.set_valign(Gtk.Align.FILL)
        action_area.child_set(
            button2,
            pack_type=Gtk.PackType.START,
            expand=True,
            fill=True,
        )
        content_area.child_set(action_area, expand=False, fill=False)
        notebook1 = Gtk.Notebook(visible=True, can_focus=True)
        grid1 = Gtk.Grid(
            visible=True,
            can_focus=False,
            margin_top=4,
            margin_bottom=4,
            row_spacing=4,
            column_spacing=4,
        )
        label1 = Gtk.Label(
            visible=True,
            can_focus=False,
            halign=Gtk.Align.START,
            label=_("X-window terminal command"),
        )
        grid1.attach(label1, 0, 0, 1, 1)
        label2 = Gtk.Label(
            visible=True,
            can_focus=False,
            halign=Gtk.Align.START,
            label=_("X-window sudo command"),
        )
        grid1.attach(label2, 0, 1, 1, 1)
        self.term_entry = Gtk.Entry(visible=True, can_focus=True, hexpand=True)
        grid1.attach(self.term_entry, 1, 0, 1, 1)
        self.sudo_entry = Gtk.Entry(visible=True, can_focus=True, hexpand=True)
        grid1.attach(self.sudo_entry, 1, 1, 1, 1)
        self.systray_switch = Gtk.Switch(
            visible=True,
            can_focus=True,
            halign=Gtk.Align.START,
        )
        grid1.attach(self.systray_switch, 1, 2, 1, 1)
        self.warn_missing_switch = Gtk.Switch(
            visible=True,
            can_focus=True,
            halign=Gtk.Align.START,
        )
        grid1.attach(self.warn_missing_switch, 1, 3, 1, 1)
        label3 = Gtk.Label(
            visible=True,
            can_focus=False,
            halign=Gtk.Align.START,
            label=_("Enable systray"),
        )
        grid1.attach(label3, 0, 2, 1, 1)
        label4 = Gtk.Label(
            visible=True,
            can_focus=False,
            halign=Gtk.Align.START,
            label=_("Warn about missing components at startup"),
        )
        grid1.attach(label4, 0, 3, 1, 1)
        label5 = Gtk.Label(visible=True, can_focus=False, label=_("General"))
        notebook1.append_page(grid1, label5)
        grid2 = Gtk.Grid(
            visible=True,
            can_focus=False,
            margin_top=4,
            margin_bottom=4,
            row_spacing=4,
            column_spacing=4,
        )
        label6 = Gtk.Label(
            visible=True,
            can_focus=False,
            halign=Gtk.Align.START,
            label=_("Binaries path"),
        )
        grid2.attach(label6, 0, 0, 1, 1)
        self.vde_path_chooser = Gtk.FileChooserButton(
            visible=True,
            can_focus=False,
            hexpand=True,
            title="",
        )
        grid2.attach(self.vde_path_chooser, 1, 0, 1, 1)
        label7 = Gtk.Label(
            visible=True,
            can_focus=False,
            halign=Gtk.Align.START,
            label=_("Use python support"),
        )
        grid2.attach(label7, 0, 1, 1, 1)
        self.use_python_switch = Gtk.Switch(
            visible=True,
            can_focus=True,
            halign=Gtk.Align.START,
        )
        grid2.attach(self.use_python_switch, 1, 1, 1, 1)
        self.female_plugs_switch = Gtk.Switch(
            visible=True,
            can_focus=True,
            halign=Gtk.Align.START,
        )
        grid2.attach(self.female_plugs_switch, 1, 2, 1, 1)
        self.loop_detection_switch = Gtk.Switch(
            visible=True,
            can_focus=True,
            halign=Gtk.Align.START,
        )
        grid2.attach(self.loop_detection_switch, 1, 3, 1, 1)
        label8 = Gtk.Label(
            visible=True,
            can_focus=False,
            halign=Gtk.Align.START,
            label=_("Allow female plugs on devices"),
        )
        grid2.attach(label8, 0, 2, 1, 1)
        label9 = Gtk.Label(
            visible=True,
            can_focus=False,
            halign=Gtk.Align.START,
            label=_("Network topology loop detection"),
        )
        grid2.attach(label9, 0, 3, 1, 1)
        label10 = Gtk.Label(visible=True, can_focus=False, label=_("VDE"))
        notebook1.append_page(grid2, label10)
        grid3 = Gtk.Grid(
            width_request=-1,
            visible=True,
            can_focus=False,
            margin_top=4,
            margin_bottom=4,
            row_spacing=4,
            column_spacing=4,
        )
        label11 = Gtk.Label(
            visible=True,
            can_focus=False,
            halign=Gtk.Align.START,
            label=_("Qemu binaries path"),
        )
        grid3.attach(label11, 0, 0, 1, 1)
        label12 = Gtk.Label(
            visible=True,
            can_focus=False,
            halign=Gtk.Align.START,
            label=_("Private COW format"),
        )
        grid3.attach(label12, 0, 1, 1, 1)
        self.cow_format_combo = Gtk.ComboBox(
            visible=True,
            can_focus=False,
            hexpand=True,
            model=cow_format_list_store,
            active=2,
        )
        cell_renderer_text1 = Gtk.CellRendererText()
        self.cow_format_combo.pack_start(cell_renderer_text1, False)
        self.cow_format_combo.add_attribute(cell_renderer_text1, "text", 0)
        grid3.attach(self.cow_format_combo, 1, 1, 1, 1)
        self.qemu_path_chooser = Gtk.FileChooserButton(
            visible=True,
            can_focus=False,
            hexpand=True,
            title="",
        )
        grid3.attach(self.qemu_path_chooser, 1, 0, 1, 1)
        use_kvm_switch = Gtk.Switch(
            visible=True,
            can_focus=True,
            halign=Gtk.Align.START,
        )
        grid3.attach(use_kvm_switch, 1, 2, 1, 1)
        self.enable_ksm_switch = Gtk.Switch(
            visible=True,
            can_focus=True,
            halign=Gtk.Align.START,
        )
        grid3.attach(self.enable_ksm_switch, 1, 3, 1, 1)
        label13 = Gtk.Label(
            visible=True,
            can_focus=False,
            halign=Gtk.Align.START,
            label=_("Use KVM"),
        )
        grid3.attach(label13, 0, 2, 1, 1)
        label14 = Gtk.Label(
            visible=True,
            can_focus=False,
            halign=Gtk.Align.START,
            label=_("Enable KSM"),
        )
        grid3.attach(label14, 0, 3, 1, 1)
        label15 = Gtk.Label(visible=True, can_focus=False, label=_("Qemu"))
        notebook1.append_page(grid3, label15)
        content_area.pack_start(notebook1, True, True, 0)

        # Signals
        self.dialog.connect(
            "delete-event",
            self.on_dialog_delete_event,
        )
        self.dialog.connect(
            "response",
            self.on_dialog_response,
        )
        self.enable_ksm_switch.connect(
            "notify::active",
            self.on_enable_ksm_switch_active_notify,
        )

    def get_root_widget(self) -> Gtk.Dialog:
        return self.dialog

    @destroy_on_exit
    def on_dialog_response(self, dialog, response_id):
        """
        :type dialog: Gtk.Dialog
        :type response_id: Gtk.ResponseType
        """

        if response_id == Gtk.ResponseType.OK:
            self.store_settings()
        return True

    def on_dialog_delete_event(self, dialog, event):
        """
        :type dialog: Gtk.Dialog
        :type event: Gdk.Event
        """

        if self._setting_ksm_deferred is not None:
            # We are setting KSM, prevent the dialog to close.
            return True

    def on_enable_ksm_switch_active_notify(self, switch, param):
        """
        :type button: Gtk.Switch
        :type param: gobject.GParamSpec
        :rtype: bool
        """

        self.toggle_ksm()
        return False

    def toggle_ksm(self):

        def set_ksm_cb(ksm_enabled):
            """
            :type ksm_enabled: bool
            :rtype: None
            """

            self._setting_ksm_deferred = None
            self.enable_ksm_switch.set_sensitive(True)
            if self.enable_ksm_switch.get_active() != ksm_enabled:
                self.enable_ksm_switch.set_active(ksm_enabled)

        if self._setting_ksm_deferred is not None:
            # If we are already setting KSM, do nothing.
            return
        # disable the switch, try to change the value of KSM and reactivate
        # the switch
        self.enable_ksm_switch.set_sensitive(False)
        deferred = tools.set_ksm(enable=self.enable_ksm_switch.get_active())
        deferred.addBoth(set_ksm_cb)
        self._setting_ksm_deferred = deferred

    def load_settings(self):
        # General tab
        self.term_entry.set_text(settings_get_default('term'))
        self.sudo_entry.set_text(settings_get_default('sudo'))
        self.systray_switch.set_active(settings_get_default('systray'))
        self.warn_missing_switch.set_active(settings_get_default('show_missing'))
        # VDE tab
        self.vde_path_chooser.set_current_folder(
            settings_get_default('vdepath'))
        self.use_python_switch.set_active(settings_get_default('python'))
        self.female_plugs_switch.set_active(settings_get_default('femaleplugs'))
        self.loop_detection_switch.set_active(
            settings_get_default('erroronloop'))
        # Qemu tab
        self.qemu_path_chooser.set_current_folder(
            settings_get_default('qemupath'))
        combobox_set_active_value(self.cow_format_combo,
                                  settings_get_default('cowfmt'), 0)
        self.enable_ksm_switch.set_active(settings_get_default('ksm'))

    def store_settings(self):
        logger.debug(apply_settings)
        # General tab
        settings.set('term', self.term_entry.get_text())
        settings.set('sudo', self.sudo_entry.get_text())
        settings.set('systray', self.systray_switch.get_active())
        settings.set('show_missing', self.warn_missing_switch.get_active())
        # VDE tab
        vdepath = self.vde_path_chooser.get_current_folder()
        if vdepath is not None:
            settings.set('vdepath', vdepath)
        settings.set('python', self.use_python_switch.get_active())
        settings.set('femaleplugs', self.female_plugs_switch.get_active())
        settings.set('erroronloop', self.loop_detection_switch.get_active())
        # Qemu tab
        qemupath = self.qemu_path_chooser.get_current_folder()
        if qemupath is not None:
            settings.set('qemupath', qemupath)
        cowfmt = combobox_get_active_value(self.cow_format_combo, 0,
                                           DEFAULT_CONF['cowfmt'])
        settings.set('cowfmt', cowfmt)
        ksm_active = self.enable_ksm_switch.get_active()
        settings.set('ksm', ksm_active)
        tools.set_ksm(ksm_active)
        if self.systray_switch.get_active():
            self.virtualbricks_gui.start_systray()
        else:
            self.virtualbricks_gui.stop_systray()
