# -*- test-case-name: virtualbricks.tests.test_main -*-
from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING, NoReturn

from virtualbricks import __version__, cli, i18n, locks

if TYPE_CHECKING:  # pragma: no cover
    from twisted.internet.posixbase import PosixReactorBase

    from virtualbricks.app import Application


starts = (
    "Virtualbricks {version} starts: Python {python} ({executable}),"
    " Twisted {twisted}, {reactor}"
)


def take_locks(options: cli.CommandLineOptions) -> tuple[locks.Lock, str]:
    """
    The locks of policy, and that of the workspace, made if missing; and the
    folder of the workspace, which the run uses: the setting is read here
    alone, so the run works in the folder it locked.
    """
    from virtualbricks.migrate import settings_to_convert, startup_workspace

    try:
        # the settings of 2.1 are the user's: converted by one alone
        user_alone = options.lock == locks.WORKSPACE and bool(
            settings_to_convert()
        )
        lock = locks.acquire(options.lock, user_alone)
        try:
            workspace = startup_workspace(options.workspace)
            if lock.locked:
                os.makedirs(workspace, exist_ok=True)
            lock.take_workspace(workspace)
        except BaseException:
            lock.unlock()
            raise
        return lock, workspace
    except OSError as exc:
        raise SystemExit(
            f"Cannot take the lock {exc.filename}: {exc.strerror}. With"
            " --lock none, Virtualbricks runs without locks."
        ) from None
    except Exception as exc:
        raise SystemExit(str(exc))


def install_reactor(options: cli.CommandLineOptions) -> None:
    assert options.mode in (cli.GUI, cli.NO_GUI, cli.REMOTE)
    if options.mode == cli.NO_GUI:
        from twisted.internet import default

        default.install()
    else:
        import gi

        gi.require_version("Gtk", "3.0")
        gi.require_version("Gdk", "3.0")
        from twisted.internet import gireactor

        gireactor.install()


def install_application(
    options: cli.CommandLineOptions, workspace: str | None
) -> Application:
    assert options.mode in (cli.NO_GUI, cli.GUI, cli.REMOTE)
    if options.mode == cli.REMOTE:
        from virtualbricks.gui.app import RemoteApplication

        return RemoteApplication(options)
    if options.mode == cli.NO_GUI:
        from virtualbricks.app import Application
    else:
        from virtualbricks.gui.app import Application

    return Application(options, workspace)


async def run(
    reactor: PosixReactorBase,
    options: cli.CommandLineOptions,
    lock: locks.Lock | None,
    workspace: str | None,
) -> None:
    import platform

    import twisted
    from twisted.internet import defer
    from twisted.logger import Logger
    from twisted.python import reflect

    if lock is not None:
        reactor.addSystemEventTrigger("after", "shutdown", lock.release)
    app = install_application(options, workspace)
    app.install_logging()
    logger = Logger("virtualbricks.main")
    logger.info(
        starts,
        version=__version__,
        python=platform.python_version(),
        executable=sys.executable,
        twisted=twisted.__version__,
        reactor=reflect.qual(type(reactor)),
    )
    reactor.addSystemEventTrigger("after", "shutdown", app.stop_logger)
    await defer.maybeDeferred(app.migrate)
    # Share the user lock, taken alone for the settings of 2.1, with the other
    # workspaces; nothing if take_locks() didn't take it alone.
    app.share_user_lock(lock)
    app.install_settings()
    reactor.addSystemEventTrigger("before", "shutdown", app.store_settings)
    app.install_workspace()
    factory = app.install_factory(reactor)
    app.open_last_project(factory)
    reactor.addSystemEventTrigger(
        "before", "shutdown", app.save_project, factory
    )
    app.start_listening(factory, reactor)
    app.install_autosave_timer(factory)
    app.install_switch_wrapper_timer(factory)
    await app.create_main_window(factory, reactor)
    if app.options.run:
        await app.run_script(factory)
    if not app.options.no_term:
        app.start_console(factory)
    app.install_sys_hooks()
    await factory.quit_d
    return None


def main() -> NoReturn:
    i18n.install()
    options = cli.parse_or_exit()
    if options.mode in (cli.GUI, cli.NO_GUI):
        lock, workspace = take_locks(options)
    else:
        lock, workspace = None, None

    if options.mode == cli.COMMAND:
        from virtualbricks.console import client

        sys.exit(
            client.main(
                options.words,
                options.target,
                script=None if options.words else options.run,
                workspace=options.workspace,
            )
        )
    else:
        from twisted.internet import task

        install_reactor(options)
        task.react(run, (options, lock, workspace))


if __name__ == "__main__":
    main()
