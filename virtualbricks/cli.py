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

from __future__ import annotations

import importlib
import os
import re
import shlex
import sys
from collections.abc import Callable, Iterable
from types import ModuleType
from typing import IO, TYPE_CHECKING, Any, Protocol, TypeVar

from twisted.python import usage, reflect
from twisted.internet import defer, task
from twisted.logger import ILogObserver, textFileLogObserver

from virtualbricks import locations, locks
from virtualbricks.console import wire

if TYPE_CHECKING:  # pragma: no cover
    # posixbase loads TCP and TLS, which --command goes without
    from twisted.internet.posixbase import PosixReactorBase

    from virtualbricks.brickfactory import Application
    from virtualbricks.gui import gui

T = TypeVar("T")

_log_file: IO[str] = sys.stdout
# The word after --listen is its description when it starts with a type.
DESCRIPTION = re.compile(r"[a-z][a-z0-9]*:", re.IGNORECASE)


def file_logger() -> ILogObserver:
    return textFileLogObserver(_log_file)


def _file_logger(filename: str) -> str:
    if filename != "-":
        from twisted.python import logfile

        global _log_file
        _log_file = logfile.LogFile.fromFullPath(filename)
    return "virtualbricks.cli.file_logger"


class Options(usage.Options):

    longdesc = """Virtualbricks - a vde/qemu gui written in python and
    GTK/Glade.

    Copyright (C) 2019 Virtualbricks team"""

    optFlags = [
        ["noterm", None, "Don't read the console in the terminal."],
        [
            "no-gui",
            None,
            "Run without the windows: the console is the way in.",
        ],
        [
            "command",
            None,
            "Send the command of the words that follow to the Virtualbricks "
            "that runs, the one of --connect or of --workspace, and print "
            "its answer; without words, the lines of the standard input.",
        ],
        # read before getopt, which has no optional arguments
        [
            "listen",
            None,
            "Listen on a control socket: .control in the runtime folder of "
            "the workspace, or the one of the description after it, as "
            "unix:PATH, tcp:PORT or ssl:PORT:privateKey=FILE. It speaks AMP, "
            "or the text protocol with protocol=text. Give it again for more "
            "sockets.",
        ],
        [
            "connect",
            None,
            "The Virtualbricks that runs that --command and --run talk to: "
            "the one of .control in the runtime folder of its workspace, or "
            "the one of the socket of the description after it, as "
            "tcp:HOST:PORT. Without them, its windows open.",
        ],
    ]
    optParameters = [
        ["logfile", "l", None, "Write log messages to file."],
        [
            "run",
            None,
            None,
            "Run the commands of a file once the project is open; with "
            "--connect, send them to the Virtualbricks that runs, and exit.",
        ],
        [
            "workspace",
            None,
            None,
            "The folder of the projects for this run, instead of the "
            "setting; with --command or --connect, the Virtualbricks that "
            "runs there.",
        ],
        [
            "lock",
            None,
            locks.SYSTEM,
            "The single-instance mode: system, one Virtualbricks on the "
            "machine; user, one for each user; workspace, one for each "
            "workspace, the default with --workspace; none, no limit.",
        ],
        [
            "logger",
            None,
            None,
            "A fully-qualified name to a log observer factory to use for the "
            "initial log observer. Takes precedence over --logfile and --syslog "
            "(when available).",
        ],
    ]

    # The options of a run, which a command sent to the Virtualbricks that
    # runs has no use for.
    RUN_OPTIONS = (
        "no-gui",
        "noterm",
        "run",
        "lock",
        "logfile",
        "logger",
    )

    def __init__(self) -> None:
        usage.Options.__init__(self)
        self["verbosity"] = 0
        self["words"] = []
        # the sockets of --listen, a wire.Socket each; the flag is never set
        del self["listen"]
        self["sockets"] = []
        # the socket of --connect, a wire.Socket; the flag says it's given
        self["target"] = None
        # --connect without --command or --run: the windows of the target
        self["windows"] = False
        # the descriptions of --listen and of --connect, None for the option
        # alone, read once the options are known to go together
        self.descriptions: list[str | None] = []
        self.targets: list[str | None] = []
        # the options given whose value doesn't tell
        self.given: set[str] = set()

    def parseOptions(self, options: Iterable[str] | None = None) -> None:
        if options is None:
            options = sys.argv[1:]
        usage.Options.parseOptions(self, self.take_sockets(options))

    def parseArgs(self, *words: str) -> None:
        # the options end at the first word: the command's own come after
        self["words"] = list(words)

    def take_sockets(self, args: Iterable[str]) -> list[str]:
        """
        Read each --listen and --connect of args, and return the other
        arguments.

        getopt has no optional arguments: --listen and --connect take the
        next word when it starts with a type, as unix:, or the description
        after =. It stops where getopt does, at the first word or at --.
        """

        args = list(args)
        rest = []
        while args:
            arg = args.pop(0)
            if arg == "--" or arg == "-" or not arg.startswith("-"):
                rest.append(arg)
                rest.extend(args)
                break
            name, equals, description = arg.partition("=")
            option = self._long_option(name)
            if option in ("listen", "connect"):
                found = (
                    self.descriptions if option == "listen" else self.targets
                )
                if equals:
                    found.append(description)
                elif args and DESCRIPTION.match(args[0]):
                    found.append(args.pop(0))
                elif args and args[0].startswith(("/", "~", ".")):
                    raise usage.UsageError(
                        f"--{option}: {args[0]} needs its type:"
                        f" unix:{args[0]}"
                    )
                else:
                    found.append(None)
                continue
            rest.append(arg)
            if args and self._takes_value(arg):
                rest.append(args.pop(0))
        return rest

    def _long_option(self, name: str) -> str | None:
        """The long option that name is, as getopt reads it, or None."""

        if not name.startswith("--"):
            return None
        name = name[2:]
        options = [option.rstrip("=") for option in self.longOpt]
        if name in options:
            return name
        # getopt takes a prefix of one option only
        found = [option for option in options if option.startswith(name)]
        return found[0] if len(found) == 1 else None

    def _takes_value(self, arg: str) -> bool:
        """Whether the option arg takes the next word as its value."""

        if arg.startswith("--"):
            option = self._long_option(arg)
            return "=" not in arg and f"{option}=" in self.longOpt
        # -vl FILE: the first short option that takes a value takes the
        # rest of the word, or the next word
        for position, char in enumerate(arg[1:], start=1):
            index = self.shortOpt.find(char)
            if index < 0 or char == ":":
                continue
            if self.shortOpt[index + 1 : index + 2] == ":":
                return position == len(arg) - 1
        return False

    def socket(self, description: str | None, option: str) -> wire.Socket:
        """
        The socket of description, or the default one if None: one to
        listen on for --listen, the one to talk to for --connect. A
        description that names no protocol speaks AMP.
        """

        client = option == "connect"
        if description is None:
            # .control of the workspace, known once the settings are read
            socket = wire.Socket(None)
            if client or wire.Socket(None) not in self["sockets"]:
                return socket
            raise usage.UsageError("--listen alone is given twice")
        else:
            try:
                socket = wire.parse_socket(description, client)
            except ValueError as exc:
                raise usage.UsageError(f"--{option}: {exc}") from None
        if socket.kind == "unix":
            return self._unix_socket(socket, option)
        return self._network_socket(socket, client)

    def _unix_socket(self, socket: wire.Socket, option: str) -> wire.Socket:
        assert socket.path is not None, "a unix socket described has a path"
        path = os.path.abspath(os.path.expanduser(socket.path))
        folder = os.path.dirname(path)
        # Virtualbricks makes the runtime folder at start
        if not os.path.isdir(folder) and not wire.in_runtime_dir(path):
            raise usage.UsageError(f"--{option}: {folder} doesn't exist")
        if os.path.isdir(path):
            raise usage.UsageError(f"--{option}: {path} is a folder")
        if len(os.fsencode(path)) > locations.SOCKET_PATH_MAX:
            raise usage.UsageError(
                f"--{option}: {path} is longer than"
                f" {locations.SOCKET_PATH_MAX} bytes, the most a socket's"
                " path can have"
            )
        if any(other.path == path for other in self["sockets"]):
            raise usage.UsageError(f"--listen: {path} is given twice")
        return socket._replace(path=path)

    def _network_socket(
        self, socket: wire.Socket, client: bool
    ) -> wire.Socket:
        # the files of the description, as absolute paths
        files: dict[str, Any] = {
            wire.FILES[key]: os.path.abspath(os.path.expanduser(path))
            for key, path in socket.files().items()
        }
        socket = socket._replace(**files)
        if client:
            # the client reads its files, and says what is wrong with them
            return socket
        address = (socket.host, socket.port)
        if any(
            other.kind != "unix" and (other.host, other.port) == address
            for other in self["sockets"]
        ):
            raise usage.UsageError(
                f"--listen: {socket.where()} is given twice"
            )
        if socket.kind == "ssl":
            try:
                self._tls().server_options(socket)
            except wire.Unusable as exc:
                raise usage.UsageError(f"--listen: {exc}") from None
        if socket.uses_token():
            self._check_token(socket.token_file)
        return socket

    def _tls(self) -> ModuleType:
        """The module of the ssl sockets, which needs pyOpenSSL."""

        try:
            return importlib.import_module("virtualbricks.console.tls")
        except ImportError:
            raise usage.UsageError(
                "--listen: ssl needs pyOpenSSL: the package python3-openssl"
            ) from None

    def _check_token(self, path: str | None) -> None:
        """
        Refuse a token file that can't be used; one that isn't there is made
        when the socket opens, in the config folder or in its own.
        """

        if path is None:
            path = locations.token_file()
        elif not os.path.isdir(os.path.dirname(path)):
            raise usage.UsageError(
                f"--listen: {os.path.dirname(path)} doesn't exist"
            )
        try:
            wire.read_token(path)
        except wire.NoToken:
            pass
        except wire.Unusable as exc:
            raise usage.UsageError(f"--listen: {exc}") from None

    def opt_logfile(self, arg: str) -> None:
        """Write log messages to file."""

        self.given.add("logfile")
        self["logger"] = _file_logger(arg)

    def opt_workspace(self, arg: str) -> None:
        """
        The folder of the projects for this run, instead of the setting;
        with --command or --connect, the Virtualbricks that runs there.
        """

        # a folder that isn't there is made, as the workspace of the setting
        if not arg:
            raise usage.UsageError("--workspace needs a folder")
        path = os.path.abspath(os.path.expanduser(arg))
        if os.path.exists(path) and not os.path.isdir(path):
            raise usage.UsageError(f"--workspace: {path} is not a folder")
        self["workspace"] = path

    def opt_run(self, arg: str) -> None:
        # the help is the text of optParameters
        path = os.path.abspath(os.path.expanduser(arg))
        if not os.path.isfile(path):
            raise usage.UsageError(f"--run: {path} is not a file")
        self["run"] = path

    def opt_lock(self, arg: str) -> None:
        # the help is the text of optParameters
        if arg not in locks.POLICIES:
            choices = ", ".join(locks.POLICIES)
            raise usage.UsageError(f"--lock: {arg!r} is not one of {choices}")
        self.given.add("lock")
        self["lock"] = arg

    def opt_verbose(self) -> None:
        """Increase log verbosity."""
        self["verbosity"] += 1

    def opt_quiet(self) -> None:
        """Decrease log verbosity."""
        self["verbosity"] -= 1

    def opt_debug(self) -> None:
        """Verbose debug output"""
        self["verbosity"] = 2

    def opt_version(self) -> None:
        """Print version and exit."""
        from virtualbricks import __version__

        print("Virtualbricks", __version__)
        sys.exit(0)

    def check_client(self) -> None:
        """
        Refuse words without --command, --connect without --command or
        --run, and with either the options of a run and --listen.
        """

        words = self["words"]
        if not self["command"]:
            if words:
                raise usage.UsageError(
                    f"unexpected words: {' '.join(words)}. To send them to"
                    " the Virtualbricks that runs: virtualbricks --command"
                    f" {shlex.join(words)}"
                )
            if not self.targets:
                return
            if not self["run"]:
                self.check_windows()
                return
        client = "--command" if self["command"] else "--connect"
        for name in self.RUN_OPTIONS:
            # --connect sends the commands of --run
            if name == "run" and not self["command"]:
                continue
            if name in self.given or (
                name not in ("lock", "logfile") and self[name]
            ):
                raise usage.UsageError(
                    f"{client} takes no --{name}: it talks to a Virtualbricks"
                    " that runs"
                )
        if self.descriptions:
            raise usage.UsageError(
                f"{client} takes no --listen: --connect names the"
                " Virtualbricks to talk to"
            )
        self.check_target()
        if (
            self["command"]
            and not words
            and sys.stdin is not None
            and sys.stdin.isatty()
        ):
            raise usage.UsageError(
                "--command needs a command, as virtualbricks --command brick"
                " list, or lines on its standard input"
            )

    def check_target(self) -> None:
        """Refuse two --connect, or one with a description and --workspace."""

        if len(self.targets) > 1:
            raise usage.UsageError("--connect names one Virtualbricks")
        if self["workspace"] and any(self.targets):
            raise usage.UsageError(
                "--connect and --workspace each name a Virtualbricks: give"
                " one of them"
            )

    def check_windows(self) -> None:
        """
        Refuse, with the windows of another Virtualbricks, what is for the
        Virtualbricks that runs the bricks; --workspace names the one whose
        windows --connect alone opens.
        """

        self.check_target()
        given = [
            name
            for name in ("no-gui", "lock")
            if name in self.given or (name != "lock" and self[name])
        ]
        if self.descriptions:
            given.append("listen")
        if given:
            raise usage.UsageError(
                "--connect opens the windows of another Virtualbricks:"
                f" --{given[0]} is for the one that runs the bricks"
            )

    def postOptions(self) -> None:
        self.check_client()
        # the windows of another Virtualbricks, which speak AMP
        windows = bool(self.targets) and not self["command"]
        windows = windows and not self["run"]
        if self["workspace"] and "lock" not in self.given:
            # one Virtualbricks for each workspace, side by side
            self["lock"] = locks.WORKSPACE
        for description in self.descriptions:
            self["sockets"].append(self.socket(description, "listen"))
        for description in self.targets:
            self["target"] = self.socket(description, "connect")
        if windows and self["target"].protocol != wire.AMP:
            raise usage.UsageError(
                "--connect opens the windows, which speak AMP:"
                " protocol=text is for --command"
            )
        self["connect"] = bool(self.targets)
        self["windows"] = windows
        if windows:
            # their terminal reads no console
            self["noterm"] = True
        if self["logger"]:
            try:
                self["logger"] = reflect.namedAny(self["logger"])
            except Exception as err:
                raise usage.UsageError(
                    "Logger '%s' could not be imported: %s"
                    % (self["logger"], err)
                )

    opt_v = opt_verbose
    opt_q = opt_quiet
    opt_b = opt_debug


def parse_options(config: Options) -> None:
    """Read the command line into config, or exit with the error."""

    try:
        config.parseOptions()
    except usage.error as ue:
        raise SystemExit("%s: %s" % (sys.argv[0], ue))


class Runnable(Protocol):
    """What runs on the reactor, until its Deferred fires."""

    def run(self, reactor: PosixReactorBase) -> defer.Deferred[Any]: ...


def run_app(
    Application: Callable[[Options], Runnable], config: Options
) -> None:
    """Run Application with config, whose options are read already."""

    task.react(Application(config).run, ())


class _LockedApplication:

    factory: Callable[[Options], Application] | None = None

    def __init__(self, config: Options) -> None:
        self.config = config

    def run(self, reactor: PosixReactorBase) -> defer.Deferred[Any]:
        assert self.factory is not None, "factory attribute is not set"
        from virtualbricks.migrate import settings_to_convert
        from virtualbricks.migrate import startup_workspace

        policy = self.config.get("lock", locks.SYSTEM)
        # the settings of 2.1 are the user's: converted by one alone
        user_alone = policy == locks.WORKSPACE and bool(settings_to_convert())
        workspace = os.path.abspath(
            startup_workspace(self.config.get("workspace"))
        )
        try:
            lock = self.lock(policy, user_alone, workspace)
        except locks.Held as held:
            return defer.fail(SystemExit(str(held)))
        except OSError as error:
            msg = (
                f"Cannot take the lock {error.filename}: {error.strerror}. "
                "With --lock none, Virtualbricks runs without locks."
            )
            return defer.fail(SystemExit(msg))
        reactor.addSystemEventTrigger("after", "shutdown", lock.unlock)
        app = self.factory(self.config)
        if user_alone:
            migrate = app.migrate
            # this run's app migrates, then shares the lock
            app.migrate = lambda: self.migrate_then_share(  # type: ignore[method-assign]
                migrate, lock
            )
        return app.run(reactor)

    def lock(
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

    def migrate_then_share(
        self,
        migrate: Callable[[], defer.Deferred[Any] | None],
        lock: locks.Lock,
    ) -> defer.Deferred[Any]:
        """Migrate, then share the user lock with the other workspaces."""

        def share(result: T) -> T:
            try:
                lock.share_user()
            except locks.Held as held:
                raise SystemExit(str(held)) from None
            return result

        return defer.maybeDeferred(migrate).addCallback(share)


def LockedApplication(
    factory: Callable[[Options], Application],
) -> Callable[[Options], _LockedApplication]:
    def init(config: Options) -> _LockedApplication:
        app = _LockedApplication(config)
        app.factory = factory
        return app

    return init


def make_application(config: Options) -> gui.Application:
    from virtualbricks.gui import gui

    return gui.Application(config)


def make_remote_application(config: Options) -> gui.RemoteApplication:
    """The windows of another Virtualbricks: no lock, no project here."""

    from virtualbricks.gui import gui

    return gui.RemoteApplication(config)


def make_plain_application(config: Options) -> Application:
    """The application without the windows: no GTK is loaded."""

    from virtualbricks import brickfactory

    return brickfactory.Application(config)


def install_gtk_reactor() -> None:
    import gi

    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")
    from twisted.internet import gireactor

    gireactor.install()


def main() -> None:
    """The virtualbricks command: with the windows, or without."""

    config = Options()
    parse_options(config)
    if config["windows"]:
        install_gtk_reactor()
        run_app(make_remote_application, config)
        return
    if config["command"] or config["connect"]:
        # no lock, no reactor, no GTK: the Virtualbricks that runs has them
        from virtualbricks import i18n
        from virtualbricks.console import client

        i18n.install()
        # --connect alone sends the commands of --run
        script = None if config["command"] else config["run"]
        sys.exit(
            client.main(
                config["words"],
                config["target"],
                script=script,
                workspace=config["workspace"],
            )
        )
    factory: Callable[[Options], Application]
    if config["no-gui"]:
        factory = make_plain_application
    else:
        install_gtk_reactor()
        factory = make_application
    run_app(LockedApplication(factory), config)
