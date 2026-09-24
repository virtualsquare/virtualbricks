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

import builtins
import os

from twisted.internet import defer
from twisted.trial import unittest

# The modules use the _ that i18n.install() puts in the builtins.
if not hasattr(builtins, "_"):
    builtins._ = str

from virtualbricks.config import settings  # noqa: E402

DATA = os.path.join(os.path.dirname(__file__), "data")


def isolate(test):
    """Point HOME, the XDG directories and the lock at a temporary directory."""

    root = os.path.abspath(test.mktemp())
    os.makedirs(root)
    env = dict(
        os.environ,
        HOME=root,
        XDG_CONFIG_HOME=os.path.join(root, ".config"),
        XDG_STATE_HOME=os.path.join(root, ".local", "state"),
        XDG_RUNTIME_DIR=os.path.join(root, "run"),
    )
    test.patch(os, "environ", env)
    # never the lock of a running Virtualbricks
    from virtualbricks import app

    test.patch(app, "LOCK_FILE", os.path.join(root, "vb.lock"))
    return root


def reset_settings(test, **values):
    """Give the test its own settings, restored when it ends."""

    test.patch(settings, "_app", settings.AppSettings(**values))
    test.patch(settings, "_project", None)
    test.patch(settings, "_state", settings.AppState())
    test.patch(settings, "_settings_path", None)
    test.patch(settings, "_state_path", None)
    test.patch(settings, "_read_only", False)


def make_factory(test=None):
    from virtualbricks.brickfactory import BrickFactory

    factory = BrickFactory(defer.Deferred())
    if test is not None:
        factory.runtime_dir = os.path.abspath(test.mktemp())
    return factory


class FakeLogger:
    """Collect what a module logs; each call is (level, format, kwargs).

    Debug messages are diagnostics, not behaviour, and are not collected.
    """

    def __init__(self):
        self.events = []

    def _emit(self, level):
        def emit(format, **kwargs):
            self.events.append((level, format, kwargs))

        return emit

    def debug(self, format, **kwargs):
        pass

    def __getattr__(self, name):
        if name in ("info", "warn", "error", "failure", "critical"):
            return self._emit(name)
        raise AttributeError(name)

    def levels(self):
        return [level for level, _, _ in self.events]

    def formatted(self):
        return [format.format(**kwargs) for _, format, kwargs in self.events]


# The programs that the bricks start, for CommandTestCase.
PROGRAMS = (
    "qemu-system-x86_64",
    "qemu-system-i386",
    "vde-netemu",
    "vde_plug2tap",
    "vde_pcapplug",
    "vde_switch",
)


def pairs(args):
    """Return the arguments as a list of (option, value) pairs."""

    return list(zip(args[::2], args[1::2]))


def adjacent(args):
    """Return every two consecutive arguments; some options take no value."""

    return list(zip(args, args[1:]))


class BrickTestCase(unittest.TestCase):
    """A test with its own settings, home directories and brick factory."""

    def setUp(self):
        isolate(self)
        reset_settings(self)
        self.factory = make_factory(self)


class CommandTestCase(BrickTestCase):
    """A brick test where the programs of the bricks are fake executables."""

    def setUp(self):
        super().setUp()
        self.bin = os.path.abspath(self.mktemp())
        os.makedirs(self.bin)
        for name in PROGRAMS:
            path = os.path.join(self.bin, name)
            with open(path, "w") as fp:
                fp.write("#!/bin/sh\n")
            os.chmod(path, 0o755)
        settings.set("qemupath", self.bin)
        settings.set("vdepath", self.bin)
