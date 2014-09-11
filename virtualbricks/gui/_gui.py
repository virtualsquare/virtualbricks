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
import string

import gtk
from zope.interface import implementer
from twisted.internet import reactor, utils, defer, error

from virtualbricks import (base, bricks, events, virtualmachines, link, log,
                           settings, tools, qemu)

from virtualbricks.gui import graphics, dialogs, help, interfaces
from virtualbricks.gui.controls import ComboBox, ListEntry


__metaclass__ = type


logger = log.Logger("virtualbricks.gui.gui")
cannot_rename = log.Event("Cannot rename Brick: it is in use.")
snap_error = log.Event("Error on snapshot")
invalid_name = log.Event("Invalid name!")
resume_vm = log.Event("Resuming virtual machine {name}")
savevm = log.Event("Save snapshot on virtual machine {name}")
proc_signal = log.Event("Sending to process signal {signame}!")
proc_restart = log.Event("Restarting process!")
s_r_not_supported = log.Event("Suspend/Resume not supported on this disk.")
send_acpi = log.Event("send ACPI {acpievent}")
machine_type = log.Event("Error while retrieving machines types.")
cpu_model = log.Event("Error while retrieving cpu model.")
usb_access = log.Event("Cannot access /dev/bus/usb. Check user privileges.")
no_kvm = log.Event("No KVM support found on the system. Check your active "
                   "configuration. KVM will stay disabled.")
event_in_use = log.Event("Cannot rename event: it is in use.")
retrieve_qemu_version_error = log.Event("Error while retrieving qemu version.")
qemu_version_parsing_error = log.Event("Error while parsing qemu version")
building_controller_error = log.Event("Unknow error while building controller")

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
        output = utils.getProcessOutput("qemu-img", args, os.environ)
        output.addCallback(grep, "virtualbricks")
        output.addCallback(loadvm)
        logger.log_failure(output, snap_error)
        return output

    def on_resume_activate(self, menuitem, gui):
        logger.debug(resume_vm, name=self.original.get_name())
        gui.user_wait_action(self.resume(gui.brickfactory))


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

    def __getattr__(self, name):
        obj = self.builder.get_object(name)
        if obj is None:
            raise AttributeError(name)
        return obj

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

    resource = "data/tapconfig.ui"

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

    resource = "data/captureconfig.ui"

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

    resource = "data/wireconfig.ui"

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


@implementer(interfaces.IControl)
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


@implementer(interfaces.IControl)
class ActiveControl:

    def __init__(self, widget):
        self.widget = widget

    def react(self, enable):
        if not enable:
            self.widget.set_active(False)


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

    resource = "data/tunnellconfig.ui"

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


class UsbState(State):

    def __init__(self, togglebtn, button):
        State.__init__(self)
        tooltip = _("USB disabled or /dev/bus/usb not accessible")
        self.add_control(SensitiveControl(button, tooltip))
        self.add_prerequisite(lambda: self.usb_check(togglebtn))
        togglebtn.connect("toggled", lambda cb: self.check())
        self.check()

    def usb_check(self, togglebtn):
        active = togglebtn.get_active()
        if active and not os.access("/dev/bus/usb", os.W_OK):
            togglebtn.set_active(False)
            logger.error(usb_access)
            return False
        return active


class KvmState(State):

    def __init__(self, togglebtn, controller, config):
        State.__init__(self)
        self.togglebtn = togglebtn
        self.config = config
        tooltip = _("KVM support not found")
        self.add_control(SensitiveControl(controller.siKvmsmem, tooltip))
        self.add_control(SensitiveControl(controller.cbKvmsm, tooltip))
        self.add_control(SensitiveControl(controller.lblKvmsm, tooltip))
        self.add_control(SensitiveControl(controller.cbTdf, tooltip))
        self.add_control(ActiveControl(controller.cbTdf))
        tooltip = _("KVM activated")
        self.add_control(InsensitiveControl(controller.cbArgv0, tooltip))
        self.add_control(InsensitiveControl(controller.cbCpu, tooltip))
        self.add_control(InsensitiveControl(controller.cbMachine, tooltip))
        self.add_prerequisite(self.check_kvm)
        togglebtn.connect("toggled", lambda cb: self.check())
        self.check()

    def check_kvm(self):
        if self.togglebtn.get_active():
            supported = tools.check_kvm(self.config.get("qemupath"))
            if not supported:
                self.togglebtn.set_active(False)
                logger.error(no_kvm)
            return supported
        return False


class QemuConfigController(ConfigController):

    resource = "data/qemuconfig.ui"
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

        qemu_exe = os.path.join(gui.config.get('qemupath'), "kvm")
        d = utils.getProcessOutput(qemu_exe, ["-version"])
        d.addCallbacks(install_qemu_version, logger.failure_eb,
                       errbackArgs=(retrieve_qemu_version_error, True))
        d.addErrback(close_panel)

        panel = gtk.Alignment(0.5, 0.5)
        label = gtk.Label("Loading configuration...")
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
        self.state_manager.add_state(UsbState(self.cbUsbmode, self.btnBind))
        self.state_manager.add_state(KvmState(self.cbKvm, self, gui.config))

        # argv0/cpu/machine comboboxes
        self.lcArgv0 = ComboBox.for_entry(self.cbArgv0)
        self.lcCpu = ComboBox.for_entry(self.cbCpu)
        self.lcMachine = ComboBox.for_entry(self.cbMachine)
        exes = qemu.get_executables()
        self.lcArgv0.set_data_source(map(ListEntry.from_tpl, exes))
        self.lcArgv0.set_selected_value(self.original.config["argv0"])

        # boot/sound/mount comboboxes
        self.lcBoot = ComboBox.for_entry(self.cbBoot)
        self.lcBoot.set_data_source(map(ListEntry.from_tpl, BOOT_DEVICE))
        self.lcBoot.set_selected_value(self.original.config["boot"])
        self.lcSound = ComboBox.for_entry(self.cbSound)
        self.lcSound.set_data_source(map(ListEntry.from_tpl, SOUND_DEVICE))
        self.lcSound.set_selected_value(self.original.config["soundhw"])
        self.lcMount = ComboBox.for_entry(self.cbMount)
        self.lcMount.set_data_source(map(ListEntry.from_tpl, MOUNT_DEVICE))
        self.lcMount.set_selected_value(self.original.config["device"])

        # harddisks
        images = [None] + list(self.original.factory.disk_images)
        fmtr = ImageFormatter()
        self.lcHda = ComboBox.with_fmt(self.cbHda, "n", fmtr)
        # all the comboboxes share the same treemodel
        self.lcHda.set_data_source(images)
        self.lcHda.set_selected_value(self.original.config["hda"].image)
        self.lcHdb = ComboBox.with_fmt(self.cbHdb, "n", fmtr)
        self.lcHdb.set_selected_value(self.original.config["hdb"].image)
        self.lcHdc = ComboBox.with_fmt(self.cbHdc, "n", fmtr)
        self.lcHdc.set_selected_value(self.original.config["hdc"].image)
        self.lcHdd = ComboBox.with_fmt(self.cbHdd, "n", fmtr)
        self.lcHdd.set_selected_value(self.original.config["hdd"].image)
        self.lcFda = ComboBox.with_fmt(self.cbFda, "n", fmtr)
        self.lcFda.set_selected_value(self.original.config["fda"].image)
        self.lcFdb = ComboBox.with_fmt(self.cbFdb, "n", fmtr)
        self.lcFdb.set_selected_value(self.original.config["fdb"].image)
        self.lcMtdblock = ComboBox.with_fmt(self.cbMtdblock, "n", fmtr)
        self.lcMtdblock.set_selected_value(
            self.original.config["mtdblock"].image)

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
        cfg["argv0"] = self.lcArgv0.get_selected_value() or ""
        cfg["cpu"] = self.lcCpu.get_selected_value() or ""
        cfg["machine"] = self.lcMachine.get_selected_value() or ""

        # boot/sound/mount comboboxes
        cfg["boot"] = self.lcBoot.get_selected_value()
        cfg["soundhw"] = self.lcSound.get_selected_value()
        cfg["device"] = self.lcMount.get_selected_value()

        # harddisks
        self.original.config["hda"].set_image(self.lcHda.get_selected_value())
        self.original.config["hdb"].set_image(self.lcHdb.get_selected_value())
        self.original.config["hdc"].set_image(self.lcHdc.get_selected_value())
        self.original.config["hdd"].set_image(self.lcHdd.get_selected_value())
        self.original.config["fda"].set_image(self.lcFda.get_selected_value())
        self.original.config["fdb"].set_image(self.lcFdb.get_selected_value())
        self.original.config["mtdblock"].set_image(
            self.lcMtdblock.get_selected_value())

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

    # signals

    def on_newimage_button_clicked(self, button):
        dialogs.choose_new_image(self.gui, self.gui.brickfactory)

    def on_configimage_button_clicked(self, button):
        dialogs.DisksLibraryDialog(self.original.factory).show()

    def on_newempty_button_clicked(self, button):
        dialogs.CreateImageDialog(self.gui, self.gui.brickfactory).show(
            self.gui.get_object("main_win"))

    def on_cbArgv0_changed(self, combobox):
        arch = self.lcArgv0.get_selected_value()
        if arch:
            cpus = qemu.get_cpus(arch)
            self.lcCpu.set_data_source(map(ListEntry.from_tpl, cpus))
            machines = qemu.get_machines(arch)
            self.lcMachine.set_data_source(map(ListEntry.from_tpl, machines))

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
