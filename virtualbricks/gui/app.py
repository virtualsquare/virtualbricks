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

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from constantly import NamedConstant
from gi.repository import Gtk
from twisted.internet import defer
from twisted.internet.posixbase import PosixReactorBase
from twisted.python.failure import Failure
from twisted.logger import (
    FilteringLogObserver,
    LogLevel,
    LogLevelFilterPredicate,
    Logger,
    ILogObserver,
    LogEvent,
    PredicateResult,
    formatEvent,
    globalLogPublisher,
)
from zope.interface import implementer

from virtualbricks import errors, i18n
from virtualbricks.app import AppLogger, Application
from virtualbricks.brickfactory import BrickFactory
from virtualbricks.config.projectfile import ProjectFormatError
from virtualbricks.config.report import Report
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

if TYPE_CHECKING:  # pragma: no cover
    from virtualbricks.remote.client import RemoteEngine, Windows
    from virtualbricks.remote.mirror import MirrorFactory
    from virtualbricks.remote.tunnel import Consoles

T = TypeVar("T")

logger = Logger()
cannot_open_last = "{message}"


@implementer(ILogObserver)
class MessageDialogObserver:

    def __init__(self, parent: Gtk.Window | None = None) -> None:
        self.__parent = parent

    def set_parent(self, parent: Gtk.Window | None) -> None:
        self.__parent = parent

    def __call__(self, event: LogEvent) -> None:
        dialog = Gtk.MessageDialog(
            transient_for=self.__parent,
            modal=True,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.CLOSE,
        )
        dialog.set_property("text", formatEvent(event))
        dialog.connect("response", lambda d, r: d.destroy())
        dialog.show()


def should_show_to_user(event: LogEvent) -> NamedConstant:
    if "hide_to_user" in event:
        return PredicateResult.no
    if event["log_level"] not in (LogLevel.error, LogLevel.critical):
        return PredicateResult.no
    return PredicateResult.maybe


def AppLoggerFactory(messages: MessageLog) -> type[AppLogger]:

    observer = FilteringLogObserver(
        MessageLogObserver(messages),
        [LogLevelFilterPredicate(LogLevel.info)],
    )

    class MessagesLogger(AppLogger):

        def get_observers(self) -> list[ILogObserver]:
            return super().get_observers() + [observer]

    return MessagesLogger


def show_errors() -> MessageDialogObserver:
    """
    Show the errors logged from now on in a dialog each: their observer,
    whose parent is the main window once it is there.
    """

    dialogs = MessageDialogObserver()
    globalLogPublisher.addObserver(
        FilteringLogObserver(
            dialogs,
            # a function is a predicate as much as a class
            [should_show_to_user],  # type: ignore[list-item]
        )
    )
    return dialogs


def _now(deferred: defer.Deferred[T]) -> T:
    """
    What a Deferred of the engine of this process gives, which has fired
    already: its result, or its failure raised.
    """

    results: list[T | Failure] = []
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

    def __init__(self, gui: VBGUI) -> None:
        self.gui = gui

    def open(self, name: str, factory: BrickFactory) -> Report:
        return _now(self.gui.on_open(name))

    def new(self, name: str, factory: BrickFactory) -> None:
        _now(self.gui.on_new(name))

    def save(self, factory: BrickFactory) -> None:
        _now(self.gui.on_save())


class GuiApplication(Application):
    """Virtualbricks that runs the bricks, with its windows."""

    def __init__(self, config: Mapping[str, Any]) -> None:
        # the messages of this run, for the messages window
        self.messages = MessageLog()
        self.logger_factory = AppLoggerFactory(self.messages)
        super().__init__(config)

    def get_namespace(self) -> dict[str, object]:
        return {"gui": self.gui}

    def _run(self, factory: BrickFactory) -> None:
        dialogs = show_errors()
        self.gui = VBGUI(LocalEngine(factory), self.messages)
        dialogs.set_parent(self.gui.window)
        # The workspace has no desktop of its own: removing a project moves
        # it to the trash only in the GUI.
        projects.trasher = DesktopTrash()
        use_frontend(WindowFrontend(self.gui))

    def migrate(self) -> defer.Deferred[Any] | None:
        from virtualbricks.migrate import startup_migration
        from virtualbricks.migrate.gui import MigrationWindow

        migration = startup_migration(self.config.get("workspace"))
        if migration is None:
            return None
        window = MigrationWindow(migration=migration)
        window.show()
        return window.closed

    def open_last_project(self, factory: BrickFactory) -> None:
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

    def _start(self, reactor: PosixReactorBase) -> defer.Deferred[None]:
        ret = super()._start(reactor)
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

    def __init__(self, config: Mapping[str, Any]) -> None:
        self.config = config
        self.target = config["target"]
        self.messages = MessageLog()
        self.logger = AppLoggerFactory(self.messages)(config)
        self.gui: VBGUI | None = None
        self.engine: RemoteEngine | None = None
        self.quitting = False
        # the Virtualbricks there said it quits
        self.ended = False

    def install_locale(self) -> None:
        i18n.install()

    def install_settings(self) -> None:
        load_settings()

    def windows(self) -> VBGUI:
        """The windows, once the connection shows them."""

        assert self.gui is not None, "the windows show"
        return self.gui

    def run(self, reactor: PosixReactorBase) -> defer.Deferred[None]:
        """Connect, then show the windows: a Deferred of their end."""

        from virtualbricks.remote import client
        from virtualbricks.remote.mirror import MirrorFactory

        self.install_locale()
        self.install_settings()
        self.logger.start(reactor)
        reactor.addSystemEventTrigger("before", "shutdown", store_settings)
        reactor.addSystemEventTrigger("before", "shutdown", self.logger.stop)
        self.reactor = reactor
        self.where = client.where(self.target)
        self.copy = MirrorFactory(reactor)
        self.done: defer.Deferred[None] = defer.Deferred()
        connecting = defer.ensureDeferred(self.reach())
        connecting.addCallbacks(self.show, self.not_connected)
        return self.done

    async def reach(self) -> Windows:
        """
        The connection; with --connect alone, to the socket that a
        Virtualbricks of yours listens on, found once: Reconnect goes there.
        """

        from virtualbricks.remote import client

        self.target = client.resolve(self.target, self.config["workspace"])
        return await client.connect(
            self.target, self.copy, self.reactor, self.made
        )

    def not_connected(self, failure: Failure) -> None:
        from virtualbricks.remote.client import Refused

        failure.trap(Refused)
        self.done.errback(SystemExit(failure.getErrorMessage()))

    def show(self, windows: Windows) -> None:
        """The windows, on the copy that the connection keeps."""

        from virtualbricks.remote import client, tunnel
        from virtualbricks.remote.client import RemoteEngine

        dialogs = show_errors()
        # the consoles of the bricks there, each over a connection of its own
        self.consoles: Consoles = tunnel.Consoles(
            lambda: defer.ensureDeferred(
                client.connect_again(self.target, self.reactor)
            ),
            self.where,
            self.reactor,
        )
        self.engine = RemoteEngine(
            self.copy, windows, self.where, self.quit, self.consoles
        )
        windows.lost.addCallback(self.lost)
        self.gui = VBGUI(self.engine, self.messages)
        dialogs.set_parent(self.gui.window)
        self.copy.synced.connect(self.synced)
        self.copy.ended.connect(self.on_ended)
        self.gui.set_title()
        self.warn(self.copy.machine)

    def made(self, windows: Windows) -> None:
        """
        A connection, before it follows: the messages of the log that come
        with the project go to the windows, and so do the calls of the
        windows that the project makes, as the Readme tab's.
        """

        windows.logged = self.logged
        if self.engine is not None:
            self.engine.windows = windows

    def logged(self, message: dict[str, Any]) -> None:
        self.messages.add_message(message, self.where)

    def synced(self, copy: MirrorFactory) -> None:
        # a project opened there, or the same again after Reconnect
        self.windows().on_opened()

    def on_ended(self, copy: MirrorFactory) -> None:
        self.ended = True

    def warn(self, machine: Mapping[str, Any]) -> None:
        """What the machine of the bricks lacks, as the warning at start."""

        if not get_setting("warn_missing_programs"):
            return
        lines = []
        # a lab machine of before ksm_available has KSM, as far as we know
        line = window.ksm_warning(
            self.copy.settings.get("kernel_samepage_merging", False),
            machine.get("ksm_available", True),
            machine.get("ksm", True),
        )
        if line:
            lines.append(line)
        missing = machine.get("missing") or []
        if missing:
            lines.append(
                window.programs_not_found.format(programs=", ".join(missing))
            )
        if lines:
            logger.error(window.components_not_found, text="\n".join(lines))

    def lost(self, reason: object) -> None:
        if self.quitting:
            return
        if self.ended:
            text = _("Virtualbricks on {where} quit").format(where=self.where)
        else:
            text = _("The connection to {where} is lost: {reason}").format(
                where=self.where, reason=reason
            )
        self.windows().connection_lost(text, self.reconnect)

    def reconnect(self) -> defer.Deferred[None]:
        """Connect again; the copy starts again, from nothing."""

        from virtualbricks.remote import client

        self.ended = False
        connecting = defer.ensureDeferred(
            client.connect(self.target, self.copy, self.reactor, self.made)
        )
        return connecting.addCallbacks(self.reconnected, self.not_reconnected)

    def reconnected(self, windows: Windows) -> None:
        windows.lost.addCallback(self.lost)
        self.windows().reconnected()

    def not_reconnected(self, failure: Failure) -> None:
        from virtualbricks.remote.client import Refused

        failure.trap(Refused)
        self.windows().connection_lost(
            failure.getErrorMessage(), self.reconnect
        )

    def quit(self) -> None:
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
