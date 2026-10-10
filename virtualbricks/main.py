from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING, Any, NoReturn

from virtualbricks import i18n
from virtualbricks import locks
from virtualbricks import cli_new as cli

if TYPE_CHECKING:
    import threading
    from types import TracebackType
    from twisted.logger import LogLevel, Logger
    from twisted.internet import defer, task
    from virtualbricks.brickfactory import BrickFactory
    from twisted.internet.posixbase import PosixReactorBase


LOOK_EVERY = 1.0

starts = (
    "Virtualbricks {version} starts: Python {python} ({executable}),"
    " Twisted {twisted}, {reactor}"
)
uncaught_exception = "Uncaught exception: {error()}"
shut_down = "Server Shut Down"


def take_locks(options: cli.CommandLineOptions) -> locks.Lock | None:
    """The locks of policy, and that of workspace, made if missing."""
    if options.mode in (cli.REMOTE, cli.COMMAND):
        return None
    else:
        from virtualbricks.migrate import (
            settings_to_convert,
            startup_workspace,
        )

        # the settings of 2.1 are the user's: converted by one alone
        user_alone = options.lock == locks.WORKSPACE and bool(
            settings_to_convert()
        )
        lock = locks.acquire(options.lock, user_alone)
        try:
            workspace = os.path.abspath(startup_workspace(options.workspace))
            if lock.locked:
                os.makedirs(workspace, exist_ok=True)
            lock.take_workspace(workspace)
        except BaseException:
            lock.unlock()
            raise
        return lock


def install_reactor(options: cli.CommandLineOptions) -> None:
    if options.mode == cli.NO_GUI:
        from twisted.internet import default

        default.install()
    else:
        import gi

        gi.require_version("Gtk", "3.0")
        gi.require_version("Gdk", "3.0")
        from twisted.internet import gireactor

        gireactor.install()


def log_level(verbosity: int) -> LogLevel:
    """Return the minimum level logged for the given -v/-q verbosity."""
    from twisted.logger import LogLevel

    if verbosity > 0:
        return LogLevel.debug
    if verbosity == 0:
        return LogLevel.info
    if verbosity == -1:
        return LogLevel.warn
    return LogLevel.error


def get_logger() -> Logger:
    from twisted.logger import Logger

    return Logger("virtualbricks.main")


def install_logging(options: cli.CommandLineOptions) -> None:

    from twisted.logger import (
        FilteringLogObserver,
        LogLevelFilterPredicate,
        globalLogBeginner,
    )
    from twisted.logger import LogLevel
    from twisted.logger import textFileLogObserver
    from twisted.python import logfile, reflect

    observers = []
    level = log_level(options.verbosity)
    if options.logger is not None:
        try:
            observer = reflect.namedAny(options.logger)
        except Exception as err:
            raise SystemExit(
                f"Logger '{options.logger}' could not be imported: {err}"
            )
        observers.append(observer)
    elif options.logfile is not None:
        if options.logfile == "-":
            text_file_observer = textFileLogObserver(sys.stdout)
        else:
            log_file = logfile.LogFile.fromFullPath(options.logfile)
            text_file_observer = textFileLogObserver(log_file)
        observer = FilteringLogObserver(
            text_file_observer,
            [LogLevelFilterPredicate(level)],
        )
        observers.append(observer)
    if options.mode == cli.GUI:
        from virtualbricks.gui.messages import MessageLog, MessageLogObserver

        messages = MessageLog()
        observer = FilteringLogObserver(
            MessageLogObserver(messages),
            [LogLevelFilterPredicate(LogLevel.info)],
        )
        observers.append(observer)

    globalLogBeginner.beginLoggingTo(observers, redirectStandardIO=False)


def migrate(options: cli.CommandLineOptions) -> defer.Deferred[Any] | None:
    """Convert the files of older versions, once; may return a Deferred."""
    from virtualbricks.migrate import startup_migration

    migration = startup_migration(options.workspace)
    if migration is None:
        return None
    if options.mode == cli.GUI:
        from virtualbricks.migrate.gui import MigrationWindow

        window = MigrationWindow(migration=migration)
        window.show()
        return window.closed
    elif options.mode == cli.NO_GUI:
        migration.run()
        migration.log(get_logger())
        return None
    else:
        raise RuntimeError(f"unknown mode: {options.mode}")


def share_user_lock(lock: locks.Lock) -> None:
    """
    Share the user lock, taken alone for the settings of 2.1, with the other
    workspaces; nothing if take_locks() didn't take it alone.
    """

    # this run migrated: the other workspaces start from now on
    try:
        lock.share_user()
    except Exception as exc:
        raise SystemExit(str(exc)) from None


def install_settings() -> None:
    from virtualbricks.config.settings import load_settings, load_state

    load_settings()
    load_state()


def install_workspace(options: cli.CommandLineOptions) -> None:
    from virtualbricks.config.workspace import projects
    from virtualbricks.config.settings import get_setting

    # the folder of the command line, for this run only: the setting
    # stays as it is. Either stays for the run, whose lock is that of
    # this folder: a new setting is for the next start.
    projects.path = options.workspace or str(get_setting("workspace"))
    # with the link to the workspace, and room for its socket
    projects.make_runtime_dir()


# TODO: window


def open_last_project(factory: BrickFactory) -> None:
    """Open the project open last, or a new new_project_N."""
    from virtualbricks.config.workspace import projects

    projects.restore_last(factory)


def start_listening(
    options: cli.CommandLineOptions,
    factory: BrickFactory,
    reactor: PosixReactorBase,
) -> None:
    """Answer on the control sockets of --listen; on none without it."""
    from virtualbricks.console.control import listen

    for socket in options.listen:
        listen(factory, socket, reactor)


def install_autosave_timer(
    factory: BrickFactory, interval: float = 180
) -> task.LoopingCall:
    from twisted.internet import task
    from virtualbricks.config.workspace import projects

    timer = task.LoopingCall(projects.autosave, factory)
    timer.start(interval, now=False)
    return timer


def install_switch_wrapper_timer(
    factory: BrickFactory, interval: float = LOOK_EVERY
) -> task.LoopingCall:
    """Look at the control folders of the switch wrappers, at each interval."""
    from twisted.internet import task
    from virtualbricks.bricks.switchwrapper import look_all

    timer = task.LoopingCall(look_all, factory)
    timer.start(interval, now=False)
    return timer


def run_script(factory: BrickFactory, path: str) -> defer.Deferred[list[str]]:
    """Run the commands of path, as the console's source does."""

    import shlex
    from typing import IO

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


def start_console(factory: BrickFactory, namespace: dict[str, Any]) -> None:
    """Read the console in the terminal that started Virtualbricks."""

    from virtualbricks.console.terminal import start

    start(factory, namespace)


def install_sys_hooks() -> None:
    import threading

    sys.excepthook = excepthook
    threading.excepthook = thread_excepthook


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
    from twisted.python.failure import Failure

    if exc_type in (SystemExit, KeyboardInterrupt):
        assert exc_value is not None, "what is raised is there"
        sys.__excepthook__(exc_type, exc_value, traceback)
    else:
        fail = Failure(exc_value, exc_type, traceback)
        get_logger().error(
            uncaught_exception,
            log_failure=fail,
            error=lambda: fail.getErrorMessage(),
        )


def stop_logger() -> None:
    get_logger().info(shut_down)


def main_command(options: cli.CommandLineOptions) -> int:
    from virtualbricks.console import client

    exit_code = client.main(
        options.words,
        options.target,
        script=None if options.words else options.run,
        workspace=options.workspace,
    )
    return exit_code


async def main_no_gui(
    reactor: PosixReactorBase,
    options: cli.CommandLineOptions,
    lock: locks.Lock,
) -> None:
    from twisted.internet import defer
    from virtualbricks.brickfactory import BrickFactory
    from virtualbricks.config.settings import store_settings
    from virtualbricks.config.workspace import projects

    await defer.maybeDeferred(migrate, options)
    share_user_lock(lock)
    install_settings()
    reactor.addSystemEventTrigger("before", "shutdown", store_settings)
    install_workspace(options)
    quit_deferred: defer.Deferred[None] = defer.Deferred()
    factory = BrickFactory(quit_deferred)
    open_last_project(factory)
    reactor.addSystemEventTrigger("before", "shutdown", projects.save, factory)
    start_listening(options, factory, reactor)
    install_autosave_timer(factory)
    install_switch_wrapper_timer(factory)
    if options.run:
        await run_script(factory, options.run)
    if not options.no_term:
        start_console(factory, {})
    install_sys_hooks()
    await quit_deferred
    return None


async def main_gui(
    reactor: PosixReactorBase,
    options: cli.CommandLineOptions,
    lock: locks.Lock,
) -> None:
    from twisted.internet import defer
    from virtualbricks.brickfactory import BrickFactory
    from virtualbricks.config.settings import store_settings

    reactor.addSystemEventTrigger("before", "shutdown", store_settings)
    await defer.maybeDeferred(migrate, options)
    share_user_lock(lock)
    install_settings()
    install_workspace(options)
    quit_deferred: defer.Deferred[None] = defer.Deferred()
    factory = BrickFactory(quit_deferred)
    open_last_project(factory)
    start_listening(options, factory, reactor)
    install_autosave_timer(factory)
    install_switch_wrapper_timer(factory)
    if options.run:
        await run_script(factory, options.run)
    if not options.no_term:
        start_console(factory, {})
    install_sys_hooks()
    await quit_deferred
    return None


def _main(
    reactor: PosixReactorBase,
    options: cli.CommandLineOptions,
    lock: locks.Lock,
) -> defer.Deferred[None]:
    import platform
    import twisted
    from twisted.internet.defer import ensureDeferred
    from twisted.python import reflect
    from virtualbricks import __version__

    assert lock is not None
    reactor.addSystemEventTrigger("after", "shutdown", lock.release)
    install_logging(options)
    get_logger().info(
        starts,
        version=__version__,
        python=platform.python_version(),
        executable=sys.executable,
        twisted=twisted.__version__,
        reactor=reflect.qual(type(reactor)),
    )
    reactor.addSystemEventTrigger("after", "shutdown", stop_logger)

    if options.mode == cli.GUI:
        return ensureDeferred(main_gui(reactor, options, lock))
    elif options.mode == cli.NO_GUI:
        return ensureDeferred(main_no_gui(reactor, options, lock))
    elif options.mode == cli.REMOTE:
        raise NotImplementedError
    else:
        raise RuntimeError(f"unknown mode: {options.mode}")


def main() -> NoReturn:
    i18n.install()
    options = cli.parse_or_exit()
    try:
        lock = take_locks(options)
    except OSError as exc:
        raise SystemExit(
            f"Cannot take the lock {exc.filename}: {exc.strerror}. With"
            " --lock none, Virtualbricks runs without locks."
        ) from None
    except Exception as exc:
        raise SystemExit(str(exc))

    if options.mode == cli.COMMAND:
        try:
            sys.exit(main_command(options))
        finally:
            if lock is not None:
                lock.release()
    else:
        from twisted.internet import task

        install_reactor(options)
        task.react(_main, (options, lock))


if __name__ == "__main__":
    main()
