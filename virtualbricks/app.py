# Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
# Copyright (C) 2018 Virtualbricks team

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

from __future__ import print_function

__metaclass__ = type

import sys

from twisted.python import usage, lockfile, reflect
from twisted.internet import defer

from virtualbricks import _backport, settings


_log_file = sys.stdout


def file_logger():
    from virtualbricks import log

    return log.FileLogObserver(_log_file)


def _file_logger(filename):
    if filename != "-":
        from twisted.python import logfile
        global _log_file
        _log_file = logfile.LogFile.fromFullPath(filename)
    return "virtualbricks.app.file_logger"


class Options(usage.Options):

    longdesc = """Virtualbricks - a vde/qemu gui written in python and
    GTK/Glade.

    Copyright (C) 2018 Virtualbricks team"""

    optFlags = [
        ["noterm", None, "Do not show the terminal."],
        ["daemon", None, ""]
    ]
    optParameters = [
        ["logfile", "l", None, "Write log messages to file."],
        ["logger", None, None,
         "A fully-qualified name to a log observer factory to use for the "
         "initial log observer. Takes precedence over --logfile and --syslog "
         "(when available)."],
    ]

    def __init__(self):
        usage.Options.__init__(self)
        self["verbosity"] = 0

    def opt_logfile(self, arg):
        """Write log messages to file."""

        self["logger"] = _file_logger(arg)

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
        print("Virtualbrics", __version__)
        sys.exit(0)

    def postOptions(self):
        if self["logger"]:
            try:
                self["logger"] = reflect.namedAny(self["logger"])
            except Exception as err:
                raise usage.UsageError("Logger '%s' could not be imported: %s"
                                       % (self['logger'], err))

    opt_v = opt_verbose
    opt_q = opt_quiet
    opt_b = opt_debug


def run_app(Application, config):
    try:
        config.parseOptions()
    except usage.error, ue:
        raise SystemExit("%s: %s" % (sys.argv[0], ue))
    _backport.react(Application(config).run, ())


class _LockedApplication:

    factory = None

    def __init__(self, config, lock=None):
        self.config = config
        self.lock = lock or lockfile.FilesystemLock(settings.LOCK_FILE)

    def run(self, reactor):
        assert self.factory is not None, \
                "factory attribute is not set"
        if self.lock.lock():
            reactor.addSystemEventTrigger("after", "shutdown",
                                          self.lock.unlock)
            app = self.factory(self.config)
            return app.run(reactor)
        else:
            msg = ("Another Virtualbricks instance is running and you cannot "
                   "run more than one instance of it. If this is an "
                   "error, please delete %s to start Virtualbricks" %
                   self.lock.name)
            return defer.fail(SystemExit(msg))


def LockedApplication(factory):
    def init(config):
        app = _LockedApplication(config)
        app.factory = factory
        return app

    return init
