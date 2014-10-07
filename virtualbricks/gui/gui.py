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

from twisted.internet import error, defer, task, protocol, reactor
from zope.interface import implementer

from virtualbricks import tools, settings, project, log, brickfactory, bricks
from virtualbricks.tools import dispose
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


def state_add_selection(manager, treeview, prerequisite, tooltip, *widgets):
    state = manager._build_state(tooltip, *widgets)
    state.add_prerequisite(prerequisite)
    selection = treeview.get_selection()
    selection.connect("changed", lambda s: state.check())
    state.check()
    return state


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
            gui.wndMain)

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
        return iter(self._factory.events)


def set_pixbuf(celllayout, cell, model, itr, data=None):
    brick = model.get_value(itr, 0)
    pixbuf = graphics.pixbuf_for_brick_at_size(brick, 48, 48)
    cell.set_property("pixbuf", pixbuf)


def is_running(model, itr):
    return bricks.is_running(model.get_value(itr, 0))


class VBGUI(TopologyMixin, ReadmeMixin, _Root):
    """
    The main GUI object for virtualbricks, containing all the configuration for
    the widgets and the connections to the main engine.
    """

    __bricks_binding_list = None
    __events_binding_list = None

    def __init__(self, factory, builder, quit, textbuffer=None):
        self.factory = self.brickfactory = factory
        self.builder = builder
        self.quit_d = quit
        self.config = settings
        self.messages_buffer = textbuffer

        logger.info(start_virtualbricks)
        self.__initialize_components()
        factory.connect("brick-changed", self.on_brick_changed)
        factory.connect("brick-added", self.on_brick_changed)
        factory.connect("brick-removed", self.on_brick_changed)
        self.progressbar = ProgressBar(self)
        if settings.get("systray"):
            self.start_systray()
        self.builder.connect_signals(self)
        task.LoopingCall(self.running_bricks.refilter).start(2)
        self.__state_manager = _gui.StateManager()
        state_add_selection(self.__state_manager, self.tvBricks,
                            self.__brick_selected, _("No brick selected"),
                            self.btnConfigure)
        state_add_selection(self.__state_manager, self.tvEvents,
                            self.__event_selected, _("No event selected"),
                            self.btnConfigureEvent)
        self.init(factory)

        # Check GUI prerequisites
        self.__complain_on_missing_prerequisites()

        # attach the quit callback at the end, so it is not called if an
        # exception is raised before because of a syntax error of another kind
        # of error
        quit.addCallback(lambda _: self.on_quit())

        # Show the main window
        self.wndMain.show()

    def __initialize_components(self):
        # bricks tab
        set_text = widgets.CellRendererFormattable.set_text
        self.tvcBrickIcon.set_cell_data_func(self.crp1, set_pixbuf)
        self.tvcBrickStatus.set_cell_data_func(self.crt1, set_text)
        self.tvcBrickType.set_cell_data_func(self.crt2, set_text)
        self.tvcBrickName.set_cell_data_func(self.crt3, set_text)
        self.tvcBrickParams.set_cell_data_func(self.crt4, set_text)
        self.__bricks_binding_list = BricksBindingList(self.factory)
        self.lBricks.set_data_source(self.__bricks_binding_list)
        self.tvBricks.enable_model_drag_source(gtk.gdk.BUTTON1_MASK,
                BRICK_DRAG_TARGETS, gtk.gdk.ACTION_LINK)
        self.tvBricks.enable_model_drag_dest(BRICK_DRAG_TARGETS,
                gtk.gdk.ACTION_LINK)

        # events tab
        self.tvcEventIcon.set_cell_data_func(self.crp2, set_pixbuf)
        self.tvcEventStatus.set_cell_data_func(self.crt5, set_text)
        self.tvcEventName.set_cell_data_func(self.crt6, set_text)
        self.tvcEventParams.set_cell_data_func(self.crt7, set_text)
        self.__events_binding_list = EventsBindingList(self.factory)
        self.lEvents.set_data_source(self.__events_binding_list)

        # jobs tab
        self.tvcJobIcon.set_cell_data_func(self.crp3, set_pixbuf)
        self.tvcJobPid.set_cell_data_func(self.crt8, set_text)
        self.tvcJobType.set_cell_data_func(self.crt9, set_text)
        self.tvcJobName.set_cell_data_func(self.crt10, set_text)
        self.running_bricks = self.brickfactory.bricks.filter_new()
        self.running_bricks.set_visible_func(is_running)
        self.tvJobs.set_model(self.running_bricks)

    def __complain_on_missing_prerequisites(self):
        qmissing, _ = tools.check_missing_qemu(settings.get("qemupath"))
        vmissing = tools.check_missing_vde(settings.get("vdepath"))
        missing = vmissing + qmissing

        if "kvm" in missing:
            settings.set("kvm", False)
        if not tools.check_ksm():
            settings.set("ksm", False)
            missing.append("ksm")
        missing_text = []
        missing_components = []
        if len(missing) > 0 and settings.show_missing:
            for m in missing:
                if m == "kvm":
                    missing_text.append("KVM not found: kvm support"
                                    " will be disabled.")
                elif m == "ksm":
                    missing_text.append("KSM not found in Linux. "
                                    "Samepage memory will not work on this "
                                    "system.")
                else:
                    missing_components.append(m)
            logger.error(components_not_found, text="\n".join(missing_text),
                components=" ".join(missing_components))

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

    def __getattr__(self, name):
        obj = self.builder.get_object(name)
        if obj is None:
            raise AttributeError(name)
        return obj

    def get_object(self, name):
        return self.builder.get_object(name)

    """ ********************************************************     """
    """ Signal handlers                                           """
    """ ********************************************************     """

    def on_brick_changed(self, brick):
        self.draw_topology()

    def curtain_down(self):
        self.get_object("main_notebook").show()
        configframe = self.get_object("configframe")
        configpanel = configframe.get_child()
        if configpanel:
            configpanel.destroy()
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

    def set_title(self, title):
        self.wndMain.set_title(title)

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
        dispose(self)
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

    def do_quit(self, *_):
        self.quit_d.callback(None)
        return True

    # end gui (programming) interface

    def on_wndMain_delete_event(self, window, event):
        #don't delete; hide instead
        if settings.get("systray"):
            window.hide()
            self.statusicon.set_tooltip("Virtualbricks Hidden")
            return True

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
        dialog.window.set_transient_for(self.wndMain)
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

    # status icon handling

    def start_systray(self):
        if not self.statusicon.get_visible():
            self.statusicon.set_visible(True)

    def stop_systray(self):
        if self.statusicon.get_visible():
            self.statusicon.set_visible(False)

    def window_toggle(self):
        if self.wndMain.get_visible():
            self.curtain_down()
            self.wndMain.hide()
            self.statusicon.set_tooltip(_("Virtualbricks hidden"))
        else:
            self.wndMain.show()
            self.statusicon.set_tooltip(_("Virtualbricks visible"))

    def on_statusicon_activate(self, statusicon):
        self.window_toggle()

    def on_statusicon_popup_menu(self, statusicon, button, time):
        if button == 3:
            self.menuSystray.popup(None, None, None, button, time)

    def on_menuSystrayToggle_activate(self, menuitem):
        self.window_toggle()

    # menu items signals

    def on_menuFileNew_activate(self, menuitem):
        dialog = dialogs.NewProjectDialog(self)
        dialog.on_destroy = self.set_title_default
        dialog.show(self.wndMain)
        return True

    def on_menuFileOpen_activate(self, menuitem):
        dialog = dialogs.OpenProjectDialog(self)
        dialog.on_destroy = self.set_title_default
        dialog.show(self.wndMain)
        return True

    def on_menuFileRename_activate(self, menuitem):
        dialog = dialogs.RenameProjectDialog(self)
        dialog.on_destroy = self.set_title_default
        dialog.show(self.wndMain)
        return True

    def on_menuFileSave_activate(self, menuitem):
        self.on_save()
        return True

    def on_menuFileSaveAs_activate(self, menuitem):
        self.on_save()
        dialog = dialogs.SaveAsDialog(self.brickfactory, iter(project.manager))
        dialog.show(self.wndMain)
        return True

    def on_menuFileImport_activate(self, menuitem):
        d = dialogs.ImportDialog(self.brickfactory)
        d.on_destroy = self.set_title_default
        d.show(self.wndMain)
        return True

    def on_menuFileExport_activate(self, menuitem):
        self.on_save()
        dialog = dialogs.ExportProjectDialog(ProgressBar(self),
                                    project.current.filepath,
                                    self.brickfactory.disk_images)
        dialog.show(self.wndMain)
        return True

    def on_menuFileDelete_activate(self, menuitem):
        dialogs.DeleteProjectDialog(self).show(self.wndMain)
        return True

    def on_menuSettingsPreferences_activate(self, menuitem):
        dialogs.SettingsDialog(self).show(self.wndMain)
        return True

    def on_menuViewMessages_activate(self, menuitem):
        dialogs.LoggingWindow(self.messages_buffer).show()
        return True

    def on_menuImagesCreate_activate(self, menuitem):
        dialogs.CreateImageDialog(self, self.brickfactory).show(self.wndMain)
        return True

    def on_menuImagesNew_activate(self, menuitem):
        dialogs.choose_new_image(self, self.brickfactory)
        return True

    def on_menuImagesCommit_activate(self, menuitem):
        dialogs.CommitImageDialog(self.progressbar, self.brickfactory).show(
            self.wndMain)
        return True

    def on_menuImagesLibrary_activate(self, menuitem):
        dialogs.DisksLibraryDialog(self.brickfactory).show()
        return True

    def on_menuHelpAbout_activate(self, menuitem):
        dialogs.AboutDialog().show(self.wndMain)
        return True

    # bricks toolbar

    def on_btnNewBrick_clicked(self, toolbutton):
        dialogs.NewBrickDialog(self.brickfactory).show(self.wndMain)
        return True

    def on_btnStartAll_clicked(self, toolbutton):
        # TODO: look at the comment in on_btnStartAll_clicked

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

    def on_btnStopAll_clicked(self, toolbutton):
        # TODO: need refactoring. filter refilter is not needed anymore,
        # neither the call to changed

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

    def __show_config_if_selected(self, treeview):
        brick = self.__get_selection(treeview)
        if brick:
            self.curtain_up(brick)

    def on_btnConfigure_clicked(self, toolbutton):
        self.__show_config_if_selected(self.tvBricks)
        return True

    # events toolbar

    def on_btnNewEvent_clicked(self, toolbutton):
        dialogs.NewEventDialog(self).show(self.wndMain)
        return True

    def on_btnStartAllEvents_clicked(self, toolbutton):
        # TODO: look at the comment in on_btnStartAll_clicked
        self.curtain_down()
        events = self.brickfactory.events
        for idx, event in enumerate(events):
            d = event.poweron()
            d.addCallback(changed, gtk.TreeRowReference(events, idx))
            events.row_changed(idx, events.get_iter(idx))
        return True

    def on_btnStopAllEvents_clicked(self, toolbutton):
        # TODO: look at the comment in on_btnStartAll_clicked
        self.curtain_down()
        events = self.brickfactory.events
        for idx, event in enumerate(events):
            event.poweroff()
            events.row_changed(idx, events.get_iter(idx))
        return True

    def on_btnConfigureEvent_clicked(self, toolbutton):
        self.__show_config_if_selected(self.tvEvents)
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
        # TODO: look at the comment in on_btnStartAll_clicked
        model = treeview.get_model()
        event = model.get_value(model.get_iter(path), 0)
        event.toggle().addCallback(changed, gtk.TreeRowReference(model, path))

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

    def user_wait_action(self, action, *args):
        return ProgressBar(self).wait_for(action, *args)

    def user_wait_deferred(self, deferred):
        return ProgressBar(self).wait_for(deferred)

    def set_insensitive(self):
        self.wndMain.set_sensitive(False)

    def set_sensitive(self):
        self.wndMain.set_sensitive(True)

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

    def __brick_selected(self):
        return bool(self.__get_selection(self.tvBricks))

    # Events tab signals

    def on_events_selection_changed(self, selection):
        self.__state_event_config.check()

    def __event_selected(self):
        return bool(self.__get_selection(self.tvEvents))


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

    def get_namespace(self):
        return {"gui": self.gui}

    def _run(self, factory, quit):
        # a bug in gtk2 make impossibile to use this and is not required anyway
        gtk.set_interactive(False)
        builder = load_ui()
        message_dialog = MessageDialogObserver()
        observer = log.FilteringLogObserver(message_dialog,
                                            (should_show_to_user,))
        logger.publisher.addObserver(observer, False)
        # disable default link_button action
        gtk.link_button_set_uri_hook(lambda b, s: None)
        self.gui = VBGUI(factory, builder, quit, self.textbuffer)
        message_dialog.set_parent(self.gui.wndMain)

    def run(self, reactor):
        ret = brickfactory.Application.run(self, reactor)
        self.gui.set_title_default()
        return ret


def load_ui():
    try:
        builder = gtk.Builder()
        builder.set_translation_domain("virtualbricks")
        source = graphics.get_filename("virtualbricks.gui",
                                       "data/virtualbricks.ui")
        builder.add_from_file(source)
        return builder
    except:
        raise SystemExit("Cannot load glade file")
