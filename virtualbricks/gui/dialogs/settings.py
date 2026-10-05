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

On the machine of the bricks, two pages: Application and This project. Over
a connection, three (page 19 R10): This computer, the settings of these
windows; the machine of the bricks, its KSM and its audio driver, with its
workspace shown; and the project open there, whose folders are paths of
that machine, typed rather than chosen.
"""

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gtk

from twisted.logger import Logger

from virtualbricks.config.settings import (
    get_setting,
    set_setting,
    store_settings,
)
from virtualbricks.i18n import _
from virtualbricks.gui.dialogs.base import Window
from virtualbricks.gui.pathentry import PathCompletion

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


def _attach(grid, row, text, widget):
    """A row of grid: the label, which the screen readers say with widget."""

    label = _label(text)
    label.set_mnemonic_widget(widget)
    grid.attach(label, 0, row, 1, 1)
    grid.attach(widget, 1, row, 1, 1)


def _switch():
    return Gtk.Switch(visible=True, can_focus=True, halign=Gtk.Align.START)


def _folder_chooser():
    return Gtk.FileChooserButton(
        visible=True, can_focus=False, hexpand=True, title=""
    )


class _FolderEntry(Gtk.Entry):
    """
    A folder of another machine, which a file chooser can't show: typed,
    with the folders there to complete it.
    """

    def __init__(self, engine):
        super().__init__(visible=True, can_focus=True, hexpand=True)
        self.completer = PathCompletion(engine, self, folders=True)

    def set_current_folder(self, folder):
        self.set_text(folder)

    def get_current_folder(self):
        return self.get_text().strip() or None


class ProjectSettingsWidgets:
    """The settings of the open project."""

    def __init__(self, note, engine=None):
        if engine is None or engine.local:
            folder = _folder_chooser
        else:
            folder = lambda: _FolderEntry(engine)  # noqa: E731
        self.grid = grid = _grid()
        grid.attach(
            Gtk.Label(visible=True, label=note, xalign=0, wrap=True),
            0,
            0,
            2,
            1,
        )
        self.vde_path_chooser = folder()
        self.female_plugs_switch = _switch()
        self.link_loops_switch = _switch()
        self.qemu_path_chooser = folder()
        rows = (
            (_("VDE binaries path"), self.vde_path_chooser),
            (_("Allow female plugs on devices"), self.female_plugs_switch),
            (_("Log an error when links make a loop"), self.link_loops_switch),
            (_("Qemu binaries path"), self.qemu_path_chooser),
        )
        for row, (text, widget) in enumerate(rows, 1):
            _attach(grid, row, text, widget)

    def load(self, get):
        self.vde_path_chooser.set_current_folder(get("vde_path"))
        self.female_plugs_switch.set_active(get("allow_female_plugs"))
        self.link_loops_switch.set_active(get("log_link_loops"))
        self.qemu_path_chooser.set_current_folder(get("qemu_path"))

    def store(self, set):
        vde_path = self.vde_path_chooser.get_current_folder()
        if vde_path is not None:
            set("vde_path", vde_path)
        set("allow_female_plugs", self.female_plugs_switch.get_active())
        set("log_link_loops", self.link_loops_switch.get_active())
        qemu_path = self.qemu_path_chooser.get_current_folder()
        if qemu_path is not None:
            set("qemu_path", qemu_path)


class SettingsDialog(Window):
    """The preferences: of the application, and of the open project."""

    def __init__(self, virtualbricks_gui):
        """
        :type virtualbricks_gui: virtualbricks.gui.gui.VBGUI
        """

        self._setting_ksm_deferred = None
        self.virtualbricks_gui = virtualbricks_gui
        # the settings of the machine of the bricks and of its project go
        # through it
        self.engine = virtualbricks_gui.engine
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
        this_computer = self._build_this_computer_page()
        if self.engine.local:
            # one page: the windows and the bricks are on this computer
            self._build_machine_page(this_computer)
            notebook.append_page(
                this_computer, Gtk.Label(visible=True, label=_("Application"))
            )
        else:
            notebook.append_page(
                this_computer,
                Gtk.Label(visible=True, label=_("This computer")),
            )
            notebook.append_page(
                self._build_machine_page(_grid()),
                Gtk.Label(visible=True, label=self.engine.where),
            )
        self.project_widgets = ProjectSettingsWidgets(
            _(
                "These settings belong to the open project: changing them "
                "doesn't change the other projects. A new project starts "
                "with a copy of them."
            ),
            self.engine,
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

    def _build_this_computer_page(self):
        """The settings of the windows."""

        grid = _grid()
        self.terminal_entry = Gtk.Entry(
            visible=True, can_focus=True, hexpand=True
        )
        self.tray_icon_switch = _switch()
        self.warn_missing_switch = _switch()
        rows = (
            (_("X-window terminal command"), self.terminal_entry),
            (_("Enable systray"), self.tray_icon_switch),
            (
                _("Warn about missing components at startup"),
                self.warn_missing_switch,
            ),
        )
        for row, (text, widget) in enumerate(rows):
            _attach(grid, row, text, widget)
        return grid

    def _build_machine_page(self, grid):
        """The settings of the machine of the bricks, under those in grid."""

        first = len(grid.get_children()) // 2
        self.enable_ksm_switch = _switch()
        self.audio_driver_entry = Gtk.Entry(
            visible=True, can_focus=True, hexpand=True
        )
        rows = [
            (_("Enable KSM"), self.enable_ksm_switch),
            (
                _("Audio driver of QEMU, as alsa, pa or pipewire"),
                self.audio_driver_entry,
            ),
        ]
        self.workspace_label = None
        if not self.engine.local:
            # shown, not changed: its command line chose it
            self.workspace_label = _label(self.engine.workspace.path)
            self.workspace_label.set_selectable(True)
            rows.append((_("Workspace"), self.workspace_label))
        for row, (text, widget) in enumerate(rows, first):
            _attach(grid, row, text, widget)
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
        deferred = self.engine.set_ksm(self.enable_ksm_switch.get_active())
        deferred.addBoth(set_ksm_cb)
        self._setting_ksm_deferred = deferred

    def load_settings(self):
        # those of the windows, of this computer
        self.terminal_entry.set_text(get_setting("terminal"))
        self.tray_icon_switch.set_active(get_setting("tray_icon"))
        self.warn_missing_switch.set_active(
            get_setting("warn_missing_programs")
        )
        # those of the machine of the bricks and of its project
        machine = self.engine.machine
        self.enable_ksm_switch.set_active(
            machine.setting("kernel_samepage_merging")
        )
        self.audio_driver_entry.set_text(machine.setting("audio_driver"))
        # with no project open, the defaults
        self.project_widgets.load(machine.setting)
        self.project_widgets.grid.set_sensitive(self.project_open())

    def project_open(self) -> bool:
        return self.engine.workspace.current is not None

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
        if self.project_open():
            self.project_widgets.store(values.__setitem__)
        engine = self.engine
        engine.set_settings(values)
        engine.set_ksm(ksm_active)
        if self.tray_icon_switch.get_active():
            self.virtualbricks_gui.start_systray()
        else:
            self.virtualbricks_gui.stop_systray()
