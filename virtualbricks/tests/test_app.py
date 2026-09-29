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


"""The launcher: the lock, the logging, the options."""

import functools
import os
import pwd

from twisted.internet import defer
from twisted.python import usage
from twisted.trial import unittest

from virtualbricks import app, locations, locks
from virtualbricks.tests import (
    hold_lock,
    isolate,
    lock_is_free,
    short_folder,
)


class FakeReactor:

    def __init__(self):
        self.triggers = []

    def addSystemEventTrigger(self, phase, event, callable):
        self.triggers.append((phase, event, callable))

    def shutdown(self):
        for phase, event, callable in self.triggers:
            callable()


class FakeApplication:

    def __init__(self, started, config):
        self.started = started
        self.config = config

    def run(self, reactor):
        self.started.append(self.config["lock"])
        return defer.succeed(None)


class TestLock(unittest.TestCase):

    def setUp(self):
        isolate(self)
        self.reactor = FakeReactor()
        self.started = []

    def parse(self, *args):
        options = app.Options()
        options.parseOptions(list(args))
        return options

    def run_app(self, *args):
        factory = functools.partial(FakeApplication, self.started)
        application = app.LockedApplication(factory)(self.parse(*args))
        return application.run(self.reactor)

    def test_the_policy(self):
        self.assertEqual(self.parse()["lock"], locks.SYSTEM)
        for policy in locks.POLICIES:
            self.assertEqual(self.parse("--lock", policy)["lock"], policy)
        self.assertEqual(self.parse("--lock=user")["lock"], locks.USER)
        error = self.assertRaises(
            usage.UsageError, self.parse, "--lock", "workspace"
        )
        self.assertEqual(
            str(error), "--lock: 'workspace' is not one of system, user, none"
        )

    def test_held_until_shutdown(self):
        self.successResultOf(self.run_app("--lock", "user"))
        self.assertEqual(self.started, [locks.USER])
        self.assertFalse(lock_is_free())
        self.reactor.shutdown()
        self.assertTrue(lock_is_free())

    def test_refused(self):
        hold_lock(self, locks.USER, "bob")
        failure = self.failureResultOf(self.run_app(), SystemExit)
        user = pwd.getpwuid(os.getuid()).pw_name
        self.assertEqual(
            str(failure.value),
            "Virtualbricks is running on this machine with --lock user, one "
            "for each user: start this one with --lock user as well. Held by "
            f"process {os.getpid()} of {user}.",
        )
        self.assertEqual(self.started, [])
        self.successResultOf(self.run_app("--lock", "user"))
        self.assertEqual(self.started, [locks.USER])
        self.reactor.shutdown()

    def test_none_starts_anyway(self):
        hold_lock(self)
        self.successResultOf(self.run_app("--lock", "none"))
        self.assertEqual(self.started, [locks.NONE])

    def test_a_lock_that_cannot_be_opened(self):
        os.symlink("elsewhere", locations.SYSTEM_LOCK_FILE)
        self.addCleanup(os.remove, locations.SYSTEM_LOCK_FILE)
        failure = self.failureResultOf(self.run_app(), SystemExit)
        self.assertEqual(
            str(failure.value),
            f"Cannot take the lock {locations.SYSTEM_LOCK_FILE}: Too many "
            "levels of symbolic links. With --lock none, Virtualbricks runs "
            "without locks.",
        )
        self.assertEqual(self.started, [])


class TestWorkspace(unittest.TestCase):

    def setUp(self):
        self.root = isolate(self)

    def parse(self, *args):
        options = app.Options()
        options.parseOptions(list(args))
        return options["workspace"]

    def test_the_setting_without_it(self):
        self.assertIsNone(self.parse())

    def test_an_absolute_path(self):
        self.assertEqual(self.parse("--workspace", "/srv/labs/"), "/srv/labs")
        self.assertEqual(self.parse("--workspace=/srv/labs"), "/srv/labs")

    def test_home_and_the_current_folder(self):
        self.assertEqual(
            self.parse("--workspace", "~/labs"),
            os.path.join(self.root, "labs"),
        )
        self.assertEqual(
            self.parse("--workspace", "labs"),
            os.path.join(os.getcwd(), "labs"),
        )

    def test_not_a_folder(self):
        path = os.path.join(self.root, "file")
        open(path, "w").close()
        error = self.assertRaises(
            usage.UsageError, self.parse, "--workspace", path
        )
        self.assertEqual(str(error), f"--workspace: {path} is not a folder")
        self.assertRaises(usage.UsageError, self.parse, "--workspace", "")


class TestSocket(unittest.TestCase):

    def setUp(self):
        self.root = isolate(self)

    def parse(self, *args):
        options = app.Options()
        options.parseOptions(list(args))
        return options["socket"]

    def refused(self, *args):
        return str(self.assertRaises(usage.UsageError, self.parse, *args))

    def test_the_runtime_folder_without_it(self):
        self.assertIsNone(self.parse())

    def test_a_path(self):
        self.assertEqual(
            self.parse("--socket", "/tmp/lab.sock"), "/tmp/lab.sock"
        )
        # a home short enough for a socket's path
        home = short_folder(self)
        os.environ["HOME"] = home
        self.assertEqual(
            self.parse("--socket", "~/lab.sock"),
            os.path.join(home, "lab.sock"),
        )
        self.assertEqual(
            self.parse("--socket", "lab.sock"),
            os.path.join(os.getcwd(), "lab.sock"),
        )

    def test_what_is_refused(self):
        self.assertEqual(self.refused("--socket", ""), "--socket needs a path")
        folder = os.path.join(self.root, "nope")
        self.assertEqual(
            self.refused("--socket", os.path.join(folder, "lab.sock")),
            f"--socket: {folder} doesn't exist",
        )
        self.assertEqual(
            self.refused("--socket", self.root),
            f"--socket: {self.root} is a folder",
        )
        path = "/tmp/" + "a" * 103
        self.assertEqual(
            self.refused("--socket", path),
            f"--socket: {path} is longer than 107 bytes, the most a"
            " socket's path can have",
        )


class TestTheConsoleOptions(unittest.TestCase):

    def setUp(self):
        self.root = isolate(self)

    def parse(self, *args):
        options = app.Options()
        options.parseOptions(list(args))
        return options

    def test_no_gui(self):
        self.assertFalse(self.parse()["no-gui"])
        self.assertTrue(self.parse("--no-gui")["no-gui"])

    def test_run(self):
        self.assertIsNone(self.parse()["run"])
        path = os.path.join(self.root, "lab.vb")
        open(path, "w").close()
        self.assertEqual(self.parse("--run", "~/lab.vb")["run"], path)
        error = self.assertRaises(
            usage.UsageError, self.parse, "--run", "/nope.vb"
        )
        self.assertEqual(str(error), "--run: /nope.vb is not a file")

    def test_no_daemon(self):
        self.assertRaises(usage.UsageError, self.parse, "--daemon")
