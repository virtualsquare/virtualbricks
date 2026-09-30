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
import shutil
import socket
import tempfile

from twisted.internet import defer
from twisted.trial import unittest

from virtualbricks import locks

# The tests of the configuration are virtualbricks.tests.config: here that
# name is theirs, so the settings are taken by name and from their module.
from virtualbricks.config.settings import AppSettings
from virtualbricks.config import settings
from virtualbricks.config.settings import AppState

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
    # Never the locks of a running Virtualbricks: the user lock is in the
    # runtime directory. The check runs after every other cleanup of the
    # test, when the locks must be free again, and before they are restored.
    from virtualbricks import locations

    test.patch(locations, "SYSTEM_LOCK_FILE", os.path.join(root, "vb.lock"))
    test.addCleanup(_check_released, test)
    return root


def short_folder(test):
    """A folder of the test with a path short enough for sockets."""

    # the folders of trial are too deep for the 107 bytes of a socket
    folder = tempfile.mkdtemp(prefix="vb-")
    test.addCleanup(shutil.rmtree, folder)
    return folder


def make_socket(path):
    """A socket file at path that nobody listens on, as after a crash."""

    sock = socket.socket(socket.AF_UNIX)
    sock.bind(path)
    sock.close()


def _check_released(test):
    if not lock_is_free():
        test.fail("the test left the lock held")


class FakeTrash:
    """A desktop trash that only remembers what was moved to it."""

    def __init__(self, can_trash=True, error=None):
        self.allowed = can_trash
        self.error = error
        self.trashed = []
        self.asked = []

    def can_trash(self, path):
        self.asked.append(path)
        return self.allowed

    def trash(self, path):
        if self.error is not None:
            raise self.error
        self.trashed.append(path)


def use_workspace(test, path=None):
    """
    Point the workspace at path, the workspace setting if None; nothing open.

    Return the workspace, ``projects``, which the modules share.
    """

    from virtualbricks.config.workspace import projects

    test.patch(projects, "_path", path)
    test.patch(projects, "current", None)
    test.patch(projects, "trasher", None)
    test.patch(projects, "_summaries", {})
    return projects


def release(lock):
    """Unlock a lock if it is held; for cleanups."""

    if lock is not None and lock.locked:
        lock.unlock()


def hold_lock(test, policy=locks.SYSTEM, user=None, workspace=None):
    """
    Hold the locks of policy, as a running Virtualbricks does, and that of
    workspace, a folder, if given.

    With user, the name of another user, the locks of a Virtualbricks of
    theirs: another runtime directory. They are released when the test ends,
    even if the test fails.
    """

    runtime = os.environ.get("XDG_RUNTIME_DIR", "")
    if user is not None:
        os.environ["XDG_RUNTIME_DIR"] = f"{runtime}-{user}"
    lock = None
    try:
        lock = locks.acquire(policy)
        if workspace is not None:
            lock.take_workspace(workspace)
    except locks.Held:
        release(lock)
        test.fail(f"the lock is already held ({policy}, {user}, {workspace})")
    except BaseException:
        release(lock)
        raise
    finally:
        if user is not None:
            os.environ["XDG_RUNTIME_DIR"] = runtime
    test.addCleanup(release, lock)
    return lock


def lock_is_free():
    """Whether the lock of the application can be taken; it is left free."""

    try:
        locks.acquire(locks.SYSTEM).unlock()
    except locks.Held:
        return False
    return True


def reset_settings(test, **values):
    """Give the test its own settings, restored when it ends."""

    test.patch(settings, "_app", AppSettings(**values))
    test.patch(settings, "_project", None)
    test.patch(settings, "_state", AppState())
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
        # failure takes the failure too, as Logger.failure(format, failure)
        def emit(format, failure=None, **kwargs):
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
        # the bricks are those of an open project, with its settings
        settings.use_project(settings.ProjectSettings())
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
        settings.set_setting("qemu_path", self.bin)
        settings.set_setting("vde_path", self.bin)
