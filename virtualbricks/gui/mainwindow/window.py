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
bricks and the events call: configure and remove. What the windows change,
run or ask of the machine goes through its engine, ``engine``, and they
read the bricks, the events and the images of ``engine.factory``.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, TypeVar

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gtk
from twisted.internet import defer, task
from twisted.logger import Logger
from twisted.python.failure import Failure

from virtualbricks import errors, ksm
from virtualbricks.brickfactory import BrickFactory
from virtualbricks.bricks import Brick
from virtualbricks.config.report import Report
from virtualbricks.engine import Engine
from virtualbricks.locations import short_path
from virtualbricks.bricks.event import Event, is_event
from virtualbricks.bricks.virtualmachine import Image, is_disk_image
from virtualbricks.config.settings import get_setting, ksm_started
from virtualbricks.config.workspace import ProjectSummary, projects
from virtualbricks.programs import missing_programs
from virtualbricks.i18n import _
from virtualbricks.gui.graphics import load_pixbuf
from virtualbricks.gui.dialogs.about import AboutDialog
from virtualbricks.gui.dialogs.deletedialog import DeleteDialog
from virtualbricks.gui.dialogs.exportproject import ExportProjectDialog
from virtualbricks.gui.dialogs.imagedialogs import RemoveImageDialog
from virtualbricks.gui.dialogs.importdialog import ImportDialog
from virtualbricks.gui.messages import MessageLog
from virtualbricks.gui.mainwindow.bricks import BricksTab
from virtualbricks.gui.mainwindow.events import EventsTab
from virtualbricks.gui.mainwindow.images import ImagesTab
from virtualbricks.gui.mainwindow.readme import ReadmeTab
from virtualbricks.gui.mainwindow.tab import Tab, switch, tabs
from virtualbricks.gui.mainwindow.topology import TopologyTab
from virtualbricks.gui.dialogs.logging import LoggingWindow
from virtualbricks.gui.dialogs import projectname
from virtualbricks.gui.dialogs.projects import ProjectsWindow
from virtualbricks.gui.dialogs.settings import SettingsWindow

if TYPE_CHECKING:  # pragma: no cover
    from virtualbricks.gui.mainwindow.rowtab import RowsTab
    from virtualbricks.remote.client import RemoteEngine
    from virtualbricks.remote.follower import Item

T = TypeVar("T")
ItemT = TypeVar("ItemT", bound="Brick | Event | Image")

logger = Logger()
cannot_open_project = 'Cannot open the project "{name}": {error}'
# The projects in Open Recent.
RECENT = 8

start_virtualbricks = "Starting VirtualBricks"
components_not_found = (
    "{text}\nThe Settings window turns this alert off: Missing programs, on"
    " its page This computer."
)
ksm_not_found = (
    "The settings ask for KSM, which this Linux doesn't have: the machines"
    " can't share memory."
)
ksm_still_off = (
    "The settings ask for KSM, which is still off: Virtualbricks couldn't"
    " turn it on."
)
programs_not_found = (
    "Some programs of the bricks are missing, each with the package that has"
    " it: {programs}. Some bricks won't start."
)
quit_refused = "{error}"
# the answers of the bar of a connection lost
RECONNECT = 1
QUIT = 2


def ksm_warning(wanted: bool, available: bool, running: bool) -> str | None:
    """
    What the warning at start says of KSM: nothing unless the settings ask
    for it (wanted); then whether this Linux has it, and whether it runs.
    """

    if not wanted:
        return None
    if not available:
        return ksm_not_found
    if not running:
        return ksm_still_off
    return None


def remote_title(engine: RemoteEngine) -> str:
    """The title of the windows of another Virtualbricks: its project."""

    copy = engine.factory
    if copy.project is None:
        return _("Virtualbricks on {where}").format(where=engine.where)
    workspace = copy.machine.get("workspace")
    if workspace and workspace != copy.settings.get("workspace", workspace):
        # not the workspace of its setting: another beside it may be
        return _(
            "Virtualbricks (project: {name}, workspace: {workspace} on"
            " {where})"
        ).format(name=copy.project, workspace=workspace, where=engine.where)
    return _("Virtualbricks (project: {name} on {where})").format(
        name=copy.project, where=engine.where
    )


class Freezer:
    """
    Show a window with a pulsing progress bar and make the parent window
    insensitive until an operation completes.
    """

    def __init__(
        self,
        freeze: Callable[[], None],
        unfreeze: Callable[[], None],
        parent: Gtk.Window | None,
    ) -> None:
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

    def wait_for(
        self,
        deferred: defer.Deferred[Any] | Callable[..., Any],
        *args: Any,
    ) -> defer.Deferred[Any]:
        if not isinstance(deferred, defer.Deferred):
            if callable(deferred):
                deferred = defer.maybeDeferred(deferred, *args)
            else:
                raise RuntimeError("Invalid argument")
        pulse = self.start()
        deferred.addBoth(self.stop, pulse)
        return deferred

    def start(self) -> task.LoopingCall:
        self.freeze_parent_window()
        self.window.show_all()
        looping_call = task.LoopingCall(self.progress.pulse)
        looping_call.start(0.2, False)
        return looping_call

    def stop(self, passthru: T, looping_call: task.LoopingCall) -> T:
        looping_call.stop()
        self.window.destroy()
        self.unfreeze_parent_window()
        return passthru


class ProgressBar:
    """
    Wait for an operation, freezing the main window.
    """

    def __init__(self, gui: VBGUI) -> None:
        self.freezer = Freezer(
            gui.set_insensitive, gui.set_sensitive, gui.window
        )

    def wait_for(
        self, something: defer.Deferred[Any] | Callable[..., Any], *args: Any
    ) -> defer.Deferred[Any]:
        return self.freezer.wait_for(something, *args)


class VBGUI:
    """
    The main GUI object for virtualbricks, containing all the configuration for
    the widgets and the connections to the main engine.
    """

    def __init__(
        self, engine: Engine, messages: MessageLog | None = None
    ) -> None:
        # what the windows call, and what they read
        self.engine = engine
        self.factory = self.brickfactory = factory = engine.factory
        self.build_ui()
        # the messages of this run, see virtualbricks.gui.messages
        self.messages = MessageLog() if messages is None else messages

        logger.info(start_virtualbricks)
        if get_setting("tray_icon"):
            self.start_systray()

        # attach the quit callback at the end, so it is not called if an
        # exception is raised before because of a syntax error of another kind
        # of error
        factory.quitting.connect(self.on_quit)

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

        def menu(label: str) -> tuple[Gtk.MenuItem, Gtk.Menu]:
            """A menu of the bar, empty."""

            top = Gtk.MenuItem(
                visible=True, can_focus=False, label=label, use_underline=True
            )
            submenu = Gtk.Menu(visible=True, can_focus=False)
            top.set_submenu(submenu)
            menubar1.append(top)
            return top, submenu

        def item(submenu: Gtk.Menu, label: str) -> Gtk.MenuItem:
            menu_item = Gtk.MenuItem(
                visible=True, label=label, use_underline=True
            )
            submenu.append(menu_item)
            return menu_item

        def separator(submenu: Gtk.Menu) -> None:
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
        self.import_item = projects_import_item
        self.export_item = projects_export_item
        if not self.engine.local:
            # the archives stay on their machine, for now (19 R12)
            for greyed in (projects_import_item, projects_export_item):
                greyed.set_sensitive(False)
                greyed.set_tooltip_text(_("Not over a connection, for now"))
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
        self.menubar = menubar1
        # the connection to the Virtualbricks of the bricks is lost
        self.lost_bar = Gtk.InfoBar(
            message_type=Gtk.MessageType.WARNING, no_show_all=True
        )
        self.lost_words = Gtk.Label(visible=True, xalign=0.0, wrap=True)
        self.lost_bar.get_content_area().add(self.lost_words)
        self.lost_bar.add_button(_("_Reconnect"), RECONNECT)
        self.lost_bar.add_button(_("_Quit"), QUIT)
        self.lost_bar.connect("response", self.on_lost_bar_response)
        self._reconnect: Callable[[], object] | None = None
        vbox1.pack_start(self.lost_bar, False, False, 0)
        self.main_notebook = Gtk.Notebook(visible=True, can_focus=True)
        self.bricks = BricksTab(self, self.factory)
        self.append_tab(self.bricks)
        self.events = EventsTab(self, self.factory)
        self.append_tab(self.events)
        self.images = ImagesTab(self, self.factory)
        self.append_tab(self.images)
        self.append_tab(TopologyTab(self, self.factory))
        self.append_tab(ReadmeTab(self.engine))
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
            Gdk.ModifierType(0),
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

    def append_tab(self, tab: Tab) -> None:
        assert isinstance(tab, Gtk.Widget), "a tab is the widget of its page"
        label = Gtk.Label(visible=True, label=tab.title, use_underline=True)
        self.main_notebook.append_page(tab, label)

    def get_root_widget(self) -> Gtk.Window:
        return self.window

    def check_prerequisites(self) -> defer.Deferred[None]:
        """
        Say which programs are missing, and the packages that have them; and
        KSM, if the settings ask for it and it isn't on once the start has
        tried to turn it on.
        """

        missing = missing_programs(
            str(get_setting("vde_path")), str(get_setting("qemu_path"))
        )

        def warn(running: bool) -> None:
            lines = []
            line = ksm_warning(
                bool(get_setting("kernel_samepage_merging")),
                ksm.ksm_available(),
                running,
            )
            if line:
                lines.append(line)
            if missing:
                names = ", ".join(map(str, missing))
                lines.append(programs_not_found.format(programs=names))
            if lines and get_setting("warn_missing_programs"):
                logger.error(components_not_found, text="\n".join(lines))

        return ksm_started().addCallback(warn)

    """ ********************************************************     """
    """ Signal handlers                                           """
    """ ********************************************************     """

    def curtain_down(self) -> None:
        """
        Close the settings that show, in the tab that shows them: their OK
        and Cancel are there.
        """

        page = self.main_notebook.get_nth_page(
            self.main_notebook.get_current_page()
        )
        rows_tabs: tuple[RowsTab[Any], ...] = (
            self.bricks,
            self.events,
            self.images,
        )
        for tab in rows_tabs:
            if page is tab:
                tab.close_settings()

    def curtain_up(self, item: Item) -> None:
        """
        Show the settings of a brick in the Bricks tab, of an event in the
        Events tab, or the details of a disk image in the Images tab.
        """

        # an image has no type: ask it first
        if is_disk_image(item):
            self._configure(self.images, item)
        elif is_event(item):
            self._configure(self.events, item)
        else:
            self._configure(self.bricks, item)

    def _configure(self, tab: RowsTab[ItemT], item: ItemT) -> None:
        self.main_notebook.set_current_page(self.main_notebook.page_num(tab))
        tab.configure(item)

    def set_title(self) -> None:
        if not self.engine.local:
            self.window.set_title(remote_title(self.engine))
            return
        if projects.current:
            name = projects.current.name
            workspace = os.path.abspath(projects.path)
            if workspace == os.path.abspath(str(get_setting("workspace"))):
                title = _("Virtualbricks (project: {0})").format(name)
            else:
                # another beside it may have a project of the same name
                title = _(
                    "Virtualbricks (project: {name}, workspace: {workspace})"
                ).format(name=name, workspace=short_path(workspace))
            self.window.set_title(title)

    """ ******************************************************** """
    """                                                          """
    """ EVENTS / SIGNALS                                         """
    """                                                          """
    """                                                          """
    """ ******************************************************** """

    # Notebook signals

    def on_main_notebook_switch_page(
        self, notebook: Gtk.Notebook, page: Gtk.Widget, page_num: int
    ) -> bool:
        switch(notebook, page)
        return True

    # gui (programming) interface

    def on_quit(self, factory: BrickFactory | None) -> None:
        for tab in tabs(self.main_notebook):
            tab.on_quit()

    def on_save(self) -> defer.Deferred[None]:
        """Save the open project, with what the tabs hold: a Deferred."""

        for tab in tabs(self.main_notebook):
            tab.on_save()
        return self.engine.save_project()

    def on_open(self, name: str) -> defer.Deferred[Report]:
        """Save the open project and open name: a Deferred of the report."""

        opening = self.on_save()
        return opening.addCallback(
            lambda _: self.engine.open_project(name)
        ).addCallback(self._opened)

    def on_new(
        self, name: str, description: str = ""
    ) -> defer.Deferred[Report]:
        """Save the open project, make name and open it: a Deferred."""

        making = self.on_save()
        return making.addCallback(
            lambda _: self.engine.new_project(name, description)
        ).addCallback(self._opened)

    def _opened(self, report: Report) -> Report:
        self.on_opened()
        return report

    def on_opened(self) -> None:
        """A project opened: the tabs show it, and the title names it."""

        for tab in tabs(self.main_notebook):
            tab.on_open()
        self.set_title()

    def do_quit(self, *_: object) -> bool:
        quitting = self.engine.quit()
        quitting.addErrback(
            lambda failure: logger.error(
                quit_refused, error=failure.getErrorMessage()
            )
        )
        return True

    # end gui (programming) interface

    def on_window_delete_event(
        self, window: Gtk.Window, event: Gdk.Event
    ) -> bool:
        # don't delete; hide instead
        if get_setting("tray_icon"):
            window.hide()
            self.status_icon.set_tooltip_text(_("Virtualbricks hidden"))
            return True
        return False

    def ask_remove_brick(self, brick: Brick) -> None:
        DeleteDialog(self.engine, brick).show(self.window)

    def ask_remove_event(self, event: Event) -> None:
        DeleteDialog(self.engine, event).show(self.window)

    def ask_remove_image(self, image: Image) -> None:
        RemoveImageDialog(self.engine, image).show(self.window)

    def show_images(self) -> None:
        """Show the Images tab."""

        self.main_notebook.set_current_page(
            self.main_notebook.page_num(self.images)
        )

    # status icon handling

    def start_systray(self) -> None:
        if not self.status_icon.get_visible():
            self.status_icon.set_visible(True)

    def stop_systray(self) -> None:
        if self.status_icon.get_visible():
            self.status_icon.set_visible(False)

    def window_toggle(self) -> None:
        if self.window.get_visible():
            self.window.hide()
            self.status_icon.set_tooltip_text(_("Virtualbricks hidden"))
        else:
            self.window.show()
            self.status_icon.set_tooltip_text(_("Virtualbricks visible"))

    def on_status_icon_activate(self, statusicon: Gtk.StatusIcon) -> None:
        self.window_toggle()

    def on_status_icon_popup_menu(
        self, statusicon: Gtk.StatusIcon, button: int, time: int
    ) -> None:
        if button == 3:
            self.systray_menu.popup(None, None, None, None, button, time)

    def on_systray_toggle_item_activate(self, menuitem: Gtk.MenuItem) -> None:
        self.window_toggle()

    # menu items signals

    def on_projects_new_item_activate(self, menuitem: Gtk.MenuItem) -> bool:
        self.project_name_dialog(projectname.NEW)
        return True

    def on_projects_open_item_activate(self, menuitem: Gtk.MenuItem) -> bool:
        self.show_projects()
        return True

    def on_projects_menu_activate(self, menuitem: Gtk.MenuItem) -> None:
        """Fill Open Recent with the projects used last."""

        for child in self.recent_menu.get_children():
            self.recent_menu.remove(child)
        reading = self.engine.project_summaries()
        reading.addCallback(self._fill_recent)

    def _fill_recent(self, summaries: list[ProjectSummary]) -> None:
        current = self.engine.workspace.current
        current_name = current.name if current is not None else None
        recent = [
            summary
            for summary in summaries
            if summary.name != current_name and summary.problem is None
        ][:RECENT]
        for summary in recent:
            recent_item = Gtk.MenuItem(visible=True, label=summary.name)
            recent_item.connect(
                "activate", self.on_recent_item_activate, summary.name
            )
            self.recent_menu.append(recent_item)
        self.projects_recent_item.set_sensitive(bool(recent))

    def on_recent_item_activate(
        self, menuitem: Gtk.MenuItem, name: str
    ) -> bool:
        self.on_open(name).addErrback(self._not_opened, name)
        return True

    def _not_opened(self, failure: Failure, name: str) -> None:
        failure.trap(OSError, errors.Error)
        logger.error(cannot_open_project, name=name, error=failure.value)

    def _current_name(self) -> str:
        current = self.engine.workspace.current
        assert current is not None, "a project is open"
        return current.name

    def on_projects_rename_item_activate(self, menuitem: Gtk.MenuItem) -> bool:
        self.project_name_dialog(projectname.RENAME, self._current_name())
        return True

    def on_projects_save_item_activate(self, menuitem: Gtk.MenuItem) -> bool:
        self.on_save()
        return True

    def on_projects_duplicate_item_activate(
        self, menuitem: Gtk.MenuItem
    ) -> bool:
        self.project_name_dialog(projectname.DUPLICATE, self._current_name())
        return True

    def on_projects_import_item_activate(self, menuitem: Gtk.MenuItem) -> bool:
        self.import_project()
        return True

    def on_projects_export_item_activate(self, menuitem: Gtk.MenuItem) -> bool:
        self.export_project(None)
        return True

    # The projects, for the Projects window and the name dialog

    def show_projects(self, problem: str | None = None) -> ProjectsWindow:
        window = ProjectsWindow(self)
        if problem is not None:
            window.show_problem(problem)
        window.show(self.window)
        return window

    def show_start_up_problem(self, message: str) -> ProjectsWindow:
        """The last project can't be opened: choose one in Projects."""

        window = self.show_projects(problem=message)

        def closed(widget: Gtk.Widget) -> None:
            # closed without opening a project: the last one, or a new one
            if self.engine.workspace.current is None:
                restoring = self.engine.restore_last()
                restoring.addCallback(lambda _: self.set_title())

        window.get_root_widget().connect("destroy", closed)
        return window

    def project_name_dialog(
        self, kind: str, original: str | None = None
    ) -> projectname.ProjectNameDialog:
        dialog = projectname.ProjectNameDialog(self, kind, original)
        dialog.show(self.window)
        return dialog

    def import_project(
        self, on_closed: Callable[[], object] | None = None
    ) -> ImportDialog:
        """Import a project; on_closed is called when the window closes."""

        dialog = ImportDialog(self.brickfactory)

        def destroyed(window: Gtk.Widget) -> None:
            self.set_title()
            if on_closed is not None:
                on_closed()

        dialog.show(self.window)
        dialog.get_root_widget().connect("destroy", destroyed)
        return dialog

    def export_project(
        self, summary: ProjectSummary | None, parent: Gtk.Window | None = None
    ) -> None:
        """Export a project, the open one if summary is None."""

        if summary is None or (
            projects.current and summary.name == projects.current.name
        ):
            self.on_save()
            assert projects.current is not None, "Export is of a project"
            path = projects.current.path
            images = [
                (image.name, image.path) for image in self.brickfactory.images
            ]
        else:
            path = summary.path
            images = [(image.name, image.path) for image in summary.images]
        dialog = ExportProjectDialog(path, images)
        dialog.show(parent or self.window)

    def on_file_settings_item_activate(self, menuitem: Gtk.MenuItem) -> bool:
        SettingsWindow(self).show(self.window)
        return True

    def on_file_logs_item_activate(self, menuitem: Gtk.MenuItem) -> bool:
        LoggingWindow(self.messages).show()
        return True

    def on_help_about_item_activate(self, menuitem: Gtk.MenuItem) -> bool:
        dialog = AboutDialog()
        dialog.show(self.window)
        return True

    # The connection to another Virtualbricks, for its windows

    def connection_lost(
        self, text: str, reconnect: Callable[[], object]
    ) -> None:
        """
        Say that the connection is lost, and why; the windows wait, while
        reconnect() tries again.
        """

        self._reconnect = reconnect
        self.lost_words.set_text(text)
        self.lost_bar.show()
        self.menubar.set_sensitive(False)
        self.main_notebook.set_sensitive(False)

    def reconnected(self) -> None:
        self.lost_bar.hide()
        self.menubar.set_sensitive(True)
        self.main_notebook.set_sensitive(True)

    def on_lost_bar_response(self, bar: Gtk.InfoBar, response: int) -> None:
        if response == RECONNECT and self._reconnect is not None:
            self._reconnect()
        elif response == QUIT:
            self.do_quit()

    def user_wait_action(
        self, action: defer.Deferred[Any] | Callable[..., Any], *args: Any
    ) -> None:
        ProgressBar(self).wait_for(action, *args)

    def set_insensitive(self) -> None:
        self.window.set_sensitive(False)

    def set_sensitive(self) -> None:
        self.window.set_sensitive(True)
