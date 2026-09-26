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

``VBGUI`` builds its UI in ``build_ui()``.
"""

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gtk
from twisted.internet import defer
from twisted.logger import Logger

from virtualbricks import config, errors, tools
from virtualbricks.config import get_setting, projects, set_setting
from virtualbricks.gui import widgets
from virtualbricks.gui.interfaces import IConfigController, IMenu
from virtualbricks.tools import dispose, is_running
from virtualbricks.gui.windows.base import _, load_pixbuf, StateManager
from virtualbricks.gui.windows.about import AboutDialog
from virtualbricks.gui.windows.commitimagedialog import CommitImageDialog
from virtualbricks.gui.windows.confirmdialog import (
    DeleteBrickConfirmDialog,
    DeleteEventConfirmDialog,
)
from virtualbricks.gui.windows.createimagedialog import CreateImageDialog
from virtualbricks.gui.windows.disklibrary import DisksLibraryWindow
from virtualbricks.gui.windows.exportproject import ExportProjectDialog
from virtualbricks.gui.windows.importdialog import ImportDialog
from virtualbricks.gui.windows.loadimagedialog import LoadImageDialog
from virtualbricks.gui.messages import MessageLog
from virtualbricks.gui.mainwindow.events import EventsTab
from virtualbricks.gui.mainwindow.readme import ReadmeTab
from virtualbricks.gui.mainwindow.running import RunningTab
from virtualbricks.gui.mainwindow.tab import switch, tabs
from virtualbricks.gui.mainwindow.topology import TopologyTab
from virtualbricks.gui.windows.logging import LoggingWindow
from virtualbricks.gui.windows.newbrick import NewBrickDialog
from virtualbricks.gui.windows import projectname
from virtualbricks.gui.windows.projects import ProjectsWindow
from virtualbricks.gui.windows.settings import SettingsDialog
from virtualbricks.gui.windows.userwait import Freezer

logger = Logger()
cannot_open_project = 'Cannot open the project "{name}": {error}'
# The projects in Open Recent.
RECENT = 8

start_virtualbricks = "Starting VirtualBricks"
components_not_found = (
    "{text}\nThere are some components not "
    "found: {components} some functionalities may not be available.\nYou can "
    "disable this alert from the general settings."
)
not_started = "Brick not started."
stop_error = "Error on stopping brick."
start_error = "Error on starting brick."
dnd_no_socks = "I don't know what to do, bricks have no socks."
dnd_dest_brick_not_found = "Cannot found dest brick"
dnd_source_brick_not_found = "Cannot find source brick {name}"
dnd_no_dest = "No destination brick"
dnd_same_brick = "Source and destination bricks are the same."

BRICK_TARGET_NAME = "brick-connect-target"
BRICK_DRAG_TARGETS = [
    (
        BRICK_TARGET_NAME,
        Gtk.TargetFlags.SAME_WIDGET | Gtk.TargetFlags.SAME_APP,
        0,
    )
]


def state_add_selection(manager, treeview, prerequisite, tooltip, *widgets):
    state = manager._build_state(tooltip, *widgets)
    state.add_prerequisite(prerequisite)
    selection = treeview.get_selection()
    selection.connect("changed", lambda s: state.check())
    state.check()
    return state


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


class _Root:
    # This object ensure that super() calls are not forwarded to object.

    def init(self, factory):
        pass

    # Notebook signals

    def on_main_notebook_switch_page(self, notebook, _, page_num):
        pass

    # VBGUI signals

    def on_quit(self, factory):
        pass

    def on_save(self):
        pass

    def on_open(self, name):
        pass

    def on_new(self, name):
        pass


class BricksBindingList(widgets.AbstractBindingList):

    def __init__(self, factory):
        widgets.AbstractBindingList.__init__(self, factory)
        factory.connect("brick-added", self._on_added)
        factory.connect("brick-removed", self._on_removed)
        factory.connect("brick-changed", self._on_changed)

    def __dispose__(self):
        self._factory.disconnect("brick-added", self._on_added)
        self._factory.disconnect("brick-removed", self._on_removed)
        self._factory.disconnect("brick-changed", self._on_changed)

    def __iter__(self):
        return iter(self._factory.bricks)


class VBGUI(_Root):
    """
    The main GUI object for virtualbricks, containing all the configuration for
    the widgets and the connections to the main engine.
    """

    __bricks_binding_list = None

    def __init__(self, factory, messages=None):
        self.factory = self.brickfactory = factory
        self.build_ui()
        self.config = config
        # the messages of this run, see virtualbricks.gui.messages
        self.messages = MessageLog() if messages is None else messages

        logger.info(start_virtualbricks)
        self.__initialize_components()
        if get_setting("systray"):
            self.start_systray()
        self.__state_manager = StateManager()
        state_add_selection(
            self.__state_manager,
            self.bricks_view,
            self.__brick_selected,
            _("No brick selected"),
            self.configure_brick_button,
        )
        self.init(factory)

        # attach the quit callback at the end, so it is not called if an
        # exception is raised before because of a syntax error of another kind
        # of error
        factory.connect("quit", self.on_quit)

        # Show the main window
        self.window.show()

    def build_ui(self) -> None:
        """Create the widgets, formerly in ``virtualbricks.ui``."""

        # bricks_store (widgets.List)
        # Custom widget from glade-catalog.xml
        self.bricks_store = widgets.List()

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
        menu_file = Gtk.MenuItem(
            visible=True,
            can_focus=False,
            label=_("_File"),
            use_underline=True,
        )
        menu1 = Gtk.Menu(visible=True, can_focus=False)

        def item(label):
            menu_item = Gtk.MenuItem(
                visible=True, label=label, use_underline=True
            )
            menu1.append(menu_item)
            return menu_item

        def separator():
            menu1.append(Gtk.SeparatorMenuItem(visible=True))

        file_open_item = item(_("_Projects…"))
        file_open_item.set_tooltip_text(
            _("See, open, rename, duplicate, export and remove your projects")
        )
        file_new_item = item(_("_New Project…"))
        file_recent_item = item(_("Open _Recent"))
        self.recent_menu = Gtk.Menu(visible=True)
        file_recent_item.set_submenu(self.recent_menu)
        self.file_recent_item = file_recent_item
        separator()
        file_save_item = item(_("_Save"))
        file_duplicate_item = item(_("_Duplicate…"))
        file_rename_item = item(_("Re_name…"))
        separator()
        file_import_item = item(_("_Import…"))
        file_export_item = item(_("E_xport…"))
        separator()
        file_quit_item = item(_("_Quit"))
        menu_file.connect("activate", self.on_file_menu_activate)
        menu_file.set_submenu(menu1)
        menubar1.append(menu_file)
        menu_settings = Gtk.MenuItem(
            visible=True,
            can_focus=False,
            label=_("_Settings"),
            use_underline=True,
        )
        menu2 = Gtk.Menu(visible=True, can_focus=False)
        settings_preferences_item = Gtk.ImageMenuItem(
            label="gtk-preferences",
            visible=True,
            can_focus=False,
            use_underline=True,
            use_stock=True,
        )
        menu2.append(settings_preferences_item)
        menu_settings.set_submenu(menu2)
        menubar1.append(menu_settings)
        menu_view = Gtk.MenuItem(
            visible=True,
            can_focus=False,
            label=_("_View"),
            use_underline=True,
        )
        menu3 = Gtk.Menu(visible=True, can_focus=False)
        view_messages_item = Gtk.MenuItem(
            visible=True,
            can_focus=False,
            label=_("_Messages"),
            use_underline=True,
        )
        menu3.append(view_messages_item)
        menu_view.set_submenu(menu3)
        menubar1.append(menu_view)
        menu_images = Gtk.MenuItem(
            visible=True,
            can_focus=False,
            label=_("_Disk images"),
            use_underline=True,
        )
        menu4 = Gtk.Menu(visible=True, can_focus=False)
        images_create_item = Gtk.MenuItem(
            visible=True,
            can_focus=False,
            label=_("_Create new image"),
            use_underline=True,
        )
        menu4.append(images_create_item)
        images_new_item = Gtk.MenuItem(
            visible=True,
            can_focus=False,
            label=_("_New image from file"),
            use_underline=True,
        )
        menu4.append(images_new_item)
        images_commit_item = Gtk.MenuItem(
            visible=True,
            can_focus=False,
            label=_("Co_mmit cow image"),
            use_underline=True,
        )
        menu4.append(images_commit_item)
        separatormenuitem2 = Gtk.SeparatorMenuItem(
            visible=True,
            can_focus=False,
        )
        menu4.append(separatormenuitem2)
        images_library_item = Gtk.MenuItem(
            visible=True,
            can_focus=False,
            label=_("Images library"),
            use_underline=True,
        )
        menu4.append(images_library_item)
        menu_images.set_submenu(menu4)
        menubar1.append(menu_images)
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
        vbox11 = Gtk.Box(
            visible=True,
            can_focus=False,
            orientation=Gtk.Orientation.VERTICAL,
        )
        tlb_bricks = Gtk.Toolbar(
            visible=True,
            can_focus=False,
            toolbar_style=Gtk.ToolbarStyle.BOTH,
        )
        new_brick_button = Gtk.ToolButton(
            visible=True,
            can_focus=False,
            label=_("New Brick"),
            use_underline=True,
            stock_id="gtk-new",
        )
        tlb_bricks.insert(new_brick_button, -1)
        separatortoolitem1 = Gtk.SeparatorToolItem(
            visible=True,
            can_focus=False,
        )
        tlb_bricks.insert(separatortoolitem1, -1)
        separatortoolitem1.set_homogeneous(False)
        start_all_button = Gtk.ToolButton(
            visible=True,
            can_focus=False,
            label=_("Start All Bricks"),
            use_underline=True,
            stock_id="gtk-yes",
        )
        tlb_bricks.insert(start_all_button, -1)
        stop_all_button = Gtk.ToolButton(
            visible=True,
            can_focus=False,
            label=_("Stop All Bricks"),
            use_underline=True,
            stock_id="gtk-no",
        )
        tlb_bricks.insert(stop_all_button, -1)
        separatortoolitem3 = Gtk.SeparatorToolItem(
            visible=True,
            can_focus=False,
        )
        tlb_bricks.insert(separatortoolitem3, -1)
        separatortoolitem3.set_homogeneous(False)
        self.configure_brick_button = Gtk.ToolButton(
            visible=True,
            sensitive=False,
            can_focus=False,
            label=_("Configure"),
            use_underline=True,
            stock_id="gtk-edit",
        )
        tlb_bricks.insert(self.configure_brick_button, -1)
        vbox11.pack_start(tlb_bricks, False, False, 0)
        bricks_scrolledwindow = Gtk.ScrolledWindow(
            visible=True,
            can_focus=True,
            shadow_type=Gtk.ShadowType.IN,
        )
        # Custom widget from glade-catalog.xml
        self.bricks_view = widgets.TreeView(
            visible=True,
            can_focus=True,
            model=self.bricks_store,
            headers_clickable=False,
        )
        tvc_brick_icon = Gtk.TreeViewColumn.new()
        tvc_brick_icon.set_properties(title=_("Icon"))
        # Custom widget from glade-catalog.xml
        crp1 = widgets.CellRendererBrickIcon()
        tvc_brick_icon.pack_start(crp1, False)
        self.bricks_view.append_column(tvc_brick_icon)
        tvc_brick_status = Gtk.TreeViewColumn.new()
        tvc_brick_status.set_properties(title=_("Status"))
        # Custom widget from glade-catalog.xml
        crt1 = widgets.CellRendererFormattable(
            format_string="s",
            formatting_enabled=True,
        )
        tvc_brick_status.pack_start(crt1, False)
        self.bricks_view.append_column(tvc_brick_status)
        tvc_brick_type = Gtk.TreeViewColumn.new()
        tvc_brick_type.set_properties(title=_("Type"))
        # Custom widget from glade-catalog.xml
        crt2 = widgets.CellRendererFormattable(
            format_string="t",
            formatting_enabled=True,
        )
        tvc_brick_type.pack_start(crt2, False)
        self.bricks_view.append_column(tvc_brick_type)
        tvc_brick_name = Gtk.TreeViewColumn.new()
        tvc_brick_name.set_properties(title=_("Name"))
        # Custom widget from glade-catalog.xml
        crt3 = widgets.CellRendererFormattable(
            format_string="n",
            formatting_enabled=True,
        )
        tvc_brick_name.pack_start(crt3, False)
        self.bricks_view.append_column(tvc_brick_name)
        tvc_brick_params = Gtk.TreeViewColumn.new()
        tvc_brick_params.set_properties(title=_("Parameters"))
        # Custom widget from glade-catalog.xml
        crt4 = widgets.CellRendererFormattable(
            format_string="p",
            formatting_enabled=True,
        )
        tvc_brick_params.pack_start(crt4, False)
        self.bricks_view.append_column(tvc_brick_params)
        bricks_scrolledwindow.add(self.bricks_view)
        vbox11.pack_start(bricks_scrolledwindow, True, True, 0)
        bricks_label = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("_Bricks"),
            use_underline=True,
        )
        self.main_notebook.append_page(vbox11, bricks_label)
        self.append_tab(EventsTab(self, self.factory))
        self.append_tab(RunningTab(self, self.bricks_store))
        self.append_tab(TopologyTab(self, self.factory))
        self.append_tab(ReadmeTab())
        vbox1.pack_start(self.main_notebook, True, True, 0)
        self.config_frame = Gtk.Frame(
            can_focus=False,
            label_xalign=0,
            shadow_type=Gtk.ShadowType.NONE,
        )
        # TODO: empty Glade placeholder, nothing to create.
        # TODO: empty Glade placeholder (label_item), nothing to create.
        vbox1.pack_start(self.config_frame, True, True, 0)
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
        file_new_item.add_accelerator(
            "activate",
            accel_group,
            Gdk.KEY_n,
            Gdk.ModifierType.CONTROL_MASK,
            Gtk.AccelFlags.VISIBLE,
        )
        file_open_item.add_accelerator(
            "activate",
            accel_group,
            Gdk.KEY_o,
            Gdk.ModifierType.CONTROL_MASK,
            Gtk.AccelFlags.VISIBLE,
        )
        file_save_item.add_accelerator(
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
        settings_preferences_item.add_accelerator(
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
        file_new_item.connect("activate", self.on_file_new_item_activate)
        file_open_item.connect("activate", self.on_file_open_item_activate)
        file_rename_item.connect(
            "activate",
            self.on_file_rename_item_activate,
        )
        file_save_item.connect("activate", self.on_file_save_item_activate)
        file_duplicate_item.connect(
            "activate",
            self.on_file_duplicate_item_activate,
        )
        file_import_item.connect(
            "activate",
            self.on_file_import_item_activate,
        )
        file_export_item.connect(
            "activate",
            self.on_file_export_item_activate,
        )
        file_quit_item.connect("activate", self.do_quit)
        settings_preferences_item.connect(
            "activate",
            self.on_settings_preferences_item_activate,
        )
        view_messages_item.connect(
            "activate",
            self.on_view_messages_item_activate,
        )
        images_create_item.connect(
            "activate",
            self.on_images_create_item_activate,
        )
        images_new_item.connect("activate", self.on_images_new_item_activate)
        images_commit_item.connect(
            "activate",
            self.on_images_commit_item_activate,
        )
        images_library_item.connect(
            "activate",
            self.on_images_library_item_activate,
        )
        help_about_item.connect("activate", self.on_help_about_item_activate)
        self.main_notebook.connect(
            "switch-page",
            self.on_main_notebook_switch_page,
        )
        new_brick_button.connect("clicked", self.on_new_brick_button_clicked)
        start_all_button.connect("clicked", self.on_start_all_button_clicked)
        stop_all_button.connect("clicked", self.on_stop_all_button_clicked)
        self.configure_brick_button.connect(
            "clicked", self.on_configure_brick_button_clicked
        )
        self.bricks_view.connect(
            "button-release-event",
            self.on_bricks_view_button_release_event,
        )
        self.bricks_view.connect(
            "drag-data-get",
            self.on_bricks_view_drag_data_get,
        )
        self.bricks_view.connect(
            "drag-data-received",
            self.on_bricks_view_drag_data_received,
        )
        self.bricks_view.connect(
            "key-release-event",
            self.on_bricks_view_key_release_event,
        )
        self.bricks_view.connect(
            "row-activated",
            self.on_bricks_view_row_activated,
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

    def __initialize_components(self):
        # bricks tab
        self.bricks_view.set_cells_data_func()
        self.__bricks_binding_list = BricksBindingList(self.factory)
        self.bricks_store.set_data_source(self.__bricks_binding_list)
        self.bricks_view.enable_model_drag_source(
            Gdk.ModifierType.BUTTON1_MASK,
            BRICK_DRAG_TARGETS,
            Gdk.DragAction.LINK,
        )
        self.bricks_view.enable_model_drag_dest(
            BRICK_DRAG_TARGETS, Gdk.DragAction.LINK
        )

    def check_prerequisites(self):
        """Say which programs are missing, in the folders of the project."""

        qmissing, _ = tools.check_missing_qemu()
        vmissing = tools.check_missing_vde()
        missing = vmissing + qmissing

        if not tools.check_ksm():
            set_setting("ksm", False)
            missing.append("ksm")
        missing_text = []
        missing_components = []
        if len(missing) > 0 and get_setting("show_missing"):
            for m in missing:
                if m == "ksm":
                    missing_text.append(
                        "KSM not found in Linux. Samepage memory will"
                        " not work on this system."
                    )
                else:
                    missing_components.append(m)
            logger.error(
                components_not_found,
                text="\n".join(missing_text),
                components=" ".join(missing_components),
            )

    def __dispose__(self):
        if self.__bricks_binding_list is not None:
            dispose(self.__bricks_binding_list)
            self.__bricks_binding_list = None

    def get_object(self, name):
        return getattr(self, name, None)

    """ ********************************************************     """
    """ Signal handlers                                           """
    """ ********************************************************     """

    def curtain_down(self):
        self.main_notebook.show()
        configframe = self.config_frame
        configpanel = configframe.get_child()
        if configpanel:
            configpanel.destroy()
        configframe.hide()
        self.set_title()

    def curtain_up(self, brick):
        configframe = self.config_frame
        configframe.add(IConfigController(brick).get_view(self))
        configframe.show()
        self.main_notebook.hide()
        self.set_title(
            "Virtualbricks (Configuring Brick %s)" % brick.get_name()
        )

    def set_title(self, title=None):
        if title is None:
            if projects.current:
                name = projects.current.name
                title = _("Virtualbricks (project: {0})").format(name)
                self.window.set_title(title)
        else:
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
        super().on_main_notebook_switch_page(notebook, page, page_num)
        return True

    # gui (programming) interface

    def init(self, factory):
        super().init(factory)

    def on_quit(self, factory):
        dispose(self)
        for tab in tabs(self.main_notebook):
            tab.on_quit()
        super().on_quit(factory)

    def on_save(self):
        for tab in tabs(self.main_notebook):
            tab.on_save()
        super().on_save()
        projects.save(self.brickfactory)

    def on_open(self, name):
        self.on_save()
        report = projects.open(name, self.brickfactory)
        for tab in tabs(self.main_notebook):
            tab.on_open()
        super().on_open(name)
        self.set_title()
        return report

    def on_new(self, name, description=""):
        self.on_save()
        projects.create(name, description)
        projects.open(name, self.brickfactory)
        for tab in tabs(self.main_notebook):
            tab.on_open()
        super().on_new(name)
        self.set_title()

    def do_quit(self, *_):
        self.factory.quit()
        return True

    # end gui (programming) interface

    def on_window_delete_event(self, window, event):
        # don't delete; hide instead
        if get_setting("systray"):
            window.hide()
            self.status_icon.set_tooltip("Virtualbricks Hidden")
            return True

    def ask_remove_brick(self, brick):
        DeleteBrickConfirmDialog(self.brickfactory, brick).show(self.window)

    def ask_remove_event(self, event):
        DeleteEventConfirmDialog(self.brickfactory, event).show(self.window)

    def on_bricks_view_key_release_event(self, treeview, event):
        if Gdk.keyval_name(event.keyval) in set(["Delete", "BackSpace"]):
            brick = treeview.get_selected_value()
            if brick is not None:
                self.ask_remove_brick(brick)

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

    def on_file_new_item_activate(self, menuitem):
        self.project_name_dialog(projectname.NEW)
        return True

    def on_file_open_item_activate(self, menuitem):
        self.show_projects()
        return True

    def on_file_menu_activate(self, menuitem):
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
        self.file_recent_item.set_sensitive(bool(recent))

    def on_recent_item_activate(self, menuitem, name):
        try:
            self.on_open(name)
        except (OSError, errors.Error) as exc:
            logger.error(cannot_open_project, name=name, error=exc)
        return True

    def on_file_rename_item_activate(self, menuitem):
        self.project_name_dialog(projectname.RENAME, projects.current.name)
        return True

    def on_file_save_item_activate(self, menuitem):
        self.on_save()
        return True

    def on_file_duplicate_item_activate(self, menuitem):
        self.project_name_dialog(projectname.DUPLICATE, projects.current.name)
        return True

    def on_file_import_item_activate(self, menuitem):
        self.import_project()
        return True

    def on_file_export_item_activate(self, menuitem):
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

        def closed():
            if projects.current is None:
                projects.restore_last(self.brickfactory)
                self.set_title()

        window.on_closed = closed
        return window

    def project_name_dialog(self, kind, original=None):
        dialog = projectname.ProjectNameDialog(self, kind, original)
        dialog.show(self.window)
        return dialog

    def import_project(self, on_destroy=None):
        dialog = ImportDialog(self.brickfactory)

        def destroyed():
            self.set_title()
            if on_destroy is not None:
                on_destroy()

        dialog.on_destroy = destroyed
        dialog.show(self.window)

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

    def on_settings_preferences_item_activate(self, menuitem):
        SettingsDialog(self).show(self.window)
        return True

    def on_view_messages_item_activate(self, menuitem):
        LoggingWindow(self.messages).show()
        return True

    def on_images_create_item_activate(self, menuitem):
        CreateImageDialog(self, self.brickfactory).show(self.window)
        return True

    def on_images_new_item_activate(self, menuitem):
        LoadImageDialog(self.brickfactory).show(self.window)
        return True

    def on_images_commit_item_activate(self, menuitem):
        CommitImageDialog(self.brickfactory).show(self.window)
        return True

    def on_images_library_item_activate(self, menuitem):
        DisksLibraryWindow(self.brickfactory).show()
        return True

    def on_help_about_item_activate(self, menuitem):
        dialog = AboutDialog()
        dialog.show(self.window)
        return True

    # bricks toolbar

    def on_new_brick_button_clicked(self, toolbutton):
        NewBrickDialog(self.brickfactory).show(self.window)
        return True

    def on_start_all_button_clicked(self, toolbutton):

        def started_all(results):
            for success, value in results:
                if not success:
                    logger.failure(not_started, value)

        deferreds = [brick.poweron() for brick in self.brickfactory.bricks]
        defer.DeferredList(deferreds, consumeErrors=True).addCallback(
            started_all
        )
        return True

    def on_stop_all_button_clicked(self, toolbutton):
        for brick in self.brickfactory.bricks:
            brick.poweroff()
        return True

    def __show_config_if_selected(self, treeview):
        brick = treeview.get_selected_value()
        if brick:
            self.curtain_up(brick)
            return True
        return False

    def on_configure_brick_button_clicked(self, toolbutton):
        return self.__show_config_if_selected(self.bricks_view)

    def confirm(self, message):
        dialog = Gtk.MessageDialog(
            None,
            Gtk.DialogFlags.MODAL,
            Gtk.MessageType.INFO,
            Gtk.ButtonsType.YES_NO,
            message,
        )
        response = dialog.run()
        dialog.destroy()

        if response == Gtk.ResponseType.YES:
            return True
        elif response == Gtk.ResponseType.NO:
            return False

    def on_bricks_view_button_release_event(self, treeview, event):
        if event.button == 3:
            pthinfo = treeview.get_path_at_pos(int(event.x), int(event.y))
            if pthinfo is not None:
                path, col, cellx, celly = pthinfo
                treeview.grab_focus()
                treeview.set_cursor(path, col, 0)
                model = treeview.get_model()
                obj = model.get_value(model.get_iter(path), 0)
                menu = IMenu(obj)
                menu.popup(event.button, event.time, self)
            return True

    def on_bricks_view_row_activated(self, treeview, path, column):
        model = treeview.get_model()
        brick = model.get_value(model.get_iter(path), 0)
        self.startstop_brick(brick)

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

    # Bricks tab signals

    def on_bricks_view_drag_data_get(
        self, treeview, context, selection, info, time
    ):
        brick = treeview.get_selected_value()
        selection.set(selection.target, 8, brick.get_name())
        return True

    def on_bricks_view_drag_data_received(
        self, treeview, context, x, y, selection, info, time
    ):
        drop_info = treeview.get_dest_row_at_pos(x, y)
        if drop_info:
            path, position = drop_info
            source_brick = self.brickfactory.get_brick_by_name(selection.data)
            if source_brick:
                # XXX log debug info
                model = treeview.get_model()
                dest_brick = model.get(model.get_iter(path), 0)[0]
                if dest_brick:
                    if dest_brick is not source_brick:
                        pass
                        if len(source_brick.socks) > 0:
                            dest_brick.connect(source_brick.socks[0])
                        elif len(dest_brick.socks) > 0:
                            source_brick.connect(dest_brick.socks[0])
                        else:
                            logger.info(dnd_no_socks)
                    else:
                        logger.debug(dnd_same_brick)
                else:
                    logger.debug(dnd_dest_brick_not_found)
            else:
                logger.debug(dnd_source_brick_not_found, name=selection.data)
        else:
            logger.debug(dnd_no_dest)
        context.finish(True, False, time)
        return True

    def __brick_selected(self):
        return bool(self.bricks_view.get_selected_value())

    # Events tab signals
