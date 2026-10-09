# -*- test-case-name: virtualbricks.tests.test_cli_new -*-
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
and ``--connect``, and :mod:`virtualbricks.locks` for the policies of
``--lock``, which ``--command`` loads anyway; no Twisted. It opens no file
and makes none. What needs
more is left to the mode that runs: the folder and the length of a socket's
path, a socket given twice, the ssl keys and the token, opening the file of
``--logfile`` and importing the factory of ``--logger``.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import TYPE_CHECKING, NamedTuple

from virtualbricks import __version__, locks, sockets

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Callable, Sequence
    from typing import IO, NoReturn

# The modes: the windows, without them, the windows of another
# Virtualbricks, and a command sent to one that runs.
GUI = "gui"
NO_GUI = "no-gui"
REMOTE = "remote"
COMMAND = "command"
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


class CommandLine(NamedTuple):
    """What the command line asks for."""

    mode: str
    # the words of the command of --command, without the options before
    words: tuple[str, ...] = ()
    # the sockets of --listen, DEFAULT_SOCKET for --listen alone
    listen: tuple[sockets.Socket, ...] = ()
    # the socket of --connect, DEFAULT_SOCKET alone, None without it
    target: sockets.Socket | None = None
    # absolute paths
    run: str | None = None
    workspace: str | None = None
    lock: str = locks.SYSTEM
    # as given: "-" is the standard output
    logfile: str | None = None
    # the fully-qualified name of a log observer factory
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
        help="A fully-qualified name to a log observer factory to use for"
        " the initial log observer. Takes precedence over --logfile.",
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
) -> CommandLine:
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
    if words[:1] == ["--"]:
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
    if listen.count(DEFAULT_SOCKET) > 1:
        raise UsageError("--listen alone is given twice")
    lock = options.lock
    if lock is None:
        # one Virtualbricks for each workspace, side by side
        lock = locks.WORKSPACE if workspace else locks.SYSTEM
    return CommandLine(
        mode=mode,
        words=tuple(words),
        listen=tuple(listen),
        target=options.target if connect else None,
        run=options.run,
        workspace=workspace,
        lock=lock,
        logfile=options.logfile,
        logger=options.logger,
        verbosity=options.verbosity,
        # the windows of another Virtualbricks read no console
        no_term=options.no_term or mode == REMOTE,
    )


def parse_or_exit(args: Sequence[str] | None = None) -> CommandLine:
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
