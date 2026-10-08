# -*- test-case-name: virtualbricks.tests.test_app -*-
# Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
# Copyright (C) 2026 Virtualbricks team

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

from __future__ import annotations

import os
import platform
import shlex
import sys
import threading
from collections.abc import Mapping
from types import TracebackType
from typing import IO, Any

import twisted
from twisted.internet import defer, task
from twisted.internet.posixbase import PosixReactorBase
from twisted.python import failure, reflect
from twisted.logger import (
    FilteringLogObserver,
    ILogObserver,
    LogLevel,
    LogLevelFilterPredicate,
    Logger,
    globalLogBeginner,
    globalLogPublisher,
)

from virtualbricks import __version__, i18n, locks
from virtualbricks.brickfactory import BrickFactory
from virtualbricks.config.settings import (
    get_setting,
    load_settings,
    load_state,
    store_settings,
)
from virtualbricks.config.workspace import projects

logger = Logger()
starts = (
    "Virtualbricks {version} starts: Python {python} ({executable}),"
    " Twisted {twisted}, {reactor}"
)
shut_down = "Server Shut Down."
uncaught_exception = "Uncaught exception: {error()}"


def AutosaveTimer(
    factory: BrickFactory, interval: float = 180
) -> task.LoopingCall:
    timer = task.LoopingCall(projects.autosave, factory)
    timer.start(interval, now=False)
    return timer


def log_level(verbosity: int) -> LogLevel:
    """Return the minimum level logged for the given -v/-q verbosity."""

    if verbosity > 0:
        return LogLevel.debug
    if verbosity == 0:
        return LogLevel.info
    if verbosity == -1:
        return LogLevel.warn
    return LogLevel.error


class AppLogger:

    def __init__(self, options: Mapping[str, Any]) -> None:
        self._observer_factory = options.get("logger")
        self._level = log_level(options.get("verbosity", 0))
        self._observers: list[ILogObserver] = []

    def get_observers(self) -> list[ILogObserver]:
        if self._observer_factory is None:
            return []
        observer = FilteringLogObserver(
            self._observer_factory(),
            [LogLevelFilterPredicate(self._level)],
        )
        return [observer]

    def start(self, reactor: object) -> None:
        self._observers = self.get_observers()
        # The standard streams are used by the interactive console.
        globalLogBeginner.beginLoggingTo(
            self._observers, redirectStandardIO=False
        )
        logger.info(
            starts,
            version=__version__,
            python=platform.python_version(),
            executable=sys.executable,
            twisted=twisted.__version__,
            reactor=reflect.qual(type(reactor)),
        )

    def stop(self) -> None:
        logger.info(shut_down)
        for observer in self._observers:
            globalLogPublisher.removeObserver(observer)
        self._observers = []


class Application:
    """
    Virtualbricks that runs the bricks: the locks, the migration, the
    project, the console in the terminal, the control sockets and the
    script of --run. Without the windows, as --no-gui runs it.
    """

    logger_factory: type[AppLogger] = AppLogger
    factory_factory: type[BrickFactory] = BrickFactory

    def __init__(self, config: Mapping[str, Any]) -> None:
        self.config = config
        self.logger = self.logger_factory(config)

    def install_locale(self) -> None:
        i18n.install()

    def install_settings(self) -> None:
        load_settings()
        load_state()

    def install_workspace(self) -> None:
        # the folder of the command line, for this run only: the setting
        # stays as it is. Either stays for the run, whose lock is that of
        # this folder: a new setting is for the next start.
        projects.path = self.config.get("workspace") or str(
            get_setting("workspace")
        )

    def install_sys_hooks(self) -> None:
        sys.excepthook = self.excepthook
        threading.excepthook = self.thread_excepthook

    def thread_excepthook(self, args: threading.ExceptHookArgs) -> None:
        # Like threading's default hook, a thread may exit silently.
        if args.exc_type is SystemExit:
            return
        self.excepthook(args.exc_type, args.exc_value, args.exc_traceback)

    def excepthook(
        self,
        exc_type: type[BaseException],
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if exc_type in (SystemExit, KeyboardInterrupt):
            assert exc_value is not None, "what is raised is there"
            sys.__excepthook__(exc_type, exc_value, traceback)
        else:
            fail = failure.Failure(exc_value, exc_type, traceback)
            logger.error(
                uncaught_exception,
                log_failure=fail,
                error=lambda: fail.getErrorMessage(),
            )

    def install_home(self) -> None:
        # with the link to the workspace, and room for its socket
        projects.make_runtime_dir()

    def get_namespace(self) -> dict[str, object]:
        return {}

    def migrate(self) -> defer.Deferred[Any] | None:
        """Convert the files of older versions, once; may return a Deferred."""

        from virtualbricks.migrate import startup_migration

        migration = startup_migration(self.config.get("workspace"))
        if migration is not None:
            migration.run()
            migration.log(logger)
        return None

    def run(self, reactor: PosixReactorBase) -> defer.Deferred[None]:
        """
        Take the locks, migrate, then start: a Deferred that fires at the
        quit, or fails with SystemExit when another Virtualbricks holds a
        lock.
        """

        from virtualbricks.migrate import settings_to_convert
        from virtualbricks.migrate import startup_workspace

        policy = self.config.get("lock", locks.SYSTEM)
        # the settings of 2.1 are the user's: converted by one alone
        user_alone = policy == locks.WORKSPACE and bool(settings_to_convert())
        workspace = os.path.abspath(
            startup_workspace(self.config.get("workspace"))
        )
        try:
            lock = self.take_locks(policy, user_alone, workspace)
        except locks.Held as held:
            return defer.fail(SystemExit(str(held)))
        except OSError as error:
            msg = (
                f"Cannot take the lock {error.filename}: {error.strerror}. "
                "With --lock none, Virtualbricks runs without locks."
            )
            return defer.fail(SystemExit(msg))
        reactor.addSystemEventTrigger("after", "shutdown", lock.unlock)
        self.install_locale()
        d = defer.maybeDeferred(self.migrate)
        if user_alone:
            # this run migrated: the other workspaces start from now on
            d.addCallback(lambda _: self.share_user_lock(lock))
        return d.addCallback(lambda _: self._start(reactor))

    def take_locks(
        self, policy: str, user_alone: bool, workspace: str
    ) -> locks.Lock:
        """The locks of policy, and that of workspace, made if missing."""

        lock = locks.acquire(policy, user_alone)
        try:
            if lock.locked:
                os.makedirs(workspace, exist_ok=True)
            lock.take_workspace(workspace)
        except BaseException:
            lock.unlock()
            raise
        return lock

    def share_user_lock(self, lock: locks.Lock) -> None:
        """Share the user lock, taken alone, with the other workspaces."""

        try:
            lock.share_user()
        except locks.Held as held:
            raise SystemExit(str(held)) from None

    def _start(self, reactor: PosixReactorBase) -> defer.Deferred[None]:
        self.install_settings()
        self.install_workspace()
        self.logger.start(reactor)
        self.install_home()
        quit: defer.Deferred[None] = defer.Deferred()
        factory = self.factory_factory(quit)
        self._run(factory)
        if self.config["verbosity"] >= 2 and not self.config["noterm"]:
            import signal
            import pdb

            from twisted.application.app import fixPdb

            signal.signal(signal.SIGUSR2, lambda *args: pdb.set_trace())
            signal.signal(signal.SIGINT, lambda *args: pdb.set_trace())
            fixPdb()
        reactor.addSystemEventTrigger("before", "shutdown", store_settings)
        self.open_last_project(factory)
        self.listen(factory, reactor)
        reactor.addSystemEventTrigger(
            "before", "shutdown", projects.save, factory
        )
        reactor.addSystemEventTrigger("before", "shutdown", self.logger.stop)
        AutosaveTimer(factory)
        started: defer.Deferred[Any] = defer.succeed(None)
        if self.config.get("run"):
            started = self.run_script(factory, self.config["run"])
        if not self.config["noterm"]:
            started.addCallback(lambda _: self.start_console(factory))
        # delay as much as possible the installation of hooks because the
        # exception hook can hide errors in the code requiring to start the
        # application again with logging redirected
        self.install_sys_hooks()
        return quit

    def _run(self, factory: BrickFactory) -> None:
        pass

    def start_console(self, factory: BrickFactory) -> None:
        """Read the console in the terminal that started Virtualbricks."""

        from virtualbricks.console.terminal import start

        start(factory, self.get_namespace())

    def listen(self, factory: BrickFactory, reactor: PosixReactorBase) -> None:
        """Answer on the control sockets of --listen; on none without it."""

        sockets = self.config.get("sockets")
        if not sockets:
            return
        from virtualbricks.console.control import listen

        for socket in sockets:
            listen(factory, socket, reactor)

    def run_script(
        self, factory: BrickFactory, path: str
    ) -> defer.Deferred[list[str]]:
        """Run the commands of path, as the console's source does."""

        from virtualbricks.console.dispatch import run
        from virtualbricks.console.terminal import error_lines

        done = run(factory, f"source {shlex.quote(path)}")

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

    def open_last_project(self, factory: BrickFactory) -> None:
        """Open the project open last, or a new new_project_N."""

        projects.restore_last(factory)
