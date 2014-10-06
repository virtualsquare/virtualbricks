# Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
# Copyright (C) 2013 Virtualbricks team

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

import os
import sys

import gobject
import gtk
import gtk.glade

from twisted.internet import error, defer, task, protocol, reactor
from zope.interface import implementer

from virtualbricks import tools, settings, project, log, brickfactory

from virtualbricks.gui import _gui, graphics, dialogs, interfaces, widgets


if False:  # pyflakes
    _ = str
    _gui.logger

logger = log.Logger()
sync_error = log.Event("Sync terminated unexpectedly")
create_image_error = log.Event("Create image terminated unexpectedly")
drawing_topology = log.Event("drawing topology")
top_invalid_format = log.Event("Error saving topology: Invalid image format")
top_write_error = log.Event("Error saving topology: Could not write file")
top_unknown = log.Event("Error saving topology: Unknown error")
start_virtualbricks = log.Event("Starting VirtualBricks")
components_not_found = log.Event("{text}\nThere are some components not "
    "found: {components} some functionalities may not be available.\nYou can "
    "disable this alert from the general settings.")
brick_invalid_name = log.Event("Cannot create brick: Invalid name.")
create_image_error = log.Event("Error on creating image")
apply_settings = log.Event("Apply settings...")
create_image = log.Event("Image creating.. ")
filename_empty = log.Event("Choose a filename first!")
not_started = log.Event("Brick not started.")
stop_error = log.Event("Error on stopping brick.")
start_error = log.Event("Error on starting brick.")
no_kvm = log.Event("No KVM support found on the local system. Check your "
    "active configuration. KVM will stay disabled.")
cannot_write = log.Event("Cannot write to the specified location")
select_file = log.Event("Select a file")
dnd_no_socks = log.Event("I don't know what to do, bricks have no socks.")
dnd_dest_brick_not_found = log.Event("Cannot found dest brick")
dnd_source_brick_not_found = log.Event("Cannot find source brick {name}")
dnd_no_dest = log.Event("No destination brick")
dnd_same_brick = log.Event("Source and destination bricks are the same.")

BRICK_TARGET_NAME = "brick-connect-target"
BRICK_DRAG_TARGETS = [
    (BRICK_TARGET_NAME, gtk.TARGET_SAME_WIDGET | gtk.TARGET_SAME_APP, 0)
]


class SyncProtocol(protocol.ProcessProtocol):

    def __init__(self, done):
        self.done = done

    def processEnded(self, status):
        if isinstance(status.value, error.ProcessTerminated):
            logger.failure(sync_error, status)
            self.done.errback(None)
        else:
            self.done.callback(None)


class QemuImgCreateProtocol(protocol.ProcessProtocol):

    def __init__(self, done):
        self.done = done

    def processEnded(self, status):
        if isinstance(status.value, error.ProcessTerminated):
            logger.failure(create_image_error, status)
            self.done.errback(None)
        else:
            reactor.spawnProcess(SyncProtocol(self.done), "sync", ["sync"],
                os.environ)


def changed(brick, row):
    if row.valid():
        path = row.get_path()
        model = row.get_model()
        model.row_changed(path, model.get_iter(path))
    return brick


def changed_brick_in_model(result, model):
    try:
        brick, status = result
    except TypeError:
        brick = result
    for path, brick_ in enumerate(model):
        if brick is brick_:
            model.row_changed(path, model.get_iter(path))
            break
    return result


BRICKS_TAB, EVENTS_TAB, RUNNING_TAB, TOPOLOGY_TAB, README_TAB = range(5)


class TopologyMixin(object):

    __should_draw_topology = False
    __topology = None

    # public interface

    def draw_topology(self, export=""):
        if self.get_object("main_notebook").get_current_page() == TOPOLOGY_TAB:
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
                if response_id == gtk.RESPONSE_OK:
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

        chooser = gtk.FileChooserDialog(title=_("Select an image file"),
                action=gtk.FILE_CHOOSER_ACTION_OPEN,
                buttons=(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                        gtk.STOCK_SAVE, gtk.RESPONSE_OK))
        chooser.set_do_overwrite_confirmation(True)
        chooser.connect("response", on_response)
        chooser.show()

    def on_topology_action(self, widget, event):
        self._draw_topology_if_needed()
        assert self.__topology, "Topology not created"
        brick = self._get_brick_in(*event.get_coords())
        if brick:
            if event.button == 3:
                menu = interfaces.IMenu(brick, None)
                menu.popup(event.button, event.time, self)
            elif event.button == 1 and event.type == gtk.gdk._2BUTTON_PRESS:
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
        topology_scrolled = self.get_object("topology_scrolled")
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
        if self.get_object('topology_tb').get_active():
            orientation = "TB"
        else:
            orientation = "LR"
        self.__topology = graphics.Topology(
            self.get_object('image_topology'),
            self.brickfactory.bricks, 1.00, orientation,
            settings.VIRTUALBRICKS_HOME)
        self.__should_draw_topology = False


class ReadmeMixin(object):

    __deleyed_call = None

    def __get_buffer(self):
        return self.get_object("readme_textview").get_buffer()

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
            project.current.set_description(self.__get_text())
            self.__set_modified(False)

    def __load_readme(self):
        buf = self.__get_buffer()
        buf.handler_block_by_func(self.__on_modify)
        try:
            self.__set_text(project.current.get_description())
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

    def on_quit(self):
        self.__cancel_delayed_save()
        self.__save_readme()
        super(ReadmeMixin, self).on_quit()


class ProgressBar:

    def __init__(self, gui):
        self.freezer = dialogs.Freezer(gui.set_insensitive, gui.set_sensitive,
            gui.get_object("main_win"))

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

    def on_quit(self):
        pass

    def on_save(self):
        pass

    def on_open(self, name):
        pass

    def on_new(self, name):
        pass


class VBGUI(TopologyMixin, ReadmeMixin, _Root):
    """
    The main GUI object for virtualbricks, containing all the configuration for
    the widgets and the connections to the main engine.
    """

    def __init__(self, factory, gladefile, quit, textbuffer=None):
        self.brickfactory = self.factory = factory
        self.gladefile = gladefile
        self.messages_buffer = textbuffer
        self.quit_d = quit
        self.wndMain = gladefile.get_widget("main_win")
        TopologyMixin.__init__(self)

        self.widg = self.get_widgets(self.widgetnames())

        logger.info(start_virtualbricks)

        # Connect all the signal from the factory to specific callbacks
        self.__row_changed_h = factory.bricks.connect("row-changed",
                self.on_bricks_model_changed)
        self.__row_deleted_h = factory.bricks.connect("row-deleted",
                self.on_bricks_model_deleted)
        factory.connect("brick-changed", self.on_brick_changed, factory.bricks)

        # General settings (system properties)
        self.config = settings

        # Show the main window
        self.widg['main_win'].show()
        self.get_object("main_win").connect("delete-event", self.delete_event)

        # Set two useful file filters
        self.vbl_filter = gtk.FileFilter()
        self.vbl_filter.set_name(_("Virtualbricks Bricks List") + " (*.vbl)")
        self.vbl_filter.add_pattern("*.vbl")
        self.all_files_filter = gtk.FileFilter()
        self.all_files_filter.set_name(_("All files"))
        self.all_files_filter.add_pattern("*")

        self.setup_bricks()
        self.setup_events()
        self.setup_joblist()

        self.statusicon = None
        self.progressbar = ProgressBar(self)

        ''' Tray icon '''
        if settings.systray:
            self.start_systray()

        ''' Set the settings panel to bottom '''
        self.curtain = self.get_object('vpaned_mainwindow')
        self.curtain_down()

        ''' Reset the selections for the TWs'''
        self.vmplug_selected = None
        self.joblist_selected = None

        ''' Initialize threads, timers etc.'''
        self.gladefile.signal_autoconnect(self)
        task.LoopingCall(self.running_bricks.refilter).start(2)

        ''' Check GUI prerequisites '''
        missing = self.check_gui_prerequisites()
        self.disable_config_kvm = False
        self.disable_config_ksm = False
        missing_text = ""
        missing_components = ""
        if len(missing) > 0 and settings.show_missing:
            for m in missing:
                if m == "kvm":
                    settings.set("kvm", "False")
                    self.disable_config_kvm = True
                    missing_text = (missing_text + "KVM not found: kvm support"
                                    " will be disabled.\n")
                elif m == "ksm":
                    settings.set("kvm", "True")
                    self.disable_config_ksm = True
                    missing_text = (missing_text + "KSM not found in Linux. "
                                    "Samepage memory will not work on this "
                                    "system.\n")
                else:
                    missing_components = missing_components + ('%s ' % m)
            logger.error(components_not_found, text=missing_text,
                components=missing_components)

        # Setup window global state pattern
        self.__state_manager = _gui.StateManager()
        # enable brick config button only if a brick is selected
        self.__config_brick_btn_state = self.__state_manager._build_state(
            None, self.get_object("configure_brick_toolbutton"))
        self.__config_brick_btn_state.add_prerequisite(
            self.__brick_selected)
        # enable event config button only if a brick is selected
        self.__config_event_btn_state = self.__state_manager._build_state(
            None, self.get_object("configure_event_toolbutton"))
        self.__config_event_btn_state.add_prerequisite(
            self.__event_selected)
        self.init(factory)

        # attach the quit callback at the end, so it is not called if an
        # exception is raised before because of a syntax error of another kind
        # of error
        quit.addCallback(lambda _: self.on_quit())

    def quit(self):
        self.brickfactory.bricks.disconnect(self.__row_changed_h)
        self.brickfactory.bricks.disconnect(self.__row_deleted_h)
        self.brickfactory.disconnect("brick-changed", self.on_brick_changed,
                                     self.brickfactory.bricks)
        self.__row_changed_h = None
        self.__row_deleted_h = None

    def __setup_treeview(self, resource, window_name, widget_name):
        ui = graphics.get_data("virtualbricks.gui", resource)
        builder = gtk.Builder()
        builder.add_from_string(ui)
        builder.connect_signals(self)
        window = self.get_object(window_name)
        widget = builder.get_object(widget_name)
        widget.reparent(window)
        return builder

    def setup_joblist(self):
        builder = self.__setup_treeview("data/joblist.ui", "scrolledwindow1",
                                        "joblist_treeview")

        def set_icon(column, cell_renderer, model, iter):
            brick = model.get_value(iter, 0)
            pixbuf = graphics.pixbuf_for_brick_at_size(brick, 48, 48)
            cell_renderer.set_property("pixbuf", pixbuf)

        def set_pid(column, cell_renderer, model, iter):
            brick = model.get_value(iter, 0)
            if brick.pid == -10:
                pid = "python-thread   "
            else:
                pid = str(brick.pid)
            cell_renderer.set_property("text", pid)

        def set_type(column, cell_renderer, model, iter):
            brick = model.get_value(iter, 0)
            cell_renderer.set_property("text", brick.get_type())

        def set_name(column, cell_renderer, model, iter):
            brick = model.get_value(iter, 0)
            cell_renderer.set_property("text", brick.name)

        icon_c = builder.get_object("icon_treeviewcolumn")
        icon_cr = builder.get_object("icon_cellrenderer")
        icon_c.set_cell_data_func(icon_cr, set_icon)
        pid_c = builder.get_object("pid_treeviewcolumn")
        pid_cr = builder.get_object("pid_cellrenderer")
        pid_c.set_cell_data_func(pid_cr, set_pid)
        type_c = builder.get_object("type_treeviewcolumn")
        type_cr = builder.get_object("type_cellrenderer")
        type_c.set_cell_data_func(type_cr, set_type)
        name_c = builder.get_object("name_treeviewcolumn")
        name_cr = builder.get_object("name_cellrenderer")
        name_c.set_cell_data_func(name_cr, set_name)
        self.running_bricks = self.brickfactory.bricks.filter_new()

        def is_running(model, iter):
            brick = model.get_value(iter, 0)
            return brick and brick.proc is not None

        self.running_bricks.set_visible_func(is_running)
        builder.get_object("joblist_treeview").set_model(self.running_bricks)

    def setup_events(self):
        builder = self.__setup_treeview("data/events.ui",
            "events_scrolledwindow", "events_treeview")

        def set_icon(column, cell_renderer, model, iter):
            event = model.get_value(iter, 0)
            pixbuf = graphics.pixbuf_for_brick_at_size(event, 48, 48)
            cell_renderer.set_property("pixbuf", pixbuf)

        def set_status(column, cell_renderer, model, iter):
            event = model.get_value(iter, 0)
            cell_renderer.set_property("text", event.get_state())

        def set_name(column, cell_renderer, model, iter):
            event = model.get_value(iter, 0)
            cell_renderer.set_property("text", event.name)

        def set_parameters(column, cell_renderer, model, iter):
            event = model.get_value(iter, 0)
            cell_renderer.set_property("text", event.get_parameters())

        icon_c = builder.get_object("icon_treeviewcolumn")
        icon_cr = builder.get_object("icon_cellrenderer")
        icon_c.set_cell_data_func(icon_cr, set_icon)
        status_c = builder.get_object("status_treeviewcolumn")
        status_cr = builder.get_object("status_cellrenderer")
        status_c.set_cell_data_func(status_cr, set_status)
        name_c = builder.get_object("name_treeviewcolumn")
        name_cr = builder.get_object("name_cellrenderer")
        name_c.set_cell_data_func(name_cr, set_name)
        parameters_c = builder.get_object("parameters_treeviewcolumn")
        parameters_cr = builder.get_object("parameters_cellrenderer")
        parameters_c.set_cell_data_func(parameters_cr, set_parameters)
        self.__events_treeview = builder.get_object("events_treeview")
        self.__events_treeview.set_model(self.brickfactory.events)
        selection = self.__events_treeview.get_selection()
        selection.connect("changed", self.on_events_selection_changed)

    def setup_bricks(self):
        builder = self.__setup_treeview("data/bricks.ui",
            "bricks_scrolledwindow", "bricks_treeview")

        def set_icon(column, cell_renderer, model, iter):
            brick = model.get_value(iter, 0)
            pixbuf = graphics.pixbuf_for_brick_at_size(brick, 48, 48)
            cell_renderer.set_property("pixbuf", pixbuf)

        def set_status(column, cell_renderer, model, iter):
            brick = model.get_value(iter, 0)
            cell_renderer.set_property("text", brick.get_state())

        def set_type(column, cell_renderer, model, iter):
            brick = model.get_value(iter, 0)
            cell_renderer.set_property("text", brick.get_type())

        def set_name(column, cell_renderer, model, iter):
            brick = model.get_value(iter, 0)
            cell_renderer.set_property("text", brick.name)

        def set_parameters(column, cell_renderer, model, iter):
            brick = model.get_value(iter, 0)
            cell_renderer.set_property("text", brick.get_parameters())

        icon_c = builder.get_object("icon_treeviewcolumn")
        icon_cr = builder.get_object("icon_cellrenderer")
        icon_c.set_cell_data_func(icon_cr, set_icon)
        status_c = builder.get_object("status_treeviewcolumn")
        status_cr = builder.get_object("status_cellrenderer")
        status_c.set_cell_data_func(status_cr, set_status)
        type_c = builder.get_object("type_treeviewcolumn")
        type_cr = builder.get_object("type_cellrenderer")
        type_c.set_cell_data_func(type_cr, set_type)
        name_c = builder.get_object("name_treeviewcolumn")
        name_cr = builder.get_object("name_cellrenderer")
        name_c.set_cell_data_func(name_cr, set_name)
        parameters_c = builder.get_object("parameters_treeviewcolumn")
        parameters_cr = builder.get_object("parameters_cellrenderer")
        parameters_c.set_cell_data_func(parameters_cr, set_parameters)
        self.__bricks_treeview = tv = builder.get_object("bricks_treeview")
        tv.set_model(self.brickfactory.bricks)
        tv.enable_model_drag_source(gtk.gdk.BUTTON1_MASK, BRICK_DRAG_TARGETS,
                                    gtk.gdk.ACTION_LINK)
        tv.enable_model_drag_dest(BRICK_DRAG_TARGETS, gtk.gdk.ACTION_LINK)
        selection = tv.get_selection()
        selection.connect("changed", self.on_bricks_selection_changed)

    def check_gui_prerequisites(self):
        qmissing, _ = tools.check_missing_qemu(settings.get("qemupath"))
        vmissing = tools.check_missing_vde(settings.get("vdepath"))
        ksmissing = []
        if not os.access("/sys/kernel/mm/ksm", os.X_OK):
            ksmissing.append("ksm")
        return vmissing + qmissing + ksmissing

    def get_object(self, name):
        return self.gladefile.get_widget(name)

    def get_active(self, widget_name):
        return self.get_object(widget_name).get_active()

    def get_text(self, widget_name):
        return self.get_object(widget_name).get_text()

    """ ********************************************************     """
    """ Signal handlers                                           """
    """ ********************************************************     """

    def on_bricks_model_changed(self, model, path, itr):
        self.draw_topology()

    def on_bricks_model_deleted(self, model, path):
        self.draw_topology()

    def on_brick_changed(self, brick, model):
        itr = model.get_iter_first()
        while itr:
            if model.get(itr, 0)[0] == brick:
                model.row_changed(model.get_path(itr), itr)
                self.draw_topology()
                break
            itr = model.iter_next(itr)

    '''
    '    Systray management
    '''
    def start_systray(self):
        if self.statusicon is None:
            self.statusicon = gtk.StatusIcon()
            self.statusicon.set_from_file(
                graphics.get_image("virtualbricks.png"))
            self.statusicon.set_tooltip("VirtualBricks Visible")
            self.statusicon.connect('activate', self.on_systray_menu_toggle)
            systray_menu = self.get_object("systray_menu")
            self.statusicon.connect('popup-menu', self.systray_menu_popup,
                                    systray_menu)

        if not self.statusicon.get_visible():
            self.statusicon.set_visible(True)

    def systray_menu_popup(self, widget, button, time, data=None):
        if button == 3 and data:
            data.show_all()
            data.popup(None, None, None, 3, time)

    def stop_systray(self):
        if self.statusicon is not None and self.statusicon.get_visible():
            self.statusicon.set_visible(False)
            self.statusicon = None

    def systray_blinking(self, disable=False):
        if self.statusicon is not None and self.statusicon.get_visible():
            self.statusicon.set_blinking(not disable)

    '''
    '    Method to catch delete event from dialog windows.
    '    Hide the main window into systray.
    '''

    def delete_event(self, window, event):
        #don't delete; hide instead
        if settings.systray and self.statusicon is not None:
            self.get_object("main_win").hide_on_delete()
            self.statusicon.set_tooltip("VirtualBricks Hidden")
            return True
        return False

    def curtain_down(self):
        self.get_object("main_notebook").show()
        configframe = self.get_object("configframe")
        configpanel = configframe.get_child()
        if configpanel:
            configpanel.destroy()
            # configframe.remove(configpanel)
        configframe.hide()
        if project.current:
            self.set_title_default()

    def curtain_up(self, brick):
        configframe = self.get_object("configframe")
        configframe.add(interfaces.IConfigController(brick).get_view(self))
        configframe.show()
        self.get_object("main_notebook").hide()
        self.set_title("Virtualbricks (Configuring Brick %s)" %
                       brick.get_name())

    def __get_selection(self, treeview):
        selection = treeview.get_selection()
        if selection is not None:
            model, iter = selection.get_selected()
            if iter is not None:
                return model.get_value(iter, 0)

    '''
    '    populate a list of all the widget whose names
    '    are listed in parameter l
    '''
    def get_widgets(self, l):
        r = dict()
        for i in l:
            r[i] = self.get_object(i)
            r[i].hide()
        return r

    '''
    '    Returns a list with all the
    '    dialog windows names
    '''
    def widgetnames(self):
        return ['main_win',
        'menu_brickactions',
        'dialog_convertimage',
        ]

    def show_window(self, name):
        self.curtain_down()
        for w in self.widg.keys():
            if name == w or w == 'main_win':
                if w.startswith('menu'):
                    self.widg[w].popup(None, None, None, 3, 0)
                else:
                    self.widg[w].show()
            elif not name.startswith('menu'):
                self.widg[w].hide()

    def pixbuf_scaled(self, filename):
        if filename is None or filename == "":
                return None
        pixbuf = gtk.gdk.pixbuf_new_from_file(filename)
        width = pixbuf.get_width()
        height = pixbuf.get_height()
        if width <= height:
            new_height = 48 * height / width
            new_width = 48
        else:
            new_height = 48
            new_width = 48 * width / height
        pixbuf = pixbuf.scale_simple(new_width, new_height,
                                     gtk.gdk.INTERP_BILINEAR)
        return pixbuf

    def set_title(self, title):
        self.get_object("main_win").set_title(title)

    def set_title_default(self):
        self.set_title("Virtualbricks (project: {0})".format(
            project.current.name))

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

    def on_quit(self):
        super(VBGUI, self).on_quit()

    def on_save(self):
        super(VBGUI, self).on_save()
        project.current.save(self.brickfactory)

    def on_open(self, name):
        self.on_save()
        project.manager.open(name, self.brickfactory)
        super(VBGUI, self).on_open(name)

    def on_new(self, name):
        self.on_save()
        prj = project.manager.create(name, self.brickfactory)
        prj.restore(self.brickfactory)
        super(VBGUI, self).on_new(name)

    def do_quit(self):
        self.quit_d.callback(None)

    # end gui (programming) interface

    def on_main_win_destroy_event(self, window):
        self.do_quit()

    def on_new_image_menuitem_activate(self, menuitem):
        dialogs.choose_new_image(self, self.brickfactory)

    def on_image_library_menuitem_activate(self, menuitem):
        dialogs.DisksLibraryDialog(self.brickfactory).show()

    def ask_remove_brick(self, brick):
        if brick.proc is not None:
            other = _("\nThe brick is still running, it will be "
                    "killed before being deleted!")
        else:
            other = None
        self.__ask_for_deletion(self.brickfactory.del_brick, brick, other)

    def ask_remove_event(self, event):
        if event.scheduled is not None:
            other = _("The event is in use, it will be stopped before.")
        else:
            other = None
        self.__ask_for_deletion(self.brickfactory.del_event, event, other)

    def __ask_for_deletion(self, on_yes, what, secondary_text=None):
        question = _("Do you really want to delete %s (%s)?") % (
            what.name, what.get_type())
        dialog = dialogs.ConfirmDialog(question, on_yes=on_yes,
                on_yes_arg=what)
        if secondary_text is not None:
            dialog.format_secondary_text(secondary_text)
        dialog.window.set_transient_for(self.widg["main_win"])
        dialog.show()

    def on_bricks_treeview_key_release_event(self, treeview, event):
        if gtk.gdk.keyval_name(event.keyval) in set(["Delete", "BackSpace"]):
            brick = self.__get_selection(treeview)
            if brick is not None:
                self.ask_remove_brick(brick)

    def on_events_treeview_key_release_event(self, treeview, event):
        if gtk.gdk.keyval_name(event.keyval) in set(["Delete", "BackSpace"]):
            event = self.__get_selection(treeview)
            if event is not None:
                self.ask_remove_event(event)

    def on_systray_menu_toggle(self, widget=None, data=""):
        if self.statusicon.get_blinking():
            self.systray_blinking(True)
            return

        if not self.get_object("main_win").get_visible():
            self.get_object("main_win").show()
            self.curtain_down()
            self.statusicon.set_tooltip("the window is visible")
        else:
            self.get_object("main_win").hide()

    def on_systray_exit(self, widget=None, data=""):
        self.do_quit()

    def on_windown_destroy(self, widget=None, data=""):
        widget.hide()
        return True

    def confirm(self, message):
        dialog = gtk.MessageDialog(None, gtk.DIALOG_MODAL, gtk.MESSAGE_INFO,
                                   gtk.BUTTONS_YES_NO, message)
        response = dialog.run()
        dialog.destroy()

        if response == gtk.RESPONSE_YES:
            return True
        elif response == gtk.RESPONSE_NO:
            return False

    def selected_type(self, group):
        for button in group.get_group():
            if button.get_active():
                return button.name.split("_")[1]
        return "Switch"

    def set_sensitivegroup(self, l):
        for i in l:
            w = self.get_object(i)
            w.set_sensitive(True)

    def set_nonsensitivegroup(self, l):
        for i in l:
            w = self.get_object(i)
            w.set_sensitive(False)

    def on_item_quit_activate(self, menuitem):
        self.do_quit()

    def on_item_settings_activate(self, menuitem):
        dialogs.SettingsDialog(self).show(self.wndMain)
        return True

    def on_item_about_activate(self, widget=None, data=""):
        dialogs.AboutDialog().show()

    def on_toolbutton_start_all_clicked(self, widget=None, data=""):

        def started_all(results):
            for success, value in results:
                if not success:
                    logger.failure(not_started, value)
            self.running_bricks.refilter()

        self.curtain_down()
        bricks = self.brickfactory.bricks
        l = []
        for idx, brick in enumerate(bricks):
            d = brick.poweron()
            d.addCallback(changed, gtk.TreeRowReference(bricks, idx))
            l.append(d)
        defer.DeferredList(l, consumeErrors=True).addCallback(started_all)

    def on_toolbutton_stop_all_clicked(self, widget=None, data=""):

        def stopped_all(results):
            self.running_bricks.refilter()

        self.curtain_down()
        bricks = self.brickfactory.bricks
        l = []
        for idx, brick in enumerate(bricks):
            d = brick.poweroff()
            d.addCallback(changed, gtk.TreeRowReference(bricks, idx))
            l.append(d)
        defer.DeferredList(l, consumeErrors=True).addCallback(stopped_all)

    def on_toolbutton_start_all_events_clicked(self, widget=None, data=""):
        self.curtain_down()
        events = self.brickfactory.events
        for idx, event in enumerate(events):
            d = event.poweron()
            d.addCallback(changed, gtk.TreeRowReference(events, idx))
            events.row_changed(idx, events.get_iter(idx))

    def on_toolbutton_stop_all_events_clicked(self, widget=None, data=""):
        self.curtain_down()
        events = self.brickfactory.events
        for idx, event in enumerate(events):
            event.poweroff()
            events.row_changed(idx, events.get_iter(idx))

    def __show_config_if_selected(self, treeview):
        brick = self.__get_selection(treeview)
        if brick:
            self.curtain_up(brick)
        return True

    def on_configure_brick_toolbutton_clicked(self, toolbutton):
        return self.__show_config_if_selected(self.__bricks_treeview)

    def on_configure_event_toolbutton_clicked(self, toolbutton):
        return self.__show_config_if_selected(self.__events_treeview)

    def show_brickactions(self):
        brick = self.__get_selection(self.__bricks_treeview)
        if brick.get_type() == "Qemu":
            self.set_sensitivegroup(['vmresume'])
        else:
            self.set_nonsensitivegroup(['vmresume'])
        self.get_object("brickaction_name").set_label(brick.name)
        self.show_window('menu_brickactions')

    def on_bricks_treeview_button_release_event(self, treeview, event):
        if event.button == 3:
            pthinfo = treeview.get_path_at_pos(int(event.x), int(event.y))
            if pthinfo is not None:
                path, col, cellx, celly = pthinfo
                treeview.grab_focus()
                treeview.set_cursor(path, col, 0)
                model = treeview.get_model()
                obj = model.get_value(model.get_iter(path), 0)
                interfaces.IMenu(obj).popup(event.button, event.time, self)
            return True

    def on_events_treeview_button_release_event(self, treeview, event):
        return self.on_bricks_treeview_button_release_event(treeview, event)

    def on_bricks_treeview_row_activated(self, treeview, path, column):
        model = treeview.get_model()
        iter = model.get_iter(path)
        brick = model.get_value(iter, 0)
        self.startstop_brick(brick)

    def on_events_treeview_row_activated(self, treeview, path, column):
        model = treeview.get_model()
        event = model.get_value(model.get_iter(path), 0)
        event.toggle().addCallback(changed, gtk.TreeRowReference(model, path))

    def on_focus_out(self, widget=None, event=None, data=""):
        self.curtain_down()

    def startstop_brick(self, brick):
        d = brick.poweron() if brick.proc is None else brick.poweroff()
        d.addCallback(changed_brick_in_model, self.brickfactory.bricks)
        d.addCallback(lambda _: self.running_bricks.refilter())
        d.addErrback(logger.failure_eb, stop_error if brick.proc else
                     start_error)

    def on_joblist_treeview_button_release_event(self, treeview, event):
        if event.button == 3:
            pthinfo = treeview.get_path_at_pos(int(event.x), int(event.y))
            if pthinfo is not None:
                path, col, cellx, celly = pthinfo
                treeview.grab_focus()
                treeview.set_cursor(path, col, 0)
                model = treeview.get_model()
                brick = model.get_value(model.get_iter(path), 0)
                interfaces.IJobMenu(brick).popup(event.button, event.time,
                                                 self)
                return True

    def on_dialog_close(self, widget=None, data=""):
        self.show_window('')
        return True

    def on_dialog_attach_event_response(self, dialog, response_id):
        dialog.hide()
        if response_id == 1:
            brick = self.__get_selection(self.__bricks_treeview)
            startevents = self.get_object('start_events_avail_treeview')
            stopevents = self.get_object('stop_events_avail_treeview')
            model, iter_ = startevents.get_selection().get_selected()
            if iter_:
                brick.config["pon_vbevent"] = model[iter_][2]
            else:
                brick.config["pon_vbevent"] = ""
            model, iter_ = stopevents.get_selection().get_selected()
            if iter_:
                brick.config["poff_vbevent"] = model[iter_][2]
            else:
                brick.config["poff_vbevent"] = ""

        return True

    def on_start_assign_nothing_button_clicked(self, widget=None, data=""):
        startevents = self.get_object('start_events_avail_treeview')
        treeselection = startevents.get_selection()
        treeselection.unselect_all()

    def on_stop_assign_nothing_button_clicked(self, widget=None, data=""):
        stopevents = self.get_object('stop_events_avail_treeview')
        treeselection = stopevents.get_selection()
        treeselection.unselect_all()

    def on_item_create_image_activate(self, widget=None, data=""):
        dialogs.CreateImageDialog(self, self.brickfactory).show(
            self.get_object("main_win"))

    def image_create(self):
        logger.info(create_image)
        path = self.get_object(
            "filechooserbutton_newimage_dest").get_filename() + "/"
        filename = self.get_object("entry_newimage_name").get_text()
        img_format = self.get_object(
            "combobox_newimage_format").get_active_text()
        img_size = str(self.get_object("spinbutton_newimage_size").get_value())
        #Get size unit and remove the last character "B"
        #because qemu-img want k, M, G or T suffixes.
        unit = self.get_object(
            "combobox_newimage_sizeunit").get_active_text()[1]
        # XXX: use a two value combobox
        if not filename:
            logger.error(filename_empty)
            return
        if img_format == "Auto":
            img_format = "raw"
        fullname = "%s%s.%s" % (path, filename, img_format)
        exe = "qemu-img"
        args = [exe, "create", "-f", img_format, fullname, img_size + unit]
        done = defer.Deferred()
        reactor.spawnProcess(QemuImgCreateProtocol(done), exe, args,
            os.environ)
        done.addCallback(
            lambda _: self.brickfactory.new_disk_image(filename, fullname))
        logger.log_failure(done, create_image_error)
        return done

    def on_button_create_image_clicked(self, widget=None, data=""):
        self.curtain_down()
        self.user_wait_action(self.image_create)

    def on_newbrick(self, toolbutton):
        dialogs.NewBrickDialog(self.factory).show(self.wndMain)
        return True

    def on_newevent(self, widget=None, event=None, data=""):
        dialog = dialogs.NewEventDialog(self)
        dialog.window.set_transient_for(self.widg["main_win"])
        dialog.show()

    def on_check_kvm(self, widget=None, event=None, data=""):
        if widget.get_active():
            kvm = tools.check_kvm(settings.get("qemupath"))
            if not kvm:
                logger.error(no_kvm)
            widget.set_active(kvm)

    def on_show_messages_activate(self, menuitem, data=None):
        dialogs.LoggingWindow(self.messages_buffer).show()

    def on_brick_attach_event(self, menuitem, data=None):
        attach_event_window = self.get_object("dialog_attach_event")

        # columns = (COL_ICON, COL_TYPE, COL_NAME, COL_CONFIG) = range(4)
        COL_ICON, COL_TYPE, COL_NAME, COL_CONFIG = range(4)

        startavailevents = self.get_object('start_events_avail_treeview')
        stopavailevents = self.get_object('stop_events_avail_treeview')

        eventsmodel = gtk.ListStore(gtk.gdk.Pixbuf, str, str, str)

        startavailevents.set_model(eventsmodel)
        stopavailevents.set_model(eventsmodel)

        treeviewselectionstart = startavailevents.get_selection()
        treeviewselectionstart.unselect_all()
        treeviewselectionstop = stopavailevents.get_selection()
        treeviewselectionstop.unselect_all()
        brick = self.__get_selection(self.__bricks_treeview)

        for event in self.brickfactory.events:
            if event.configured():
                parameters = event.get_parameters()
                if len(parameters) > 30:
                    parameters = "%s..." % parameters[:30]
                image = graphics.pixbuf_for_running_brick_at_size(event, 48,
                                                                  48)
                iter_ = eventsmodel.append([image, event.get_type(),
                                            event.name, parameters])
                if brick.config["pon_vbevent"] == event.name:
                    treeviewselectionstart.select_iter(iter_)
                if brick.config["poff_vbevent"] == event.name:
                    treeviewselectionstop.select_iter(iter_)

        cell = gtk.CellRendererPixbuf()
        column_icon = gtk.TreeViewColumn(_("Icon"), cell, pixbuf=COL_ICON)
        cell = gtk.CellRendererText()
        column_type = gtk.TreeViewColumn(_("Type"), cell, text=COL_TYPE)
        cell = gtk.CellRendererText()
        column_name = gtk.TreeViewColumn(_("Name"), cell, text=COL_NAME)
        cell = gtk.CellRendererText()
        column_config = gtk.TreeViewColumn(_("Parameters"), cell,
                                           text=COL_CONFIG)

        # Clear columns
        for c in startavailevents.get_columns():
            startavailevents.remove_column(c)

        for c in stopavailevents.get_columns():
            stopavailevents.remove_column(c)

        # Add columns
        startavailevents.append_column(column_icon)
        startavailevents.append_column(column_type)
        startavailevents.append_column(column_name)
        startavailevents.append_column(column_config)

        cell = gtk.CellRendererPixbuf()
        column_icon = gtk.TreeViewColumn(_("Icon"), cell, pixbuf=COL_ICON)
        cell = gtk.CellRendererText()
        column_type = gtk.TreeViewColumn(_("Type"), cell, text=COL_TYPE)
        cell = gtk.CellRendererText()
        column_name = gtk.TreeViewColumn(_("Name"), cell, text=COL_NAME)
        cell = gtk.CellRendererText()
        column_config = gtk.TreeViewColumn(_("Parameters"), cell,
                                           text=COL_CONFIG)

        stopavailevents.append_column(column_icon)
        stopavailevents.append_column(column_type)
        stopavailevents.append_column(column_name)
        stopavailevents.append_column(column_config)

        self.get_object('dialog_attach_event').\
        set_title(_("Virtualbricks-Events to attach to the start/stop Brick "
                    "Events"))

        attach_event_window.show_all()
        return True

    def on_project_open_activate(self, menuitem):
        dialog = dialogs.OpenProjectDialog(self)
        dialog.on_destroy = self.set_title_default
        dialog.show(self.get_object("main_win"))
        return True

    def on_project_delete_activate(self, menuitem):
        dialogs.DeleteProjectDialog(self).show(self.get_object("main_win"))
        return True

    def on_rename_menuitem_activate(self, menuitem):
        dialog = dialogs.RenameProjectDialog(self)
        dialog.on_destroy = self.set_title_default
        dialog.show(self.get_object("main_win"))
        return True

    def on_project_new_activate(self, menuitem):
        dialog = dialogs.NewProjectDialog(self)
        dialog.on_destroy = self.set_title_default
        dialog.show(self.get_object("main_win"))
        return True

    def on_project_save_activate(self, menuitem):
        self.on_save()

    def on_project_saveas_activate(self, menuitem):
        self.on_save()
        dialog = dialogs.SaveAsDialog(self.brickfactory, iter(project.manager))
        dialog.show(self.get_object("main_win"))
        return True

    def on_export_menuitem_activate(self, menuitem):
        self.on_save()
        dialog = dialogs.ExportProjectDialog(ProgressBar(self),
                                    project.current.filepath,
                                    self.brickfactory.disk_images)
        dialog.show(self.get_object("main_win"))
        return True

    def on_import_menuitem_activate(self, menuitem):
        d = dialogs.ImportDialog(self.brickfactory)
        d.on_destroy = self.set_title_default
        d.show(self.get_object("main_win"))

    def do_image_convert(self, arg=None):
        raise NotImplementedError("do_image_convert")
        # src = self.get_object('filechooser_imageconvert_source').get_filename()
        # fmt = self.get_object('combobox_imageconvert_format').get_active_text()
        # # dst = src.rstrip(src.split('.')[-1]).rstrip('.')+'.'+fmt
        # src.rstrip(src.split('.')[-1]).rstrip('.')+'.'+fmt
        # # self.user_wait_action(self.exec_image_convert)
        # self.exec_image_convert()

    def on_convertimage_convert(self, widget, event=None, data=None):
        if (self.get_object('filechooser_imageconvert_source').get_filename()
                is None):
            logger.error(select_file)
            return

        # src = self.get_object('filechooser_imageconvert_source').get_filename()
        # fmt = self.get_object('combobox_imageconvert_format').get_active_text()
        filename = self.get_object(
            'filechooser_imageconvert_source').get_filename()
        if not os.access(os.path.dirname(filename), os.W_OK):
            logger.error(cannot_write)
        else:
            self.do_image_convert()

        self.show_window('')
        return True

    def on_commit_menuitem_activate(self, menuitem):
        dialogs.CommitImageDialog(self.progressbar, self.brickfactory).show(
            self.get_object("main_win"))

    def on_convert_image(self, widget, event=None, data=None):
        self.get_object('combobox_imageconvert_format').set_active(2)
        self.show_window('dialog_convertimage')

    def user_wait_action(self, action, *args):
        return ProgressBar(self).wait_for(action, *args)

    def user_wait_deferred(self, deferred):
        return ProgressBar(self).wait_for(deferred)

    def set_insensitive(self):
        self.get_object("main_win").set_sensitive(False)

    def set_sensitive(self):
        self.get_object("main_win").set_sensitive(True)

    # Bricks tab signals

    def on_bricks_treeview_drag_data_get(self, treeview, context, selection,
                                         info, time):
        treeselection = treeview.get_selection()
        model, iter = treeselection.get_selected()
        brick = model.get_value(iter, 0)
        selection.set(selection.target, 8, brick.get_name())
        return True

    def on_bricks_treeview_drag_data_received(self, treeview, context, x, y,
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

    def on_bricks_selection_changed(self, selection):
        self.__config_brick_btn_state.check()

    def __brick_selected(self):
        return bool(self.__get_selection(self.__bricks_treeview))

    # Events tab signals

    def on_events_selection_changed(self, selection):
        self.__config_event_btn_state.check()

    def __event_selected(self):
        return bool(self.__get_selection(self.__events_treeview))


class List(gtk.ListStore):

    def __init__(self):
        gtk.ListStore.__init__(self, object)

    def __iter__(self):
        i = self.get_iter_first()
        while i:
            yield self.get_value(i, 0)
            i = self.iter_next(i)

    def append(self, element):
        gtk.ListStore.append(self, (element, ))

    def remove(self, element):
        itr = self.get_iter_first()
        while itr:
            el = self.get_value(itr, 0)
            if el is element:
                return gtk.ListStore.remove(self, itr)
            itr = self.iter_next(itr)
        raise ValueError("%r not in list" % (element, ))

    def __delitem__(self, key):
        if isinstance(key, int):
            gtk.ListStore.__delitem__(self, key)
        elif isinstance(key, slice):
            if (key.start in (None, 0) and key.stop in (None, sys.maxint) and
                    key.step in (1, -1, None)):
                self.clear()
            else:
                raise TypeError("Invalid slice %r" % (key, ))
        else:
            raise TypeError("Invalid key %r" % (key, ))


class VisualFactory(brickfactory.BrickFactory):

    def __init__(self, quit):
        brickfactory.BrickFactory.__init__(self, quit)
        self.events = List()
        self.bricks = List()
        self.socks = List()


@implementer(log.ILogObserver)
class TextBufferObserver:

    def __init__(self, textbuffer):
        textbuffer.create_mark("end", textbuffer.get_end_iter(), False)
        self.textbuffer = textbuffer

    def __call__(self, event):
        gobject.idle_add(self.emit, event)

    def emit(self, event):
        entry = "{iso8601_time} [{log_namespace}] {msg}\n{traceback}"
        if "log_failure" in event:
            event["traceback"] = event["log_failure"].getTraceback()
        else:
            event["traceback"] = ""
        event["iso8601_time"] = log.format_time(event["log_time"])
        msg = entry.format(msg=log.formatEvent(event), **event)
        mark = self.textbuffer.get_mark("end")
        iter = self.textbuffer.get_iter_at_mark(mark)
        self.textbuffer.insert_with_tags_by_name(iter, msg,
                                                 event["log_level"].name)


class MessageDialogObserver:

    def __init__(self, parent=None):
        self.__parent = parent

    def set_parent(self, parent):
        self.__parent = parent

    def __call__(self, event):
        dialog = gtk.MessageDialog(self.__parent, gtk.DIALOG_MODAL,
                gtk.MESSAGE_ERROR, gtk.BUTTONS_CLOSE)
        dialog.set_property('text', log.formatEvent(event))
        dialog.connect("response", lambda d, r: d.destroy())
        dialog.show()


def should_show_to_user(event):
    if "hide_to_user" in event or event["log_level"] != log.LogLevel.error:
        return log.PredicateResult.no
    return log.PredicateResult.maybe


TEXT_TAGS = [('debug', {'foreground': '#a29898'}),
             ('info', {}),
             ('warn', {'foreground': '#ff9500'}),
             ('error', {'foreground': '#b8032e'})]


def AppLoggerFactory(textbuffer):

    observer = TextBufferObserver(textbuffer)

    class AppLogger(brickfactory.AppLogger):

        def start(self, application):
            logger.publisher.addObserver(observer)
            brickfactory.AppLogger.start(self, application)

        def stop(self):
            logger.publisher.removeObserver(observer)
            brickfactory.AppLogger.stop(self)

    return AppLogger


class Application(brickfactory.Application):

    factory_factory = VisualFactory

    def __init__(self, config):
        self.textbuffer = gtk.TextBuffer()
        for name, attrs in TEXT_TAGS:
            self.textbuffer.create_tag(name, **attrs)
        self.logger_factory = AppLoggerFactory(self.textbuffer)
        brickfactory.Application.__init__(self, config)

    def install_locale(self):
        brickfactory.Application.install_locale(self)
        gtk.glade.bindtextdomain("virtualbricks", "/usr/share/locale")
        gtk.glade.textdomain("virtualbricks")

    def get_namespace(self):
        return {"gui": self.gui}

    def _run(self, factory, quit):
        # a bug in gtk2 make impossibile to use this and is not required anyway
        gtk.set_interactive(False)
        gladefile = load_gladefile()
        message_dialog = MessageDialogObserver()
        observer = log.FilteringLogObserver(message_dialog,
                                            (should_show_to_user,))
        logger.publisher.addObserver(observer, False)
        # disable default link_button action
        gtk.link_button_set_uri_hook(lambda b, s: None)
        self.gui = VBGUI(factory, gladefile, quit, self.textbuffer)
        message_dialog.set_parent(self.gui.widg["main_win"])

    def run(self, reactor):
        ret = brickfactory.Application.run(self, reactor)
        self.gui.set_title_default()
        return ret


def load_gladefile():
    try:
        gladefile = graphics.get_filename("virtualbricks.gui",
                                    "data/virtualbricks.glade")
        return gtk.glade.XML(gladefile)
    except:
        raise SystemExit("Cannot load gladefile")
