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

from virtualbricks import project, tools
from virtualbricks.config import settings
from virtualbricks.gui.windows.base import _, _Dialog, destroy_on_exit

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
    """The per-project settings, of the open project or of new projects."""

    def __init__(self, note):
        self.grid = grid = _grid()
        grid.attach(
            Gtk.Label(visible=True, label=note, xalign=0, wrap=True),
            0,
            0,
            2,
            1,
        )
        self.vdepath_chooser = _folder_chooser()
        self.femaleplugs_switch = _switch()
        self.erroronloop_switch = _switch()
        self.qemupath_chooser = _folder_chooser()
        formats = Gtk.ListStore(str)
        for cow_format in settings.COW_FORMATS:
            formats.append([cow_format])
        self.cowfmt_combo = Gtk.ComboBox(
            visible=True, can_focus=False, hexpand=True, model=formats
        )
        cell = Gtk.CellRendererText()
        self.cowfmt_combo.pack_start(cell, False)
        self.cowfmt_combo.add_attribute(cell, "text", 0)
        rows = (
            (_("VDE binaries path"), self.vdepath_chooser),
            (_("Allow female plugs on devices"), self.femaleplugs_switch),
            (_("Network topology loop detection"), self.erroronloop_switch),
            (_("Qemu binaries path"), self.qemupath_chooser),
            (_("Private COW format"), self.cowfmt_combo),
        )
        for row, (text, widget) in enumerate(rows, 1):
            grid.attach(_label(text), 0, row, 1, 1)
            grid.attach(widget, 1, row, 1, 1)

    def load(self, get):
        self.vdepath_chooser.set_current_folder(get("vdepath"))
        self.femaleplugs_switch.set_active(get("femaleplugs"))
        self.erroronloop_switch.set_active(get("erroronloop"))
        self.qemupath_chooser.set_current_folder(get("qemupath"))
        combobox_set_active_value(self.cowfmt_combo, get("cowfmt"), 0)

    def store(self, set):
        vdepath = self.vdepath_chooser.get_current_folder()
        if vdepath is not None:
            set("vdepath", vdepath)
        set("femaleplugs", self.femaleplugs_switch.get_active())
        set("erroronloop", self.erroronloop_switch.get_active())
        qemupath = self.qemupath_chooser.get_current_folder()
        if qemupath is not None:
            set("qemupath", qemupath)
        cowfmt = combobox_get_active_value(self.cowfmt_combo, 0)
        if cowfmt is not None:
            set("cowfmt", cowfmt)


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
    The preferences: of the application, of the open project and the ones
    new projects start with.
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
                "doesn't change the other projects."
            )
        )
        notebook.append_page(
            self.project_widgets.grid,
            Gtk.Label(visible=True, label=_("This project")),
        )
        self.new_project_widgets = ProjectSettingsWidgets(
            _("A new project starts with these settings.")
        )
        notebook.append_page(
            self.new_project_widgets.grid,
            Gtk.Label(visible=True, label=_("New projects")),
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
        self.term_entry = Gtk.Entry(visible=True, can_focus=True, hexpand=True)
        self.sudo_entry = Gtk.Entry(visible=True, can_focus=True, hexpand=True)
        self.systray_switch = _switch()
        self.warn_missing_switch = _switch()
        self.enable_ksm_switch = _switch()
        rows = (
            (_("X-window terminal command"), self.term_entry),
            (_("X-window sudo command"), self.sudo_entry),
            (_("Enable systray"), self.systray_switch),
            (
                _("Warn about missing components at startup"),
                self.warn_missing_switch,
            ),
            (_("Enable KSM"), self.enable_ksm_switch),
        )
        for row, (text, widget) in enumerate(rows):
            grid.attach(_label(text), 0, row, 1, 1)
            grid.attach(widget, 1, row, 1, 1)
        return grid

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
        self.term_entry.set_text(settings.get_app("term"))
        self.sudo_entry.set_text(settings.get_app("sudo"))
        self.systray_switch.set_active(settings.get_app("systray"))
        self.warn_missing_switch.set_active(settings.get_app("show_missing"))
        self.enable_ksm_switch.set_active(settings.get_app("ksm"))
        self.new_project_widgets.load(settings.get_app)
        if settings.project_settings() is None:
            self.project_widgets.load(settings.get_app)
            self.project_widgets.grid.set_sensitive(False)
        else:
            self.project_widgets.load(settings.get)

    def store_settings(self):
        logger.debug(apply_settings)
        settings.set_app("term", self.term_entry.get_text())
        settings.set_app("sudo", self.sudo_entry.get_text())
        settings.set_app("systray", self.systray_switch.get_active())
        settings.set_app("show_missing", self.warn_missing_switch.get_active())
        self.new_project_widgets.store(settings.set_app)
        if settings.project_settings() is not None:
            self.project_widgets.store(settings.set)
            project.manager.save_current(self.virtualbricks_gui.brickfactory)
        ksm_active = self.enable_ksm_switch.get_active()
        settings.set_app("ksm", ksm_active)
        tools.set_ksm(ksm_active)
        settings.store()
        if self.systray_switch.get_active():
            self.virtualbricks_gui.start_systray()
        else:
            self.virtualbricks_gui.stop_systray()
