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

from virtualbricks import brickfactory, errors
from virtualbricks.config.projectfile import ProjectFormatError
from virtualbricks.config.workspace import projects
from virtualbricks.console.projects import use_frontend
from virtualbricks.gui.mainwindow import VBGUI
from virtualbricks.gui.messages import MessageLog, MessageLogObserver
from virtualbricks.gui.trash import DesktopTrash
from virtualbricks.i18n import _

logger = Logger()
cannot_open_last = "{message}"
sync_error = "Sync terminated unexpectedly"
create_image_error = "Create image terminated unexpectedly"


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


class WindowFrontend:
    """
    How the console opens, makes and saves projects with the windows: through
    the main window, which saves what its tabs hold and shows the project.
    """

    def __init__(self, gui):
        self.gui = gui

    def open(self, name, factory):
        return self.gui.on_open(name)

    def new(self, name, factory):
        self.gui.on_new(name)

    def save(self, factory):
        self.gui.on_save()


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
        use_frontend(WindowFrontend(self.gui))

    def migrate(self):
        from virtualbricks.migrate import startup_migration
        from virtualbricks.migrate.gui import MigrationWindow

        migration = startup_migration(self.config.get("workspace"))
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

        name = projects.last_name()
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
