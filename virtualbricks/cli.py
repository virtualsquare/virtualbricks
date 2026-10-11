# -*- test-case-name: virtualbricks.tests.test_cli -*-
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

"""
The command line of ``virtualbricks``, read with argparse: the options, the
mode they ask for, and the checks that need only them and the names of the
files they give (page 27, section 9).

It imports as little as it can, so that ``--command`` starts fast: the
standard library's ``argparse``, ``os``, ``sys`` and ``typing``,
:mod:`virtualbricks.sockets`, which reads the descriptions of ``--listen``
and ``--connect``, :mod:`virtualbricks.locks` for the policies of
``--lock``, and :mod:`virtualbricks.console.wire` for the checks of the
sockets, which ``--command`` loads anyway; no Twisted.

The sockets are checked as the old parser did: their paths made absolute,
a folder that isn't there, a path too long for a socket, one given twice;
and for those of ``--listen``, the token and the ssl keys, which it reads.
The keys need :mod:`virtualbricks.console.tls`, imported for them only,
which loads pyOpenSSL and Twisted. It makes no file. Opening the file of
``--logfile`` and importing the observer of ``--logger`` are left to the
mode that runs.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import TYPE_CHECKING, Literal, NamedTuple, get_args

from virtualbricks import __version__, locations, locks, sockets
from virtualbricks.console import wire

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Callable, Sequence
    from typing import IO, Any, NoReturn

# The modes: the windows, without them, the windows of another
# Virtualbricks, and a command sent to one that runs.
Mode = Literal["gui", "no-gui", "remote", "command"]
GUI, NO_GUI, REMOTE, COMMAND = get_args(Mode)
# --listen and --connect alone: .control in the runtime folder of the
# workspace, known once the settings are read.
DEFAULT_SOCKET = sockets.Socket(None)
# The default of an option whose absence tells: not on the command line.
UNSET = object()
# The options of a run, which a command sent to the Virtualbricks that runs
# has no use for, in the order they are refused.
RUN_OPTIONS = ("no-gui", "no-term", "run", "lock", "logfile", "logger")

DESCRIPTION_TEXT = """\
Virtualbricks - a vde/qemu gui written in python and GTK/Glade.

Copyright (C) 2026 Virtualbricks team"""


class UsageError(Exception):
    """The command line is wrong; str() says why, to the user."""


class CommandLineOptions(NamedTuple):
    """What the command line asks for."""

    mode: Mode
    # the words of the command of --command, without the options before
    words: tuple[str, ...] = ()
    # the sockets of --listen, DEFAULT_SOCKET for --listen alone
    listen: tuple[sockets.Socket, ...] = ()
    # the socket of --connect, DEFAULT_SOCKET alone, None without it
    target: sockets.Socket | None = None
    # absolute paths
    run: str | None = None
    workspace: str | None = None
    lock: locks.Policy = locks.SYSTEM
    # as given: "-" is the standard output
    logfile: str | None = None
    # the fully-qualified name of a log observer
    logger: str | None = None
    verbosity: int = 0
    no_term: bool = False


class _Parser(argparse.ArgumentParser):
    """A parser whose errors are raised, not printed."""

    def error(self, message: str) -> NoReturn:
        raise UsageError(message)


class _Quieter(argparse.Action):
    """-q: one step less of verbosity, as -v is one more."""

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: object,
        option_string: str | None = None,
    ) -> None:
        namespace.verbosity -= 1


def parser() -> argparse.ArgumentParser:
    """The options of ``virtualbricks``, as virtualbricks(1) describes them."""

    parser = _Parser(
        prog="virtualbricks",
        description=DESCRIPTION_TEXT,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.set_defaults(verbosity=0)
    parser.add_argument(
        "--no-term",
        action="store_true",
        help="Don't read the console in the terminal.",
    )
    parser.add_argument(
        "--no-gui",
        action="store_true",
        help="Run without the windows: the console is the way in.",
    )
    parser.add_argument(
        "--command",
        action="store_true",
        help="Send the command of the words that follow to the Virtualbricks"
        " that runs, the one of --connect or of --workspace, and print its"
        " answer; without words, the lines of the standard input.",
    )
    # given alone, the option is its const
    parser.add_argument(
        "--listen",
        nargs="?",
        action="append",
        const=DEFAULT_SOCKET,
        type=_socket("listen"),
        metavar="DESCRIPTION",
        help="Listen on a control socket: .control in the runtime folder of"
        " the workspace, or the one of the description after it, as"
        " unix:PATH, tcp:PORT or ssl:PORT:privateKey=FILE. It speaks AMP, or"
        " the JSON protocol with protocol=json. Give it again for more"
        " sockets.",
    )
    parser.add_argument(
        "--connect",
        dest="target",
        nargs="?",
        default=UNSET,
        const=DEFAULT_SOCKET,
        type=_socket("connect"),
        metavar="DESCRIPTION",
        help="The Virtualbricks that runs that --command and --run talk to:"
        " the one of .control in the runtime folder of its workspace, or the"
        " one of the socket of the description after it, as tcp:HOST:PORT."
        " Without them, its windows open.",
    )
    parser.add_argument(
        "-l", "--logfile", metavar="FILE", help="Write log messages to file."
    )
    parser.add_argument(
        "--run",
        type=_run,
        metavar="FILE",
        help="Run the commands of a file once the project is open; with"
        " --connect, send them to the Virtualbricks that runs, and exit.",
    )
    parser.add_argument(
        "--workspace",
        type=_workspace,
        metavar="FOLDER",
        help="The folder of the projects for this run, instead of the"
        " setting; with --command or --connect, the Virtualbricks that runs"
        " there.",
    )
    parser.add_argument(
        "--lock",
        choices=locks.POLICIES,
        help="The single-instance mode: system, one Virtualbricks on the"
        " machine; user, one for each user; workspace, one for each"
        " workspace, the default with --workspace; none, no limit."
        " Default: system.",
    )
    parser.add_argument(
        "--logger",
        metavar="NAME",
        help="The fully qualified name of a log observer, instead of"
        " --logfile.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        dest="verbosity",
        action="count",
        help="Increase log verbosity.",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        dest="verbosity",
        nargs=0,
        action=_Quieter,
        help="Decrease log verbosity.",
    )
    parser.add_argument(
        "-b",
        "--debug",
        dest="verbosity",
        action="store_const",
        const=2,
        help="Verbose debug output.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"Virtualbricks {__version__}",
        help="Print version and exit.",
    )
    # the options end at the first word: the command's own come after
    parser.add_argument(
        "words",
        nargs=argparse.REMAINDER,
        metavar="COMMAND",
        help="With --command, the command to send, as brick list.",
    )
    return parser


def parse(
    args: Sequence[str] | None = None, stdin: IO[str] | None = None
) -> CommandLineOptions:
    """
    Read args, sys.argv[1:] if None, and return what they ask for; raise
    UsageError if they are wrong. stdin, sys.stdin if None, tells whether
    --command alone has lines to read.
    """

    if args is None:
        args = sys.argv[1:]
    if stdin is None:
        stdin = sys.stdin
    options = parser().parse_args(args)
    words = list(options.words)
    # as getopt, the first -- ends the options and isn't a word
    if words and words[0] == "--":
        del words[0]
    listen = options.listen or []
    connect = options.target is not UNSET
    workspace = options.workspace
    given = _given(options)
    if not options.command and words:
        raise UsageError(_unexpected(words))
    if options.command or (connect and options.run):
        mode = COMMAND
        _check_client(options, given, listen, words, stdin)
    elif connect:
        mode = REMOTE
        _check_windows(options, given, listen)
    elif options.no_gui:
        mode = NO_GUI
    else:
        mode = GUI
    checked: list[sockets.Socket] = []
    for socket in listen:
        checked.append(_checked_socket(socket, "listen", checked))
    target = options.target if connect else None
    if target is not None:
        target = _checked_socket(target, "connect", [])
    lock = options.lock
    if lock is None:
        # one Virtualbricks for each workspace, side by side
        lock = locks.WORKSPACE if workspace else locks.SYSTEM
    return CommandLineOptions(
        mode=mode,
        words=tuple(words),
        listen=tuple(checked),
        target=target,
        run=options.run,
        workspace=workspace,
        lock=lock,
        logfile=options.logfile,
        logger=options.logger,
        verbosity=options.verbosity,
        # the windows of another Virtualbricks read no console
        no_term=options.no_term or mode == REMOTE,
    )


def parse_or_exit(
    args: Sequence[str] | None = None, stdin: IO[str] | None = None
) -> CommandLineOptions:
    """parse(args), or exit with the error, and the status 1."""

    try:
        return parse(args)
    except UsageError as error:
        raise SystemExit(f"virtualbricks: {error}") from None


def _socket(option: str) -> Callable[[str], sockets.Socket]:
    """The socket of the description after --listen or --connect."""

    def socket(description: str) -> sockets.Socket:
        try:
            return sockets.parse_socket(description, option == "connect")
        except ValueError as exc:
            message = str(exc)
        if option == "connect" and sockets.TYPE.fullmatch(description):
            # argparse takes the next word, which may be the command's
            message += (
                ". For --connect alone before the words of --command, end the"
                f" options with --: --connect -- {description}"
            )
        raise argparse.ArgumentTypeError(message)

    return socket


def _checked_socket(
    socket: sockets.Socket, option: str, others: Sequence[sockets.Socket]
) -> sockets.Socket:
    """
    socket, of --listen or --connect, with its paths absolute; raise
    UsageError if it can't be used. others are the sockets of --listen
    before it.
    """

    if socket == DEFAULT_SOCKET:
        if option == "listen" and socket in others:
            raise UsageError("--listen alone is given twice")
        return socket
    if socket.kind == "unix":
        return _unix_socket(socket, option, others)
    return _network_socket(socket, option == "connect", others)


def _unix_socket(
    socket: sockets.Socket, option: str, others: Sequence[sockets.Socket]
) -> sockets.Socket:
    assert socket.path is not None, "a unix socket described has a path"
    path = os.path.abspath(os.path.expanduser(socket.path))
    folder = os.path.dirname(path)
    if not os.path.isdir(folder):
        # Virtualbricks makes the runtime folder at start
        if not wire.in_runtime_dir(path):
            raise UsageError(f"--{option}: {folder} doesn't exist")
    if os.path.isdir(path):
        raise UsageError(f"--{option}: {path} is a folder")
    if len(os.fsencode(path)) > locations.SOCKET_PATH_MAX:
        raise UsageError(
            f"--{option}: {path} is longer than {locations.SOCKET_PATH_MAX}"
            " bytes, the most a socket's path can have"
        )
    if any(other.path == path for other in others):
        raise UsageError(f"--listen: {path} is given twice")
    return socket._replace(path=path)


def _network_socket(
    socket: sockets.Socket, client: bool, others: Sequence[sockets.Socket]
) -> sockets.Socket:
    # the files of the description, as absolute paths
    files: dict[str, Any] = {
        sockets.FILES[key]: os.path.abspath(os.path.expanduser(path))
        for key, path in socket.files().items()
    }
    socket = socket._replace(**files)
    if client:
        # the client reads its files, and says what is wrong with them
        return socket
    address = (socket.host, socket.port)
    if any(
        other.kind != "unix" and (other.host, other.port) == address
        for other in others
    ):
        raise UsageError(f"--listen: {socket.where()} is given twice")
    if socket.kind == "ssl":
        _check_keys(socket)
    if socket.uses_token():
        _check_token(socket.token_file)
    return socket


def _check_keys(socket: sockets.Socket) -> None:
    """Refuse the files of an ssl socket of --listen that can't be used."""

    from virtualbricks.console import tls

    try:
        tls.server_options(socket)
    except wire.Unusable as exc:
        raise UsageError(f"--listen: {exc}") from None


def _check_token(path: str | None) -> None:
    """
    Refuse a token file that can't be used; one that isn't there is made
    when the socket opens, in the config folder or in its own.
    """

    if path is None:
        path = locations.token_file()
    elif not os.path.isdir(os.path.dirname(path)):
        raise UsageError(f"--listen: {os.path.dirname(path)} doesn't exist")
    try:
        wire.read_token(path)
    except wire.NoToken:
        pass
    except wire.Unusable as exc:
        raise UsageError(f"--listen: {exc}") from None


def _workspace(folder: str) -> str:
    """The absolute path of --workspace; a folder that isn't there is made."""

    if not folder:
        raise argparse.ArgumentTypeError("needs a folder, as ~/labs")
    path = os.path.abspath(os.path.expanduser(folder))
    if os.path.exists(path) and not os.path.isdir(path):
        raise argparse.ArgumentTypeError(f"{path} is not a folder")
    return path


def _run(file: str) -> str:
    """The absolute path of --run, a file."""

    path = os.path.abspath(os.path.expanduser(file))
    if not os.path.isfile(path):
        raise argparse.ArgumentTypeError(f"{path} is not a file")
    return path


def _given(options: argparse.Namespace) -> list[str]:
    """The options of a run that the command line gives, in RUN_OPTIONS."""

    values = {
        "no-gui": options.no_gui,
        "no-term": options.no_term,
        "run": options.run,
        "lock": options.lock,
        "logfile": options.logfile,
        "logger": options.logger,
    }
    return [name for name in RUN_OPTIONS if values[name] not in (None, False)]


def _unexpected(words: list[str]) -> str:
    import shlex

    return (
        f"unexpected words: {' '.join(words)}. To send them to the"
        f" Virtualbricks that runs: virtualbricks --command"
        f" {shlex.join(words)}"
    )


def _check_client(
    options: argparse.Namespace,
    given: list[str],
    listen: list[sockets.Socket],
    words: list[str],
    stdin: IO[str] | None,
) -> None:
    """
    Refuse, with --command or --connect --run, the options of a run and
    --listen; refuse --command without words or lines to read.
    """

    client = "--command" if options.command else "--connect"
    for name in given:
        # --connect sends the commands of --run
        if name == "run" and not options.command:
            continue
        raise UsageError(
            f"{client} takes no --{name}: it talks to a Virtualbricks that"
            " runs"
        )
    if listen:
        raise UsageError(
            f"{client} takes no --listen: --connect names the Virtualbricks"
            " to talk to"
        )
    _check_target(options)
    if options.command and not words and stdin is not None and stdin.isatty():
        raise UsageError(
            "--command needs a command, as virtualbricks --command brick list,"
            " or lines on its standard input"
        )


def _check_windows(
    options: argparse.Namespace,
    given: list[str],
    listen: list[sockets.Socket],
) -> None:
    """
    Refuse, with the windows of another Virtualbricks, what is for the
    Virtualbricks that runs the bricks, and another protocol than AMP.
    """

    _check_target(options)
    refused = [name for name in given if name in ("no-gui", "lock")]
    if listen:
        refused.append("listen")
    if refused:
        raise UsageError(
            "--connect opens the windows of another Virtualbricks:"
            f" --{refused[0]} is for the one that runs the bricks"
        )
    if options.target.protocol != sockets.AMP:
        raise UsageError(
            "--connect opens the windows, which speak AMP: protocol=json is"
            " for --command"
        )


def _check_target(options: argparse.Namespace) -> None:
    """Refuse --connect with a description, and --workspace."""

    if options.workspace and options.target not in (UNSET, DEFAULT_SOCKET):
        raise UsageError(
            "--connect and --workspace each name a Virtualbricks: give one"
            " of them"
        )
