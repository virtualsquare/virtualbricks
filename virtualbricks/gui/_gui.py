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
from zope.interface import implements
from twisted.internet import reactor, utils, defer, error

from virtualbricks import (interfaces, base, bricks, events, virtualmachines,
                           console, link, _compat)

from virtualbricks.gui import graphics, dialogs


log = _compat.getLogger("virtualbricks.gui.gui")

if False:  # pyflakes
    _ = str


def cancel_call(passthru, call):
    if call.active():
        call.cancel()
    return passthru


def refilter(passthru, filter_model):
    filter_model.refilter()
    return passthru


class BaseMenu:
    implements(interfaces.IMenu)

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
        gui.curtain_is_down = False


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
            log.error(_("Cannot rename Brick: it is in use."))
        else:
            gui.gladefile.get_widget('entry_brick_newname').set_text(
                self.original.get_name())
            gui.gladefile.get_widget('dialog_rename').show_all()

    def on_attach_activate(self, menuitem, gui):
        gui.on_brick_attach_event(menuitem)

interfaces.registerAdapter(BrickPopupMenu, bricks.Brick, interfaces.IMenu)


# NOTE: there is a problem with this approach, it is not transparent, it must
# know the type of the brick, however virtual machines are already not
# transparent to the gui
class GVirtualMachine(virtualmachines.VirtualMachine):

    def has_graphic(self):
        return self.homehost is None


class VMPopupMenu(BrickPopupMenu):

    def build(self, gui):
        menu = BrickPopupMenu.build(self, gui)
        resume = gtk.MenuItem("_Resume VM")
        resume.connect("activate", self.on_resume_activate, gui)
        menu.append(resume)
        return menu

    def snapshot(self):

        def grep(out, pattern):
            if out.find(pattern) == -1:
                raise RuntimeError(_("Cannot find suspend point."))

        def loadvm(_):
            if self.original.proc is not None:
                self.original.send("loadvm virtualbricks\n")
            else:
                self.original.poweron("virtualbricks")

        hda = self.original.config["basehda"]
        exe = "qemu-img"
        args = [exe, "snapshot" "-l", hda]
        output = utils.getProcessOutput(exe, args, os.environ)
        output.addCallback(grep, "virtualbricks")
        output.addCallbacks(loadvm, log.err)
        return output

    def on_resume_activate(self, menuitem, gui):
        log.debug("Resuming virtual machine %s", self.original.get_name())
        gui.user_wait_action(self.snapshot)


interfaces.registerAdapter(VMPopupMenu, GVirtualMachine, interfaces.IMenu)


class EventPopupMenu(BaseMenu):

    def on_startstop_activate(self, menuitem, gui):
        self.original.toggle()

    def on_delete_activate(self, menuitem, gui):
        gui.ask_remove_event(self.original)

    def on_copy_activate(self, menuitem, gui):
        gui.brickfactory.dupevent(self.original)

    def on_rename_activate(self, menuitem, gui):
        dialog = dialogs.RenameEventDialog(self.original, gui.brickfactory)
        dialog.window.set_transient_for(gui.widg["main_win"])
        dialog.show()

interfaces.registerAdapter(EventPopupMenu, events.Event, interfaces.IMenu)


class RemoteHostPopupMenu:
    implements(interfaces.IMenu)

    def __init__(self, original):
        self.original = original

    def build(self, gui):
        menu = gtk.Menu()
        label = _("Disconnect") if self.original.connected else _("Connect")
        connect = gtk.MenuItem(label)
        connect.connect("activate", self.on_connect_activate, gui)
        menu.append(connect)
        change_pw = gtk.MenuItem("Change password")
        change_pw.connect("activate", self.on_change_password_activate, gui)
        menu.append(change_pw)
        ac = gtk.CheckMenuItem("Auto-connect at startup")
        ac.set_active(self.original.autoconnect)
        ac.connect("activate", self.on_ac_activate, gui)
        menu.append(ac)
        delete = gtk.MenuItem("Delete")
        delete.connect("activate", self.on_delete_activate, gui)
        menu.append(delete)
        return menu

    def popup(self, button, time, gui):
        menu = self.build(gui)
        menu.show_all()
        menu.popup(None, None, None, button, time)

    def on_connect_activate(self, menuitem, gui):
        if self.original.connected:
            self.original.disconnect()
        else:
            # XXX: this will block
            conn_ok, msg = self.original.connect()
            if not conn_ok:
                log.error("Error connecting to remote host %s: %s",
                    self.original.addr[0], msg)

    def on_change_password_activate(self, menuitem, gui):
        dialogs.ChangePasswordDialog(self.original).show()

    def on_ac_activate(self, menuitem, gui):
        self.original.autoconnect = menuitem.get_active()

    def on_delete_activate(self, menuitem, gui):
        gui.ask_confirm(_("Do you really want to delete remote host ") +
            " \"" + self.original.addr[0] + "\" and all the bricks related?",
            on_yes=gui.brickfactory.delremote, arg=self.original)

interfaces.registerAdapter(RemoteHostPopupMenu, console.RemoteHost,
                           interfaces.IMenu)


class LinkMenu:
    implements(interfaces.IMenu)

    def __init__(self, original):
        self.original = original

    def build(self, gui):
        menu = gtk.Menu()
        edit = gtk.MenuItem(_("Edit"))
        edit.connect("activate", self.on_edit_activate, gui)
        menu.append(edit)
        remove = gtk.MenuItem(_("Remove"))
        remove.connect("activate", self.on_remove_activate, gui)
        menu.append(remove)
        return menu

    def popup(self, button, time, gui):
        menu = self.build(gui)
        menu.show_all()
        menu.popup(None, None, None, button, time)

    def on_edit_activate(self, menuitem, gui):
        dialog = dialogs.EthernetDialog(gui, self.original.brick,
                                  self.original)
        dialog.window.set_transient_for(gui.widg["main_win"])
        dialog.show()

    def on_remove_activate(self, menuitem, gui):
        gui.ask_remove_link(self.original)

interfaces.registerAdapter(LinkMenu, link.Plug, interfaces.IMenu)
interfaces.registerAdapter(LinkMenu, link.Sock, interfaces.IMenu)


class JobMenu:
    implements(interfaces.IMenu)

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
        log.debug("Sending to process signal SIGSTOP!")
        try:
            self.original.send_signal(19)
        except error.ProcessExitedAlready:
            pass

    def on_cont_activate(self, menuitem):
        log.debug("Sending to process signal SIGCONT!")
        try:
            self.original.send_signal(18)
        except error.ProcessExitedAlready:
            pass

    def on_reset_activate(self, menuitem):
        log.debug("Restarting process!")
        d = self.original.poweroff()
        # give it 2 seconds before an hard reset
        call = reactor.callLater(2, self.original.poweroff, kill=True)
        d.addBoth(cancel_call, call)
        d.addCallback(lambda _: self.original.poweron())

    def on_kill_activate(self, menuitem, gui):
        log.debug("Sending to process signal SIGKILL!")
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

    def suspend(self):

        def do_suspend(exit_code):
            if exit_code == 0:
                done = defer.Deferred()
                self.original.send("savevm virtualbricks\n", done)
                done.addCallback(lambda _: self.original.poweroff())
            else:
                log.msg(_("Suspend/Resume not supported on this disk."),
                        isError=True)

        hda = self.original.config["basehda"]
        if hda is None:
            log.msg(_("Suspend/Resume not supported on this disk."),
                    isError=True)
            return defer.fail()
        exe = "qemu-img"
        args = [exe, "snapshot", "-c", "virtualbricks", hda]
        value = utils.getProcessValue(exe, args, os.environ)
        value.addCallback(do_suspend)
        return value

    def on_suspend_activate(self, menuitem, gui):
        gui.user_wait_action(self.suspend)

    def on_powerdown_activate(self, menuitem):
        log.info("send ACPI powerdown")
        self.original.send("system_powerdown\n")

    def on_reset_activate(self, menuitem):
        log.info("send ACPI reset")
        self.original.send("system_reset\n")

    def on_term_activate(self, menuitem, gui):
        log.debug("Sending to process signal SIGTERM!")
        d = self.original.poweroff(term=True)
        d.addCallback(refilter, gui.running_bricks)

interfaces.registerAdapter(VMJobMenu, GVirtualMachine, interfaces.IJobMenu)


class ConfigController(object):
    implements(interfaces.IConfigController)

    domain = "virtualbricks"
    resource = None

    def __init__(self, original):
        self.original = original
        self.builder = builder = gtk.Builder()
        builder.set_translation_domain(self.domain)
        builder.add_from_file(graphics.get_filename("virtualbricks.gui",
                                                    self.resource))
        builder.connect_signals(self)

    def get_object(self, name):
        return self.builder.get_object(name)


class EventConfigController(ConfigController, dialogs.EventControllerMixin):

    resource = "data/eventconfig.ui"

    def get_view(self, gui):
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


class SwitchConfigController(ConfigController):

    resource = "data/switchconfig.ui"

    def get_view(self, gui):
        self.get_object("fstp_checkbutton").set_active(
            self.original.config["fstp"])
        self.get_object("hub_checkbutton").set_active(
            self.original.config["hub"])
        minports = len([1 for b in iter(gui.brickfactory.bricks)
                        for p in b.plugs if b.socks
                        and p.sock.nickname == b.socks[0].nickname])
        spinner = self.get_object("ports_spinbutton")
        spinner.set_range(max(minports, 1), 128)
        spinner.set_value(self.original.config["numports"])
        return self.get_object("table")

    def configure_brick(self, gui):
        go = self.get_object
        self.original.set(fstp=go("fstp_checkbutton").get_active(),
                          hub=go("hub_checkbutton").get_active(),
                          numports=go("ports_spinbutton").get_value_as_int())


class SwitchWrapperConfigController(ConfigController):

    resource = "data/switchwrapperconfig.ui"

    def get_view(self, gui):
        self.get_object("entry").set_text(self.original.config["path"])
        return self.get_object("table1")

    def configure_brick(self, gui):
        self.original.set({"path": self.get_object("entry").get_text()})


def should_insert_sock(sock, brick, python, femaleplugs):
    return ((sock.brick.homehost == brick.homehost or
             (brick.get_type() == 'Wire' and python)) and
            (sock.brick.get_type().startswith('Switch') or femaleplugs))

class PlugMixin(object):

    def _should_insert_sock(self, sock, brick, python, femaleplugs):
        return ((sock.brick.homehost == brick.homehost or
                 (brick.get_type() == 'Wire' and python)) and
                (sock.brick.get_type().startswith('Switch') or femaleplugs))

    def _sock_should_visible(self, model, itr, extra):
        gui, brick = extra
        return self._should_insert_sock(model[itr][0], brick,
                                        settings.python,
                                        settings.femaleplugs)

    def _set_text(self, column, cell_renderer, model, itr):
        sock = model.get_value(itr, 0)
        cell_renderer.set_property("text", sock.nickname)

    def configure_sock_combobox(self, combo, model, brick, plug, gui):
        model.set_visible_func(self._sock_should_visible, (gui, brick))
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


class TapConfigController(PlugMixin, ConfigController):

    resource = "data/tapconfig.ui"

    def get_view(self, gui):
        model = gui.brickfactory.socks.filter_new()
        combo = self.get_object("combobox")
        self.configure_sock_combobox(combo, model, self.original,
                                     self.original.plugs[0], gui)

        self.get_object("ip_entry").set_text(self.original.config["ip"])
        self.get_object("nm_entry").set_text(self.original.config["nm"])
        self.get_object("gw_entry").set_text(self.original.config["gw"])
        # default to manual if not valid mode is set
        if self.original.config["mode"] == "off":
            self.get_object("nocfg_radiobutton").set_active(True)
        elif self.original.config["mode"] == "dhcp":
            self.get_object("dhcp_radiobutton").set_active(True)
        else:
            self.get_object("manual_radiobutton").set_active(True)

        self.get_object("ipconfig_table").set_sensitive(
            self.original.config["mode"] == "manual")

        return self.get_object("table1")

    def configure_brick(self, gui):
        if self.get_object("nocfg_radiobutton").get_active():
            self.original.set(mode="off")
        elif self.get_object("dhcp_radiobutton").get_active():
            self.original.set(mode="dhcp")
        else:
            self.original.set(mode="manual",
                              ip=self.get_object("ip_entry").get_text(),
                              nm=self.get_object("nm_entry").get_text(),
                              gw=self.get_object("gw_entry").get_text())
        self.connect_plug(self.original.plugs[0], self.get_object("combobox"))

    def on_manual_radiobutton_toggled(self, radiobtn):
        self.get_object("ipconfig_table").set_sensitive(radiobtn.get_active())


class CaptureConfigController(PlugMixin, ConfigController):

    resource = "data/captureconfig.ui"

    def get_view(self, gui):
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
                    if self.original.config["iface"] == name:
                        combo2.set_active_iter(itr)

        return self.get_object("table1")

    def configure_brick(self, gui):
        self.connect_plug(self.original.plugs[0], self.get_object("combobox1"))
        combo = self.get_object("combobox2")
        itr = combo.get_active_iter()
        if itr is not None:
            model = combo.get_model()
            self.original.set(iface=model[itr][0])

    def on_manual_radiobutton_toggled(self, radiobtn):
        self.get_object("ipconfig_table").set_sensitive(radiobtn.get_active())


class WireConfigController(PlugMixin, ConfigController):

    resource = "data/wireconfig.ui"

    def get_view(self, gui):
        model = gui.brickfactory.socks.filter_new()
        for i, wname in enumerate(("sock0_combobox", "sock1_combobox")):
            combo = self.get_object(wname)
            self.configure_sock_combobox(combo, model, self.original,
                                         self.original.plugs[i], gui)

        return self.get_object("vbox")

    def configure_brick(self, gui):
        for i, wname in enumerate(("sock0_combobox", "sock1_combobox")):
            self.connect_plug(self.original.plugs[i], self.get_object(wname))


class WirefilterConfigController(WireConfigController):

    pass

    # resource = "data/wirefilterconfig.ui"


class TunnelListenConfigController(PlugMixin, ConfigController):

    resource = "data/tunnellconfig.ui"

    def get_view(self, gui):
        model = gui.brickfactory.socks.filter_new()
        combo = self.get_object("combobox")
        self.configure_sock_combobox(combo, model, self.original,
                                     self.original.plugs[0], gui)
        port = self.get_object("port_spinbutton")
        port.set_value(self.original.config["port"])
        password = self.get_object("password_entry")
        password.set_text(self.original.config["password"])
        return self.get_object("table1")

    def configure_brick(self, gui):
        self.connect_plug(self.original.plugs[0], self.get_object("combobox"))
        port = self.get_object("port_spinbutton").get_value_as_int()
        password = self.get_object("password_entry").get_text()
        self.original.set(port=port, password=password)


class TunnelClientConfigController(TunnelListenConfigController):

    resource = "data/tunnelcconfig.ui"

    def get_view(self, gui):
        host = self.get_object("host_entry")
        host.set_text(self.original.config["host"])
        localport = self.get_object("localport_spinbutton")
        localport.set_value(self.original.config["localport"])
        return TunnelListenConfigController.get_view(self, gui)

    def configure_brick(self, gui):
        TunnelListenConfigController.configure_brick(self, gui)
        host = self.get_object("host").get_text()
        lport = self.get_object("localport_spinbutton").get_value_as_int()
        self.original.set(host=host, localport=lport)


def config_panel_factory(context):
    type = context.get_type()
    if type == "Event":
        return EventConfigController(context)
    elif type == "Switch":
        return SwitchConfigController(context)
    elif type == "SwitchWrapper":
        return SwitchWrapperConfigController(context)
    elif type == "Tap":
        return TapConfigController(context)
    elif type == "Capture":
        return CaptureConfigController(context)
    elif type == "Wire":
        return WireConfigController(context)
    # elif type == "Wirefilter":
    #     return WirefilterConfigController(context)
    elif type == "TunnelConnect":
        return TunnelClientConfigController(context)
    elif type == "TunnelListen":
        return TunnelListenConfigController(context)

interfaces.registerAdapter(config_panel_factory, base.Base,
                           interfaces.IConfigController)
