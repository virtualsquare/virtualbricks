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

import os
import shlex
import sys

from twisted.python import usage, reflect
from twisted.internet import defer, task
from twisted.logger import textFileLogObserver

from virtualbricks import locations, locks

_log_file = sys.stdout


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
            "socket",
            None,
            None,
            "The path of the control socket, instead of .control in the "
            "runtime folder.",
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
        # the options given whose value doesn't tell
        self.given = set()

    def parseArgs(self, *words):
        # the options end at the first word: the command's own come after
        self["words"] = list(words)

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

    def opt_socket(self, arg):
        # the help is the text of optParameters
        if not arg:
            raise usage.UsageError("--socket needs a path")
        path = os.path.abspath(os.path.expanduser(arg))
        folder = os.path.dirname(path)
        if not os.path.isdir(folder):
            raise usage.UsageError(f"--socket: {folder} doesn't exist")
        if os.path.isdir(path):
            raise usage.UsageError(f"--socket: {path} is a folder")
        if len(os.fsencode(path)) > locations.SOCKET_PATH_MAX:
            raise usage.UsageError(
                f"--socket: {path} is longer than"
                f" {locations.SOCKET_PATH_MAX} bytes, the most a socket's"
                " path can have"
            )
        self["socket"] = path

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
        if not words and sys.stdin is not None and sys.stdin.isatty():
            raise usage.UsageError(
                "--command needs a command, as virtualbricks --command brick"
                " list, or lines on its standard input"
            )

    def postOptions(self):
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
