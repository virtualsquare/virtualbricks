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

"""The policies of --lock: one Virtualbricks on the machine, per user, any."""

import errno
import os
import signal
import stat
import subprocess
import sys

from twisted.trial import unittest

from virtualbricks import locations, locks
from virtualbricks.locks import NONE, SYSTEM, USER
from virtualbricks.tests import hold_lock, isolate, lock_is_free, release

# A Virtualbricks of the system policy in a process of its own, until killed.
CHILD = """\
import sys
from virtualbricks import locations, locks
locations.SYSTEM_LOCK_FILE = sys.argv[1]
locks.acquire(locks.SYSTEM)
print("held", flush=True)
sys.stdin.read()
"""


class TestPolicies(unittest.TestCase):

    def setUp(self):
        isolate(self)

    def refused(self, policy):
        return self.assertRaises(locks.Held, locks.acquire, policy)

    def acquire(self, policy):
        lock = locks.acquire(policy)
        self.addCleanup(release, lock)
        return lock

    def test_system_runs_alone(self):
        hold_lock(self, SYSTEM)
        held = self.refused(SYSTEM)
        self.assertEqual(
            (held.policy, held.holder, held.path),
            (SYSTEM, SYSTEM, locations.SYSTEM_LOCK_FILE),
        )
        # a user lock complies with the system lock
        held = self.refused(USER)
        self.assertEqual((held.policy, held.holder), (USER, SYSTEM))
        self.assertEqual(held.path, locations.SYSTEM_LOCK_FILE)

    def test_system_alone_whoever_holds_it(self):
        hold_lock(self, SYSTEM, "bob")
        self.assertEqual(self.refused(SYSTEM).holder, SYSTEM)
        self.assertEqual(self.refused(USER).holder, SYSTEM)

    def test_one_for_each_user(self):
        hold_lock(self, USER)
        hold_lock(self, USER, "bob")
        held = self.refused(USER)
        self.assertEqual((held.policy, held.holder), (USER, USER))
        self.assertEqual(held.path, locations.user_lock_file())
        # and none of the machine to itself
        held = self.refused(SYSTEM)
        self.assertEqual((held.policy, held.holder), (SYSTEM, USER))
        self.assertEqual(held.path, locations.SYSTEM_LOCK_FILE)

    def test_system_after_the_users(self):
        bob = hold_lock(self, USER, "bob")
        self.refused(SYSTEM)
        bob.unlock()
        self.assertTrue(self.acquire(SYSTEM).locked)

    def test_none_holds_nothing(self):
        hold_lock(self, SYSTEM)
        lock = self.acquire(NONE)
        self.assertEqual(lock.policy, NONE)
        self.assertFalse(lock.locked)
        lock.unlock()

    def test_none_stops_nobody(self):
        self.acquire(NONE)
        self.assertTrue(self.acquire(SYSTEM).locked)

    def test_unlock(self):
        lock = self.acquire(USER)
        self.assertEqual(lock.policy, USER)
        self.assertTrue(lock.locked)
        self.assertFalse(lock_is_free())
        lock.unlock()
        self.assertFalse(lock.locked)
        self.assertTrue(lock_is_free())
        lock.unlock()

    def test_refused_takes_nothing(self):
        # the second takes the shared system lock, then fails on the user's
        lock = hold_lock(self, USER)
        self.refused(USER)
        lock.unlock()
        self.assertTrue(lock_is_free())

    def test_unknown_policy(self):
        self.assertRaises(ValueError, locks.acquire, "workspace")
        self.assertTrue(lock_is_free())


class TestFiles(unittest.TestCase):

    def setUp(self):
        isolate(self)
        self.umask = os.umask(0o077)
        self.addCleanup(os.umask, self.umask)

    def test_every_user_opens_the_system_lock(self):
        locks.acquire(USER).unlock()
        mode = os.stat(locations.SYSTEM_LOCK_FILE).st_mode
        self.assertEqual(stat.S_IMODE(mode), 0o644)
        # the user lock is in the private runtime directory
        mode = os.stat(os.path.dirname(locations.user_lock_file())).st_mode
        self.assertEqual(stat.S_IMODE(mode), 0o700)
        self.assertTrue(os.path.isfile(locations.user_lock_file()))

    def test_an_existing_file(self):
        with open(locations.SYSTEM_LOCK_FILE, "w") as fp:
            fp.write("left by someone\n")
        locks.acquire(SYSTEM).unlock()
        with open(locations.SYSTEM_LOCK_FILE) as fp:
            self.assertEqual(fp.read(), "left by someone\n")

    def test_a_symlink_is_not_followed(self):
        target = os.path.join(os.path.dirname(locations.SYSTEM_LOCK_FILE), "t")
        os.symlink(target, locations.SYSTEM_LOCK_FILE)
        self.addCleanup(os.remove, locations.SYSTEM_LOCK_FILE)
        error = self.assertRaises(OSError, locks.acquire, SYSTEM)
        self.assertEqual(error.errno, errno.ELOOP)
        self.assertFalse(os.path.exists(target))

    def test_the_programs_of_the_bricks_dont_inherit_it(self):
        lock = locks.acquire(USER)
        self.addCleanup(lock.unlock)
        self.assertEqual(len(lock._fds), 2)
        for fd in lock._fds:
            self.assertFalse(os.get_inheritable(fd))


class TestProcesses(unittest.TestCase):

    def setUp(self):
        isolate(self)

    def test_a_crash_leaves_no_lock(self):
        child = subprocess.Popen(
            [sys.executable, "-c", CHILD, locations.SYSTEM_LOCK_FILE],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
        )
        self.addCleanup(child.wait)
        self.addCleanup(child.stdin.close)
        self.addCleanup(child.stdout.close)
        self.assertEqual(child.stdout.readline(), "held\n")
        self.assertEqual(
            self.assertRaises(locks.Held, locks.acquire, USER).holder, SYSTEM
        )
        child.send_signal(signal.SIGKILL)
        child.wait()
        self.assertTrue(lock_is_free())


class TestMessages(unittest.TestCase):

    def message(self, policy, holder):
        return str(locks.Held(policy, holder, "/tmp/virtualbricks.lock"))

    def test_messages(self):
        running_alone = (
            "Another Virtualbricks is running on this machine with --lock "
            "system, the default, which lets only one run at a time."
        )
        self.assertEqual(self.message(SYSTEM, SYSTEM), running_alone)
        self.assertEqual(self.message(USER, SYSTEM), running_alone)
        self.assertEqual(
            self.message(SYSTEM, USER),
            "Virtualbricks is running on this machine with --lock user, one "
            "for each user: start this one with --lock user as well.",
        )
        self.assertEqual(
            self.message(USER, USER),
            "Another Virtualbricks of yours is running, and --lock user lets "
            "each user run one.",
        )
