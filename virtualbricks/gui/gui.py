# -*- test-case-name: virtualbricks.tests.test_gui -*-
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

# This module is ported to new GTK3 using PyGObject

import os
import sys

from gi.repository import GObject, Gtk
from twisted.internet import error, defer, protocol, reactor
from zope.interface import implementer

from virtualbricks import tools, log, brickfactory
from virtualbricks.spawn import qemu_img
from virtualbricks.bricks import Brick
from virtualbricks.events import Event
from virtualbricks.gui.windows import (
    AttachEventDialog,
    EditEthernetDialog,
    ProgressBar,
    RenameDialog,
    SwitchConfigController,
    SwitchWrapperConfigController,
    TapConfigController,
    CaptureConfigController,
    WireConfigController,
    NetemuConfigController,
    TunnelClientConfigController,
    TunnelListenConfigController,
    QemuConfigController,
    EventConfigController,
    VBGUI,
)
from virtualbricks.gui.interfaces import IMenu, IJobMenu, IConfigController
from virtualbricks.interfaces import registerAdapter
from virtualbricks.link import Plug, Sock
from virtualbricks.virtualmachines import VirtualMachine


if False:  # pyflakes
    _ = str

logger = log.Logger()
sync_error = log.Event("Sync terminated unexpectedly")
create_image_error = log.Event("Create image terminated unexpectedly")
cannot_rename = log.Event("Cannot rename Brick: it is in use.")
s_r_not_supported = log.Event("Suspend/Resume not supported on this disk.")
snap_error = log.Event("Error on snapshot")
resume_vm = log.Event("Resuming virtual machine {name}")
event_in_use = log.Event("Cannot rename event: it is in use.")
proc_signal = log.Event("Sending to process signal {signame}!")
send_acpi = log.Event("send ACPI {acpievent}")
proc_restart = log.Event("Restarting process!")
savevm = log.Event("Save snapshot on virtual machine {name}")


@implementer(IMenu)
class BaseMenu:

    def __init__(self, brick):
        self.original = brick

    def build(self, gui):
        _clear_menu()
        menu = _menu
        menu.append(Gtk.MenuItem(self.original.get_name(), False))
        menu.append(Gtk.SeparatorMenuItem())
        start_stop = Gtk.MenuItem.new_with_mnemonic("_Start/Stop")
        start_stop.connect("activate", self.on_startstop_activate, gui)
        menu.append(start_stop)
        delete = Gtk.MenuItem.new_with_mnemonic("_Delete")
        delete.connect("activate", self.on_delete_activate, gui)
        menu.append(delete)
        copy = Gtk.MenuItem.new_with_mnemonic("Make a C_opy")
        copy.connect("activate", self.on_copy_activate, gui)
        menu.append(copy)
        rename = Gtk.MenuItem.new_with_mnemonic("Re_name")
        rename.connect("activate", self.on_rename_activate, gui)
        menu.append(rename)
        configure = Gtk.MenuItem.new_with_mnemonic("_Configure")
        configure.connect("activate", self.on_configure_activate, gui)
        menu.append(configure)
        return menu

    def popup(self, button, time, gui):
        menu = self.build(gui)
        menu.show_all()
        menu.popup(None, None, None, None, button, time)

    def on_configure_activate(self, menuitem, gui):
        gui.curtain_up(self.original)


class BrickPopupMenu(BaseMenu):

    def build(self, gui):
        menu = BaseMenu.build(self, gui)
        attach = Gtk.MenuItem.new_with_mnemonic("_Attach Event")
        attach.connect("activate", self.on_attach_activate, gui)
        menu.append(attach)
        return menu

    def on_startstop_activate(self, menuitem, gui):
        gui.startstop_brick(self.original)
        _clear_menu()

    def on_delete_activate(self, menuitem, gui):
        gui.ask_remove_brick(self.original)

    def on_copy_activate(self, menuitem, gui):
        gui.brickfactory.dup_brick(self.original)

    def on_rename_activate(self, menuitem, gui):
        if self.original.proc is not None:
            logger.error(cannot_rename)
        else:
            RenameDialog(gui.brickfactory, self.original).show(gui.window)

    def on_attach_activate(self, menuitem, gui):
        AttachEventDialog(self.original, gui.factory).show(gui.window)
        return True


registerAdapter(BrickPopupMenu, Brick, IMenu)


class VMPopupMenu(BrickPopupMenu):

    def build(self, gui):
        menu = BrickPopupMenu.build(self, gui)
        resume = Gtk.MenuItem.new_with_mnemonic("_Resume VM")
        resume.connect("activate", self.on_resume_activate, gui)
        menu.append(resume)
        return menu

    def resume(self, factory):

        def grep(out, pattern):
            if out.find(pattern) == -1:
                raise RuntimeError(_("Cannot find suspend point."))

        def loadvm(_):
            if self.original.proc is not None:
                self.original.send(b"loadvm virtualbricks\n")
            else:
                return self.original.poweron("virtualbricks")

        img = self.original.get("hda")
        if img.is_cow():
            path = img.get_cow_path()
        elif img.image:
            path = img.image.path
        else:
            logger.error(s_r_not_supported)
            return defer.fail(RuntimeError(_("Suspend/Resume not supported on "
                                             "this disk.")))
        output = qemu_img(['snapshot', '-l', path])
        output.addCallback(grep, "virtualbricks")
        output.addCallback(loadvm)
        logger.log_failure(output, snap_error)
        return output

    def on_resume_activate(self, menuitem, gui):
        logger.debug(resume_vm, name=self.original.get_name())
        ProgressBar(gui).wait_for(self.resume(gui.brickfactory))


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
            RenameDialog(gui.brickfactory, self.original).show(gui.window)
        else:
            logger.error(event_in_use)


registerAdapter(EventPopupMenu, Event, IMenu)


@implementer(IMenu)
class LinkMenu:

    def __init__(self, original):
        self.original = original

    def build(self, controller, gui):
        _clear_menu()
        menu = _menu
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
        menu.popup(None, None, None, None, button, time)

    def on_edit_activate(self, menuitem, controller, gui):
        EditEthernetDialog(gui.brickfactory, self.original.brick,
                           self.original).show(gui.window)

    def on_remove_activate(self, menuitem, controller):
        controller.ask_remove_link(self.original)


registerAdapter(LinkMenu, Plug, IMenu)
registerAdapter(LinkMenu, Sock, IMenu)


@implementer(IMenu)
class JobMenu:

    def __init__(self, original):
        self.original = original

    def build(self, gui):
        _clear_menu()
        menu = _menu
        open = Gtk.MenuItem(_("Open control monitor"))
        open.connect("activate", self.on_open_activate)
        menu.append(open)
        menu.append(Gtk.SeparatorMenuItem())
        stop = Gtk.MenuItem.new_with_mnemonic(_("_Stop"))
        stop.connect("activate", self.on_stop_activate)
        menu.append(stop)
        cont = Gtk.MenuItem.new_with_mnemonic(_("_Play"))
        cont.set_label(_("Continue"))
        cont.connect("activate", self.on_cont_activate)
        menu.append(cont)
        menu.append(Gtk.SeparatorMenuItem())
        reset = Gtk.MenuItem.new_with_mnemonic(_("_Redo"))
        reset.set_label(_("Restart"))
        reset.connect("activate", self.on_reset_activate)
        menu.append(reset)
        kill = Gtk.MenuItem.new_with_mnemonic(_("_Stop"))
        kill.set_label(_("Kill"))
        kill.connect("activate", self.on_kill_activate, gui)
        menu.append(kill)
        return menu

    def popup(self, button, time, gui):
        menu = self.build(gui)
        menu.show_all()
        menu.popup(None, None, None, None, button, time)

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
            self.original.poweroff(kill=True)
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
        term = Gtk.MenuItem.new_with_mnemonic(_("_Delete"))
        term.set_label(_("Terminate"))
        term.connect("activate", self.on_term_activate, gui)
        menu.insert(term, 10)
        return menu

    def suspend(self, factory):
        img = self.original.get("hda")
        if img.is_cow():
            path = img.get_cow_path()
        elif img.image:
            path = img.image.path
        else:
            logger.error(s_r_not_supported)
            return defer.fail(RuntimeError(_("Suspend/Resume not supported on "
                                             "this disk.")))
        image_type = tools.image_type_from_file(path)
        if image_type in (tools.ImageFormat.QCOW2, tools.ImageFormat.QCOW3):
            self.original.send(b'savevm virtualbricks\n')
            return self.original.poweroff()
        else:
            logger.error(s_r_not_supported)
            return defer.fail(RuntimeError(_("Suspend/Resume not supported on "
                                             "this disk.")))

    def on_suspend_activate(self, menuitem, gui):
        logger.debug(savevm, name=self.original.get_name())
        # TODO: this blocks forever if the machine does not stop.
        ProgressBar(gui).wait_for(self.suspend(gui.brickfactory))

    def on_powerdown_activate(self, menuitem):
        logger.info(send_acpi, acpievent="powerdown")
        self.original.send(b"system_powerdown\n")

    def on_reset_activate(self, menuitem):
        logger.info(send_acpi, acpievent="reset")
        self.original.send(b"system_reset\n")

    def on_term_activate(self, menuitem, gui):
        logger.debug(proc_signal, signame="SIGTERM")
        self.original.poweroff(term=True)


registerAdapter(VMJobMenu, VirtualMachine, IJobMenu)


registerAdapter(EventConfigController, Event, IConfigController)


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
            reactor.spawnProcess(
                SyncProtocol(self.done),
                "sync",
                ["sync"],
                os.environ
            )


# These instructions keep a reference of a popup menu and reinitialize
# it
def _clear_menu():
    global _menu
    _menu = Gtk.Menu()

_menu = Gtk.Menu()


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
            if (key.start in (None, 0) and key.stop in (None, sys.maxsize) and
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
        self.textbuffer = textbuffer

    def __call__(self, event):
        GObject.idle_add(self.emit, event)

    def emit(self, event):
        entry = "{iso8601_time} [{log_namespace}] {msg}\n{traceback}"
        if "log_failure" in event:
            event["traceback"] = event["log_failure"].getTraceback()
        else:
            event["traceback"] = ""
        event["iso8601_time"] = log.format_time(event["log_time"])
        self.textbuffer.insert_with_tags_by_name(
            self.textbuffer.get_iter_at_mark(self.textbuffer.get_mark('end')),
            entry.format(msg=log.formatEvent(event), **event),
            event["log_level"].name
        )


class MessageDialogObserver:

    def __init__(self, parent=None):
        self.__parent = parent

    def set_parent(self, parent):
        self.__parent = parent

    def __call__(self, event):
        dialog = Gtk.MessageDialog(
            self.__parent,
            Gtk.DialogFlags.MODAL,
            Gtk.MessageType.ERROR,
            Gtk.ButtonsType.CLOSE
        )
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
        self.textbuffer = textbuffer = Gtk.TextBuffer()
        textbuffer.create_mark(
            mark_name='end',
            where=textbuffer.get_end_iter(),
            left_gravity=False
        )
        for name, attrs in TEXT_TAGS:
            self.textbuffer.create_tag(name, **attrs)
        self.logger_factory = AppLoggerFactory(textbuffer)
        brickfactory.Application.__init__(self, config)

    def get_namespace(self):
        return {"gui": self.gui}

    def _run(self, factory):
        # a bug in gtk2 make impossibile to use this and is not required anyway
        # gtk.set_interactive(False)
        message_dialog = MessageDialogObserver()
        observer = log.FilteringLogObserver(message_dialog,
                                            (should_show_to_user,))
        logger.publisher.addObserver(observer, False)
        # disable default link_button action
        # gtk.link_button_set_uri_hook(lambda b, s: None)
        self.gui = VBGUI(factory, self.textbuffer)
        message_dialog.set_parent(self.gui.window)

    def run(self, reactor):
        ret = brickfactory.Application.run(self, reactor)
        self.gui.set_title()
        return ret

