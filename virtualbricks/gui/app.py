# -*- test-case-name: virtualbricks.tests.gui.test_app,virtualbricks.tests.gui.test_remote -*-
from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from gi.repository import Gtk
from twisted.internet import defer
from twisted.logger import (
    FilteringLogObserver,
    ILogObserver,
    Logger,
    LogLevel,
    LogLevelFilterPredicate,
    PredicateResult,
    formatEvent,
)
from twisted.python.failure import Failure
from zope.interface import implementer

from virtualbricks import cli, errors, ksm
from virtualbricks.app import LOOK_EVERY
from virtualbricks.app import Application as CliApplication
from virtualbricks.brickfactory import BrickFactory
from virtualbricks.config.projectfile import ProjectFormatError
from virtualbricks.config.settings import (
    get_setting,
    ksm_started,
    load_settings,
)
from virtualbricks.config.workspace import projects
from virtualbricks.console.projects import use_frontend
from virtualbricks.engine import LocalEngine
from virtualbricks.gui.mainwindow import MAIN_ROLE, MainWindow
from virtualbricks.gui.messages import MessageLog, MessageLogObserver
from virtualbricks.gui.trash import DesktopTrash
from virtualbricks.i18n import _
from virtualbricks.migrate import startup_migration
from virtualbricks.migrate.gui import MigrationWindow
from virtualbricks.programs import missing_programs

if TYPE_CHECKING:  # pragma: no cover
    from twisted.internet.posixbase import PosixReactorBase
    from twisted.logger import LogEvent

    from virtualbricks.config.report import Report
    from virtualbricks.remote.client import RemoteEngine, Windows
    from virtualbricks.remote.mirror import MirrorFactory


T = TypeVar("T")

logger = Logger("virtualbricks.main")
cannot_open_last = "{message}"
ksm_not_found = (
    "The settings ask for KSM, which this Linux doesn't have: the machines"
    " can't share memory."
)
ksm_still_off = (
    "The settings ask for KSM, which is still off: Virtualbricks couldn't"
    " turn it on."
)
programs_not_found = (
    "Some programs of the bricks are missing, each with the package that has"
    " it: {programs}. Some bricks won't start."
)
components_not_found = (
    "{text}\nThe Settings window turns this alert off: Missing programs, on"
    " its page This computer."
)


def find_parent() -> Gtk.Window | None:
    """The window the user is in, else the main window, else None."""

    toplevels = [
        toplevel
        for toplevel in Gtk.Window.list_toplevels()
        # the stubs say widgets; not menus, popovers or tooltips; not hidden
        # windows
        if isinstance(toplevel, Gtk.Window)
        and toplevel.get_window_type() == Gtk.WindowType.TOPLEVEL
        and toplevel.get_visible()
    ]
    for toplevel in toplevels:
        if toplevel.is_active():
            return toplevel
    for toplevel in toplevels:
        if toplevel.get_role() == MAIN_ROLE:
            return toplevel
    return None


@implementer(ILogObserver)
class MessageDialogObserver:

    def __call__(self, event: LogEvent) -> None:
        dialog = Gtk.MessageDialog(
            transient_for=find_parent(),
            modal=True,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.CLOSE,
        )
        dialog.set_property("text", formatEvent(event))
        dialog.connect("response", lambda d, r: d.destroy())
        dialog.show()


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
    How the console opens, makes and saves projects with the windows: as the
    main window does, which saves what its tabs hold and shows the project,
    with open_project, new_project and save_project. Its engine is that of
    this process, which answers at once, as the console wants.
    """

    def __init__(
        self,
        *,
        open_project: Callable[[str], defer.Deferred[Report]],
        new_project: Callable[[str], defer.Deferred[Report]],
        save_project: Callable[[], defer.Deferred[None]],
    ) -> None:
        self.open_project = open_project
        self.new_project = new_project
        self.save_project = save_project

    def open(self, name: str, factory: BrickFactory) -> Report:
        return _now(self.open_project(name))

    def new(self, name: str, factory: BrickFactory) -> None:
        _now(self.new_project(name))

    def save(self, factory: BrickFactory) -> None:
        _now(self.save_project())


class Application(CliApplication):

    start_up_problem = None

    def get_log_observers(self) -> list[ILogObserver]:
        observers = super().get_log_observers()
        self.gui_message_log = MessageLog()
        observers.append(
            FilteringLogObserver(
                MessageLogObserver(self.gui_message_log),
                [LogLevelFilterPredicate(LogLevel.info)],
            )
        )
        observers.append(
            FilteringLogObserver(
                MessageDialogObserver(),
                # a function is a predicate as much as a class
                [should_show_to_user],  # type: ignore[list-item]
            )
        )
        return observers

    def migrate(self) -> defer.Deferred[Any] | None:
        """Convert the files of older versions, once; may return a Deferred."""
        assert self.workspace is not None, "take_locks() gives it"
        migration = startup_migration(self.workspace)
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

        try:
            projects.open_last(factory)
        except (errors.InvalidNameError, ProjectFormatError) as exc:
            name = projects.last_name()
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
            logger.warn(cannot_open_last, message=message)
            self.start_up_problem = message

    async def create_main_window(
        self, factory: BrickFactory, reactor: PosixReactorBase
    ) -> None:
        assert self.gui_message_log is not None
        self.main_window = MainWindow(
            LocalEngine(factory), self.gui_message_log
        )
        self.main_window.set_title()
        # The workspace has no desktop of its own: removing a project moves
        # it to the trash only in the GUI.
        projects.trasher = DesktopTrash()
        use_frontend(
            WindowFrontend(
                open_project=self.main_window.on_open,
                new_project=self.main_window.on_new,
                save_project=self.main_window.on_save,
            )
        )
        await self.check_prerequisites()
        if self.start_up_problem is not None:
            self.main_window.show_start_up_problem(self.start_up_problem)

    def check_prerequisites(self) -> defer.Deferred[None]:
        """
        Say which programs are missing, and the packages that have them; and
        KSM, if the settings ask for it and it isn't on once the start has
        tried to turn it on.
        """

        missing = missing_programs(
            str(get_setting("vde_path")), str(get_setting("qemu_path"))
        )

        def warn(running: bool) -> None:
            lines = []
            line = ksm_warning(
                bool(get_setting("kernel_samepage_merging")),
                ksm.ksm_available(),
                running,
            )
            if line:
                lines.append(line)
            if missing:
                names = ", ".join(map(str, missing))
                lines.append(programs_not_found.format(programs=names))
            if lines and get_setting("warn_missing_programs"):
                logger.error(components_not_found, text="\n".join(lines))

        return ksm_started().addCallback(warn)

    def get_console_namespace(self) -> dict[str, Any]:
        ns = super().get_console_namespace()
        ns["main_window"] = self.main_window
        return ns


def ksm_warning(wanted: bool, available: bool, running: bool) -> str | None:
    """
    What the warning at start says of KSM: nothing unless the settings ask
    for it (wanted); then whether this Linux has it, and whether it runs.
    """

    if not wanted:
        return None
    if not available:
        return ksm_not_found
    if not running:
        return ksm_still_off
    return None


def should_show_to_user(event: LogEvent) -> PredicateResult:
    if "hide_to_user" in event:
        return PredicateResult.no
    if event["log_level"] not in (LogLevel.error, LogLevel.critical):
        return PredicateResult.no
    return PredicateResult.maybe


class RemoteApplication(Application):
    """
    The windows of another Virtualbricks, the one of the socket of
    ``--connect`` (page 19): its copy, and an engine that sends there what
    the windows do. No lock, no migration, no workspace, no autosave, no
    socket and no console of their own; the settings are those of this
    computer. Quit closes the windows; the Virtualbricks there goes on.
    """

    def __init__(self, options: cli.CommandLineOptions) -> None:
        # no workspace: that of the Virtualbricks there
        super().__init__(options, None)
        self.engine: RemoteEngine | None = None
        self.quitting = False
        # the Virtualbricks there said it quits
        self.ended = False

    def migrate(self) -> None:
        return None

    def install_settings(self) -> None:
        load_settings()

    def install_workspace(self) -> None:
        pass

    def install_factory(self, reactor: PosixReactorBase) -> BrickFactory:
        from virtualbricks.remote.mirror import MirrorFactory

        self.copy = MirrorFactory(reactor)
        return self.copy

    def open_last_project(self, factory: BrickFactory) -> None:
        pass

    def save_project(self, factory: BrickFactory) -> None:
        pass

    def start_listening(
        self, factory: BrickFactory, reactor: PosixReactorBase
    ) -> None:
        pass

    def install_autosave_timer(
        self, factory: BrickFactory, interval: float = 180
    ) -> None:
        pass

    def install_switch_wrapper_timer(
        self, factory: BrickFactory, interval: float = LOOK_EVERY
    ) -> None:
        pass

    async def create_main_window(
        self, factory: BrickFactory, reactor: PosixReactorBase
    ) -> None:
        """
        Connect, then show the windows of factory, the copy that
        install_factory() made; done ends the run, once the windows close.
        """

        from virtualbricks.remote import client
        from virtualbricks.remote.client import Refused

        assert self.options.target is not None, "--connect names it"
        self.reactor = reactor
        self.where = client.where(self.options.target)
        try:
            # with --connect alone, the socket that a Virtualbricks of yours
            # listens on, found once: Reconnect goes there
            self.target = client.resolve(
                self.options.target, self.options.workspace
            )
            windows = await client.connect(
                self.target, self.copy, reactor, self.made
            )
        except Refused as exc:
            raise SystemExit(str(exc)) from None
        self.show(windows)

    def show(self, windows: Windows) -> None:
        """The windows, on the copy that the connection keeps."""

        from virtualbricks.remote import client, tunnel
        from virtualbricks.remote.client import RemoteEngine

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
        windows.lost.addCallback(self.lost)
        self.main_window = MainWindow(self.engine, self.gui_message_log)
        self.copy.synced.connect(self.synced)
        self.copy.ended.connect(self.on_ended)
        self.main_window.set_title()
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
        self.gui_message_log.add_message(message, self.where)

    def synced(self, copy: MirrorFactory) -> None:
        # a project opened there, or the same again after Reconnect
        self.main_window.on_opened()

    def on_ended(self, copy: MirrorFactory) -> None:
        self.ended = True

    def warn(self, machine: Mapping[str, Any]) -> None:
        """What the machine of the bricks lacks, as the warning at start."""

        if not get_setting("warn_missing_programs"):
            return
        lines = []
        # a lab machine of before ksm_available has KSM, as far as we know
        line = ksm_warning(
            self.copy.settings.get("kernel_samepage_merging", False),
            machine.get("ksm_available", True),
            machine.get("ksm", True),
        )
        if line:
            lines.append(line)
        missing = machine.get("missing") or []
        if missing:
            lines.append(
                programs_not_found.format(programs=", ".join(missing))
            )
        if lines:
            logger.error(components_not_found, text="\n".join(lines))

    def lost(self, reason: object) -> None:
        if self.quitting:
            return
        if self.ended:
            text = _("Virtualbricks on {where} quit").format(where=self.where)
        else:
            text = _("The connection to {where} is lost: {reason}").format(
                where=self.where, reason=reason
            )
        self.main_window.connection_lost(text, self.reconnect)

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
        self.main_window.reconnected()

    def not_reconnected(self, failure: Failure) -> None:
        from virtualbricks.remote.client import Refused

        failure.trap(Refused)
        self.main_window.connection_lost(
            failure.getErrorMessage(), self.reconnect
        )

    def quit(self) -> None:
        """The windows close; the Virtualbricks there goes on."""

        if self.quitting:
            return
        self.quitting = True
        self.main_window.on_quit(None)
        # closing the window quits too
        if not self.main_window.window.in_destruction():
            self.main_window.window.destroy()
        assert self.engine is not None, "the engine of the windows quits them"
        windows = self.engine.windows
        if windows is not None and windows.transport is not None:
            windows.transport.loseConnection()
        # the sockets of the consoles
        self.consoles.close()
        self.done.callback(None)
