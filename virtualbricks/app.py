# -*- test-case-name: virtualbricks.tests.test_app -*-
from __future__ import annotations

import shlex
import sys
import threading
from typing import IO, TYPE_CHECKING, Any

from twisted.internet import defer, task
from twisted.logger import (
    FilteringLogObserver,
    ILogObserver,
    Logger,
    LogLevel,
    LogLevelFilterPredicate,
    globalLogBeginner,
    textFileLogObserver,
)
from twisted.python import logfile, reflect
from twisted.python.failure import Failure

from virtualbricks import cli, locks
from virtualbricks.brickfactory import BrickFactory
from virtualbricks.bricks.switchwrapper import look_all
from virtualbricks.config.settings import (
    load_settings,
    load_state,
    store_settings,
)
from virtualbricks.config.workspace import projects
from virtualbricks.console.control import listen
from virtualbricks.console.dispatch import run
from virtualbricks.console.terminal import error_lines, start
from virtualbricks.migrate import startup_migration

if TYPE_CHECKING:  # pragma: no cover
    from types import TracebackType

    from twisted.internet.posixbase import PosixReactorBase


LOOK_EVERY = 1.0

logger = Logger("virtualbricks.main")
uncaught_exception = "Uncaught exception: {error()}"
shut_down = "Server Shut Down"


def log_level(verbosity: int) -> LogLevel:
    """Return the minimum level logged for the given -v/-q verbosity."""
    if verbosity > 0:
        return LogLevel.debug
    if verbosity == 0:
        return LogLevel.info
    if verbosity == -1:
        return LogLevel.warn
    return LogLevel.error


def thread_excepthook(args: threading.ExceptHookArgs) -> None:
    # Like threading's default hook, a thread may exit silently.
    if args.exc_type is SystemExit:
        return
    excepthook(args.exc_type, args.exc_value, args.exc_traceback)


def excepthook(
    exc_type: type[BaseException],
    exc_value: BaseException | None,
    traceback: TracebackType | None,
) -> None:
    if exc_type in (SystemExit, KeyboardInterrupt):
        assert exc_value is not None, "what is raised is there"
        sys.__excepthook__(exc_type, exc_value, traceback)
    else:
        fail = Failure(exc_value, exc_type, traceback)
        logger.error(
            uncaught_exception,
            log_failure=fail,
            error=lambda: fail.getErrorMessage(),
        )


class Application:

    def __init__(self, options: cli.CommandLineOptions, workspace: str | None):
        self.options = options
        # the folder of the workspace, --workspace or the setting's, as
        # take_locks() read it to lock it: the migration and the run use it,
        # and don't read the setting again
        self.workspace = workspace

    def get_log_observers(self) -> list[ILogObserver]:
        observers = []
        level = log_level(self.options.verbosity)
        if self.options.logger is not None:
            try:
                observer = reflect.namedAny(self.options.logger)
            except Exception as err:
                raise SystemExit(
                    f"Logger '{self.options.logger}' could not be imported: {err}"
                )
            observers.append(observer)
        elif self.options.logfile is not None:
            if self.options.logfile == "-":
                text_file_observer = textFileLogObserver(sys.stdout)
            else:
                log_file = logfile.LogFile.fromFullPath(self.options.logfile)
                text_file_observer = textFileLogObserver(log_file)
            observer = FilteringLogObserver(
                text_file_observer,
                [LogLevelFilterPredicate(level)],
            )
            observers.append(observer)

        return observers

    def install_logging(self) -> None:
        observers = self.get_log_observers()
        globalLogBeginner.beginLoggingTo(observers, redirectStandardIO=False)

    def stop_logger(self) -> None:
        logger.info(shut_down)

    def migrate(self) -> defer.Deferred[Any] | None:
        """Convert the files of older versions, once; may return a Deferred."""
        assert self.workspace is not None, "take_locks() gives it"
        migration = startup_migration(self.workspace)
        if migration is None:
            return None
        migration.run()
        migration.log(logger)
        return None

    def share_user_lock(self, lock: locks.Lock | None) -> None:
        """
        Share the user lock, taken alone for the settings of 2.1, with the other
        workspaces; nothing if take_locks() didn't take it alone.
        """

        # this run migrated: the other workspaces start from now on
        if lock is not None:
            try:
                lock.share_user()
            except Exception as exc:
                raise SystemExit(str(exc)) from None

    def install_settings(self) -> None:
        load_settings()
        load_state()

    def store_settings(self) -> None:
        store_settings()

    def install_workspace(self) -> None:
        # the folder of the command line, for this run only: the setting
        # stays as it is. Either stays for the run, whose lock is that of
        # this folder: a new setting is for the next start.
        assert self.workspace is not None, "take_locks() gives it"
        projects.path = self.workspace
        # with the link to the workspace, and room for its socket
        projects.make_runtime_dir()

    def install_factory(self, reactor: PosixReactorBase) -> BrickFactory:
        return BrickFactory(defer.Deferred())

    def open_last_project(self, factory: BrickFactory) -> None:
        """Open the project open last, or a new new_project_N."""

        projects.restore_last(factory)

    def save_project(self, factory: BrickFactory) -> None:
        projects.save(factory)

    def start_listening(
        self, factory: BrickFactory, reactor: PosixReactorBase
    ) -> None:
        """Answer on the control sockets of --listen; on none without it."""

        for socket in self.options.listen:
            listen(factory, socket, reactor)

    def install_autosave_timer(
        self, factory: BrickFactory, interval: float = 180
    ) -> None:
        timer = task.LoopingCall(projects.autosave, factory)
        timer.start(interval, now=False)

    def install_switch_wrapper_timer(
        self, factory: BrickFactory, interval: float = LOOK_EVERY
    ) -> None:
        """Look at the control folders of the switch wrappers, at each interval."""

        timer = task.LoopingCall(look_all, factory)
        timer.start(interval, now=False)

    async def create_main_window(
        self, factory: BrickFactory, reactor: PosixReactorBase
    ) -> None:
        pass

    def run_script(self, factory: BrickFactory) -> defer.Deferred[list[str]]:
        """Run the commands of options.run, as the console's source does."""

        assert self.options.run is not None
        done = run(factory, f"source {shlex.quote(self.options.run)}")

        def write(lines: list[str], stream: IO[str]) -> None:
            for line in lines:
                stream.write(line + "\n")
            stream.flush()

        done.addCallbacks(
            write,
            lambda failure: write(error_lines(failure), sys.stderr),
            callbackArgs=(sys.stdout,),
        )
        return done

    def get_console_namespace(self) -> dict[str, Any]:
        return {}

    def start_console(self, factory: BrickFactory) -> None:
        """Read the console in the terminal that started Virtualbricks."""

        start(factory, self.get_console_namespace())

    def install_sys_hooks(self) -> None:

        sys.excepthook = excepthook
        threading.excepthook = thread_excepthook
