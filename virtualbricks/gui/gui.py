# -*- test-case-name: virtualbricks.tests.gui.test_gui -*-
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

from gi.repository import Gtk
from twisted.internet import error, protocol, reactor
from twisted.logger import (
    FilteringLogObserver,
    LogLevel,
    LogLevelFilterPredicate,
    Logger,
    PredicateResult,
    formatEvent,
    globalLogPublisher,
)
from zope.interface import implementer

from virtualbricks import brickfactory, errors
from virtualbricks.config.projectfile import ProjectFormatError
from virtualbricks.config.settings import current_project
from virtualbricks.config.workspace import projects
from virtualbricks.bricks import Brick
from virtualbricks.gui.mainwindow.bricks.config import (
    CaptureConfigController,
    NetemuConfigController,
    QemuConfigController,
    SwitchConfigController,
    SwitchWrapperConfigController,
    TapConfigController,
    TunnelClientConfigController,
    TunnelListenConfigController,
    WireConfigController,
)
from virtualbricks.gui.dialogs import EditEthernetDialog
from virtualbricks.gui.mainwindow import VBGUI
from virtualbricks.gui.interfaces import IMenu, IConfigController
from virtualbricks.gui.messages import MessageLog, MessageLogObserver
from virtualbricks.gui.trash import DesktopTrash
from virtualbricks.i18n import _
from virtualbricks.interfaces import registerAdapter
from virtualbricks.bricks.plug import Plug
from virtualbricks.bricks.sock import Sock

logger = Logger()
cannot_open_last = "{message}"
sync_error = "Sync terminated unexpectedly"
create_image_error = "Create image terminated unexpectedly"


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
        EditEthernetDialog(
            gui.brickfactory, self.original.brick, self.original
        ).show(gui.window)

    def on_remove_activate(self, menuitem, controller):
        controller.ask_remove_link(self.original)


registerAdapter(LinkMenu, Plug, IMenu)
registerAdapter(LinkMenu, Sock, IMenu)


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
                SyncProtocol(self.done), "sync", ["sync"], os.environ
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
        Gtk.ListStore.append(self, (element,))

    def remove(self, element):
        itr = self.get_iter_first()
        while itr:
            el = self.get_value(itr, 0)
            if el is element:
                return Gtk.ListStore.remove(self, itr)
            itr = self.iter_next(itr)
        raise ValueError("%r not in list" % (element,))

    def __delitem__(self, key):
        if isinstance(key, int):
            Gtk.ListStore.__delitem__(self, key)
        elif isinstance(key, slice):
            if (
                key.start in (None, 0)
                and key.stop in (None, sys.maxsize)
                and key.step in (1, -1, None)
            ):
                self.clear()
            else:
                raise TypeError("Invalid slice %r" % (key,))
        else:
            raise TypeError("Invalid key %r" % (key,))


class VisualFactory(brickfactory.BrickFactory):

    def __init__(self, quit):
        brickfactory.BrickFactory.__init__(self, quit)
        self.socks = List()


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
            Gtk.ButtonsType.CLOSE,
        )
        dialog.set_property("text", formatEvent(event))
        dialog.connect("response", lambda d, r: d.destroy())
        dialog.show()


def should_show_to_user(event):
    if "hide_to_user" in event:
        return PredicateResult.no
    if event["log_level"] not in (LogLevel.error, LogLevel.critical):
        return PredicateResult.no
    return PredicateResult.maybe


def AppLoggerFactory(messages):

    observer = FilteringLogObserver(
        MessageLogObserver(messages),
        [LogLevelFilterPredicate(LogLevel.info)],
    )

    class AppLogger(brickfactory.AppLogger):

        def get_observers(self):
            return super().get_observers() + [observer]

    return AppLogger


class Application(brickfactory.Application):

    factory_factory = VisualFactory

    def __init__(self, config):
        # the messages of this run, for the messages window
        self.messages = MessageLog()
        self.logger_factory = AppLoggerFactory(self.messages)
        brickfactory.Application.__init__(self, config)

    def get_namespace(self):
        return {"gui": self.gui}

    def _run(self, factory):
        # a bug in gtk2 make impossibile to use this and is not required anyway
        # gtk.set_interactive(False)
        message_dialog = MessageDialogObserver()
        observer = FilteringLogObserver(message_dialog, [should_show_to_user])
        globalLogPublisher.addObserver(observer)
        # disable default link_button action
        # gtk.link_button_set_uri_hook(lambda b, s: None)
        self.gui = VBGUI(factory, self.messages)
        message_dialog.set_parent(self.gui.window)
        # The workspace has no desktop of its own: removing a project moves
        # it to the trash only in the GUI.
        projects.trasher = DesktopTrash()

    def migrate(self):
        from virtualbricks.migrate import startup_migration
        from virtualbricks.migrate.gui import MigrationWindow

        migration = startup_migration()
        if migration is None:
            return None
        window = MigrationWindow(migration=migration)
        window.show()
        return window.closed

    def open_last_project(self, factory):
        """
        Open the project open last, or say why in the Projects window.

        The Projects window takes the place of a new new_project_N; closed
        without opening a project, it leaves one as the console does.
        """

        name = current_project()
        try:
            projects.open_last(factory)
        except (errors.InvalidNameError, ProjectFormatError) as exc:
            if projects.exists(name):
                message = _(
                    'The project "{name}" that was open last can\'t be'
                    " opened: {error}"
                ).format(name=name, error=exc)
            else:
                message = _(
                    'The project "{name}" that was open last doesn\'t exist'
                    " any more. Open another one, or create one."
                ).format(name=name)
        else:
            return
        logger.warn(cannot_open_last, message=message)
        self.gui.show_start_up_problem(message)

    def _start(self, reactor):
        ret = brickfactory.Application._start(self, reactor)
        self.gui.set_title()
        # the folders of QEMU and VDE are those of the project, open by now
        self.gui.check_prerequisites()
        return ret
