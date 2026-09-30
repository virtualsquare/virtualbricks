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

from twisted.logger import Logger

from virtualbricks.config.settings import (
    COW_FORMATS,
    get_setting,
    project_settings,
    set_setting,
    store_settings,
)
from virtualbricks.i18n import _
from virtualbricks.gui.dialogs.base import Window

logger = Logger()

apply_settings = "Apply settings..."


def _grid():
    return Gtk.Grid(
        visible=True,
        can_focus=False,
        margin_top=4,
        margin_bottom=4,
        row_spacing=4,
        column_spacing=4,
    )


def _label(text):
    return Gtk.Label(
        visible=True, can_focus=False, halign=Gtk.Align.START, label=text
    )


def _switch():
    return Gtk.Switch(visible=True, can_focus=True, halign=Gtk.Align.START)


def _folder_chooser():
    return Gtk.FileChooserButton(
        visible=True, can_focus=False, hexpand=True, title=""
    )


class ProjectSettingsWidgets:
    """The settings of the open project."""

    def __init__(self, note):
        self.grid = grid = _grid()
        grid.attach(
            Gtk.Label(visible=True, label=note, xalign=0, wrap=True),
            0,
            0,
            2,
            1,
        )
        self.vde_path_chooser = _folder_chooser()
        self.female_plugs_switch = _switch()
        self.link_loops_switch = _switch()
        self.qemu_path_chooser = _folder_chooser()
        formats = Gtk.ListStore(str)
        for cow_format in COW_FORMATS:
            formats.append([cow_format])
        self.cow_format_combo = Gtk.ComboBox(
            visible=True, can_focus=False, hexpand=True, model=formats
        )
        cell = Gtk.CellRendererText()
        self.cow_format_combo.pack_start(cell, False)
        self.cow_format_combo.add_attribute(cell, "text", 0)
        rows = (
            (_("VDE binaries path"), self.vde_path_chooser),
            (_("Allow female plugs on devices"), self.female_plugs_switch),
            (_("Log an error when links make a loop"), self.link_loops_switch),
            (_("Qemu binaries path"), self.qemu_path_chooser),
            (_("Private COW format"), self.cow_format_combo),
        )
        for row, (text, widget) in enumerate(rows, 1):
            grid.attach(_label(text), 0, row, 1, 1)
            grid.attach(widget, 1, row, 1, 1)

    def load(self, get):
        self.vde_path_chooser.set_current_folder(get("vde_path"))
        self.female_plugs_switch.set_active(get("allow_female_plugs"))
        self.link_loops_switch.set_active(get("log_link_loops"))
        self.qemu_path_chooser.set_current_folder(get("qemu_path"))
        combobox_set_active_value(self.cow_format_combo, get("cow_format"), 0)

    def store(self, set):
        vde_path = self.vde_path_chooser.get_current_folder()
        if vde_path is not None:
            set("vde_path", vde_path)
        set("allow_female_plugs", self.female_plugs_switch.get_active())
        set("log_link_loops", self.link_loops_switch.get_active())
        qemu_path = self.qemu_path_chooser.get_current_folder()
        if qemu_path is not None:
            set("qemu_path", qemu_path)
        cow_format = combobox_get_active_value(self.cow_format_combo, 0)
        if cow_format is not None:
            set("cow_format", cow_format)


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


class SettingsDialog(Window):
    """The preferences: of the application, and of the open project."""

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
        notebook = Gtk.Notebook(visible=True, can_focus=True)
        notebook.append_page(
            self._build_application_page(),
            Gtk.Label(visible=True, label=_("Application")),
        )
        self.project_widgets = ProjectSettingsWidgets(
            _(
                "These settings belong to the open project: changing them "
                "doesn't change the other projects. A new project starts "
                "with a copy of them."
            )
        )
        notebook.append_page(
            self.project_widgets.grid,
            Gtk.Label(visible=True, label=_("This project")),
        )
        content_area.pack_start(notebook, True, True, 0)

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

    def _build_application_page(self):
        grid = _grid()
        self.terminal_entry = Gtk.Entry(
            visible=True, can_focus=True, hexpand=True
        )
        self.tray_icon_switch = _switch()
        self.warn_missing_switch = _switch()
        self.enable_ksm_switch = _switch()
        self.audio_driver_entry = Gtk.Entry(
            visible=True, can_focus=True, hexpand=True
        )
        rows = (
            (_("X-window terminal command"), self.terminal_entry),
            (_("Enable systray"), self.tray_icon_switch),
            (
                _("Warn about missing components at startup"),
                self.warn_missing_switch,
            ),
            (_("Enable KSM"), self.enable_ksm_switch),
            (
                _("Audio driver of QEMU, as alsa, pa or pipewire"),
                self.audio_driver_entry,
            ),
        )
        for row, (text, widget) in enumerate(rows):
            grid.attach(_label(text), 0, row, 1, 1)
            grid.attach(widget, 1, row, 1, 1)
        return grid

    def get_root_widget(self) -> Gtk.Dialog:
        return self.dialog

    def on_dialog_response(self, dialog, response_id):
        """
        :type dialog: Gtk.Dialog
        :type response_id: Gtk.ResponseType
        """

        if response_id == Gtk.ResponseType.OK:
            self.store_settings()
        dialog.destroy()
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
        engine = self.virtualbricks_gui.engine
        deferred = engine.set_ksm(self.enable_ksm_switch.get_active())
        deferred.addBoth(set_ksm_cb)
        self._setting_ksm_deferred = deferred

    def load_settings(self):
        self.terminal_entry.set_text(get_setting("terminal"))
        self.tray_icon_switch.set_active(get_setting("tray_icon"))
        self.warn_missing_switch.set_active(
            get_setting("warn_missing_programs")
        )
        self.enable_ksm_switch.set_active(
            get_setting("kernel_samepage_merging")
        )
        self.audio_driver_entry.set_text(get_setting("audio_driver"))
        # with no project open, the defaults
        self.project_widgets.load(get_setting)
        self.project_widgets.grid.set_sensitive(project_settings() is not None)

    def store_settings(self):
        logger.debug(apply_settings)
        # those of the windows
        set_setting("terminal", self.terminal_entry.get_text())
        set_setting("tray_icon", self.tray_icon_switch.get_active())
        set_setting(
            "warn_missing_programs", self.warn_missing_switch.get_active()
        )
        store_settings()
        # those of the Virtualbricks of the bricks, and of its project,
        # through the engine
        ksm_active = self.enable_ksm_switch.get_active()
        values = {
            "audio_driver": self.audio_driver_entry.get_text().strip(),
            "kernel_samepage_merging": ksm_active,
        }
        if project_settings() is not None:
            self.project_widgets.store(values.__setitem__)
        engine = self.virtualbricks_gui.engine
        engine.set_settings(values)
        engine.set_ksm(ksm_active)
        if self.tray_icon_switch.get_active():
            self.virtualbricks_gui.start_systray()
        else:
            self.virtualbricks_gui.stop_systray()
