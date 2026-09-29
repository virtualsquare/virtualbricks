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

import importlib
import os
import re
import shlex
import sys

from twisted.python import usage, reflect
from twisted.internet import defer, task
from twisted.logger import textFileLogObserver

from virtualbricks import locations, locks
from virtualbricks.console import wire

_log_file = sys.stdout
# The word after --socket is its description when it starts with a type.
DESCRIPTION = re.compile(r"[a-z][a-z0-9]*:", re.IGNORECASE)


def file_logger():
    return textFileLogObserver(_log_file)


def _file_logger(filename):
    if filename != "-":
        from twisted.python import logfile

        global _log_file
        _log_file = logfile.LogFile.fromFullPath(filename)
    return "virtualbricks.app.file_logger"


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
            "that runs, and print its answer; without words, the lines of "
            "the standard input.",
        ],
        # read before getopt, which has no optional arguments
        [
            "socket",
            None,
            "Listen on a control socket: .control in the runtime folder, or "
            "the one of the description after it, as "
            "unix:PATH:protocol=amp, tcp:PORT or ssl:PORT:privateKey=FILE. "
            "Give it again for more sockets. With --command, the socket to "
            "talk to, as tcp:HOST:PORT.",
        ],
    ]
    optParameters = [
        ["logfile", "l", None, "Write log messages to file."],
        [
            "run",
            None,
            None,
            "Run the commands of a file once the project is open.",
        ],
        [
            "workspace",
            None,
            None,
            "The folder of the projects for this run, instead of the setting.",
        ],
        [
            "lock",
            None,
            locks.SYSTEM,
            "The single-instance mode: system, one Virtualbricks on the "
            "machine; user, one for each user; none, no limit.",
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
        "workspace",
        "lock",
        "logfile",
        "logger",
    )

    def __init__(self):
        usage.Options.__init__(self)
        self["verbosity"] = 0
        self["words"] = []
        # the sockets of --socket, a wire.Socket each; the flag is never set
        del self["socket"]
        self["sockets"] = []
        # the descriptions of --socket, None for --socket alone, read once
        # it is known whether --command talks to them
        self.descriptions = []
        # the options given whose value doesn't tell
        self.given = set()

    def parseOptions(self, options=None):
        if options is None:
            options = sys.argv[1:]
        usage.Options.parseOptions(self, self.take_sockets(options))

    def parseArgs(self, *words):
        # the options end at the first word: the command's own come after
        self["words"] = list(words)

    def take_sockets(self, args):
        """
        Read each --socket of args, and return the other arguments.

        getopt has no optional arguments: --socket takes the next word when
        it starts with a type, as unix:, or the description after =. It
        stops where getopt does, at the first word or at --.
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
            if self._long_option(name) == "socket":
                if equals:
                    self.descriptions.append(description)
                elif args and DESCRIPTION.match(args[0]):
                    self.descriptions.append(args.pop(0))
                elif args and args[0].startswith(("/", "~", ".")):
                    raise usage.UsageError(
                        f"--socket: {args[0]} needs its type:"
                        f" unix:{args[0]}"
                    )
                else:
                    self.descriptions.append(None)
                continue
            rest.append(arg)
            if args and self._takes_value(arg):
                rest.append(args.pop(0))
        return rest

    def _long_option(self, name):
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

    def _takes_value(self, arg):
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

    def add_socket(self, description, client=False):
        """
        Listen on the socket of description, or on the default one; with
        client, talk to it with --command.
        """

        if description is None:
            socket = wire.Socket(locations.control_socket())
        else:
            try:
                socket = wire.parse_socket(description, client)
            except ValueError as exc:
                raise usage.UsageError(f"--socket: {exc}") from None
        if socket.kind == "unix":
            socket = self._unix_socket(socket)
        else:
            socket = self._network_socket(socket, client)
        self["sockets"].append(socket)

    def _unix_socket(self, socket):
        path = os.path.abspath(os.path.expanduser(socket.path))
        folder = os.path.dirname(path)
        # Virtualbricks makes the runtime folder at start
        if not os.path.isdir(folder) and not wire.in_runtime_dir(path):
            raise usage.UsageError(f"--socket: {folder} doesn't exist")
        if os.path.isdir(path):
            raise usage.UsageError(f"--socket: {path} is a folder")
        if len(os.fsencode(path)) > locations.SOCKET_PATH_MAX:
            raise usage.UsageError(
                f"--socket: {path} is longer than"
                f" {locations.SOCKET_PATH_MAX} bytes, the most a socket's"
                " path can have"
            )
        if any(other.path == path for other in self["sockets"]):
            raise usage.UsageError(f"--socket: {path} is given twice")
        return socket._replace(path=path)

    def _network_socket(self, socket, client):
        socket = socket._replace(
            **{
                wire.FILES[key]: os.path.abspath(os.path.expanduser(path))
                for key, path in socket.files().items()
            }
        )
        if client:
            # --command reads its files, and says what is wrong with them
            return socket
        address = (socket.host, socket.port)
        if any(
            other.kind != "unix" and (other.host, other.port) == address
            for other in self["sockets"]
        ):
            raise usage.UsageError(
                f"--socket: {socket.where()} is given twice"
            )
        if socket.kind == "ssl":
            try:
                self._tls().server_options(socket)
            except wire.Unusable as exc:
                raise usage.UsageError(f"--socket: {exc}") from None
        if socket.uses_token():
            self._check_token(socket.token_file)
        return socket

    def _tls(self):
        """The module of the ssl sockets, which needs pyOpenSSL."""

        try:
            return importlib.import_module("virtualbricks.console.tls")
        except ImportError:
            raise usage.UsageError(
                "--socket: ssl needs pyOpenSSL: the package python3-openssl"
            ) from None

    def _check_token(self, path):
        """
        Refuse a token file that can't be used; one that isn't there is made
        when the socket opens, in the config folder or in its own.
        """

        if path is None:
            path = locations.token_file()
        elif not os.path.isdir(os.path.dirname(path)):
            raise usage.UsageError(
                f"--socket: {os.path.dirname(path)} doesn't exist"
            )
        try:
            wire.read_token(path)
        except wire.NoToken:
            pass
        except wire.Unusable as exc:
            raise usage.UsageError(f"--socket: {exc}") from None

    def opt_logfile(self, arg):
        """Write log messages to file."""

        self.given.add("logfile")
        self["logger"] = _file_logger(arg)

    def opt_workspace(self, arg):
        """The folder of the projects for this run, instead of the setting."""

        # a folder that isn't there is made, as the workspace of the setting
        if not arg:
            raise usage.UsageError("--workspace needs a folder")
        path = os.path.abspath(os.path.expanduser(arg))
        if os.path.exists(path) and not os.path.isdir(path):
            raise usage.UsageError(f"--workspace: {path} is not a folder")
        self["workspace"] = path

    def opt_run(self, arg):
        # the help is the text of optParameters
        path = os.path.abspath(os.path.expanduser(arg))
        if not os.path.isfile(path):
            raise usage.UsageError(f"--run: {path} is not a file")
        self["run"] = path

    def opt_lock(self, arg):
        # the help is the text of optParameters
        if arg not in locks.POLICIES:
            choices = ", ".join(locks.POLICIES)
            raise usage.UsageError(f"--lock: {arg!r} is not one of {choices}")
        self.given.add("lock")
        self["lock"] = arg

    def opt_verbose(self):
        """Increase log verbosity."""
        self["verbosity"] += 1

    def opt_quiet(self):
        """Decrease log verbosity."""
        self["verbosity"] -= 1

    def opt_debug(self):
        """Verbose debug output"""
        self["verbosity"] = 2

    def opt_version(self):
        """Print version and exit."""
        from virtualbricks import __version__

        print("Virtualbricks", __version__)
        sys.exit(0)

    def check_command(self):
        """Refuse words without --command, and the options of a run with it."""

        words = self["words"]
        if not self["command"]:
            if words:
                raise usage.UsageError(
                    f"unexpected words: {' '.join(words)}. To send them to"
                    " the Virtualbricks that runs: virtualbricks --command"
                    f" {shlex.join(words)}"
                )
            return
        for name in self.RUN_OPTIONS:
            if name in self.given or (
                name not in ("lock", "logfile") and self[name]
            ):
                raise usage.UsageError(
                    f"--command takes no --{name}: it talks to a Virtualbricks"
                    " that runs"
                )
        sockets = self["sockets"]
        if len(sockets) > 1:
            raise usage.UsageError("--command talks to one --socket")
        if sockets and sockets[0].protocol != wire.TEXT:
            raise usage.UsageError(
                "--command speaks the text protocol, not"
                f" {sockets[0].protocol}"
            )
        if not words and sys.stdin is not None and sys.stdin.isatty():
            raise usage.UsageError(
                "--command needs a command, as virtualbricks --command brick"
                " list, or lines on its standard input"
            )

    def postOptions(self):
        for description in self.descriptions:
            self.add_socket(description, client=self["command"])
        self.check_command()
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


def parse_options(config):
    """Read the command line into config, or exit with the error."""

    try:
        config.parseOptions()
    except usage.error as ue:
        raise SystemExit("%s: %s" % (sys.argv[0], ue))


def run_app(Application, config):
    """Run Application with config, whose options are read already."""

    task.react(Application(config).run, ())


class _LockedApplication:

    factory = None

    def __init__(self, config):
        self.config = config

    def run(self, reactor):
        assert self.factory is not None, "factory attribute is not set"
        try:
            lock = locks.acquire(self.config.get("lock", locks.SYSTEM))
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
        return app.run(reactor)


def LockedApplication(factory):
    def init(config):
        app = _LockedApplication(config)
        app.factory = factory
        return app

    return init
