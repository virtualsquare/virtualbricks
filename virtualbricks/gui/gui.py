# -*- test-case-name: virtualbricks.tests.test_gui -*-
# Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
# Copyright (C) 2018 Virtualbricks team

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

# This module is ported to new GTK3 using PyGObject

import os
import sys
import string
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import GObject

from twisted.internet import error, defer, task, protocol, reactor
from twisted.python import filepath
from zope.interface import implementer

from virtualbricks.interfaces import registerAdapter
from virtualbricks.gui.interfaces import (IMenu, IJobMenu, IConfigController,
                                          IPrerequisite, IState, IControl,
                                          IStateManager)
from virtualbricks._spawn import getQemuOutput
from virtualbricks.bricks import Brick
from virtualbricks.events import Event
from virtualbricks.link import Plug, Sock
from virtualbricks.virtualmachines import VirtualMachine
from virtualbricks import tools, settings, project, log, brickfactory, qemu
from virtualbricks.tools import dispose, is_running
from virtualbricks.gui import graphics, dialogs, widgets, help


if False:  # pyflakes
    _ = str

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
not_started = log.Event("Brick not started.")
stop_error = log.Event("Error on stopping brick.")
start_error = log.Event("Error on starting brick.")
dnd_no_socks = log.Event("I don't know what to do, bricks have no socks.")
dnd_dest_brick_not_found = log.Event("Cannot found dest brick")
dnd_source_brick_not_found = log.Event("Cannot find source brick {name}")
dnd_no_dest = log.Event("No destination brick")
dnd_same_brick = log.Event("Source and destination bricks are the same.")
cannot_rename = log.Event("Cannot rename Brick: it is in use.")
s_r_not_supported = log.Event("Suspend/Resume not supported on this disk.")
snap_error = log.Event("Error on snapshot")
resume_vm = log.Event("Resuming virtual machine {name}")
event_in_use = log.Event("Cannot rename event: it is in use.")
proc_signal = log.Event("Sending to process signal {signame}!")
send_acpi = log.Event("send ACPI {acpievent}")
proc_restart = log.Event("Restarting process!")
savevm = log.Event("Save snapshot on virtual machine {name}")
qemu_version_parsing_error = log.Event("Error while parsing qemu version")
retrieve_qemu_version_error = log.Event("Error while retrieving qemu version.")
usb_access = log.Event("Cannot access /dev/bus/usb. Check user privileges.")
no_kvm = log.Event("No KVM support found on the system. Check your active "
                   "configuration. KVM will stay disabled.")

BRICK_TARGET_NAME = "brick-connect-target"
BRICK_DRAG_TARGETS = [
    (BRICK_TARGET_NAME, Gtk.TargetFlags.SAME_WIDGET | Gtk.TargetFlags.SAME_APP, 0)
]


@implementer(IMenu)
class BaseMenu:

    def __init__(self, brick):
        self.original = brick

    def build(self, gui):
        menu = Gtk.Menu()
        menu.append(Gtk.MenuItem(self.original.get_name(), False))
        menu.append(Gtk.SeparatorMenuItem())
        start_stop = Gtk.MenuItem("_Start/Stop")
        start_stop.connect("activate", self.on_startstop_activate, gui)
        menu.append(start_stop)
        delete = Gtk.MenuItem("_Delete")
        delete.connect("activate", self.on_delete_activate, gui)
        menu.append(delete)
        copy = Gtk.MenuItem("Make a C_opy")
        copy.connect("activate", self.on_copy_activate, gui)
        menu.append(copy)
        rename = Gtk.MenuItem("Re_name")
        rename.connect("activate", self.on_rename_activate, gui)
        menu.append(rename)
        configure = Gtk.MenuItem("_Configure")
        configure.connect("activate", self.on_configure_activate, gui)
        menu.append(configure)
        return menu

    def popup(self, button, time, gui):
        menu = self.build(gui)
        menu.show_all()
        menu.popup(None, None, None, button, time)

    def on_configure_activate(self, menuitem, gui):
        gui.curtain_up(self.original)


class BrickPopupMenu(BaseMenu):

    def build(self, gui):
        menu = BaseMenu.build(self, gui)
        attach = Gtk.MenuItem("_Attach Event")
        attach.connect("activate", self.on_attach_activate, gui)
        menu.append(attach)
        return menu

    def on_startstop_activate(self, menuitem, gui):
        gui.startstop_brick(self.original)

    def on_delete_activate(self, menuitem, gui):
        gui.ask_remove_brick(self.original)

    def on_copy_activate(self, menuitem, gui):
        gui.brickfactory.dup_brick(self.original)

    def on_rename_activate(self, menuitem, gui):
        if self.original.proc is not None:
            logger.error(cannot_rename)
        else:
            dialogs.RenameBrickDialog(self.original,
                gui.brickfactory.normalize_name).show(gui.wndMain)

    def on_attach_activate(self, menuitem, gui):
        dialogs.AttachEventDialog(self.original, gui.factory).show(gui.wndMain)
        return True

registerAdapter(BrickPopupMenu, Brick, IMenu)


class VMPopupMenu(BrickPopupMenu):

    def build(self, gui):
        menu = BrickPopupMenu.build(self, gui)
        resume = Gtk.MenuItem("_Resume VM")
        resume.connect("activate", self.on_resume_activate, gui)
        menu.append(resume)
        return menu

    def resume(self, factory):

        def grep(out, pattern):
            if out.find(pattern) == -1:
                raise RuntimeError(_("Cannot find suspend point."))

        def loadvm(_):
            if self.original.proc is not None:
                self.original.send("loadvm virtualbricks\n")
            else:
                return self.original.poweron("virtualbricks")

        img = self.original.get("hda")
        if img.cow:
            path = img.get_cow_path()
        elif img.image:
            path = img.image.path
        else:
            logger.error(s_r_not_supported)
            return defer.fail(RuntimeError(_("Suspend/Resume not supported on "
                                             "this disk.")))
        args = ["snapshot", "-l", path]
        output = getQemuOutput("qemu-img", args, os.environ)
        output.addCallback(grep, "virtualbricks")
        output.addCallback(loadvm)
        logger.log_failure(output, snap_error)
        return output

    def on_resume_activate(self, menuitem, gui):
        logger.debug(resume_vm, name=self.original.get_name())
        gui.user_wait_action(self.resume(gui.brickfactory))


registerAdapter(VMPopupMenu, VirtualMachine, IMenu)


class EventPopupMenu(BaseMenu):

    def on_startstop_activate(self, menuitem, gui):
        self.original.toggle()

    def on_delete_activate(self, menuitem, gui):
        gui.ask_remove_event(self.original)

    def on_copy_activate(self, menuitem, gui):
        gui.brickfactory.dup_event(self.original)

    def on_rename_activate(self, menuitem, gui):
        if not self.original.scheduled:
            dialogs.RenameDialog(self.original,
                gui.brickfactory.normalize_name).show(gui.wndMain)
        else:
            logger.error(event_in_use)

registerAdapter(EventPopupMenu, Event, IMenu)


@implementer(IMenu)
class LinkMenu:

    def __init__(self, original):
        self.original = original

    def build(self, controller, gui):
        menu = Gtk.Menu()
        edit = Gtk.MenuItem(_("Edit"))
        edit.connect("activate", self.on_edit_activate, controller, gui)
        menu.append(edit)
        remove = Gtk.MenuItem(_("Remove"))
        remove.connect("activate", self.on_remove_activate, controller)
        menu.append(remove)
        return menu

    def popup(self, button, time, controller, gui):
        menu = self.build(controller, gui)
        menu.show_all()
        menu.popup(None, None, None, button, time)

    def on_edit_activate(self, menuitem, controller, gui):
        dialogs.EditEthernetDialog(gui.brickfactory, self.original.brick,
                                   self.original).show(gui.wndMain)

    def on_remove_activate(self, menuitem, controller):
        controller.ask_remove_link(self.original)


registerAdapter(LinkMenu, Plug, IMenu)
registerAdapter(LinkMenu, Sock, IMenu)


@implementer(IMenu)
class JobMenu:

    def __init__(self, original):
        self.original = original

    def build(self, gui):
        menu = Gtk.Menu()
        open = Gtk.MenuItem(_("Open control monitor"))
        open.connect("activate", self.on_open_activate)
        menu.append(open)
        menu.append(Gtk.SeparatorMenuItem())
        stop = Gtk.ImageMenuItem(Gtk.STOCK_STOP)
        stop.connect("activate", self.on_stop_activate)
        menu.append(stop)
        cont = Gtk.ImageMenuItem(Gtk.STOCK_MEDIA_PLAY)
        cont.set_label(_("Continue"))
        cont.connect("activate", self.on_cont_activate)
        menu.append(cont)
        menu.append(Gtk.SeparatorMenuItem())
        reset = Gtk.ImageMenuItem(Gtk.STOCK_REDO)
        reset.set_label(_("Restart"))
        reset.connect("activate", self.on_reset_activate)
        menu.append(reset)
        kill = Gtk.ImageMenuItem(Gtk.STOCK_STOP)
        kill.set_label(_("Kill"))
        kill.connect("activate", self.on_kill_activate, gui)
        menu.append(kill)
        return menu

    def popup(self, button, time, gui):
        menu = self.build(gui)
        menu.show_all()
        menu.popup(None, None, None, button, time)

    @staticmethod
    def _cancel_call(passthru, call):
        if call.active():
            call.cancel()
        return passthru

    @staticmethod
    def _refilter(passthru, filter_model):
        filter_model.refilter()
        return passthru

    def on_open_activate(self, menuitem):
        self.original.open_console()

    def on_stop_activate(self, menuitem):
        logger.debug(proc_signal, signame="SIGSTOP")
        try:
            self.original.send_signal(19)
        except error.ProcessExitedAlready:
            pass

    def on_cont_activate(self, menuitem):
        logger.debug(proc_signal, signame="SIGCONT")
        try:
            self.original.send_signal(18)
        except error.ProcessExitedAlready:
            pass

    def on_reset_activate(self, menuitem):
        logger.debug(proc_restart)
        d = self.original.poweroff()
        # give it 2 seconds before an hard reset
        call = reactor.callLater(2, self.original.poweroff, kill=True)
        d.addBoth(self._cancel_call, call)
        d.addCallback(lambda _: self.original.poweron())

    def on_kill_activate(self, menuitem, gui):
        logger.debug(proc_signal, signame="SIGKILL")
        try:
            d = self.original.poweroff(kill=True)
        except error.ProcessExitedAlready:
            pass

registerAdapter(JobMenu, Brick, IJobMenu)


class VMJobMenu(JobMenu):

    def build(self, gui):
        menu = JobMenu.build(self, gui)
        suspend = Gtk.MenuItem(_("Suspend virtual machine"))
        suspend.connect("activate", self.on_suspend_activate, gui)
        menu.insert(suspend, 5)
        powerdown = Gtk.MenuItem(_("Send ACPI powerdown"))
        powerdown.connect("activate", self.on_powerdown_activate)
        menu.insert(powerdown, 6)
        reset = Gtk.MenuItem(_("Send ACPI hard reset"))
        reset.connect("activate", self.on_reset_activate)
        menu.insert(reset, 7)
        menu.insert(Gtk.SeparatorMenuItem(), 8)
        term = Gtk.ImageMenuItem(Gtk.STOCK_DELETE)
        term.set_label(_("Terminate"))
        term.connect("activate", self.on_term_activate, gui)
        menu.insert(term, 10)
        return menu

    def suspend(self, factory):
        img = self.original.get("hda")
        if img.cow:
            path = img.get_cow_path()
        elif img.image:
            path = img.image.path
        else:
            logger.error(s_r_not_supported)
            return defer.fail(RuntimeError(_("Suspend/Resume not supported on "
                                             "this disk.")))

        if tools.image_type_from_file(path) == tools.ImageFormat.QCOW2:
            self.original.send("savevm virtualbricks\n")
            return self.original.poweroff()
        else:
            logger.error(s_r_not_supported)
            return defer.fail(RuntimeError(_("Suspend/Resume not supported on "
                                             "this disk.")))

    def on_suspend_activate(self, menuitem, gui):
        logger.debug(savevm, name=self.original.get_name())
        gui.user_wait_action(self.suspend(gui.brickfactory))

    def on_powerdown_activate(self, menuitem):
        logger.info(send_acpi, acpievent="powerdown")
        self.original.send("system_powerdown\n")

    def on_reset_activate(self, menuitem):
        logger.info(send_acpi, acpievent="reset")
        self.original.send("system_reset\n")

    def on_term_activate(self, menuitem, gui):
        logger.debug(proc_signal, signame="SIGTERM")
        d = self.original.poweroff(term=True)

registerAdapter(VMJobMenu, VirtualMachine, IJobMenu)


@implementer(IConfigController)
class ConfigController(object):

    domain = "virtualbricks"
    resource = None

    def __init__(self, original):
        self.original = original
        self.builder = builder = Gtk.Builder()
        builder.set_translation_domain(self.domain)
        builder.add_from_file(graphics.get_data_filename(self.resource))
        builder.connect_signals(self)

    def __getattr__(self, name):
        obj = self.builder.get_object(name)
        if obj is None:
            raise AttributeError(name)
        return obj

    def __dispose__(self):
        pass

    def on_ok_button_clicked(self, button, gui):
        self.configure_brick(gui)
        dispose(self)
        gui.curtain_down()

    # def on_save_button_clicked(self, button, gui):
    #     # TODO: update config values
    #     self.configure_brick(gui)

    def on_cancel_button_clicked(self, button, gui):
        dispose(self)
        gui.curtain_down()

    def get_object(self, name):
        return self.builder.get_object(name)

    def get_view(self, gui):
        bbox = Gtk.HButtonBox()
        bbox.set_layout(Gtk.ButtonBoxStyle.END)
        bbox.set_spacing(5)
        ok_button = Gtk.Button(stock=Gtk.STOCK_OK)
        ok_button.connect("clicked", self.on_ok_button_clicked, gui)
        bbox.add(ok_button)
        bbox.set_child_secondary(ok_button, False)
        # save_button = Gtk.Button(stock=Gtk.STOCK_SAVE)
        # save_button.connect("clicked", self.on_save_button_clicked, gui)
        # bbox.add(save_button)
        cancel_button = Gtk.Button(stock=Gtk.STOCK_CANCEL)
        cancel_button.connect("clicked", self.on_cancel_button_clicked, gui)
        bbox.add(cancel_button)
        bbox.set_child_secondary(cancel_button, True)
	#VBox and HBox are deprecated, the suggestion is to use Orientation in the builder of a Box
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL) 
	#methods pack_start and pack_end must have 4 arguments. If they are not specified, use default values : True, True, 0	
        box.pack_end(bbox, False, True, 0)
        box.pack_end(Gtk.HSeparator(), False, False, 3)
        box.show_all()
        box.pack_start(self.get_config_view(gui), True, True, 0)
        return box


class EventConfigController(ConfigController, dialogs.EventControllerMixin):

    resource = "eventconfig.ui"

    def get_config_view(self, gui):
        self.setup_controller(self.original)
        entry = self.get_object("delay_entry")
        entry.set_text(self.original.config.get("delay"))
        return self.get_object("vbox1")

    def configure_brick(self, gui):
        attributes = {}
        text = self.get_object("delay_entry").get_text()
        if self.original.config.get("delay") != text:
            if not text:
                text = 0
            attributes["delay"] = int(text)
        self.configure_event(self.original, attributes)

    def on_delay_entry_key_press_event(self, entry, event):
        if Gdk.keyval_name(event.keyval) not in dialogs.VALIDKEY:
            return True

    def on_action_treeview_key_press_event(self, treeview, event):
        if Gdk.keyval_name(event.keyval) == "Delete":
            selection = treeview.get_selection()
            model, selected = selection.get_selected_rows()
            rows = []
            for path in selected:
                rows.append(Gtk.TreeRowReference(model, path))
            for row in rows:
                iter = model.get_iter(row.get_path())
                next = model.iter_next(iter)
                model.remove(iter)
                if next is None:
                    self.model.append(("", False))

registerAdapter(EventConfigController, Event, IConfigController)


class SwitchConfigController(ConfigController):

    resource = "switchconfig.ui"

    def get_config_view(self, gui):
        self.get_object("fstp_checkbutton").set_active(
            self.original.get("fstp"))
        self.get_object("hub_checkbutton").set_active(
            self.original.get("hub"))
        minports = len([1 for b in iter(gui.brickfactory.bricks)
                        for p in b.plugs if b.socks
                        and p.sock.nickname == b.socks[0].nickname])
        spinner = self.get_object("ports_spinbutton")
        spinner.set_range(max(minports, 1), 128)
        spinner.set_value(self.original.get("numports"))
        return self.get_object("table")

    def configure_brick(self, gui):
        cfg = {
            "fstp": self.get_object("fstp_checkbutton").get_active(),
            "hub": self.get_object("hub_checkbutton").get_active(),
            "numports": self.get_object("ports_spinbutton").get_value_as_int()
        }
        self.original.set(cfg)


class SwitchWrapperConfigController(ConfigController):

    resource = "switchwrapperconfig.ui"

    def get_config_view(self, gui):
        self.get_object("entry").set_text(self.original.get("path"))
        return self.get_object("table1")

    def configure_brick(self, gui):
        self.original.set({"path": self.get_object("entry").get_text()})


def _sock_should_visible(model, iter):
    sock = model.get_value(iter, 0)
    return sock and (sock.brick.get_type().startswith('Switch') or
                     settings.femaleplugs)


def _set_text(column, cell_renderer, model, itr):
    sock = model.get_value(itr, 0)
    cell_renderer.set_property("text", sock.nickname)


class _PlugMixin(object):

    def configure_sock_combobox(self, combo, model, brick, plug, gui):
        filtered_model = model.filter_new()
        filtered_model.set_visible_func(_sock_should_visible)
        combo.set_model(filtered_model)
        cell = combo.get_cells()[0]
        combo.set_cell_data_func(cell, _set_text)
        if plug.configured():
            itr = filtered_model.get_iter_first()
            while itr:
                if filtered_model[itr][0] is plug.sock:
                    combo.set_active_iter(itr)
                    break
                itr = filtered_model.iter_next(itr)

    def connect_plug(self, plug, combo):
        itr = combo.get_active_iter()
        if itr:
            model = combo.get_model()
            plug.connect(model[itr][0])


class TapConfigController(_PlugMixin, ConfigController):

    resource = "tapconfig.ui"

    def get_config_view(self, gui):
        combo = self.get_object("combobox")
        self.configure_sock_combobox(combo,
                gui.brickfactory.socks.filter_new(), self.original,
                self.original.plugs[0], gui)

        self.get_object("ip_entry").set_text(self.original.get("ip"))
        self.get_object("nm_entry").set_text(self.original.get("nm"))
        self.get_object("gw_entry").set_text(self.original.get("gw"))
        # default to manual if not valid mode is set
        if self.original.get("mode") == "off":
            self.get_object("nocfg_radiobutton").set_active(True)
        elif self.original.get("mode") == "dhcp":
            self.get_object("dhcp_radiobutton").set_active(True)
        else:
            self.get_object("manual_radiobutton").set_active(True)

        self.get_object("ipconfig_table").set_sensitive(
            self.original.get("mode") == "manual")

        return self.get_object("table1")

    def configure_brick(self, gui):
        if self.get_object("nocfg_radiobutton").get_active():
            self.original.set({"mode": "off"})
        elif self.get_object("dhcp_radiobutton").get_active():
            self.original.set({"mode": "dhcp"})
        else:
            self.original.set({"mode": "manual",
                               "ip": self.get_object("ip_entry").get_text(),
                               "nm": self.get_object("nm_entry").get_text(),
                               "gw": self.get_object("gw_entry").get_text()})
        self.connect_plug(self.original.plugs[0], self.get_object("combobox"))

    def on_manual_radiobutton_toggled(self, radiobtn):
        self.get_object("ipconfig_table").set_sensitive(radiobtn.get_active())


class CaptureConfigController(_PlugMixin, ConfigController):

    resource = "captureconfig.ui"

    def get_config_view(self, gui):
        combo = self.get_object("combobox1")
        self.configure_sock_combobox(combo,
                gui.brickfactory.socks.filter_new(), self.original,
                self.original.plugs[0], gui)
        combo2 = self.get_object("combobox2")
        model = combo2.get_model()
        with open("/proc/net/dev") as fd:
            # skip the header
            next(fd), next(fd)
            for line in fd:
                name = line.strip().split(":")[0]
                if name != "lo":
                    itr = model.append((name, ))
                    if self.original.get("iface") == name:
                        combo2.set_active_iter(itr)

        return self.get_object("table1")

    def configure_brick(self, gui):
        self.connect_plug(self.original.plugs[0], self.get_object("combobox1"))
        combo = self.get_object("combobox2")
        itr = combo.get_active_iter()
        if itr is not None:
            model = combo.get_model()
            self.original.set({"iface": model[itr][0]})

    def on_manual_radiobutton_toggled(self, radiobtn):
        self.get_object("ipconfig_table").set_sensitive(radiobtn.get_active())


class WireConfigController(_PlugMixin, ConfigController):

    resource = "wireconfig.ui"

    def get_config_view(self, gui):
        for i, wname in enumerate(("sock0_combobox", "sock1_combobox")):
            combo = self.get_object(wname)
            self.configure_sock_combobox(combo,
                    gui.brickfactory.socks.filter_new(), self.original,
                    self.original.plugs[i], gui)

        return self.get_object("vbox")

    def configure_brick(self, gui):
        for i, wname in enumerate(("sock0_combobox", "sock1_combobox")):
            self.connect_plug(self.original.plugs[i], self.get_object(wname))


NO, MAYBE, YES = range(3)


@implementer(IPrerequisite)
class CompoundPrerequisite:

    def __init__(self, *prerequisites):
        self.prerequisites = list(prerequisites)

    def add_prerequisite(self, prerequisite):
        self.prerequisites.append(prerequisite)

    def __call__(self):
        for prerequisite in self.prerequisites:
            satisfied = prerequisite()
            if satisfied in (YES, NO):
                return satisfied
        return MAYBE


@implementer(IState)
class State:

    def __init__(self):
        self.prerequisite = CompoundPrerequisite()
        self.controls = []

    def add_prerequisite(self, prerequisite):
        self.prerequisite.add_prerequisite(prerequisite)

    def add_control(self, control):
        self.controls.append(control)

    def check(self):
        enable = self.prerequisite()
        for control in self.controls:
            control.react(enable)


@implementer(IControl)
class SensitiveControl:

    def __init__(self, widget, tooltip=None):
        self.widget = widget
        self.tooltip = tooltip

    def react(self, enable):
        self.set_sensitive(enable)

    def set_sensitive(self, sensitive):
        if self.widget.get_sensitive() ^ sensitive:
            self.widget.set_sensitive(sensitive)
            tooltip = self.tooltip
            self.tooltip = self.widget.get_tooltip_markup()
            self.widget.set_tooltip_markup(tooltip)


@implementer(IControl)
class InsensitiveControl:

    def __init__(self, widget, tooltip=None):
        self.widget = widget
        self.tooltip = widget.get_tooltip_markup()
        widget.set_tooltip_markup(tooltip)

    def react(self, enable):
        disable = not enable
        if self.widget.get_sensitive() ^ disable:
            self.widget.set_sensitive(disable)
            tooltip = self.tooltip
            self.tooltip = self.widget.get_tooltip_markup()
            self.widget.set_tooltip_markup(tooltip)


@implementer(IControl)
class ActiveControl:

    def __init__(self, widget):
        self.widget = widget

    def react(self, enable):
        if not enable:
            self.widget.set_active(False)


@implementer(IStateManager)
class StateManager:

    control_factory = SensitiveControl

    def __init__(self):
        self.states = []

    def add_state(self, state):
        self.states.append(state)

    def _build_state(self, tooltip, *widgets):
        state = State()
        for widget in widgets:
            state.add_control(self.control_factory(widget, tooltip))
        self.add_state(state)
        return state

    def _add_checkbutton(self, checkbutton, prerequisite, tooltip=None,
                         *widgets):
        state = self._build_state(tooltip, *widgets)
        state.add_prerequisite(prerequisite)
        checkbutton.connect("toggled", lambda cb: state.check())
        state.check()
        return state

    def add_checkbutton_active(self, checkbutton, tooltip=None, *widgets):
        return self._add_checkbutton(checkbutton, checkbutton.get_active,
                                     tooltip, *widgets)

    def add_checkbutton_not_active(self, checkbutton, tooltip=None, *widgets):
        return self._add_checkbutton(checkbutton,
                                     lambda: not checkbutton.get_active(),
                                     tooltip, *widgets)


class NetemuConfigController(_PlugMixin, ConfigController):

    resource = "netemuconfig.ui"
    state_manager = None
    help = help.Help()
    config_to_checkbutton_mapping = (
        ("chanbufsizesymm", "chanbufsize_checkbutton"),
        ("delaysymm", "delay_checkbutton"),
        ("losssymm", "loss_checkbutton"),
        ("bandwidthsymm", "bandwidth_checkbutton"),
    )
    config_to_spinint_mapping = (
        ("chanbufsizer", "chanbufsizer_spinbutton"),
        ("chanbufsize", "chanbufsize_spinbutton"),
        ("delayr", "delayr_spinbutton"),
        ("delay", "delay_spinbutton"),
        ("bandwidthr", "bandwidthr_spinbutton"),
        ("bandwidth", "bandwidth_spinbutton"),
    )
    config_to_spinfloat_mapping = (
        ("lossr", "lossr_spinbutton"),
        ("loss", "loss_spinbutton"),
    )
    help_buttons = (
        "chanbufsize_help_button",
        "delay_help_button",
        "loss_help_button",
        "bandwidth_help_button",
    )

    def get_config_view(self, gui):
        go = self.get_object
        get = self.original.get
        for pname, wname in self.config_to_checkbutton_mapping:
            go(wname).set_active(not get(pname))
        for pname, wname in self.config_to_spinint_mapping:
            go(wname).set_value(get(pname))
        for pname, wname in self.config_to_spinfloat_mapping:
            go(wname).set_value(get(pname))

        self.state_manager = manager = StateManager()
        params = ("chanbufsize", "delay", "loss", "bandwidth")
        for param in params:
            checkbutton = go(param + "_checkbutton")
            checkbutton.set_active(not self.original.get(param + "symm"))
            tooltip = _("Disabled because set symmetric")
            spinbutton = go(param + "r_spinbutton")
            manager.add_checkbutton_active(checkbutton, tooltip, spinbutton)

        # setup help buttons
        for button in self.help_buttons:
            go(button).connect("clicked", self.help.on_help_button_clicked)

        # setup plugs
        for i, wname in enumerate(("sock0_combobox", "sock1_combobox")):
            combo = self.get_object(wname)
            self.configure_sock_combobox(combo,
                    gui.brickfactory.socks.filter_new(), self.original,
                    self.original.plugs[i], gui)

        return go("netemu_config_panel")

    def configure_brick(self, gui):
        cfg = {}
        go = self.get_object
        for config_name, widget_name in self.config_to_checkbutton_mapping:
            cfg[config_name] = not go(widget_name).get_active()
        for pname, wname in self.config_to_spinint_mapping:
            cfg[pname] = go(wname).get_value_as_int()
        for pname, wname in self.config_to_spinfloat_mapping:
            cfg[pname] = go(wname).get_value()
        self.original.set(cfg)

        # configure plug
        for i, wname in enumerate(("sock0_combobox", "sock1_combobox")):
            self.connect_plug(self.original.plugs[i], self.get_object(wname))

    def on_reset_button_clicked(self, button):
        self.get_object("chanbufsize_spinbutton").set_value(75000)
        self.get_object("chanbufsizer_spinbutton").set_value(75000)
        self.get_object("delay_spinbutton").set_value(0)
        self.get_object("delayr_spinbutton").set_value(0)
        self.get_object("loss_spinbutton").set_value(0)
        self.get_object("lossr_spinbutton").set_value(0)
        self.get_object("bandwidth_spinbutton").set_value(125000)
        self.get_object("bandwidthr_spinbutton").set_value(125000)


class TunnelListenConfigController(_PlugMixin, ConfigController):

    resource = "tunnellconfig.ui"

    def get_config_view(self, gui):
        combo = self.get_object("combobox")
        self.configure_sock_combobox(combo,
                gui.brickfactory.socks.filter_new(), self.original,
                self.original.plugs[0], gui)
        port = self.get_object("port_spinbutton")
        port.set_value(self.original.get("port"))
        password = self.get_object("password_entry")
        password.set_text(self.original.get("password"))
        return self.get_object("table1")

    def configure_brick(self, gui):
        self.connect_plug(self.original.plugs[0], self.get_object("combobox"))
        port = self.get_object("port_spinbutton").get_value_as_int()
        password = self.get_object("password_entry").get_text()
        self.original.set({"port": port, "password": password})


class TunnelClientConfigController(TunnelListenConfigController):

    resource = "data/tunnelcconfig.ui"

    def get_config_view(self, gui):
        host = self.get_object("host_entry")
        host.set_text(self.original.get("host"))
        localport = self.get_object("localport_spinbutton")
        localport.set_value(self.original.get("localport"))
        return TunnelListenConfigController.get_config_view(self, gui)

    def configure_brick(self, gui):
        TunnelListenConfigController.configure_brick(self, gui)
        host = self.get_object("host_entry").get_text()
        lport = self.get_object("localport_spinbutton").get_value_as_int()
        self.original.set({"host": host, "localport": lport})


def get_selection(treeview):
    selection = treeview.get_selection()
    if selection is not None:
        model, iter = selection.get_selected()
        if iter is not None:
            return model.get_value(iter, 0)


def get_element_at_click(treeview, event):
    pthinfo = treeview.get_path_at_pos(int(event.x), int(event.y))
    if pthinfo is not None:
        path, col, cellx, celly = pthinfo
        treeview.grab_focus()
        treeview.set_cursor(path, col, 0)
        model = treeview.get_model()
        obj = model.get_value(model.get_iter(path), 0)
        return obj


def _set_vlan(column, cell_renderer, model, itr):
    vlan = model.get_path(itr)[0]
    cell_renderer.set_property("text", vlan)


def _set_connection(column, cell_renderer, model, iter):
    link = model.get_value(iter, 0)
    if link.mode == "hostonly":
        conn = "Host"
    elif link.sock:
        conn = link.sock.brick.name
    elif link.mode == "sock" and settings.femaleplugs:
        conn = "Vde socket (female plug)"
    else:
        conn = "None"
    cell_renderer.set_property("text", conn)


def _set_model(column, cell_renderer, model, iter):
    link = model.get_value(iter, 0)
    cell_renderer.set_property("text", link.model)


def _set_mac(column, cell_renderer, model, iter):
    link = model.get_value(iter, 0)
    cell_renderer.set_property("text", link.mac)


class ImageFormatter(string.Formatter):

    def format(self, format_string, image):
        if image is None:
            return ""
        return format(image, format_string)


BOOT_DEVICE = (
    ("", "hd1"),
    ("a", "floppy"),
    ("d", "cdrom"),
)

SOUND_DEVICE = (
    ("", "no audio"),
    ("pcspk", "PC speaker"),
    ("sb16", "Creative Sound Blaster 16"),
    ("ac97", "Intel 82801AA AC97 Audio"),
    ("es1370", "ENSONIQ AudioPCI ES1370"),
)

MOUNT_DEVICE = (
    ("", "No"),
    ("/dev/cdrom", "cdrom"),
)


class ImagesBindingList(widgets.ImagesBindingList):

    def __iter__(self):
        yield None
        for image in widgets.ImagesBindingList.__iter__(self):
            yield image


class QemuConfigController(ConfigController):

    resource = "qemuconfig.ui"
    config_to_widget_mapping = (
        ("snapshot", "snapshot_checkbutton"),
        ("deviceen", "rbDeviceen"),
        ("cdromen", "rbCdromen"),
        ("use_virtio", "virtio_checkbutton"),
        ("privatehda", "privatehda_checkbutton"),
        ("privatehdb", "privatehdb_checkbutton"),
        ("privatehdc", "privatehdc_checkbutton"),
        ("privatehdd", "privatehdd_checkbutton"),
        ("privatefda", "privatefda_checkbutton"),
        ("privatefdb", "privatefdb_checkbutton"),
        ("privatemtdblock", "privatemtdblock_checkbutton"),
        ("kvm", "cbKvm"),
        ("kvmsm", "cbKvmsm"),
        ("novga", "cbNovga"),
        ("vga", "vga_checkbutton"),
        ("vnc", "cbVnc"),
        ("sdl", "sdl_checkbutton"),
        ("portrait", "portrait_checkbutton"),
        ("usbmode", "cbUsbmode"),
        ("rtc", "rtc_checkbutton"),
        ("tdf", "cbTdf"),
        ("serial", "serial_checkbutton"),
        ("kernelenbl", "cbKernelen"),
        ("initrdenbl", "cbInitrden"),
        ("gdb", "cbGdb")
    )
    config_to_filechooser_mapping = (
        ("cdrom", "fcCdrom"),
        ("kernel", "fcKernel"),
        ("initrd", "fcInitrd"),
        ("icon", "icon_filechooser")
    )
    config_to_spinint_mapping = (
        ("smp", "smp_spinint"),
        ("ram", "ram_spinint"),
        ("kvmsmem", "siKvmsmem"),
        ("vncN", "siVncN"),
        ("gdbport", "siGdbport")
    )

    state_manager = None
    __images_list = None

    def setup_netwoks_cards(self):
        vmplugs = self.get_object("plugsmodel")
        vmplugs.clear()
        for plug in self.original.plugs:
            vmplugs.append((plug, ))

        if self.gui.config.femaleplugs:
            for sock in self.original.socks:
                vmplugs.append((sock,))

        vlan_c = self.get_object("vlan_treeviewcolumn")
        vlan_cr = self.get_object("vlan_cellrenderer")
        vlan_c.set_cell_data_func(vlan_cr, _set_vlan)
        connection_c = self.get_object("connection_treeviewcolumn")
        connection_cr = self.get_object("connection_cellrenderer")
        connection_c.set_cell_data_func(connection_cr, _set_connection)
        model_c = self.get_object("model_treeviewcolumn")
        model_cr = self.get_object("model_cellrenderer")
        model_c.set_cell_data_func(model_cr, _set_model)
        mac_c = self.get_object("mac_treeviewcolumn")
        mac_cr = self.get_object("mac_cellrenderer")
        mac_c.set_cell_data_func(mac_cr, _set_mac)

    def get_config_view(self, gui):

        def install_qemu_version(version):
            qemu.parse_and_install(version)
            container = panel.get_parent()
            container.remove(panel)
            container.pack_start(self._get_config_view(gui))

        def close_panel(failure):
            logger.failure(qemu_version_parsing_error, failure)
            gui.curtain_down()

        d = getQemuOutput("qemu-system-x86_64", ["-version"])
        d.addCallbacks(install_qemu_version, logger.failure_eb,
                       errbackArgs=(retrieve_qemu_version_error, True))
        d.addErrback(close_panel)

        #panel = Gtk.Alignment(0.5, 0.5) new default values for xscale and yscale are 1, before : 0
	panel = Gtk.Alignment(0.5, 0.5, 0.0, 0.0)
        label = Gtk.Label("Loading configuration...")
        panel.add(label)
        panel.show_all()
        return panel

    def _get_config_view(self, gui):
        self.gui = gui
        self.usb_devices = list(self.original.config["usbdevlist"])

        self.state_manager = StateManager()
        self.state_manager.add_checkbutton_active(self.rbDeviceen,
            _("Mount cdrom option not active"), self.cbMount)
        self.state_manager.add_checkbutton_active(self.rbCdromen,
            _("File image option not active"), self.fcCdrom)
        self.state_manager.add_checkbutton_not_active(self.cbNovga,
            _("Graphical output disabled"), self.cbVnc, self.siVncN,
            self.lblVnc)
        self.state_manager.add_checkbutton_not_active(self.cbVnc,
            _("VNC enabled"), self.cbNovga)
        self.state_manager.add_checkbutton_active(self.cbKernelen,
            _("Custom kernel selction option disabled"), self.fcKernel)
        self.state_manager.add_checkbutton_active(self.cbInitrden,
            _("Initrd option disabled"), self.fcInitrd)
        self.state_manager.add_checkbutton_active(self.cbGdb,
            _("Kernel debugging disabled"), self.siGdbport, self.lblGdbport)

        # usb options
        def usb_check():
            active = self.cbUsbmode.get_active()
            if active and not os.access("/dev/bus/usb", os.W_OK):
                self.cbUsbmode.set_active(False)
                logger.error(usb_access)
                return False
            return active

        usbstate = State()
        tooltip = _("USB disabled or /dev/bus/usb not accessible")
        usbstate.add_control(SensitiveControl(self.btnBind, tooltip))
        usbstate.add_prerequisite(usb_check)
        self.cbUsbmode.connect("toggled", lambda cb: usbstate.check())
        usbstate.check()

        # kvm options
        def _check_kvm():
            if self.cbKvm.get_active():
                supported = tools.check_kvm()
                if not supported:
                    self.cbKvm.set_active(False)
                    logger.error(no_kvm)
                return supported
            return False

        kvmstate = State()
        kvmstate.add_prerequisite(_check_kvm)
        self.cbKvm.connect("toggled", lambda cb: kvmstate.check())
        kvmstate.check()

        # argv0/cpu/machine comboboxes
        exes = qemu.get_executables()
        self.lArgv0.set_data_source(map(widgets.ListEntry.from_tuple, exes))
        self.cbArgv0.set_selected_value(self.original.config["argv0"])
        self.cbArgv0.set_cell_data_func(self.crf1, self.crf1.set_text)
        self.cbCpu.set_cell_data_func(self.crf2, self.crf2.set_text)
        self.cbMachine.set_cell_data_func(self.crf3, self.crf3.set_text)

        # boot/sound/mount comboboxes
        boots = map(widgets.ListEntry.from_tuple, BOOT_DEVICE)
        self.lBoot.set_data_source(boots)
        self.cbBoot.set_selected_value(self.original.config["boot"])
        self.cbBoot.set_cell_data_func(self.crf4, self.crf4.set_text)
        sounds = map(widgets.ListEntry.from_tuple, SOUND_DEVICE)
        self.lSound.set_data_source(sounds)
        self.cbSound.set_selected_value(self.original.config["soundhw"])
        self.cbSound.set_cell_data_func(self.crf5, self.crf5.set_text)
        devices = map(widgets.ListEntry.from_tuple, MOUNT_DEVICE)
        self.lDevice.set_data_source(devices)
        self.cbMount.set_selected_value(self.original.config["device"])
        self.cbMount.set_cell_data_func(self.crf6, self.crf6.set_text)

        # harddisks
        self.__images_list = ImagesBindingList(gui.factory)
        formatter = ImageFormatter()
        self.lImages.set_data_source(self.__images_list)
        self.cbHda.set_selected_value(self.original.config["hda"].image)
        self.cbHda.set_cell_data_func(self.crf7, self.crf7.set_text)
        self.crf7.set_property("formatter", formatter)
        self.cbHdb.set_selected_value(self.original.config["hdb"].image)
        self.cbHdb.set_cell_data_func(self.crf8, self.crf8.set_text)
        self.crf8.set_property("formatter", formatter)
        self.cbHdc.set_selected_value(self.original.config["hdc"].image)
        self.cbHdc.set_cell_data_func(self.crf9, self.crf9.set_text)
        self.crf9.set_property("formatter", formatter)
        self.cbHdd.set_selected_value(self.original.config["hdd"].image)
        self.cbHdd.set_cell_data_func(self.crf10, self.crf10.set_text)
        self.crf10.set_property("formatter", formatter)
        self.cbFda.set_selected_value(self.original.config["fda"].image)
        self.cbFda.set_cell_data_func(self.crf11, self.crf11.set_text)
        self.crf11.set_property("formatter", formatter)
        self.cbFdb.set_selected_value(self.original.config["fdb"].image)
        self.cbFdb.set_cell_data_func(self.crf12, self.crf12.set_text)
        self.crf12.set_property("formatter", formatter)
        self.cbMtdblock.set_selected_value(
            self.original.config["mtdblock"].image)
        self.crf13.set_property("formatter", formatter)
        self.cbMtdblock.set_cell_data_func(self.crf13, self.crf13.set_text)

        cfg = self.original.config
        go = self.get_object
        for pname, wname in self.config_to_widget_mapping:
            go(wname).set_active(cfg[pname])
        for pname, wname in self.config_to_spinint_mapping:
            go(wname).set_value(cfg[pname])
        for pname, wname in self.config_to_filechooser_mapping:
            if cfg[pname]:
                go(wname).set_filename(cfg[pname])
        self.setup_netwoks_cards()
        go("cfg_Qemu_keyboard_text").set_text(cfg["keyboard"])
        go("kopt_textbutton").set_text(cfg["kopt"])
        return self.get_object("box_vmconfig")

    def configure_brick(self, gui):
        cfg = {}

        # argv0/cpu/machine comboboxes
        cfg["argv0"] = self.cbArgv0.get_selected_value() or ""
        cfg["cpu"] = self.cbCpu.get_selected_value() or ""
        cfg["machine"] = self.cbMachine.get_selected_value() or ""

        # boot/sound/mount comboboxes
        cfg["boot"] = self.cbBoot.get_selected_value()
        cfg["soundhw"] = self.cbSound.get_selected_value()
        cfg["device"] = self.cbMount.get_selected_value()

        # harddisks
        self.original.set_image("hda", self.cbHda.get_selected_value())
        self.original.set_image("hdb", self.cbHdb.get_selected_value())
        self.original.set_image("hdc", self.cbHdc.get_selected_value())
        self.original.set_image("hdd", self.cbHdd.get_selected_value())
        self.original.set_image("fda", self.cbFda.get_selected_value())
        self.original.set_image("fdb", self.cbFdb.get_selected_value())
        self.original.set_image("mtdblock",
                                self.cbMtdblock.get_selected_value())

        for config_name, widget_name in self.config_to_widget_mapping:
            cfg[config_name] = self.get_object(widget_name).get_active()
        for pname, wname in self.config_to_spinint_mapping:
            cfg[pname] = self.get_object(wname).get_value_as_int()
        for pname, wname in self.config_to_filechooser_mapping:
            filename = self.get_object(wname).get_filename()
            if filename:
                cfg[pname] = filename
        cfg["keyboard"] = self.get_object("cfg_Qemu_keyboard_text").get_text()
        cfg["kopt"] = self.get_object("kopt_textbutton").get_text()
        if self.cbUsbmode.get_active():
            devs = list(set(self.usb_devices))
        else:
            devs = []
        cfg["usbdevlist"] = devs
        self.original.update_usbdevlist(devs)
        self.original.set(cfg)

    def __dispose__(self):
        if self.__images_list is not None:
            dispose(self.__images_list)
            self.__images_list = None

    # signals

    def on_newimage_button_clicked(self, button):
        dialogs.choose_new_image(self.gui, self.gui.brickfactory)

    def on_configimage_button_clicked(self, button):
        dialogs.DisksLibraryDialog(self.original.factory).show()

    def on_newempty_button_clicked(self, button):
        dialogs.CreateImageDialog(self.gui, self.gui.brickfactory).show(
            self.gui.wndMain)

    def on_cbArgv0_changed(self, combobox):
        arch = self.cbArgv0.get_selected_value()
        if arch:
            cpus = map(widgets.ListEntry.from_tuple, qemu.get_cpus(arch))
            self.lCpu.set_data_source(cpus)
            machines = map(widgets.ListEntry.from_tuple,
                           qemu.get_machines(arch))
            self.lMachine.set_data_source(machines)

    def on_btnBind_clicked(self, button):
        dialogs.UsbDevWindow.show_dialog(self.gui, self.usb_devices)

    def _remove_link(self, link, model):
        if link.brick.proc and link.hotdel:
            # XXX: why checking hotdel? is a method it is always true or raise
            # an exception if it is not defined
            link.hotdel()
        self.original.remove_plug(link)
        itr = model.get_iter_first()
        while itr:
            plug = model.get_value(itr, 0)
            if plug is link:
                model.remove(itr)
                break
            itr = model.iter_next(itr)

    def ask_remove_link(self, link):
        question = _("Do you really want to delete the network interface?")
        model = self.get_object("plugsmodel")
        remove = lambda _: self._remove_link(link, model)
        dialogs.ConfirmDialog(question, on_yes=remove).show(
            self.gui.wndMain)

    def on_networkcards_treeview_key_press_event(self, treeview, event):
        if Gdk.keyval_from_name("Delete") == event.keyval:
            link = get_selection(treeview)
            if link is not None:
                self.ask_remove_link(link)
                return True

    def on_networkcards_treeview_button_release_event(self, treeview, event):
        if event.button == 3:
            link = get_element_at_click(treeview, event)
            if link:
                IMenu(link).popup(event.button, event.time, self, self.gui)
                return True

    def on_addplug_button_clicked(self, button):
        model = self.get_object("plugsmodel")
        dialogs.AddEthernetDialog(self.gui.brickfactory, self.original,
                                  model).show(self.gui.wndMain)

    def on_setdefaulticon_button_clicked(self, button):
        self.get_object("qemuicon").set_from_pixbuf(
            graphics.pixbuf_for_brick_type("qemu"))

    def on_icon_filechooser_file_set(self, filechooser):
        raise NotImplementedError(
            "QemuConfigController.on_icon_filechooser_file_set")


def config_panel_factory(context):
    type = context.get_type()
    if type == "Switch":
        return SwitchConfigController(context)
    elif type == "SwitchWrapper":
        return SwitchWrapperConfigController(context)
    elif type == "Tap":
        return TapConfigController(context)
    elif type == "Capture":
        return CaptureConfigController(context)
    elif type == "Wire":
        return WireConfigController(context)
    elif type == "Netemu":
        return NetemuConfigController(context)
    elif type == "TunnelConnect":
        return TunnelClientConfigController(context)
    elif type == "TunnelListen":
        return TunnelListenConfigController(context)
    elif type == "Qemu":
        return QemuConfigController(context)

registerAdapter(config_panel_factory, Brick, IConfigController)


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

        chooser = Gtk.FileChooserDialog(title=_("Select an image file"),
                action=Gtk.FileChooserAction.OPEN,
                buttons=(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                        Gtk.STOCK_SAVE, Gtk.ResponseType.OK))
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
    manager = project.manager

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
        return iter(self._factory.events)


def is_running_filter(model, itr):
    brick = model.get_value(itr, 0)
    if brick:
        return is_running(brick)


class VBGUI(TopologyMixin, ReadmeMixin, _Root):
    """
    The main GUI object for virtualbricks, containing all the configuration for
    the widgets and the connections to the main engine.
    """

    __bricks_binding_list = None
    __events_binding_list = None

    def __init__(self, factory, builder, textbuffer=None):
        self.factory = self.brickfactory = factory
        self.builder = builder
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
        task.LoopingCall(self.lRunning.refilter).start(2)
        self.__state_manager = StateManager()
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
        factory.connect("quit", self.on_quit)

        # Show the main window
        self.wndMain.show()

    def __initialize_components(self):
        # bricks tab
        self.tvBricks.set_cells_data_func()
        self.__bricks_binding_list = BricksBindingList(self.factory)
        self.lBricks.set_data_source(self.__bricks_binding_list)
        self.tvBricks.enable_model_drag_source(Gdk.ModifierType.BUTTON1_MASK,
                BRICK_DRAG_TARGETS, Gdk.DragAction.LINK)
        self.tvBricks.enable_model_drag_dest(BRICK_DRAG_TARGETS,
                Gdk.DragAction.LINK)

        # events tab
        self.tvEvents.set_cells_data_func()
        self.__events_binding_list = EventsBindingList(self.factory)
        self.lEvents.set_data_source(self.__events_binding_list)

        # jobs tab
        self.tvJobs.set_cells_data_func()
        self.lRunning.set_visible_func(is_running_filter)

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
        self.set_title()

    def curtain_up(self, brick):
        configframe = self.get_object("configframe")
        configframe.add(IConfigController(brick).get_view(self))
        configframe.show()
        self.get_object("main_notebook").hide()
        self.set_title("Virtualbricks (Configuring Brick %s)" %
                       brick.get_name())

    def set_title(self, title=None):
        if title is None:
            if project.manager.current:
                name = project.manager.current.name
                title = _("Virtualbricks (project: {0})").format(name)
                self.wndMain.set_title(title)
        else:
            self.wndMain.set_title(title)

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

    def on_wndMain_delete_event(self, window, event):
        #don't delete; hide instead
        if settings.get("systray"):
            window.hide()
            self.statusicon.set_tooltip("Virtualbricks Hidden")
            return True

    def ask_remove_brick(self, brick):
        self.__ask_for_deletion(self.brickfactory.del_brick, brick)

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
        if Gdk.keyval_name(event.keyval) in set(["Delete", "BackSpace"]):
            brick = treeview.get_selected_value()
            if brick is not None:
                self.ask_remove_brick(brick)

    def on_events_treeview_key_release_event(self, treeview, event):
        if Gdk.keyval_name(event.keyval) in set(["Delete", "BackSpace"]):
            event = treeview.get_selected_value()
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
        dialog.on_destroy = self.set_title
        dialog.show(self.wndMain)
        return True

    def on_menuFileOpen_activate(self, menuitem):
        dialog = dialogs.OpenProjectDialog(self)
        dialog.on_destroy = self.set_title
        dialog.show(self.wndMain)
        return True

    def on_menuFileRename_activate(self, menuitem):
        dialog = dialogs.RenameProjectDialog(self)
        dialog.on_destroy = self.set_title
        dialog.show(self.wndMain)
        return True

    def on_menuFileSave_activate(self, menuitem):
        self.on_save()
        return True

    def on_menuFileSaveAs_activate(self, menuitem):
        self.on_save()
        dialog = dialogs.SaveAsDialog(self.brickfactory,
              (prj.name for prj in project.manager))
        dialog.show(self.wndMain)
        return True

    def on_menuFileImport_activate(self, menuitem):
        d = dialogs.ImportDialog(self.brickfactory)
        d.on_destroy = self.set_title
        d.show(self.wndMain)
        return True

    def on_menuFileExport_activate(self, menuitem):
        self.on_save()
        dialog = dialogs.ExportProjectDialog(ProgressBar(self),
            filepath.FilePath(project.manager.current.path),
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

        def started_all(results):
            for success, value in results:
                if not success:
                    logger.failure(not_started, value)

        l = [brick.poweron() for brick in self.brickfactory.bricks]
        defer.DeferredList(l, consumeErrors=True).addCallback(started_all)
        return True

    def on_btnStopAll_clicked(self, toolbutton):
        for brick in self.brickfactory.bricks:
            brick.poweroff()
        return True

    def __show_config_if_selected(self, treeview):
        brick = treeview.get_selected_value()
        if brick:
            self.curtain_up(brick)
            return True
        return False

    def on_btnConfigure_clicked(self, toolbutton):
        return self.__show_config_if_selected(self.tvBricks)

    # events toolbar

    def on_btnNewEvent_clicked(self, toolbutton):
        dialogs.NewEventDialog(self).show(self.wndMain)
        return True

    def on_btnStartAllEvents_clicked(self, toolbutton):
        for event in self.brickfactory.events:
            event.poweron()
        return True

    def on_btnStopAllEvents_clicked(self, toolbutton):
        for event in self.brickfactory.events:
            event.poweroff()
        return True

    def on_btnConfigureEvent_clicked(self, toolbutton):
        return self.__show_config_if_selected(self.tvEvents)

    def confirm(self, message):
        dialog = Gtk.MessageDialog(None, Gtk.DialogFlags.MODAL, Gtk.MessageType.INFO,
                                   Gtk.ButtonsType.YES_NO, message)
        response = dialog.run()
        dialog.destroy()

        if response == Gtk.ResponseType.YES:
            return True
        elif response == Gtk.ResponseType.NO:
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
                IMenu(obj).popup(event.button, event.time, self)
            return True

    def on_events_treeview_button_release_event(self, treeview, event):
        return self.on_bricks_treeview_button_release_event(treeview, event)

    def on_bricks_treeview_row_activated(self, treeview, path, column):
        model = treeview.get_model()
        brick = model.get_value(model.get_iter(path), 0)
        self.startstop_brick(brick)

    def on_events_treeview_row_activated(self, treeview, path, column):
        model = treeview.get_model()
        event = model.get_value(model.get_iter(path), 0)
        event.toggle()

    def startstop_brick(self, brick):
        if is_running(brick):
            brick.poweroff().addErrback(logger.failure_eb, stop_error)
        else:
            brick.poweron().addErrback(logger.failure_eb, start_error)

    def on_joblist_treeview_button_release_event(self, treeview, event):
        if event.button == 3:
            pthinfo = treeview.get_path_at_pos(int(event.x), int(event.y))
            if pthinfo is not None:
                path, col, cellx, celly = pthinfo
                treeview.grab_focus()
                treeview.set_cursor(path, col, 0)
                model = treeview.get_model()
                brick = model.get_value(model.get_iter(path), 0)
                IJobMenu(brick).popup(event.button, event.time, self)
                return True

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
        brick = treeview.get_selected_value()
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
        return bool(self.tvBricks.get_selected_value())

    # Events tab signals

    def on_events_selection_changed(self, selection):
        self.__state_event_config.check()

    def __event_selected(self):
        return bool(self.tvEvents.get_selected_value())


class List(Gtk.ListStore):

    def __init__(self):
        Gtk.ListStore.__init__(self, object)

    def __iter__(self):
        i = self.get_iter_first()
        while i:
            yield self.get_value(i, 0)
            i = self.iter_next(i)

    def append(self, element):
        Gtk.ListStore.append(self, (element, ))

    def remove(self, element):
        itr = self.get_iter_first()
        while itr:
            el = self.get_value(itr, 0)
            if el is element:
                return Gtk.ListStore.remove(self, itr)
            itr = self.iter_next(itr)
        raise ValueError("%r not in list" % (element, ))

    def __delitem__(self, key):
        if isinstance(key, int):
            Gtk.ListStore.__delitem__(self, key)
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
        dialog = Gtk.MessageDialog(self.__parent, Gtk.DialogFlags.MODAL,
                Gtk.MessageType.ERROR, Gtk.ButtonsType.CLOSE)
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
        self.textbuffer = Gtk.TextBuffer()
        for name, attrs in TEXT_TAGS:
            self.textbuffer.create_tag(name, **attrs)
        self.logger_factory = AppLoggerFactory(self.textbuffer)
        brickfactory.Application.__init__(self, config)

    def get_namespace(self):
        return {"gui": self.gui}

    def _run(self, factory):
        # a bug in gtk2 make impossibile to use this and is not required anyway
        gtk.set_interactive(False)
        builder = load_ui()
        message_dialog = MessageDialogObserver()
        observer = log.FilteringLogObserver(message_dialog,
                                            (should_show_to_user,))
        logger.publisher.addObserver(observer, False)
        # disable default link_button action
        gtk.link_button_set_uri_hook(lambda b, s: None)
        self.gui = VBGUI(factory, builder, self.textbuffer)
        message_dialog.set_parent(self.gui.wndMain)

    def run(self, reactor):
        ret = brickfactory.Application.run(self, reactor)
        self.gui.set_title()
        return ret


def load_ui():
    try:
        builder = Gtk.Builder()
        builder.set_translation_domain("virtualbricks")
        source = graphics.get_data_filename("virtualbricks.ui")
        builder.add_from_file(source)
        return builder
    except:
        raise SystemExit("Cannot load glade file")
