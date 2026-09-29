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
import sys

from twisted.python import usage, reflect
from twisted.internet import defer, task
from twisted.logger import textFileLogObserver

from virtualbricks import locks

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
        ["noterm", None, "Do not show the terminal."],
        ["daemon", None, ""],
    ]
    optParameters = [
        ["logfile", "l", None, "Write log messages to file."],
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

    def __init__(self):
        usage.Options.__init__(self)
        self["verbosity"] = 0

    def opt_logfile(self, arg):
        """Write log messages to file."""

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

    def opt_lock(self, arg):
        # the help is the text of optParameters
        if arg not in locks.POLICIES:
            choices = ", ".join(locks.POLICIES)
            raise usage.UsageError(f"--lock: {arg!r} is not one of {choices}")
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

    def postOptions(self):
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


def run_app(Application, config):
    try:
        config.parseOptions()
    except usage.error as ue:
        raise SystemExit("%s: %s" % (sys.argv[0], ue))
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
