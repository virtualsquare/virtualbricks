# -*- test-case-name: virtualbricks.tests.test_gui -*-
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

import gtk
from zope.interface import implementer
from twisted.internet import reactor, utils, defer, error
from twisted.python import failure

from virtualbricks import (base, bricks, events, virtualmachines, link, log,
                           settings, tools)

from virtualbricks.gui import graphics, dialogs, help, interfaces


logger = log.Logger("virtualbricks.gui.gui")
cannot_rename = log.Event("Cannot rename Brick: it is in use.")
snap_error = log.Event("Error on snapshot")
invalid_name = log.Event("Invalid name!")
resume_vm = log.Event("Resuming virtual machine {name}")
proc_signal = log.Event("Sending to process signal {signame}!")
proc_restart = log.Event("Restarting process!")
s_r_not_supported = log.Event("Suspend/Resume not supported on this disk.")
send_acpi = log.Event("send ACPI {event}")
machine_type = log.Event("Error while retrieving machines types.")
cpu_model = log.Event("Error while retrieving cpu model.")
usb_access = log.Event("Cannot access /dev/bus/usb. Check user privileges.")
no_kvm = log.Event("No KVM support found on the system. Check your active "
                   "configuration. KVM will stay disabled.")
search_usb = log.Event("Searching USB devices")
retr_usb = log.Event("Error while retrieving usb devices.")
event_in_use = log.Event("Cannot rename event: it is in use.")

if False:  # pyflakes
    _ = str


def cancel_call(passthru, call):
    if call.active():
        call.cancel()
    return passthru


def refilter(passthru, filter_model):
    filter_model.refilter()
    return passthru


@implementer(interfaces.IMenu)
class BaseMenu:

    def __init__(self, brick):
        self.original = brick

    def build(self, gui):
        menu = gtk.Menu()
        menu.append(gtk.MenuItem(self.original.get_name(), False))
        menu.append(gtk.SeparatorMenuItem())
        start_stop = gtk.MenuItem("_Start/Stop")
        start_stop.connect("activate", self.on_startstop_activate, gui)
        menu.append(start_stop)
        delete = gtk.MenuItem("_Delete")
        delete.connect("activate", self.on_delete_activate, gui)
        menu.append(delete)
        copy = gtk.MenuItem("Make a C_opy")
        copy.connect("activate", self.on_copy_activate, gui)
        menu.append(copy)
        rename = gtk.MenuItem("Re_name")
        rename.connect("activate", self.on_rename_activate, gui)
        menu.append(rename)
        configure = gtk.MenuItem("_Configure")
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
        attach = gtk.MenuItem("_Attach Event")
        attach.connect("activate", self.on_attach_activate, gui)
        menu.append(attach)
        return menu

    def on_startstop_activate(self, menuitem, gui):
        gui.startstop_brick(self.original)

    def on_delete_activate(self, menuitem, gui):
        gui.ask_remove_brick(self.original)

    def on_copy_activate(self, menuitem, gui):
        gui.brickfactory.dupbrick(self.original)

    def on_rename_activate(self, menuitem, gui):
        if self.original.proc is not None:
            logger.error(cannot_rename)
        else:
            dialogs.RenameBrickDialog(self.original,
                gui.brickfactory.normalize_name).show(
                    gui.get_object("main_win"))

    def on_attach_activate(self, menuitem, gui):
        gui.on_brick_attach_event(menuitem)

interfaces.registerAdapter(BrickPopupMenu, bricks.Brick, interfaces.IMenu)


class VMPopupMenu(BrickPopupMenu):

    def build(self, gui):
        menu = BrickPopupMenu.build(self, gui)
        resume = gtk.MenuItem("_Resume VM")
        resume.connect("activate", self.on_resume_activate, gui)
        menu.append(resume)
        return menu

    def snapshot(self, factory):

        def grep(out, pattern):
            if out.find(pattern) == -1:
                raise RuntimeError(_("Cannot find suspend point."))

        def loadvm(_):
            if self.original.proc is not None:
                self.original.send("loadvm virtualbricks\n")
            else:
                self.original.poweron("virtualbricks")

        img = factory.get_image_by_name(self.original.get("hda"))
        if img is not None:
            args = ["snapshot", "-l", img.path]
            output = utils.getProcessOutput("qemu-img", args, os.environ)
            output.addCallback(grep, "virtualbricks")
            output.addCallback(loadvm)
            output.addErrback(logger.failure_eb, snap_error)
            return output
        try:
            raise RuntimeError("No such image")
        except:
            return defer.fail(failure.Failure())

    def on_resume_activate(self, menuitem, gui):
        logger.debug(resume_vm, name=self.original.get_name())
        gui.user_wait_action(self.snapshot, gui.brickfactory)


interfaces.registerAdapter(VMPopupMenu, virtualmachines.VirtualMachine,
                           interfaces.IMenu)


class EventPopupMenu(BaseMenu):

    def on_startstop_activate(self, menuitem, gui):
        self.original.toggle()

    def on_delete_activate(self, menuitem, gui):
        gui.ask_remove_event(self.original)

    def on_copy_activate(self, menuitem, gui):
        gui.brickfactory.dupevent(self.original)

    def on_rename_activate(self, menuitem, gui):
        if not self.original.scheduled:
            dialogs.RenameDialog(self.original,
                gui.brickfactory.normalize_name).show(
                    gui.get_object("main_win"))
        else:
            logger.error(event_in_use)

interfaces.registerAdapter(EventPopupMenu, events.Event, interfaces.IMenu)


@implementer(interfaces.IMenu)
class LinkMenu:

    def __init__(self, original):
        self.original = original

    def build(self, controller, gui):
        menu = gtk.Menu()
        edit = gtk.MenuItem(_("Edit"))
        edit.connect("activate", self.on_edit_activate, controller, gui)
        menu.append(edit)
        remove = gtk.MenuItem(_("Remove"))
        remove.connect("activate", self.on_remove_activate, controller)
        menu.append(remove)
        return menu

    def popup(self, button, time, controller, gui):
        menu = self.build(controller, gui)
        menu.show_all()
        menu.popup(None, None, None, button, time)

    def on_edit_activate(self, menuitem, controller, gui):
        parent = gui.get_object("main_win")
        dialogs.EditEthernetDialog(gui.brickfactory, self.original.brick,
                                   self.original).show(parent)

    def on_remove_activate(self, menuitem, controller):
        controller.ask_remove_link(self.original)


interfaces.registerAdapter(LinkMenu, link.Plug, interfaces.IMenu)
interfaces.registerAdapter(LinkMenu, link.Sock, interfaces.IMenu)


@implementer(interfaces.IMenu)
class JobMenu:

    def __init__(self, original):
        self.original = original

    def build(self, gui):
        menu = gtk.Menu()
        open = gtk.MenuItem(_("Open control monitor"))
        open.connect("activate", self.on_open_activate)
        menu.append(open)
        menu.append(gtk.SeparatorMenuItem())
        stop = gtk.ImageMenuItem(gtk.STOCK_STOP)
        stop.connect("activate", self.on_stop_activate)
        menu.append(stop)
        cont = gtk.ImageMenuItem(gtk.STOCK_MEDIA_PLAY)
        cont.set_label(_("Continue"))
        cont.connect("activate", self.on_cont_activate)
        menu.append(cont)
        menu.append(gtk.SeparatorMenuItem())
        reset = gtk.ImageMenuItem(gtk.STOCK_REDO)
        reset.set_label(_("Restart"))
        reset.connect("activate", self.on_reset_activate)
        menu.append(reset)
        kill = gtk.ImageMenuItem(gtk.STOCK_STOP)
        kill.set_label(_("Kill"))
        kill.connect("activate", self.on_kill_activate, gui)
        menu.append(kill)
        return menu

    def popup(self, button, time, gui):
        menu = self.build(gui)
        menu.show_all()
        menu.popup(None, None, None, button, time)

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
        d.addBoth(cancel_call, call)
        d.addCallback(lambda _: self.original.poweron())

    def on_kill_activate(self, menuitem, gui):
        logger.debug(proc_signal, signame="SIGKILL")
        try:
            d = self.original.poweroff(kill=True)
            d.addCallback(refilter, gui.running_bricks)
        except error.ProcessExitedAlready:
            pass

interfaces.registerAdapter(JobMenu, bricks.Brick, interfaces.IJobMenu)


class VMJobMenu(JobMenu):

    def build(self, gui):
        menu = JobMenu.build(self, gui)
        suspend = gtk.MenuItem(_("Suspend virtual machine"))
        suspend.connect("activate", self.on_suspend_activate, gui)
        menu.insert(suspend, 5)
        powerdown = gtk.MenuItem(_("Send ACPI powerdown"))
        powerdown.connect("activate", self.on_powerdown_activate)
        menu.insert(powerdown, 6)
        reset = gtk.MenuItem(_("Send ACPI hard reset"))
        reset.connect("activate", self.on_reset_activate)
        menu.insert(reset, 7)
        menu.insert(gtk.SeparatorMenuItem(), 8)
        term = gtk.ImageMenuItem(gtk.STOCK_DELETE)
        term.set_label(_("Terminate"))
        term.connect("activate", self.on_term_activate, gui)
        menu.insert(term, 10)
        return menu

    def suspend(self, factory):

        def do_suspend(exit_code):
            if exit_code == 0:
                done = defer.Deferred()
                self.original.send("savevm virtualbricks\n", done)
                done.addCallback(lambda _: self.original.poweroff())
            else:
                logger.error(s_r_not_supported)

        img = factory.get_image_by_name(self.original.get("hda"))
        if not img:
            logger.error(s_r_not_supported)
            try:
                raise RuntimeError(_("Suspend/Resume not supported on this "
                                     "disk."))
            except:
                return defer.fail()
        args = ["snapshot", "-c", "virtualbricks", img.path]
        value = utils.getProcessValue("qemu-img", args, os.environ)
        value.addCallback(do_suspend)
        return value

    def on_suspend_activate(self, menuitem, gui):
        gui.user_wait_action(self.suspend, gui.factory)

    def on_powerdown_activate(self, menuitem):
        logger.info(send_acpi, event="powerdown")
        self.original.send("system_powerdown\n")

    def on_reset_activate(self, menuitem):
        logger.info(send_acpi, event="reset")
        self.original.send("system_reset\n")

    def on_term_activate(self, menuitem, gui):
        logger.debug(proc_signal, signame="SIGTERM")
        d = self.original.poweroff(term=True)
        d.addCallback(refilter, gui.running_bricks)

interfaces.registerAdapter(VMJobMenu, virtualmachines.VirtualMachine,
                           interfaces.IJobMenu)


@implementer(interfaces.IConfigController)
class ConfigController(object):

    domain = "virtualbricks"
    resource = None

    def __init__(self, original):
        self.original = original
        self.builder = builder = gtk.Builder()
        builder.set_translation_domain(self.domain)
        builder.add_from_file(graphics.get_filename("virtualbricks.gui",
                                                    self.resource))
        builder.connect_signals(self)

    def on_ok_button_clicked(self, button, gui):
        self.configure_brick(gui)
        gui.curtain_down()

    # def on_save_button_clicked(self, button, gui):
    #     # TODO: update config values
    #     self.configure_brick(gui)

    def on_cancel_button_clicked(self, button, gui):
        gui.curtain_down()

    def get_object(self, name):
        return self.builder.get_object(name)

    def get_view(self, gui):
        bbox = gtk.HButtonBox()
        bbox.set_layout(gtk.BUTTONBOX_END)
        bbox.set_spacing(5)
        ok_button = gtk.Button(stock=gtk.STOCK_OK)
        ok_button.connect("clicked", self.on_ok_button_clicked, gui)
        bbox.add(ok_button)
        bbox.set_child_secondary(ok_button, False)
        # save_button = gtk.Button(stock=gtk.STOCK_SAVE)
        # save_button.connect("clicked", self.on_save_button_clicked, gui)
        # bbox.add(save_button)
        cancel_button = gtk.Button(stock=gtk.STOCK_CANCEL)
        cancel_button.connect("clicked", self.on_cancel_button_clicked, gui)
        bbox.add(cancel_button)
        bbox.set_child_secondary(cancel_button, True)
        box = gtk.VBox()
        box.pack_end(bbox, False)
        box.pack_end(gtk.HSeparator(), False, False, 3)
        box.show_all()
        box.pack_start(self.get_config_view(gui))
        return box


class EventConfigController(ConfigController, dialogs.EventControllerMixin):

    resource = "data/eventconfig.ui"

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
        if gtk.gdk.keyval_name(event.keyval) not in dialogs.VALIDKEY:
            return True

    def on_action_treeview_key_press_event(self, treeview, event):
        if gtk.gdk.keyval_name(event.keyval) == "Delete":
            selection = treeview.get_selection()
            model, selected = selection.get_selected_rows()
            rows = []
            for path in selected:
                rows.append(gtk.TreeRowReference(model, path))
            for row in rows:
                iter = model.get_iter(row.get_path())
                next = model.iter_next(iter)
                model.remove(iter)
                if next is None:
                    self.model.append(("", False))

interfaces.registerAdapter(EventConfigController, events.Event,
                           interfaces.IConfigController)


class SwitchConfigController(ConfigController):

    resource = "data/switchconfig.ui"

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

    resource = "data/switchwrapperconfig.ui"

    def get_config_view(self, gui):
        self.get_object("entry").set_text(self.original.get("path"))
        return self.get_object("table1")

    def configure_brick(self, gui):
        self.original.set({"path": self.get_object("entry").get_text()})


def _sock_should_visible(model, iter):
    sock = model.get_value(iter, 0)
    return sock and (sock.brick.get_type().startswith('Switch') or
                     settings.femaleplugs)

class _PlugMixin(object):

    def _set_text(self, column, cell_renderer, model, itr):
        sock = model.get_value(itr, 0)
        cell_renderer.set_property("text", sock.nickname)

    def configure_sock_combobox(self, combo, model, brick, plug, gui):
        model.set_visible_func(_sock_should_visible)
        combo.set_model(model)
        cell = combo.get_cells()[0]
        combo.set_cell_data_func(cell, self._set_text)
        if plug.configured():
            itr = model.get_iter_first()
            while itr:
                if model[itr][0] is plug.sock:
                    combo.set_active_iter(itr)
                    break
                itr = model.iter_next(itr)

    def connect_plug(self, plug, combo):
        itr = combo.get_active_iter()
        if itr:
            model = combo.get_model()
            plug.connect(model[itr][0])


class TapConfigController(_PlugMixin, ConfigController):

    resource = "data/tapconfig.ui"

    def get_config_view(self, gui):
        model = gui.brickfactory.socks.filter_new()
        combo = self.get_object("combobox")
        self.configure_sock_combobox(combo, model, self.original,
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

    resource = "data/captureconfig.ui"

    def get_config_view(self, gui):
        model = gui.brickfactory.socks.filter_new()
        combo = self.get_object("combobox1")
        self.configure_sock_combobox(combo, model, self.original,
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

    resource = "data/wireconfig.ui"

    def get_config_view(self, gui):
        model = gui.brickfactory.socks.filter_new()
        for i, wname in enumerate(("sock0_combobox", "sock1_combobox")):
            combo = self.get_object(wname)
            self.configure_sock_combobox(combo, model, self.original,
                                         self.original.plugs[i], gui)

        return self.get_object("vbox")

    def configure_brick(self, gui):
        for i, wname in enumerate(("sock0_combobox", "sock1_combobox")):
            self.connect_plug(self.original.plugs[i], self.get_object(wname))


NO, MAYBE, YES = range(3)


@implementer(interfaces.IPrerequisite)
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


@implementer(interfaces.IState)
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


@implementer(interfaces.IControl)
class SensitiveControl:

    tooltip = None

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


@implementer(interfaces.IStateManager)
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

    resource = "data/netemuconfig.ui"
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
        model = gui.brickfactory.socks.filter_new()
        for i, wname in enumerate(("sock0_combobox", "sock1_combobox")):
            combo = self.get_object(wname)
            self.configure_sock_combobox(combo, model, self.original,
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

    resource = "data/tunnellconfig.ui"

    def get_config_view(self, gui):
        model = gui.brickfactory.socks.filter_new()
        combo = self.get_object("combobox")
        self.configure_sock_combobox(combo, model, self.original,
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


class QemuConfigController(ConfigController):

    resource = "data/qemuconfig.ui"
    config_to_widget_mapping = (
        ("snapshot", "snapshot_checkbutton"),
        ("deviceen", "deviceen_radiobutton"),
        ("cdromen", "cdromen_radiobutton"),
        ("use_virtio", "virtio_checkbutton"),
        ("privatehda", "privatehda_checkbutton"),
        ("privatehdb", "privatehdb_checkbutton"),
        ("privatehdc", "privatehdc_checkbutton"),
        ("privatehdd", "privatehdd_checkbutton"),
        ("privatefda", "privatefda_checkbutton"),
        ("privatefdb", "privatefdb_checkbutton"),
        ("privatemtdblock", "privatemtdblock_checkbutton"),
        ("kvm", "kvm_checkbutton"),
        ("kvmsm", "kvmsm_checkbutton"),
        ("novga", "novga_checkbutton"),
        ("vga", "vga_checkbutton"),
        ("vnc", "vnc_checkbutton"),
        ("sdl", "sdl_checkbutton"),
        ("portrait", "portrait_checkbutton"),
        ("usbmode", "usbmode_checkbutton"),
        ("rtc", "rtc_checkbutton"),
        ("tdf", "tdf_checkbutton"),
        ("serial", "serial_checkbutton"),
        ("kernelenbl", "kernelenbl_checkbutton"),
        ("initrdenbl", "initrdenbl_checkbutton"),
        ("gdb", "gdb_checkbutton")
    )
    config_to_combo_mapping = (
        ("boot", "boot_combobox"),
        ("device", "device_combobox"),
        ("argv0", "argv0_combobox"),
        ("cpu", "cpu_combobox"),
        ("machine", "machine_combobox"),
        ("soundhw", "soundhw_combobox"),
    )
    hd_to_combo_mapping = (
        ("hda", "hda_combobox"),
        ("hdb", "hdb_combobox"),
        ("hdc", "hdc_combobox"),
        ("hdd", "hdd_combobox"),
        ("fda", "fda_combobox"),
        ("fdb", "fdb_combobox"),
        ("mtdblock", "mtdblock_combobox")
    )
    config_to_filechooser_mapping = (
        ("cdrom", "cdrom_filechooser"),
        ("kernel", "kernel_filechooser"),
        ("initrd", "initrd_filechooser"),
        ("icon", "icon_filechooser")
    )
    config_to_spinint_mapping = (
        ("smp", "smp_spinint"),
        ("ram", "ram_spinint"),
        ("kvmsmem", "kvmsmem_spinint"),
        ("vncN", "vncN_spinint"),
        ("gdbport", "gdbport_spinint")
    )

    def _combo_select(self, combo, value):
        model = combo.get_model()
        itr = model.get_iter_first()
        while itr:
            if model[itr][1] == value:
                combo.set_active_iter(itr)
                break
            itr = model.iter_next(itr)

    def _set_text(self, layout, cell, model, itr):
        cell.set_property("text", model[itr][0].name)

    def _build_images_model(self, model, images):
        model.clear()
        model.append(("", None))
        itr = images.get_iter_first()
        while itr:
            image = images[itr][0]
            model.append((image.name, image))
            itr = images.iter_next(itr)

    def setup_netwoks_cards(self):
        vmplugs = self.get_object("plugsmodel")
        vmplugs.clear()
        for plug in self.original.plugs:
            vmplugs.append((plug, ))

        if self.gui.config.femaleplugs:
            for sock in self.original.socks:
                vmplugs.append((sock,))

        def set_vlan(column, cell_renderer, model, itr):
            vlan = model.get_path(itr)[0]
            cell_renderer.set_property("text", vlan)

        def set_connection(column, cell_renderer, model, iter):
            link = model.get_value(iter, 0)
            if link.mode == "hostonly":
                conn = "Host"
            elif link.sock:
                conn = link.sock.brick.name
            elif link.mode == "sock" and self.gui.config.femaleplugs:
                conn = "Vde socket (female plug)"
            else:
                conn = "None"
            cell_renderer.set_property("text", conn)

        def set_model(column, cell_renderer, model, iter):
            link = model.get_value(iter, 0)
            cell_renderer.set_property("text", link.model)

        def set_mac(column, cell_renderer, model, iter):
            link = model.get_value(iter, 0)
            cell_renderer.set_property("text", link.mac)

        vlan_c = self.get_object("vlan_treeviewcolumn")
        vlan_cr = self.get_object("vlan_cellrenderer")
        vlan_c.set_cell_data_func(vlan_cr, set_vlan)
        connection_c = self.get_object("connection_treeviewcolumn")
        connection_cr = self.get_object("connection_cellrenderer")
        connection_c.set_cell_data_func(connection_cr, set_connection)
        model_c = self.get_object("model_treeviewcolumn")
        model_cr = self.get_object("model_cellrenderer")
        model_c.set_cell_data_func(model_cr, set_model)
        mac_c = self.get_object("mac_treeviewcolumn")
        mac_cr = self.get_object("mac_cellrenderer")
        mac_c.set_cell_data_func(mac_cr, set_mac)

    def get_config_view(self, gui):
        self.gui = gui
        cfg = self.original.config
        go = self.get_object
        argv0 = go("argv0_combobox")
        model = argv0.get_model()
        for found in tools.check_missing_qemu(gui.config.get("qemupath"))[1]:
            if found.startswith("qemu-system-"):
                model.append((found[12:], found))
            else:
                model.append((found, found))
        self._build_images_model(go("imagesmodel"),
                                 self.original.factory.disk_images)
        for pname, wname in self.config_to_widget_mapping:
            go(wname).set_active(cfg[pname])
        for pname, wname in self.config_to_spinint_mapping:
            go(wname).set_value(cfg[pname])
        for pname, wname in self.config_to_combo_mapping:
            self._combo_select(go(wname), cfg[pname])
        for pname, wname in self.hd_to_combo_mapping:
            self._combo_select(go(wname), self.original.config[pname].image)
        for pname, wname in self.config_to_filechooser_mapping:
            if cfg[pname]:
                go(wname).set_filename(cfg[pname])
        self.setup_netwoks_cards()
        go("cfg_Qemu_keyboard_text").set_text(cfg["keyboard"])
        return self.get_object("box_vmconfig")

    def _config_set_combo(self, config, name, combo):
        model = combo.get_model()
        itr = combo.get_active_iter()
        if itr:
            obj = model[itr][1]
            if obj is None:
                obj = ""
            config[name] = obj

    def _hd_config_set_combo(self, disk, combo):
        model = combo.get_model()
        itr = combo.get_active_iter()
        if itr:
            img = model[itr][1]
            disk.set_image(img)

    def configure_brick(self, gui):
        cfg = {}
        for config_name, widget_name in self.config_to_widget_mapping:
            cfg[config_name] = self.get_object(widget_name).get_active()
        for pname, wname in self.config_to_spinint_mapping:
            cfg[pname] = self.get_object(wname).get_value_as_int()
        for pname, wname in self.config_to_combo_mapping:
            self._config_set_combo(cfg, pname, self.get_object(wname))
        for pname, wname in self.hd_to_combo_mapping:
            self._hd_config_set_combo(self.original.config[pname],
                                      self.get_object(wname))
        for pname, wname in self.config_to_filechooser_mapping:
            filename = self.get_object(wname).get_filename()
            if filename:
                cfg[pname] = filename
        cfg["keyboard"] = self.get_object("cfg_Qemu_keyboard_text").get_text()
        self.original.set(cfg)

    def on_deviceen_radiobutton_toggled(self, radiobutton):
        self.get_object("device_combobox").set_sensitive(
            radiobutton.get_active())

    def on_cdromen_radiobutton_toggled(self, radiobutton):
        self.get_object("cdrom_filechooser").set_sensitive(
            radiobutton.get_active())

    def on_newimage_button_clicked(self, button):
        dialogs.choose_new_image(self.gui, self.gui.brickfactory)

    def on_configimage_button_clicked(self, button):
        dialogs.DisksLibraryDialog(self.original.factory).show()

    def on_newempty_button_clicked(self, button):
        dialogs.CreateImageDialog(self.gui, self.gui.brickfactory).show(
            self.gui.get_object("main_win"))

    def _update_cpu_combobox(self, output, combobox):
        model = combobox.get_model()
        model.clear()
        lines = iter(output.splitlines())
        if output.startswith("Available CPUs:"):
            next(lines)
        for line in lines:
            if line.startswith(" "):
                label = value = line.strip()
            else:
                _, v = line.split(None, 1)
                label = value = v.strip("'[]")
            itr = model.append((label, value))
            if self.original.get("cpu") == value:
                combobox.set_active_iter(itr)

    def _update_machine_combobox(self, output, combobox):
        model = combobox.get_model()
        model.clear()
        lines = iter(output.splitlines())
        next(lines)
        for line in lines:
            value, label = line.split(None, 1)
            itr = model.append((label, value))
            if self.original.get("machine") == value:
                combobox.set_active_iter(itr)

    def on_argv0_combobox_changed(self, combobox):
        itr = combobox.get_active_iter()
        if itr:
            argv0 = combobox.get_model()[itr][1]
            exe = os.path.join(self.gui.config.get('qemupath'), argv0)
            exit = utils.getProcessOutput(exe, ["-M", "?"])
            cmb = self.get_object("machine_combobox")
            exit.addCallback(self._update_machine_combobox, cmb)
            exit.addErrback(logger.failure_eb, machine_type)

            exit = utils.getProcessOutput(exe, ["-cpu", "?"])
            cmb = self.get_object("cpu_combobox")
            exit.addCallback(self._update_cpu_combobox, cmb)
            exit.addErrback(logger.failure_eb, cpu_model)

    def on_kvm_checkbutton_toggled(self, togglebutton):
        if togglebutton.get_active():
            kvm = tools.check_kvm(self.gui.config.get("qemupath"))
            self._kvm_toggle_all(kvm)
            togglebutton.set_active(kvm)
            if not kvm:
                logger.error(no_kvm)
        else:
            self._kvm_toggle_all(False)

    def _kvm_toggle_all(self, enabled):
        self.get_object("kvmsmem_spinint").set_sensitive(enabled)
        self.get_object("kvmsm_checkbutton").set_sensitive(enabled)
        # disable incompatible options
        self.get_object("tdf_checkbutton").set_active(enabled)
        self.get_object("tdf_checkbutton").set_sensitive(enabled)
        self._disable_qemu_combos(not enabled)

    def _disable_qemu_combos(self, active):
        self.get_object("argv0_combobox").set_sensitive(active)
        self.get_object("cpu_combobox").set_sensitive(active)
        self.get_object("machine_combobox").set_sensitive(active)

    def on_vnc_novga_checkbutton_toggled(self, togglebutton):
        novga = self.get_object("novga_checkbutton")
        vnc = self.get_object("vnc_checkbutton")
        active = not togglebutton.get_active()
        if togglebutton is novga:
            vnc.set_sensitive(active)
            self.get_object("vncN_spinint").set_sensitive(active)
            self.get_object("label17").set_sensitive(active)
        else:
            novga.set_sensitive(active)

    def on_usbmode_checkbutton_toggled(self, togglebutton):
        active = togglebutton.get_active()
        if active and not os.access("/dev/bus/usb", os.W_OK):
            logger.error(usb_access)
            togglebutton.set_active(False)
        else:
            self.original.set({"usbmode": active})
            if not active:
                self.original.set({"usbdevlist": []})
            self.get_object("bind_button").set_sensitive(active)

    def on_bind_button_clicked(self, button):

        def show_dialog(output):
            dialogs.UsbDevWindow(self.gui, output.strip(), self.original).show(
                self.gui.get_object("main_win"))

        logger.info(search_usb)
        devices_d = utils.getProcessOutput("lsusb", env=os.environ)
        devices_d.addCallback(show_dialog)
        devices_d.addErrback(logger.failure_eb, retr_usb)
        self.gui.user_wait_action(devices_d)

    def _remove_link(self, link, model):
        if link.brick.proc and link.hotdel:
            # XXX: why checking hotdel? is a method it is always true or raise
            # an exception if it is not defined
            link.hotdel()
        link.brick.remove_plug(link)
        itr = model.get_iter_first()
        while itr:
            link = model.get_value(itr, 0)
            if link is link:
                model.remove(itr)
                break
            itr = model.iter_next(itr)

    def ask_remove_link(self, link):
        question = _("Do you really want to delete the network interface?")
        model = self.get_object("plugsmodel")
        remove = lambda _: self._remove_link(link, model)
        dialogs.ConfirmDialog(question, on_yes=remove).show(
            self.gui.get_object("main_win"))

    def on_networkcards_treeview_key_press_event(self, treeview, event):
        if gtk.gdk.keyval_from_name("Delete") == event.keyval:
            link = get_selection(treeview)
            if link is not None:
                self.ask_remove_link(link)
                return True

    def on_networkcards_treeview_button_release_event(self, treeview, event):
        if event.button == 3:
            link = get_element_at_click(treeview, event)
            if link:
                interfaces.IMenu(link).popup(event.button, event.time, self,
                                             self.gui)
                return True

    def on_addplug_button_clicked(self, button):
        model = self.get_object("plugsmodel")
        parent = self.gui.get_object("main_win")
        dialogs.AddEthernetDialog(self.gui.brickfactory, self.original,
                                  model).show(parent)

    def on_kernelenbl_checkbutton_toggled(self, togglebutton):
        self.get_object("kernel_filechooser").set_sensitive(
            togglebutton.get_active())

    def on_initrdenbl_checkbutton_toggled(self, togglebutton):
        self.get_object("initrd_filechooser").set_sensitive(
            togglebutton.get_active())

    def on_gdb_checkbutton_toggled(self, togglebutton):
        self.get_object("gdbport_spinint").set_sensitive(
            togglebutton.get_active())

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

interfaces.registerAdapter(config_panel_factory, base.Base,
                           interfaces.IConfigController)
