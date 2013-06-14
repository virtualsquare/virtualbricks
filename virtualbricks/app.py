# Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
# Copyright (C) 2013 Virtualbricks team

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

import sys

from twisted.python import usage

from virtualbricks import _backport


class Options(usage.Options):

    optFlags = [
        ["noterm", None, "Do not show the terminal."],
        ["daemon", None, ""]
    ]
    optParameters = [
        ["logfile", "l", None, "Write log messages to file."]
    ]

    def __init__(self):
        usage.Options.__init__(self)
        self["verbosity"] = 0

    def opt_verbose(self):
        """Increase log verbosity."""
        self["vebosity"] += 1

    def opt_quiet(self):
        """Decrease log verbosity."""
        self["vebosity"] -= 1

    def opt_debug(self):
        """Verbose debug output"""
        self["verbosity"] = 2

    def opt_version(self):
        """Print version and exit."""
        from virtualbricks import version
        print("Virtualbrics", version.short())
        sys.exit(0)

    opt_v = opt_verbose
    opt_q = opt_quiet
    opt_b = opt_debug


def run_app(Application, config):
    try:
        config.parseOptions()
    except usage.error, ue:
        raise SystemExit("%s: %s" % (sys.argv[0], ue))
    _backport.react(Application(config).run, ())
