# -*- test-case-name: virtualbricks.tests.gui.mainwindow.test_window -*-
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
The main window of Virtualbricks.

``VBGUI`` builds its UI in ``build_ui()``: the menus, the status icon, and
a notebook with the tabs of the other modules of this package, which it
tells when a project opens, is saved, or Virtualbricks quits (see
:mod:`virtualbricks.gui.mainwindow.tab`). It keeps what the menus of the
bricks and the events call: configure, start or stop, remove.
"""

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gtk
from twisted.internet import defer, task
from twisted.logger import Logger

from virtualbricks import errors, ksm
from virtualbricks.bricks.event import is_event
from virtualbricks.bricks.virtualmachine import is_disk_image
from virtualbricks.config.settings import get_setting, set_setting
from virtualbricks.config.workspace import projects
from virtualbricks.programs import missing_programs
from virtualbricks.tools import is_running
from virtualbricks.i18n import _
from virtualbricks.gui.graphics import load_pixbuf
from virtualbricks.gui.dialogs.about import AboutDialog
from virtualbricks.gui.dialogs.confirmdialog import (
    DeleteBrickConfirmDialog,
    DeleteEventConfirmDialog,
)
from virtualbricks.gui.dialogs.exportproject import ExportProjectDialog
from virtualbricks.gui.dialogs.imagedialogs import RemoveImageDialog
from virtualbricks.gui.dialogs.importdialog import ImportDialog
from virtualbricks.gui.messages import MessageLog
from virtualbricks.gui.mainwindow.bricks import BricksTab
from virtualbricks.gui.mainwindow.events import EventsTab
from virtualbricks.gui.mainwindow.images import ImagesTab
from virtualbricks.gui.mainwindow.readme import ReadmeTab
from virtualbricks.gui.mainwindow.tab import switch, tabs
from virtualbricks.gui.mainwindow.topology import TopologyTab
from virtualbricks.gui.dialogs.logging import LoggingWindow
from virtualbricks.gui.dialogs import projectname
from virtualbricks.gui.dialogs.projects import ProjectsWindow
from virtualbricks.gui.dialogs.settings import SettingsDialog

logger = Logger()
cannot_open_project = 'Cannot open the project "{name}": {error}'
# The projects in Open Recent.
RECENT = 8

start_virtualbricks = "Starting VirtualBricks"
components_not_found = (
    "{text}\nYou can disable this alert from the general settings."
)
ksm_not_found = (
    "KSM not found in Linux. Samepage memory will not work on this system."
)
programs_not_found = (
    "Some programs of the bricks are missing, each with the package that has"
    " it: {programs}. Some bricks won't start."
)
stop_error = "Error on stopping brick."
start_error = "Error on starting brick."


class Freezer:
    """
    Show a window with a pulsing progress bar and make the parent window
    insensitive until an operation completes.
    """

    def __init__(self, freeze, unfreeze, parent):
        """
        :type freeze: Callable
        :type unfreeze: Callable
        :type parent: Optional[Gtk.Window]
        """

        self.freeze_parent_window = freeze
        self.unfreeze_parent_window = unfreeze
        self.build_ui()
        self.window.set_transient_for(parent)
        self.window.set_modal(True)

    def build_ui(self) -> None:
        """Create the widgets, formerly in ``userwait.ui``."""

        # window (Gtk.Window)
        self.window = Gtk.Window(
            width_request=200,
            height_request=50,
            can_focus=False,
            title=_("Virtualbricks: action in progress"),
            window_position=Gtk.WindowPosition.CENTER_ALWAYS,
            destroy_with_parent=True,
            type_hint=Gdk.WindowTypeHint.NOTIFICATION,
            skip_taskbar_hint=True,
            skip_pager_hint=True,
            urgency_hint=True,
            decorated=False,
            deletable=False,
        )
        vbox1 = Gtk.Box(
            visible=True,
            can_focus=False,
            orientation=Gtk.Orientation.VERTICAL,
        )
        Pleaselabel = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("Please wait"),
        )
        vbox1.pack_start(Pleaselabel, True, True, 0)
        self.progress = Gtk.ProgressBar(visible=True, can_focus=False)
        vbox1.pack_start(self.progress, False, False, 0)
        label2 = Gtk.Label(visible=True, can_focus=False)
        vbox1.pack_start(label2, True, True, 0)
        self.window.add(vbox1)

    def wait_for(self, deferred, *args):
        """
        :type deferred: Union[twisted.internet.defer.Deferred[Any], Callable]
        :type args: Tuple[Any]
        :rtype: twisted.internet.defer.Deferred[Any]
        """

        if not isinstance(deferred, defer.Deferred):
            if callable(deferred):
                deferred = defer.maybeDeferred(deferred, *args)
            else:
                raise RuntimeError("Invalid argument")
        pulse = self.start()
        deferred.addBoth(self.stop, pulse)
        return deferred

    def start(self):
        """
        :rtype: twisted.internet.task.LoopingCall
        """

        self.freeze_parent_window()
        self.window.show_all()
        looping_call = task.LoopingCall(self.progress.pulse)
        looping_call.start(0.2, False)
        return looping_call

    def stop(self, passthru, looping_call):
        """
        :type passthru: Any
        :type looping_call: twisted.internet.task.LoopingCall
        :rtype: Any
        """

        looping_call.stop()
        self.window.destroy()
        self.unfreeze_parent_window()
        return passthru


class ProgressBar:
    """
    Wait for an operation, freezing the main window.
    """

    def __init__(self, gui):
        self.freezer = Freezer(
            gui.set_insensitive, gui.set_sensitive, gui.window
        )

    def wait_for(self, something, *args):
        return self.freezer.wait_for(something, *args)


class VBGUI:
    """
    The main GUI object for virtualbricks, containing all the configuration for
    the widgets and the connections to the main engine.
    """

    def __init__(self, factory, messages=None):
        self.factory = self.brickfactory = factory
        self.build_ui()
        # the messages of this run, see virtualbricks.gui.messages
        self.messages = MessageLog() if messages is None else messages

        logger.info(start_virtualbricks)
        if get_setting("tray_icon"):
            self.start_systray()

        # attach the quit callback at the end, so it is not called if an
        # exception is raised before because of a syntax error of another kind
        # of error
        factory.connect("quit", self.on_quit)

        # Show the main window
        self.window.show()

    def build_ui(self) -> None:
        """Create the widgets, formerly in ``virtualbricks.ui``."""

        # window (Gtk.Window)
        # Glade image "virtualbricks.png" (virtualbricks/gui/data)
        self.window = Gtk.Window(
            width_request=800,
            height_request=600,
            can_focus=False,
            border_width=2,
            title=_("Virtualbricks"),
            window_position=Gtk.WindowPosition.CENTER,
            default_width=850,
            default_height=600,
            icon=load_pixbuf("virtualbricks.png"),
        )
        vbox1 = Gtk.Box(
            visible=True,
            can_focus=False,
            orientation=Gtk.Orientation.VERTICAL,
        )
        menubar1 = Gtk.MenuBar(visible=True, can_focus=False)

        def menu(label):
            """A menu of the bar, empty."""

            top = Gtk.MenuItem(
                visible=True, can_focus=False, label=label, use_underline=True
            )
            submenu = Gtk.Menu(visible=True, can_focus=False)
            top.set_submenu(submenu)
            menubar1.append(top)
            return top, submenu

        def item(submenu, label):
            menu_item = Gtk.MenuItem(
                visible=True, label=label, use_underline=True
            )
            submenu.append(menu_item)
            return menu_item

        def separator(submenu):
            submenu.append(Gtk.SeparatorMenuItem(visible=True))

        # File: what isn't a project's
        file_menu = menu(_("_File"))[1]
        file_settings_item = item(file_menu, _("_Settings"))
        file_logs_item = item(file_menu, _("_Logs"))
        separator(file_menu)
        file_quit_item = item(file_menu, _("_Quit"))

        # Projects
        menu_projects, projects_menu = menu(_("_Projects"))
        projects_open_item = item(projects_menu, _("_Projects…"))
        projects_open_item.set_tooltip_text(
            _("See, open, rename, duplicate, export and remove your projects")
        )
        projects_new_item = item(projects_menu, _("_New Project…"))
        projects_recent_item = item(projects_menu, _("Open _Recent"))
        self.recent_menu = Gtk.Menu(visible=True)
        projects_recent_item.set_submenu(self.recent_menu)
        self.projects_recent_item = projects_recent_item
        separator(projects_menu)
        projects_save_item = item(projects_menu, _("_Save"))
        projects_duplicate_item = item(projects_menu, _("_Duplicate…"))
        projects_rename_item = item(projects_menu, _("Re_name…"))
        separator(projects_menu)
        projects_import_item = item(projects_menu, _("_Import…"))
        projects_export_item = item(projects_menu, _("E_xport…"))
        menu_projects.connect("activate", self.on_projects_menu_activate)

        menu_help = Gtk.MenuItem(
            visible=True,
            can_focus=False,
            label=_("_Help"),
            use_underline=True,
        )
        menu5 = Gtk.Menu(visible=True, can_focus=False)
        help_about_item = Gtk.ImageMenuItem(
            label="gtk-about",
            visible=True,
            can_focus=False,
            use_underline=True,
            use_stock=True,
        )
        menu5.append(help_about_item)
        menu_help.set_submenu(menu5)
        menubar1.append(menu_help)
        vbox1.pack_start(menubar1, False, False, 0)
        self.main_notebook = Gtk.Notebook(visible=True, can_focus=True)
        self.bricks = BricksTab(self, self.factory)
        self.append_tab(self.bricks)
        self.events = EventsTab(self, self.factory)
        self.append_tab(self.events)
        self.images = ImagesTab(self, self.factory)
        self.append_tab(self.images)
        self.append_tab(TopologyTab(self, self.factory))
        self.append_tab(ReadmeTab())
        vbox1.pack_start(self.main_notebook, True, True, 0)
        self.window.add(vbox1)

        # systray_menu (Gtk.Menu)
        self.systray_menu = Gtk.Menu(visible=True, can_focus=False)
        systray_toggle_item = Gtk.MenuItem(
            visible=True,
            can_focus=False,
            label=_("Toggle window"),
            use_underline=True,
        )
        self.systray_menu.append(systray_toggle_item)
        separatormenuitem4 = Gtk.SeparatorMenuItem(
            visible=True,
            can_focus=False,
        )
        self.systray_menu.append(separatormenuitem4)
        systray_close_item = Gtk.MenuItem(
            visible=True,
            can_focus=False,
            label=_("Close"),
            use_underline=True,
        )
        self.systray_menu.append(systray_close_item)

        # status_icon (Gtk.StatusIcon)
        # Glade image "virtualbricks.png" (virtualbricks/gui/data)
        self.status_icon = Gtk.StatusIcon(
            pixbuf=load_pixbuf("virtualbricks.png"),
            has_tooltip=True,
            tooltip_text=_("Virtualbricks visible"),
        )

        # Need the complete widget tree:
        # accelerators.
        accel_group = Gtk.AccelGroup()
        self.window.add_accel_group(accel_group)
        projects_new_item.add_accelerator(
            "activate",
            accel_group,
            Gdk.KEY_n,
            Gdk.ModifierType.CONTROL_MASK,
            Gtk.AccelFlags.VISIBLE,
        )
        projects_open_item.add_accelerator(
            "activate",
            accel_group,
            Gdk.KEY_o,
            Gdk.ModifierType.CONTROL_MASK,
            Gtk.AccelFlags.VISIBLE,
        )
        projects_save_item.add_accelerator(
            "activate",
            accel_group,
            Gdk.KEY_s,
            Gdk.ModifierType.CONTROL_MASK,
            Gtk.AccelFlags.VISIBLE,
        )
        file_quit_item.add_accelerator(
            "activate",
            accel_group,
            Gdk.KEY_q,
            Gdk.ModifierType.CONTROL_MASK,
            Gtk.AccelFlags.VISIBLE,
        )
        file_settings_item.add_accelerator(
            "activate",
            accel_group,
            Gdk.KEY_p,
            Gdk.ModifierType.CONTROL_MASK,
            Gtk.AccelFlags.VISIBLE,
        )
        help_about_item.add_accelerator(
            "activate",
            accel_group,
            Gdk.KEY_F1,
            0,
            Gtk.AccelFlags.VISIBLE,
        )

        # Signals
        self.window.connect("delete-event", self.on_window_delete_event)
        self.window.connect("destroy", self.do_quit)
        projects_new_item.connect(
            "activate", self.on_projects_new_item_activate
        )
        projects_open_item.connect(
            "activate", self.on_projects_open_item_activate
        )
        projects_rename_item.connect(
            "activate",
            self.on_projects_rename_item_activate,
        )
        projects_save_item.connect(
            "activate", self.on_projects_save_item_activate
        )
        projects_duplicate_item.connect(
            "activate",
            self.on_projects_duplicate_item_activate,
        )
        projects_import_item.connect(
            "activate",
            self.on_projects_import_item_activate,
        )
        projects_export_item.connect(
            "activate",
            self.on_projects_export_item_activate,
        )
        file_quit_item.connect("activate", self.do_quit)
        file_settings_item.connect(
            "activate", self.on_file_settings_item_activate
        )
        file_logs_item.connect("activate", self.on_file_logs_item_activate)
        help_about_item.connect("activate", self.on_help_about_item_activate)
        self.main_notebook.connect(
            "switch-page",
            self.on_main_notebook_switch_page,
        )
        systray_toggle_item.connect(
            "activate",
            self.on_systray_toggle_item_activate,
        )
        systray_close_item.connect("activate", self.do_quit)
        self.status_icon.connect("activate", self.on_status_icon_activate)
        self.status_icon.connect("popup-menu", self.on_status_icon_popup_menu)

    def append_tab(self, tab) -> None:
        label = Gtk.Label(visible=True, label=tab.title, use_underline=True)
        self.main_notebook.append_page(tab, label)

    def get_root_widget(self) -> Gtk.Window:
        return self.window

    def check_prerequisites(self):
        """Say which programs are missing, and the packages that have them."""

        lines = []
        if not ksm.check_ksm():
            set_setting("kernel_samepage_merging", False)
            lines.append(ksm_not_found)
        missing = missing_programs(
            get_setting("vde_path"), get_setting("qemu_path")
        )
        if missing:
            names = ", ".join(map(str, missing))
            lines.append(programs_not_found.format(programs=names))
        if lines and get_setting("warn_missing_programs"):
            logger.error(components_not_found, text="\n".join(lines))

    """ ********************************************************     """
    """ Signal handlers                                           """
    """ ********************************************************     """

    def curtain_down(self):
        """
        Close the settings that show, in the tab that shows them: their OK
        and Cancel are there.
        """

        page = self.main_notebook.get_nth_page(
            self.main_notebook.get_current_page()
        )
        if page in (self.bricks, self.events, self.images):
            page.close_settings()

    def curtain_up(self, item):
        """
        Show the settings of a brick in the Bricks tab, of an event in the
        Events tab, or the details of a disk image in the Images tab.
        """

        # an image has no type: ask it first
        if is_disk_image(item):
            tab = self.images
        elif is_event(item):
            tab = self.events
        else:
            tab = self.bricks
        self.main_notebook.set_current_page(self.main_notebook.page_num(tab))
        tab.configure(item)

    def set_title(self):
        if projects.current:
            name = projects.current.name
            title = _("Virtualbricks (project: {0})").format(name)
            self.window.set_title(title)

    """ ******************************************************** """
    """                                                          """
    """ EVENTS / SIGNALS                                         """
    """                                                          """
    """                                                          """
    """ ******************************************************** """

    # Notebook signals

    def on_main_notebook_switch_page(self, notebook, page, page_num):
        switch(notebook, page)
        return True

    # gui (programming) interface

    def on_quit(self, factory):
        for tab in tabs(self.main_notebook):
            tab.on_quit()

    def on_save(self):
        for tab in tabs(self.main_notebook):
            tab.on_save()
        projects.save(self.brickfactory)

    def on_open(self, name):
        self.on_save()
        report = projects.open(name, self.brickfactory)
        for tab in tabs(self.main_notebook):
            tab.on_open()
        self.set_title()
        return report

    def on_new(self, name, description=""):
        self.on_save()
        projects.create(name, description)
        projects.open(name, self.brickfactory)
        for tab in tabs(self.main_notebook):
            tab.on_open()
        self.set_title()

    def do_quit(self, *_):
        self.factory.quit()
        return True

    # end gui (programming) interface

    def on_window_delete_event(self, window, event):
        # don't delete; hide instead
        if get_setting("tray_icon"):
            window.hide()
            self.status_icon.set_tooltip("Virtualbricks Hidden")
            return True

    def ask_remove_brick(self, brick):
        DeleteBrickConfirmDialog(self.brickfactory, brick).show(self.window)

    def ask_remove_event(self, event):
        DeleteEventConfirmDialog(self.brickfactory, event).show(self.window)

    def ask_remove_image(self, image):
        RemoveImageDialog(self.brickfactory, image).show(self.window)

    def show_images(self):
        """Show the Images tab."""

        self.main_notebook.set_current_page(
            self.main_notebook.page_num(self.images)
        )

    # status icon handling

    def start_systray(self):
        if not self.status_icon.get_visible():
            self.status_icon.set_visible(True)

    def stop_systray(self):
        if self.status_icon.get_visible():
            self.status_icon.set_visible(False)

    def window_toggle(self):
        if self.window.get_visible():
            self.window.hide()
            self.status_icon.set_tooltip(_("Virtualbricks hidden"))
        else:
            self.window.show()
            self.status_icon.set_tooltip(_("Virtualbricks visible"))

    def on_status_icon_activate(self, statusicon):
        self.window_toggle()

    def on_status_icon_popup_menu(self, statusicon, button, time):
        if button == 3:
            self.systray_menu.popup(None, None, None, button, time)

    def on_systray_toggle_item_activate(self, menuitem):
        self.window_toggle()

    # menu items signals

    def on_projects_new_item_activate(self, menuitem):
        self.project_name_dialog(projectname.NEW)
        return True

    def on_projects_open_item_activate(self, menuitem):
        self.show_projects()
        return True

    def on_projects_menu_activate(self, menuitem):
        """Fill Open Recent with the projects used last."""

        for child in self.recent_menu.get_children():
            self.recent_menu.remove(child)
        current = projects.current.name if projects.current else None
        recent = [
            summary
            for summary in projects.summaries()
            if summary.name != current and summary.problem is None
        ][:RECENT]
        for summary in recent:
            recent_item = Gtk.MenuItem(visible=True, label=summary.name)
            recent_item.connect(
                "activate", self.on_recent_item_activate, summary.name
            )
            self.recent_menu.append(recent_item)
        self.projects_recent_item.set_sensitive(bool(recent))

    def on_recent_item_activate(self, menuitem, name):
        try:
            self.on_open(name)
        except (OSError, errors.Error) as exc:
            logger.error(cannot_open_project, name=name, error=exc)
        return True

    def on_projects_rename_item_activate(self, menuitem):
        self.project_name_dialog(projectname.RENAME, projects.current.name)
        return True

    def on_projects_save_item_activate(self, menuitem):
        self.on_save()
        return True

    def on_projects_duplicate_item_activate(self, menuitem):
        self.project_name_dialog(projectname.DUPLICATE, projects.current.name)
        return True

    def on_projects_import_item_activate(self, menuitem):
        self.import_project()
        return True

    def on_projects_export_item_activate(self, menuitem):
        self.export_project(None)
        return True

    # The projects, for the Projects window and the name dialog

    def show_projects(self, problem=None):
        window = ProjectsWindow(self)
        if problem is not None:
            window.show_problem(problem)
        window.show(self.window)
        return window

    def show_start_up_problem(self, message):
        """The last project can't be opened: choose one in Projects."""

        window = self.show_projects(problem=message)

        def closed(widget):
            # closed without opening a project: the last one, or a new one
            if projects.current is None:
                projects.restore_last(self.brickfactory)
                self.set_title()

        window.get_root_widget().connect("destroy", closed)
        return window

    def project_name_dialog(self, kind, original=None):
        dialog = projectname.ProjectNameDialog(self, kind, original)
        dialog.show(self.window)
        return dialog

    def import_project(self, on_closed=None):
        """Import a project; on_closed is called when the window closes."""

        dialog = ImportDialog(self.brickfactory)

        def destroyed(window):
            self.set_title()
            if on_closed is not None:
                on_closed()

        dialog.show(self.window)
        dialog.get_root_widget().connect("destroy", destroyed)
        return dialog

    def export_project(self, summary, parent=None):
        """Export a project, the open one if summary is None."""

        if summary is None or (
            projects.current and summary.name == projects.current.name
        ):
            self.on_save()
            path = projects.current.path
            images = [
                (image.name, image.path)
                for image in self.brickfactory.iter_disk_images()
            ]
        else:
            path = summary.path
            images = [(image.name, image.path) for image in summary.images]
        dialog = ExportProjectDialog(path, images)
        dialog.show(parent or self.window)

    def on_file_settings_item_activate(self, menuitem):
        SettingsDialog(self).show(self.window)
        return True

    def on_file_logs_item_activate(self, menuitem):
        LoggingWindow(self.messages).show()
        return True

    def on_help_about_item_activate(self, menuitem):
        dialog = AboutDialog()
        dialog.show(self.window)
        return True

    # What the menus and the lists of the bricks call

    def startstop_brick(self, brick):
        if is_running(brick):
            brick.poweroff().addErrback(
                lambda f: logger.failure(stop_error, f)
            )
        else:
            brick.poweron().addErrback(
                lambda f: logger.failure(start_error, f)
            )

    def user_wait_action(self, action, *args):
        ProgressBar(self).wait_for(action, *args)

    def set_insensitive(self):
        self.window.set_sensitive(False)

    def set_sensitive(self):
        self.window.set_sensitive(True)
