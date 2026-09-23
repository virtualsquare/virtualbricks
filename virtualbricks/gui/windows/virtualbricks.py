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
from twisted.internet import defer, reactor, task
from twisted.python import filepath

from virtualbricks import log, project, settings, tools
from virtualbricks.gui import graphics, widgets
from virtualbricks.gui.interfaces import IConfigController, IJobMenu, IMenu
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
from virtualbricks.gui.windows.logging import LoggingWindow
from virtualbricks.gui.windows.newbrick import NewBrickDialog
from virtualbricks.gui.windows.newevent import NewEventDialog
from virtualbricks.gui.windows.projectlistdialog import (
    DeleteProjectDialog,
    OpenProjectDialog,
)
from virtualbricks.gui.windows.saveprojectasdialog import SaveProjectAsDialog
from virtualbricks.gui.windows.settings import SettingsDialog
from virtualbricks.gui.windows.simpleentry import (
    NewProjectDialog,
    RenameProjectDialog,
)
from virtualbricks.gui.windows.userwait import Freezer


logger = log.Logger()

drawing_topology = log.Event("drawing topology")
top_invalid_format = log.Event("Error saving topology: Invalid image format")
top_write_error = log.Event("Error saving topology: Could not write file")
top_unknown = log.Event("Error saving topology: Unknown error")
start_virtualbricks = log.Event("Starting VirtualBricks")
components_not_found = log.Event(
    "{text}\nThere are some components not "
    "found: {components} some functionalities may not be available.\nYou can "
    "disable this alert from the general settings."
)
not_started = log.Event("Brick not started.")
stop_error = log.Event("Error on stopping brick.")
start_error = log.Event("Error on starting brick.")
dnd_no_socks = log.Event("I don't know what to do, bricks have no socks.")
dnd_dest_brick_not_found = log.Event("Cannot found dest brick")
dnd_source_brick_not_found = log.Event("Cannot find source brick {name}")
dnd_no_dest = log.Event("No destination brick")
dnd_same_brick = log.Event("Source and destination bricks are the same.")

BRICK_TARGET_NAME = "brick-connect-target"
BRICK_DRAG_TARGETS = [
    (
        BRICK_TARGET_NAME,
        Gtk.TargetFlags.SAME_WIDGET | Gtk.TargetFlags.SAME_APP,
        0
    )
]


def state_add_selection(manager, treeview, prerequisite, tooltip, *widgets):
    state = manager._build_state(tooltip, *widgets)
    state.add_prerequisite(prerequisite)
    selection = treeview.get_selection()
    selection.connect("changed", lambda s: state.check())
    state.check()
    return state


BRICKS_TAB, EVENTS_TAB, RUNNING_TAB, TOPOLOGY_TAB, README_TAB = range(5)


def is_running_filter(model, itr, data):
    brick = model.get_value(itr, 0)
    if brick:
        return is_running(brick)


class TopologyMixin(object):

    __should_draw_topology = False
    __topology = None

    # public interface

    def draw_topology(self, export=""):
        if self.main_notebook.get_current_page() == TOPOLOGY_TAB:
            self._draw_topology()
        else:
            self.__should_draw_topology = True

    # callbacks

    def on_topology_h_scrolled(self, adjustment):
        self.__topology.x_adj = adjustment.get_value()

    def on_topology_v_scrolled(self, adjustment):
        self.__topology.y_adj = adjustment.get_value()

    def on_topology_orientation_toggled(self, togglebutton):
        self._draw_topology()

    def on_topology_export_button_clicked(self, button):
        def on_response(dialog, response_id):
            assert self.__topology, "Topology not created"
            try:
                if response_id == Gtk.ResponseType.OK:
                    try:
                        self._draw_topology_if_needed()
                        self.__topology.export(dialog.get_filename())
                    except KeyError:
                        logger.failure(top_invalid_format)
                    except IOError:
                        logger.failure(top_write_error)
                    except:
                        logger.failure(top_unknown)
            finally:
                dialog.destroy()

        chooser = Gtk.FileChooserDialog(
            title=_("Select an image file"),
            action=Gtk.FileChooserAction.SAVE,
            buttons=(
                "_Cancel",
                Gtk.ResponseType.CANCEL,
                "_Save",
                Gtk.ResponseType.OK
            )
        )
        chooser.set_do_overwrite_confirmation(True)
        chooser.connect("response", on_response)
        chooser.show()

    def on_topology_action(self, widget, event):
        self._draw_topology_if_needed()
        assert self.__topology, "Topology not created"
        brick = self._get_brick_in(*event.get_coords())
        if brick:
            if event.button == 3:
                IMenu(brick, None).popup(event.button, event.time, self)
            elif event.button == 1 and event.type == Gdk.EventType._2BUTTON_PRESS:
                self.startstop_brick(brick)
            return True

    # Notebook callbacks

    def on_main_notebook_change_current_page(self, notebook, offset):
        self._draw_topology_if_on_page(notebook.get_current_page())
        super(TopologyMixin, self).on_main_notebook_change_current_page(
            notebook,  offset)

    def on_main_notebook_switch_page(self, notebook, _, page_num):
        self._draw_topology_if_on_page(page_num)
        super(TopologyMixin, self).on_main_notebook_switch_page(
            notebook, _, page_num)

    def on_main_notebook_select_page(self, notebook, move_focus):
        self._draw_topology_if_on_page(notebook.get_current_page())
        super(TopologyMixin, self).on_main_notebook_select_page(
            notebook, move_focus)

    # VBGUI callbacks

    def init(self, factory):
        super(TopologyMixin, self).init(factory)
        topology_scrolled = self.topology_scrolled
        hadjustment = topology_scrolled.get_hadjustment()
        hadjustment.connect("value-changed", self.on_topology_h_scrolled)
        vadjustment = topology_scrolled.get_vadjustment()
        vadjustment.connect("value-changed", self.on_topology_v_scrolled)

    def _get_brick_in(self, x, y):
        assert self.__topology, "Topology not created"
        for n in self.__topology.nodes:
            if n.here(x, y):
                return self.brickfactory.get_brick_by_name(n.name)

    def _draw_topology_if_on_page(self, page):
        if page == TOPOLOGY_TAB and self.__should_draw_topology:
            self._draw_topology()

    def _draw_topology_if_needed(self):
        if self.__should_draw_topology:
            self._draw_topology()

    def _draw_topology(self):
        logger.debug(drawing_topology)
        if self.topology_vertical_radio.get_active():
            orientation = "TB"
        else:
            orientation = "LR"
        self.__topology = graphics.Topology(
            self.topology_image,
            self.brickfactory.bricks, 1.00, orientation,
            settings.VIRTUALBRICKS_HOME)
        self.__should_draw_topology = False


class ReadmeMixin(object):

    __deleyed_call = None
    manager = project.manager

    def __get_buffer(self):
        return self.readme_text.get_buffer()

    def __get_modified(self):
        return self.__get_buffer().get_modified()

    def __set_modified(self, modified):
        return self.__get_buffer().set_modified(modified)

    def __get_text(self):
        return self.__get_buffer().get_property("text")

    def __set_text(self, text):
        self.__get_buffer().set_text(text)

    def __save_readme(self):
        if self.__get_modified():
            self.manager.current.set_description(self.__get_text())
            self.__set_modified(False)

    def __load_readme(self):
        buf = self.__get_buffer()
        buf.handler_block_by_func(self.__on_modify)
        try:
            self.__set_text(self.manager.current.get_description())
            self.__set_modified(False)
        finally:
            buf.handler_unblock_by_func(self.__on_modify)

    def on_main_notebook_switch_page(self, notebook, _, page_num):
        # if I leave the readme tab
        if notebook.get_current_page() == README_TAB:
            self.__save_readme()
        # if I switch to readme tab
        if page_num == README_TAB:
            self.__load_readme()
        super(ReadmeMixin, self).on_main_notebook_switch_page(
            notebook, _, page_num)

    def init(self, factory):
        self.__get_buffer().connect("modified-changed", self.__on_modify)
        super(ReadmeMixin, self).init(factory)

    def __cancel_delayed_save(self):
        if self.__deleyed_call:
            if self.__deleyed_call.active():
                self.__deleyed_call.cancel()
            self.__deleyed_call = None

    def __on_modify(self, textbuffer):
        if not self.__get_modified() and self.__deleyed_call:
            self.__cancel_delayed_save()
        if self.__get_modified() and not self.__deleyed_call:
            self.__deleyed_call = reactor.callLater(30, self.__save_readme)

    def on_new(self, name):
        self.__load_readme()
        super(ReadmeMixin, self).on_new(name)

    def on_save(self):
        self.__save_readme()
        super(ReadmeMixin, self).on_save()

    def on_open(self, name):
        self.__load_readme()
        super(ReadmeMixin, self).on_open(name)

    def on_quit(self, factory):
        self.__cancel_delayed_save()
        self.__save_readme()
        super(ReadmeMixin, self).on_quit(factory)


class ProgressBar:
    """
    Wait for an operation, freezing the main window.
    """

    def __init__(self, gui):
        self.freezer = Freezer(
            gui.set_insensitive,
            gui.set_sensitive,
            gui.window
        )

    def wait_for(self, something, *args):
        return self.freezer.wait_for(something, *args)


class _Root(object):
    # This object ensure that super() calls are not forwarded to object.

    def init(self, factory):
        pass

    # Notebook signals

    def on_main_notebook_switch_page(self, notebook, _, page_num):
        pass

    def on_main_notebook_select_page(self, notebook, move_focus):
        pass

    def on_main_notebook_change_current_page(self, notebook, offset):
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


class EventsBindingList(widgets.AbstractBindingList):

    def __init__(self, factory):
        widgets.AbstractBindingList.__init__(self, factory)
        factory.connect("event-added", self._on_added)
        factory.connect("event-removed", self._on_removed)
        factory.connect("event-changed", self._on_changed)

    def __dispose__(self):
        self._factory.disconnect("event-added", self._on_added)
        self._factory.disconnect("event-removed", self._on_removed)
        self._factory.disconnect("event-changed", self._on_changed)

    def __iter__(self):
        return self._factory.iter_events()


class VBGUI(TopologyMixin, ReadmeMixin, _Root):
    """
    The main GUI object for virtualbricks, containing all the configuration for
    the widgets and the connections to the main engine.
    """

    __bricks_binding_list = None
    __events_binding_list = None

    def __init__(self, factory, textbuffer=None):
        self.factory = self.brickfactory = factory
        self.build_ui()
        self.config = settings
        self.messages_buffer = textbuffer

        logger.info(start_virtualbricks)
        self.__initialize_components()
        factory.connect("brick-changed", self.on_brick_changed)
        factory.connect("brick-added", self.on_brick_changed)
        factory.connect("brick-removed", self.on_brick_changed)
        if settings.get("systray"):
            self.start_systray()
        task.LoopingCall(self.running_filter.refilter).start(2)
        self.__state_manager = StateManager()
        state_add_selection(self.__state_manager, self.bricks_view,
                            self.__brick_selected, _("No brick selected"),
                            self.configure_brick_button)
        state_add_selection(self.__state_manager, self.events_view,
                            self.__event_selected, _("No event selected"),
                            self.configure_event_button)
        self.init(factory)

        # Check GUI prerequisites
        self.__complain_on_missing_prerequisites()

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

        # running_filter (Gtk.TreeModelFilter)
        self.running_filter = Gtk.TreeModelFilter(child_model=self.bricks_store)

        # events_store (widgets.List)
        # Custom widget from glade-catalog.xml
        self.events_store = widgets.List()

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
        file_new_item = Gtk.ImageMenuItem(
            label="gtk-new",
            visible=True,
            can_focus=False,
            use_underline=True,
            use_stock=True,
        )
        menu1.append(file_new_item)
        separatormenuitem1 = Gtk.SeparatorMenuItem(
            visible=True,
            can_focus=False,
        )
        menu1.append(separatormenuitem1)
        file_open_item = Gtk.ImageMenuItem(
            label="gtk-open",
            visible=True,
            can_focus=False,
            use_underline=True,
            use_stock=True,
        )
        menu1.append(file_open_item)
        file_rename_item = Gtk.MenuItem(
            visible=True,
            can_focus=False,
            label=_("_Rename project"),
            use_underline=True,
        )
        menu1.append(file_rename_item)
        file_save_item = Gtk.ImageMenuItem(
            label="gtk-save",
            visible=True,
            can_focus=False,
            use_underline=True,
            use_stock=True,
        )
        menu1.append(file_save_item)
        file_save_as_item = Gtk.ImageMenuItem(
            label="gtk-save-as",
            visible=True,
            can_focus=False,
            use_underline=True,
            use_stock=True,
        )
        menu1.append(file_save_as_item)
        file_import_item = Gtk.MenuItem(
            visible=True,
            can_focus=False,
            label=_("_Import project"),
            use_underline=True,
        )
        menu1.append(file_import_item)
        file_export_item = Gtk.MenuItem(
            visible=True,
            can_focus=False,
            label=_("E_xport project"),
            use_underline=True,
        )
        menu1.append(file_export_item)
        file_delete_item = Gtk.MenuItem(
            visible=True,
            can_focus=False,
            label=_("_Delete project"),
            use_underline=True,
        )
        menu1.append(file_delete_item)
        separatormenuitem3 = Gtk.SeparatorMenuItem(
            visible=True,
            can_focus=False,
        )
        menu1.append(separatormenuitem3)
        file_quit_item = Gtk.ImageMenuItem(
            label="gtk-quit",
            visible=True,
            can_focus=False,
            use_underline=True,
            use_stock=True,
        )
        menu1.append(file_quit_item)
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
        vbox16 = Gtk.Box(
            visible=True,
            can_focus=False,
            orientation=Gtk.Orientation.VERTICAL,
        )
        toolbar2 = Gtk.Toolbar(
            visible=True,
            can_focus=False,
            toolbar_style=Gtk.ToolbarStyle.BOTH,
        )
        new_event_button = Gtk.ToolButton(
            visible=True,
            can_focus=False,
            label=_("New Event"),
            use_underline=True,
            stock_id="gtk-new",
        )
        toolbar2.insert(new_event_button, -1)
        separatortoolitem2 = Gtk.SeparatorToolItem(
            visible=True,
            can_focus=False,
        )
        toolbar2.insert(separatortoolitem2, -1)
        separatortoolitem2.set_homogeneous(False)
        start_all_events_button = Gtk.ToolButton(
            visible=True,
            can_focus=False,
            label=_("Start All Events"),
            use_underline=True,
            stock_id="gtk-media-play",
        )
        toolbar2.insert(start_all_events_button, -1)
        stop_all_events_button = Gtk.ToolButton(
            visible=True,
            can_focus=False,
            label=_("Stop All Events"),
            use_underline=True,
            stock_id="gtk-media-stop",
        )
        toolbar2.insert(stop_all_events_button, -1)
        separatortoolitem4 = Gtk.SeparatorToolItem(
            visible=True,
            can_focus=False,
        )
        toolbar2.insert(separatortoolitem4, -1)
        separatortoolitem4.set_homogeneous(False)
        self.configure_event_button = Gtk.ToolButton(
            visible=True,
            sensitive=False,
            can_focus=False,
            label=_("Configure"),
            use_underline=True,
            stock_id="gtk-edit",
        )
        toolbar2.insert(self.configure_event_button, -1)
        vbox16.pack_start(toolbar2, False, False, 0)
        events_scrolledwindow = Gtk.ScrolledWindow(
            visible=True,
            can_focus=True,
            shadow_type=Gtk.ShadowType.IN,
        )
        # Custom widget from glade-catalog.xml
        self.events_view = widgets.TreeView(
            visible=True,
            can_focus=True,
            model=self.events_store,
            headers_clickable=False,
        )
        tvc_event_icon = Gtk.TreeViewColumn.new()
        tvc_event_icon.set_properties(title=_("Icon"))
        # Custom widget from glade-catalog.xml
        crp2 = widgets.CellRendererBrickIcon()
        tvc_event_icon.pack_start(crp2, False)
        self.events_view.append_column(tvc_event_icon)
        tvc_event_status = Gtk.TreeViewColumn.new()
        tvc_event_status.set_properties(title=_("Status"))
        # Custom widget from glade-catalog.xml
        crt5 = widgets.CellRendererFormattable(
            format_string="s",
            formatting_enabled=True,
        )
        tvc_event_status.pack_start(crt5, False)
        self.events_view.append_column(tvc_event_status)
        tvc_event_name = Gtk.TreeViewColumn.new()
        tvc_event_name.set_properties(title=_("Name"))
        # Custom widget from glade-catalog.xml
        crt6 = widgets.CellRendererFormattable(
            format_string="n",
            formatting_enabled=True,
        )
        tvc_event_name.pack_start(crt6, False)
        self.events_view.append_column(tvc_event_name)
        tvc_event_params = Gtk.TreeViewColumn.new()
        tvc_event_params.set_properties(title=_("Parameters"))
        # Custom widget from glade-catalog.xml
        crt7 = widgets.CellRendererFormattable(
            format_string="p",
            formatting_enabled=True,
        )
        tvc_event_params.pack_start(crt7, False)
        self.events_view.append_column(tvc_event_params)
        events_scrolledwindow.add(self.events_view)
        vbox16.pack_start(events_scrolledwindow, True, True, 0)
        event_label = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("_Events"),
            use_underline=True,
        )
        self.main_notebook.append_page(vbox16, event_label)
        scrolledwindow1 = Gtk.ScrolledWindow(
            visible=True,
            can_focus=True,
            shadow_type=Gtk.ShadowType.IN,
        )
        # Custom widget from glade-catalog.xml
        self.jobs_view = widgets.TreeView(
            visible=True,
            can_focus=True,
            model=self.running_filter,
        )
        tvc_job_icon = Gtk.TreeViewColumn.new()
        tvc_job_icon.set_properties(title=_("Icon"))
        # Custom widget from glade-catalog.xml
        crp3 = widgets.CellRendererBrickIcon()
        tvc_job_icon.pack_start(crp3, False)
        self.jobs_view.append_column(tvc_job_icon)
        tvc_job_pid = Gtk.TreeViewColumn.new()
        tvc_job_pid.set_properties(title=_("Pid"))
        # Custom widget from glade-catalog.xml
        crt8 = widgets.CellRendererFormattable(
            format_string="d",
            formatting_enabled=True,
        )
        tvc_job_pid.pack_start(crt8, False)
        self.jobs_view.append_column(tvc_job_pid)
        tvc_job_type = Gtk.TreeViewColumn.new()
        tvc_job_type.set_properties(title=_("Type"))
        # Custom widget from glade-catalog.xml
        crt9 = widgets.CellRendererFormattable(
            format_string="t",
            formatting_enabled=True,
        )
        tvc_job_type.pack_start(crt9, False)
        self.jobs_view.append_column(tvc_job_type)
        tvc_job_name = Gtk.TreeViewColumn.new()
        tvc_job_name.set_properties(title=_("Name"))
        # Custom widget from glade-catalog.xml
        crt10 = widgets.CellRendererFormattable(
            format_string="n",
            formatting_enabled=True,
        )
        tvc_job_name.pack_start(crt10, False)
        self.jobs_view.append_column(tvc_job_name)
        scrolledwindow1.add(self.jobs_view)
        running_components_label = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("R_unning"),
            use_underline=True,
            yalign=0.47999998927116394,
        )
        self.main_notebook.append_page(
            scrolledwindow1,
            running_components_label,
        )
        vbox17 = Gtk.Box(
            visible=True,
            can_focus=False,
            orientation=Gtk.Orientation.VERTICAL,
        )
        hbox47 = Gtk.Box(visible=True, can_focus=False)
        export_topology_button = Gtk.Button(
            visible=True,
            can_focus=True,
            receives_default=True,
        )
        hbox48 = Gtk.Box(visible=True, can_focus=False)
        image13 = Gtk.Image(
            visible=True,
            can_focus=False,
            stock="gtk-save-as",
        )
        hbox48.pack_start(image13, True, True, 0)
        label18 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("Export as Image"),
        )
        hbox48.pack_start(label18, True, True, 0)
        export_topology_button.add(hbox48)
        hbox47.pack_start(export_topology_button, False, True, 0)
        topology_lr = Gtk.RadioButton(
            label=_("Expand Horizontally"),
            visible=True,
            can_focus=True,
            receives_default=False,
            xalign=0.5,
            active=True,
            draw_indicator=True,
        )
        hbox47.pack_start(topology_lr, False, True, 0)
        self.topology_vertical_radio = Gtk.RadioButton(
            label=_("Expand Vertically"),
            visible=True,
            can_focus=True,
            receives_default=False,
            xalign=0.5,
            draw_indicator=True,
            group=topology_lr,
        )
        hbox47.pack_start(self.topology_vertical_radio, False, True, 0)
        vbox17.pack_start(hbox47, False, True, 0)
        self.topology_scrolled = Gtk.ScrolledWindow(
            visible=True,
            can_focus=True,
            shadow_type=Gtk.ShadowType.IN,
        )
        viewport1 = Gtk.Viewport(
            visible=True,
            can_focus=False,
            resize_mode=Gtk.ResizeMode.QUEUE,
        )
        self.topology_image = Gtk.Image(
            visible=True,
            can_focus=False,
            xalign=0,
            yalign=0,
            stock="gtk-missing-image",
        )
        viewport1.add(self.topology_image)
        self.topology_scrolled.add(viewport1)
        vbox17.pack_start(self.topology_scrolled, True, True, 0)
        label20 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("_Topology"),
            use_underline=True,
        )
        self.main_notebook.append_page(vbox17, label20)
        scrolledwindow2 = Gtk.ScrolledWindow(visible=True, can_focus=True)
        self.readme_text = Gtk.TextView(visible=True, can_focus=True)
        scrolledwindow2.add(self.readme_text)
        label1 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("Readme"),
        )
        self.main_notebook.append_page(scrolledwindow2, label1)
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
        file_save_as_item.connect(
            "activate",
            self.on_file_save_as_item_activate,
        )
        file_import_item.connect(
            "activate",
            self.on_file_import_item_activate,
        )
        file_export_item.connect(
            "activate",
            self.on_file_export_item_activate,
        )
        file_delete_item.connect(
            "activate",
            self.on_file_delete_item_activate,
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
            "change-current-page",
            self.on_main_notebook_change_current_page,
        )
        self.main_notebook.connect(
            "select-page",
            self.on_main_notebook_select_page,
        )
        self.main_notebook.connect(
            "switch-page",
            self.on_main_notebook_switch_page,
        )
        new_brick_button.connect("clicked", self.on_new_brick_button_clicked)
        start_all_button.connect("clicked", self.on_start_all_button_clicked)
        stop_all_button.connect("clicked", self.on_stop_all_button_clicked)
        self.configure_brick_button.connect("clicked", self.on_configure_brick_button_clicked)
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
        new_event_button.connect("clicked", self.on_new_event_button_clicked)
        start_all_events_button.connect(
            "clicked",
            self.on_start_all_events_button_clicked,
        )
        stop_all_events_button.connect(
            "clicked",
            self.on_stop_all_events_button_clicked,
        )
        self.configure_event_button.connect(
            "clicked",
            self.on_configure_event_button_clicked,
        )
        self.events_view.connect(
            "button-release-event",
            self.on_events_view_button_release_event,
        )
        self.events_view.connect(
            "key-release-event",
            self.on_events_view_key_release_event,
        )
        self.events_view.connect(
            "row-activated",
            self.on_events_view_row_activated,
        )
        self.jobs_view.connect(
            "button-release-event",
            self.on_jobs_view_button_release_event,
        )
        export_topology_button.connect(
            "clicked",
            self.on_topology_export_button_clicked,
        )
        topology_lr.connect(
            "toggled",
            self.on_topology_orientation_toggled,
        )
        viewport1.connect("button-press-event", self.on_topology_action)
        systray_toggle_item.connect(
            "activate",
            self.on_systray_toggle_item_activate,
        )
        systray_close_item.connect("activate", self.do_quit)
        self.status_icon.connect("activate", self.on_status_icon_activate)
        self.status_icon.connect("popup-menu", self.on_status_icon_popup_menu)

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
            Gdk.DragAction.LINK
        )
        self.bricks_view.enable_model_drag_dest(
            BRICK_DRAG_TARGETS,
            Gdk.DragAction.LINK
        )

        # events tab
        self.events_view.set_cells_data_func()
        self.__events_binding_list = EventsBindingList(self.factory)
        self.events_store.set_data_source(self.__events_binding_list)

        # jobs tab
        self.jobs_view.set_cells_data_func()
        self.running_filter.set_visible_func(is_running_filter)

    def __complain_on_missing_prerequisites(self):
        qmissing, _ = tools.check_missing_qemu()
        vmissing = tools.check_missing_vde()
        missing = vmissing + qmissing

        if not tools.check_ksm():
            settings.set("ksm", False)
            missing.append("ksm")
        missing_text = []
        missing_components = []
        if len(missing) > 0 and settings.show_missing:
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
                components=" ".join(missing_components)
            )

    def __dispose__(self):
        self.factory.disconnect("brick-changed", self.on_brick_changed)
        self.factory.disconnect("brick-added", self.on_brick_changed)
        self.factory.disconnect("brick-removed", self.on_brick_changed)
        if self.__bricks_binding_list is not None:
            dispose(self.__bricks_binding_list)
            self.__bricks_binding_list = None
        if self.__events_binding_list is not None:
            dispose(self.__events_binding_list)
            self.__events_binding_list = None

    def get_object(self, name):
        return getattr(self, name, None)

    """ ********************************************************     """
    """ Signal handlers                                           """
    """ ********************************************************     """

    def on_brick_changed(self, brick):
        self.draw_topology()

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
        self.set_title("Virtualbricks (Configuring Brick %s)" %
                       brick.get_name())

    def set_title(self, title=None):
        if title is None:
            if project.manager.current:
                name = project.manager.current.name
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

    def on_main_notebook_switch_page(self, notebook, _, page_num):
        super(VBGUI, self).on_main_notebook_switch_page(notebook, _, page_num)
        return True

    def on_main_notebook_select_page(self, notebook, move_focus):
        super(VBGUI, self).on_main_notebook_select_page(notebook, move_focus)
        return True

    def on_main_notebook_change_current_page(self, notebook, offset):
        super(VBGUI, self).on_main_notebook_change_current_page(notebook,
                                                                offset)
        return True

    # gui (programming) interface

    def init(self, factory):
        super(VBGUI, self).init(factory)

    def on_quit(self, factory):
        dispose(self)
        super(VBGUI, self).on_quit(factory)

    def on_save(self):
        super(VBGUI, self).on_save()
        project.manager.save_current(self.brickfactory)

    def on_open(self, name):
        self.on_save()
        prj = project.manager.get_project(name)
        prj.open(self.brickfactory)
        super(VBGUI, self).on_open(name)

    def on_new(self, name):
        self.on_save()
        prj = project.manager.get_project(name)
        prj.create()
        prj.open(self.brickfactory)
        super(VBGUI, self).on_new(name)

    def do_quit(self, *_):
        self.factory.quit()
        return True

    # end gui (programming) interface

    def on_window_delete_event(self, window, event):
        # don't delete; hide instead
        if settings.get("systray"):
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

    def on_events_view_key_release_event(self, treeview, event):
        if Gdk.keyval_name(event.keyval) in set(["Delete", "BackSpace"]):
            event = treeview.get_selected_value()
            if event is not None:
                self.ask_remove_event(event)

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
        dialog = NewProjectDialog(self)
        dialog.on_destroy = self.set_title
        dialog.show(self.window)
        return True

    def on_file_open_item_activate(self, menuitem):
        OpenProjectDialog(self).show(self.window)
        return True

    def on_file_rename_item_activate(self, menuitem):
        dialog = RenameProjectDialog(self)
        dialog.on_destroy = self.set_title
        dialog.show(self.window)
        return True

    def on_file_save_item_activate(self, menuitem):
        self.on_save()
        return True

    def on_file_save_as_item_activate(self, menuitem):
        self.on_save()
        SaveProjectAsDialog(self.brickfactory).show(self.window)
        return True

    def on_file_import_item_activate(self, menuitem):
        d = ImportDialog(self.brickfactory)
        d.on_destroy = self.set_title
        d.show(self.window)
        return True

    def on_file_export_item_activate(self, menuitem):
        self.on_save()
        dialog = ExportProjectDialog(
            ProgressBar(self),
            filepath.FilePath(project.manager.current.path),
            self.brickfactory.iter_disk_images()
        )
        dialog.show(self.window)
        return True

    def on_file_delete_item_activate(self, menuitem):
        DeleteProjectDialog(self).show(self.window)
        return True

    def on_settings_preferences_item_activate(self, menuitem):
        SettingsDialog(self).show(self.window)
        return True

    def on_view_messages_item_activate(self, menuitem):
        LoggingWindow(self.messages_buffer).show()
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

        l = [brick.poweron() for brick in self.brickfactory.bricks]
        defer.DeferredList(l, consumeErrors=True).addCallback(started_all)
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

    # events toolbar

    def on_new_event_button_clicked(self, toolbutton):
        NewEventDialog(self).show(self.window)
        return True

    def on_start_all_events_button_clicked(self, toolbutton):
        for event in self.brickfactory.iter_events():
            event.poweron()
        return True

    def on_stop_all_events_button_clicked(self, toolbutton):
        for event in self.brickfactory.iter_events():
            event.poweroff()
        return True

    def on_configure_event_button_clicked(self, toolbutton):
        return self.__show_config_if_selected(self.events_view)

    def confirm(self, message):
        dialog = Gtk.MessageDialog(
            None,
            Gtk.DialogFlags.MODAL,
            Gtk.MessageType.INFO,
            Gtk.ButtonsType.YES_NO,
            message
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

    def on_events_view_button_release_event(self, treeview, event):
        return self.on_bricks_view_button_release_event(treeview, event)

    def on_bricks_view_row_activated(self, treeview, path, column):
        model = treeview.get_model()
        brick = model.get_value(model.get_iter(path), 0)
        self.startstop_brick(brick)

    def on_events_view_row_activated(self, treeview, path, column):
        model = treeview.get_model()
        event = model.get_value(model.get_iter(path), 0)
        event.toggle()

    def startstop_brick(self, brick):
        if is_running(brick):
            brick.poweroff().addErrback(logger.failure_eb, stop_error)
        else:
            brick.poweron().addErrback(logger.failure_eb, start_error)

    def on_jobs_view_button_release_event(self, treeview, event):
        if event.button == 3:
            pthinfo = treeview.get_path_at_pos(int(event.x), int(event.y))
            if pthinfo is not None:
                path, col, cellx, celly = pthinfo
                treeview.grab_focus()
                treeview.set_cursor(path, col, 0)
                model = treeview.get_model()
                brick = model.get_value(model.get_iter(path), 0)
                menu = IJobMenu(brick)
                menu.popup(event.button, event.time, self)
                return True

    def user_wait_action(self, action, *args):
        ProgressBar(self).wait_for(action, *args)

    def set_insensitive(self):
        self.window.set_sensitive(False)

    def set_sensitive(self):
        self.window.set_sensitive(True)

    # Bricks tab signals

    def on_bricks_view_drag_data_get(self, treeview, context, selection,
                                         info, time):
        brick = treeview.get_selected_value()
        selection.set(selection.target, 8, brick.get_name())
        return True

    def on_bricks_view_drag_data_received(self, treeview, context, x, y,
                                              selection, info, time):
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
                            log.info(dnd_no_socks)
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

    def on_events_selection_changed(self, selection):
        self.__state_event_config.check()

    def __event_selected(self):
        return bool(self.events_view.get_selected_value())
