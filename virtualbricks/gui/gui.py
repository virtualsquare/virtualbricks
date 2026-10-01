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
from twisted.internet import defer, error, protocol, reactor
from twisted.python.failure import Failure
from twisted.logger import (
    FilteringLogObserver,
    LogLevel,
    LogLevelFilterPredicate,
    Logger,
    PredicateResult,
    formatEvent,
    globalLogPublisher,
)

from virtualbricks import brickfactory, errors, i18n
from virtualbricks.config.projectfile import ProjectFormatError
from virtualbricks.config.settings import (
    get_setting,
    load_settings,
    store_settings,
)
from virtualbricks.config.workspace import projects
from virtualbricks.console.projects import use_frontend
from virtualbricks.engine import LocalEngine
from virtualbricks.gui.mainwindow import VBGUI, window
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


def _now(deferred):
    """
    What a Deferred of the engine of this process gives, which has fired
    already: its result, or its failure raised.
    """

    results = []
    deferred.addBoth(results.append)
    [result] = results
    if isinstance(result, Failure):
        result.raiseException()
    return result


class WindowFrontend:
    """
    How the console opens, makes and saves projects with the windows: through
    the main window, which saves what its tabs hold and shows the project.
    Its engine is that of this process, which answers at once, as the
    console wants.
    """

    def __init__(self, gui):
        self.gui = gui

    def open(self, name, factory):
        return _now(self.gui.on_open(name))

    def new(self, name, factory):
        _now(self.gui.on_new(name))

    def save(self, factory):
        _now(self.gui.on_save())


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
        self.gui = VBGUI(LocalEngine(factory), self.messages)
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


class RemoteApplication:
    """
    The windows of another Virtualbricks, the one of the socket of
    ``--connect`` (page 19): its copy, and an engine that sends there what
    the windows do. No lock, no migration, no workspace, no autosave, no
    socket and no console of their own; the settings are those of this
    computer. Quit closes the windows; the Virtualbricks there goes on.
    """

    def __init__(self, config):
        self.config = config
        self.target = config["target"]
        self.messages = MessageLog()
        self.logger = AppLoggerFactory(self.messages)(config)
        self.gui = None
        self.engine = None
        self.quitting = False
        # the Virtualbricks there said it quits
        self.ended = False

    def getComponent(self, interface, default):
        return default

    def install_locale(self):
        i18n.install()

    def install_settings(self):
        load_settings()

    def run(self, reactor):
        """Connect, then show the windows: a Deferred of their end."""

        from virtualbricks.remote import client
        from virtualbricks.remote.mirror import MirrorFactory

        self.install_locale()
        self.install_settings()
        self.logger.start(self)
        reactor.addSystemEventTrigger("before", "shutdown", store_settings)
        reactor.addSystemEventTrigger("before", "shutdown", self.logger.stop)
        self.reactor = reactor
        self.where = client.where(self.target)
        self.copy = MirrorFactory(reactor)
        self.done = defer.Deferred()
        connecting = defer.ensureDeferred(
            client.connect(self.target, self.copy, reactor)
        )
        connecting.addCallbacks(self.show, self.not_connected)
        return self.done

    def not_connected(self, failure):
        from virtualbricks.remote.client import Refused

        failure.trap(Refused)
        self.done.errback(SystemExit(failure.getErrorMessage()))

    def show(self, windows):
        """The windows, on the copy that the connection keeps."""

        from virtualbricks.remote import client, tunnel
        from virtualbricks.remote.client import RemoteEngine

        message_dialog = MessageDialogObserver()
        globalLogPublisher.addObserver(
            FilteringLogObserver(message_dialog, [should_show_to_user])
        )
        # the consoles of the bricks there, each over a connection of its own
        self.consoles = tunnel.Consoles(
            lambda: defer.ensureDeferred(
                client.connect_again(self.target, self.reactor)
            ),
            self.where,
            self.reactor,
        )
        self.engine = RemoteEngine(
            self.copy, windows, self.where, self.quit, self.consoles
        )
        self.watch(windows)
        self.gui = VBGUI(self.engine, self.messages)
        message_dialog.set_parent(self.gui.window)
        self.copy.synced.connect(self.synced)
        self.copy.ended.connect(self.on_ended)
        self.gui.set_title()
        self.warn(self.copy.machine)

    def watch(self, windows):
        windows.logged = self.logged
        windows.lost.addCallback(self.lost)

    def logged(self, message):
        self.messages.add_message(message, self.where)

    def synced(self, copy):
        # a project opened there, or the same again after Reconnect
        self.gui.on_opened()

    def on_ended(self, copy):
        self.ended = True

    def warn(self, machine):
        """What the machine of the bricks lacks, as the warning at start."""

        if not get_setting("warn_missing_programs"):
            return
        lines = []
        if not machine.get("ksm", True):
            lines.append(window.ksm_not_found)
        missing = machine.get("missing") or []
        if missing:
            lines.append(
                window.programs_not_found.format(programs=", ".join(missing))
            )
        if lines:
            logger.error(window.components_not_found, text="\n".join(lines))

    def lost(self, reason):
        if self.quitting:
            return
        if self.ended:
            text = _("Virtualbricks on {where} quit").format(where=self.where)
        else:
            text = _("The connection to {where} is lost: {reason}").format(
                where=self.where, reason=reason
            )
        self.gui.connection_lost(text, self.reconnect)

    def reconnect(self):
        """Connect again; the copy starts again, from nothing."""

        from virtualbricks.remote import client

        self.ended = False
        connecting = defer.ensureDeferred(
            client.connect(self.target, self.copy, self.reactor)
        )
        connecting.addCallbacks(self.reconnected, self.not_reconnected)
        return connecting

    def reconnected(self, windows):
        self.engine.windows = windows
        self.watch(windows)
        self.gui.reconnected()

    def not_reconnected(self, failure):
        from virtualbricks.remote.client import Refused

        failure.trap(Refused)
        self.gui.connection_lost(failure.getErrorMessage(), self.reconnect)

    def quit(self):
        """The windows close; the Virtualbricks there goes on."""

        if self.quitting:
            return
        self.quitting = True
        if self.gui is not None:
            self.gui.on_quit(None)
            # closing the window quits too
            if not self.gui.window.in_destruction():
                self.gui.window.destroy()
        windows = self.engine.windows if self.engine is not None else None
        if windows is not None and windows.transport is not None:
            windows.transport.loseConnection()
        if self.engine is not None:
            # the sockets of the consoles
            self.consoles.close()
        if not self.done.called:
            self.done.callback(None)
