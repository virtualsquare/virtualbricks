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

"""
The policies of --lock: one Virtualbricks on the machine, per user, per
workspace, any.
"""

import errno
import fcntl
import os
import pwd
import signal
import stat
import subprocess
import sys

from twisted.trial import unittest

from virtualbricks import locations, locks
from virtualbricks.locks import NONE, SYSTEM, USER, WORKSPACE
from virtualbricks.tests import hold_lock, isolate, lock_is_free, release

# A Virtualbricks in a process of its own, until its input ends or it's
# killed: the system lock, the policy, the runtime directory of its user.
CHILD = """\
import os, sys
from virtualbricks import locations, locks
locations.SYSTEM_LOCK_FILE = sys.argv[1]
os.environ["XDG_RUNTIME_DIR"] = sys.argv[3]
locks.acquire(sys.argv[2])
print("held", flush=True)
sys.stdin.read()
"""
ME = pwd.getpwuid(os.getuid()).pw_name


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
        self.assertRaises(ValueError, locks.acquire, "group")
        self.assertTrue(lock_is_free())


class TestWorkspaces(unittest.TestCase):
    """One Virtualbricks for each workspace, and the lock of a workspace."""

    def setUp(self):
        self.root = isolate(self)
        self.a = self.folder("a")
        self.b = self.folder("b")

    def folder(self, name):
        path = os.path.join(self.root, name)
        os.makedirs(path)
        return path

    def starts(self, policy, workspace):
        """Whether a Virtualbricks of policy starts in workspace."""

        try:
            lock = locks.acquire(policy)
        except locks.Held:
            return False
        try:
            lock.take_workspace(workspace)
        except locks.Held:
            return False
        finally:
            lock.unlock()
        return True

    def assertStarts(self, workspace, *expected):
        """The modes that start in workspace: system, user, workspace, none."""

        policies = (SYSTEM, USER, WORKSPACE, NONE)
        starts = tuple(self.starts(policy, workspace) for policy in policies)
        self.assertEqual(starts, expected)

    def test_one_for_each_workspace(self):
        hold_lock(self, WORKSPACE, workspace=self.a)
        lock = locks.acquire(WORKSPACE)
        self.addCleanup(release, lock)
        lock.take_workspace(self.b)
        self.assertTrue(lock.locked)
        other = locks.acquire(WORKSPACE)
        self.addCleanup(release, other)
        held = self.assertRaises(locks.Held, other.take_workspace, self.a)
        self.assertEqual(
            (held.policy, held.holder, held.workspace),
            (WORKSPACE, WORKSPACE, self.a),
        )
        self.assertEqual(held.path, locations.workspace_lock_file(self.a))
        self.assertEqual(held.holders, ((os.getpid(), ME),))
        # a refused workspace keeps the locks of the policy
        self.assertTrue(other.locked)

    def test_system_alone(self):
        # yours or another user's, in whatever workspace
        for user in (None, "bob"):
            lock = hold_lock(self, SYSTEM, user, self.a)
            self.assertStarts(self.b, False, False, False, True)
            lock.unlock()

    def test_user_alone_for_its_user(self):
        hold_lock(self, USER, workspace=self.a)
        self.assertStarts(self.b, False, False, False, True)

    def test_workspace_beside_another(self):
        hold_lock(self, WORKSPACE, workspace=self.a)
        self.assertStarts(self.b, False, False, True, True)

    def test_the_same_workspace(self):
        # yours or another user's, a folder you share
        for policy, user in ((USER, None), (WORKSPACE, "bob"), (USER, "bob")):
            lock = hold_lock(self, policy, user, self.a)
            self.assertStarts(self.a, False, False, False, True)
            lock.unlock()

    def test_another_users_in_another_workspace(self):
        for policy in (USER, WORKSPACE):
            lock = hold_lock(self, policy, "bob", self.a)
            self.assertStarts(self.b, False, True, True, True)
            lock.unlock()

    def test_none_takes_no_workspace(self):
        lock = hold_lock(self, NONE, workspace=self.a)
        self.assertFalse(lock.locked)
        self.assertFalse(os.path.exists(locations.workspace_lock_file(self.a)))
        self.assertStarts(self.a, True, True, True, True)

    def test_the_workspace_mode_against_the_user_mode(self):
        hold_lock(self, USER)
        held = self.assertRaises(locks.Held, locks.acquire, WORKSPACE)
        self.assertEqual((held.policy, held.holder), (WORKSPACE, USER))
        self.assertEqual(held.path, locations.user_lock_file())

    def test_the_user_mode_against_the_workspace_mode(self):
        hold_lock(self, WORKSPACE)
        hold_lock(self, WORKSPACE)
        held = self.assertRaises(locks.Held, locks.acquire, USER)
        self.assertEqual((held.policy, held.holder), (USER, WORKSPACE))
        self.assertEqual(held.path, locations.user_lock_file())
        self.assertEqual(held.holders, ((os.getpid(), ME),))
        held = self.assertRaises(locks.Held, locks.acquire, SYSTEM)
        self.assertEqual((held.policy, held.holder), (SYSTEM, USER))

    def test_a_link_to_the_workspace(self):
        hold_lock(self, WORKSPACE, workspace=self.a)
        link = os.path.join(self.root, "link")
        os.symlink(self.a, link)
        self.assertFalse(self.starts(WORKSPACE, link))

    def test_the_user_lock_alone(self):
        # while the settings of 2.1 are converted
        lock = locks.acquire(WORKSPACE, user_alone=True)
        self.addCleanup(release, lock)
        held = self.assertRaises(locks.Held, locks.acquire, WORKSPACE)
        self.assertEqual(held.holder, USER)
        lock.share_user()
        self.assertTrue(lock.locked)
        self.assertTrue(self.starts(WORKSPACE, self.b))
        self.assertFalse(self.starts(USER, self.b))

    def test_the_user_lock_alone_while_others_run(self):
        hold_lock(self, WORKSPACE, workspace=self.a)
        held = self.assertRaises(
            locks.Held, locks.acquire, WORKSPACE, user_alone=True
        )
        self.assertEqual((held.policy, held.holder), (WORKSPACE, WORKSPACE))
        self.assertIn("settings of Virtualbricks 2.1", str(held))

    def test_another_takes_the_user_lock_in_between(self):
        lock = locks.acquire(WORKSPACE, user_alone=True)
        self.addCleanup(release, lock)
        flock = fcntl.flock

        def taken(fd, operation):
            if fd == lock._user and operation & fcntl.LOCK_SH:
                raise BlockingIOError(errno.EAGAIN, "taken")
            flock(fd, operation)

        self.patch(fcntl, "flock", taken)
        held = self.assertRaises(locks.Held, lock.share_user)
        self.assertEqual((held.policy, held.holder), (WORKSPACE, USER))


class TestWorkspaceFile(unittest.TestCase):

    def setUp(self):
        self.root = isolate(self)
        self.workspace = os.path.join(self.root, "labs")
        os.makedirs(self.workspace)
        self.path = locations.workspace_lock_file(self.workspace)

    def take(self):
        lock = locks.acquire(WORKSPACE)
        self.addCleanup(release, lock)
        lock.take_workspace(self.workspace)
        return lock

    def test_the_file(self):
        umask = os.umask(0o077)
        self.addCleanup(os.umask, umask)
        lock = self.take()
        self.assertEqual(stat.S_IMODE(os.stat(self.path).st_mode), 0o644)
        # open for writing, as NFS needs for an exclusive flock
        fd = lock._fds[-1]
        mode = fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE
        self.assertEqual(mode, os.O_RDWR)
        self.assertFalse(os.get_inheritable(fd))

    def test_read_only_if_it_cant_be_written(self):
        # as another user's file
        with open(self.path, "w"):
            pass
        os.chmod(self.path, 0o444)
        lock = self.take()
        fd = lock._fds[-1]
        mode = fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE
        self.assertEqual(mode, os.O_RDONLY)
        # and still held alone
        other = locks.acquire(WORKSPACE)
        self.addCleanup(release, other)
        self.assertRaises(locks.Held, other.take_workspace, self.workspace)

    def test_a_workspace_that_cant_be_written(self):
        os.chmod(self.workspace, 0o555)
        self.addCleanup(os.chmod, self.workspace, 0o755)
        lock = locks.acquire(WORKSPACE)
        self.addCleanup(release, lock)
        error = self.assertRaises(OSError, lock.take_workspace, self.workspace)
        self.assertEqual(error.errno, errno.EACCES)

    def test_a_symlink_is_not_followed(self):
        target = os.path.join(self.root, "target")
        os.symlink(target, self.path)
        lock = locks.acquire(WORKSPACE)
        self.addCleanup(release, lock)
        error = self.assertRaises(OSError, lock.take_workspace, self.workspace)
        self.assertEqual(error.errno, errno.ELOOP)
        self.assertFalse(os.path.exists(target))


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
        lock.take_workspace(os.path.dirname(locations.SYSTEM_LOCK_FILE))
        self.assertEqual(len(lock._fds), 3)
        for fd in lock._fds:
            self.assertFalse(os.get_inheritable(fd))


class TestHold(unittest.TestCase):
    """The lock of one file, as the control socket's."""

    def setUp(self):
        isolate(self)
        self.path = os.path.abspath(self.mktemp())

    def hold(self):
        lock = locks.hold(self.path)
        self.addCleanup(release, lock)
        return lock

    def test_alone(self):
        lock = self.hold()
        self.assertTrue(lock.locked)
        self.assertIsNone(locks.hold(self.path))
        self.assertEqual(locks.holders(self.path), ((os.getpid(), ME),))
        lock.unlock()
        self.assertTrue(self.hold().locked)

    def test_apart_from_the_policies(self):
        hold_lock(self, USER)
        self.assertTrue(self.hold().locked)

    def test_a_symlink_is_not_followed(self):
        target = self.path + "-target"
        os.symlink(target, self.path)
        error = self.assertRaises(OSError, locks.hold, self.path)
        self.assertEqual(error.errno, errno.ELOOP)
        self.assertFalse(os.path.exists(target))

    def test_held_alone(self):
        # as the socket's, whose Virtualbricks listens
        self.assertFalse(locks.held_alone(self.path))
        self.assertFalse(os.path.exists(self.path))
        lock = self.hold()
        self.assertTrue(locks.held_alone(self.path))
        # the lock stays held
        self.assertIsNone(locks.hold(self.path))
        lock.unlock()
        self.assertFalse(locks.held_alone(self.path))

    def test_held_but_shared(self):
        # the user lock of the workspace policy: not alone
        hold_lock(self, WORKSPACE)
        self.assertFalse(locks.held_alone(locations.user_lock_file()))


class TestProcesses(unittest.TestCase):

    def setUp(self):
        isolate(self)

    def spawn(self, policy, runtime=None):
        runtime = runtime or os.environ["XDG_RUNTIME_DIR"]
        argv = [locations.SYSTEM_LOCK_FILE, policy, runtime]
        child = subprocess.Popen(
            [sys.executable, "-c", CHILD, *argv],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
        )
        self.addCleanup(child.wait)
        self.addCleanup(child.stdin.close)
        self.addCleanup(child.stdout.close)
        self.assertEqual(child.stdout.readline(), "held\n")
        return child

    def test_a_crash_leaves_no_lock(self):
        child = self.spawn(SYSTEM)
        held = self.assertRaises(locks.Held, locks.acquire, USER)
        self.assertEqual(held.holder, SYSTEM)
        self.assertEqual(held.holders, ((child.pid, ME),))
        child.send_signal(signal.SIGKILL)
        child.wait()
        self.assertTrue(lock_is_free())

    def test_every_holder_of_a_shared_lock(self):
        runtime = os.environ["XDG_RUNTIME_DIR"]
        alice = self.spawn(USER, runtime + "-alice")
        bob = self.spawn(USER, runtime + "-bob")
        held = self.assertRaises(locks.Held, locks.acquire, SYSTEM)
        self.assertEqual(held.holder, USER)
        self.assertEqual(
            sorted(held.holders), sorted([(alice.pid, ME), (bob.pid, ME)])
        )
        self.assertIn(" Held by processes ", str(held))

    def test_the_holder_of_your_lock(self):
        child = self.spawn(USER)
        held = self.assertRaises(locks.Held, locks.acquire, USER)
        self.assertEqual(held.path, locations.user_lock_file())
        self.assertEqual(held.holders, ((child.pid, ME),))


class TestHolders(unittest.TestCase):

    def setUp(self):
        self.root = isolate(self)

    def test_in_this_process(self):
        hold_lock(self)
        held = self.assertRaises(locks.Held, locks.acquire, SYSTEM)
        self.assertEqual(held.holders, ((os.getpid(), ME),))
        self.assertTrue(
            str(held).endswith(f" Held by process {os.getpid()} of {ME}.")
        )

    def test_without_proc(self):
        self.patch(locks, "PROC", os.path.join(self.root, "no-proc"))
        hold_lock(self)
        held = self.assertRaises(locks.Held, locks.acquire, SYSTEM)
        self.assertEqual(held.holders, ())
        self.assertNotIn("Held by", str(held))
        self.assertEqual(locks.holders(locations.SYSTEM_LOCK_FILE), ())

    def test_the_lines_of_proc_locks(self):
        text = (
            "1: FLOCK  ADVISORY  WRITE 4242 00:2b:77 0 EOF\n"
            "2: -> FLOCK  ADVISORY  WRITE 4343 00:2b:77 0 EOF\n"
            "3: POSIX  ADVISORY  WRITE 4444 00:2b:77 0 EOF\n"
            "4: FLOCK  ADVISORY  READ 4545 00:2b:78 0 EOF\n"
            "5: FLOCK  ADVISORY  READ 4646 00:2b:77 0 EOF\n"
            "6: FLOCK  ADVISORY  READ 4646 00:2b:77 0 EOF\n"
            "7: FLOCK  ADVISORY  READ 0 00:2b:77 0 EOF\n"
        )
        # not a waiter, a POSIX lock, another file, twice, another namespace
        self.assertEqual(locks._lock_pids(text, "00:2b:77"), [4242, 4646])

    def test_users(self):
        proc = os.path.join(self.root, "proc")
        self.patch(locks, "PROC", proc)
        unknown = 2**31 - 7
        self.assertRaises(KeyError, pwd.getpwuid, unknown)
        statuses = {
            4242: "Name:\tvirtualbricks\nUid:\t0\t1000\t1000\t1000\n",
            4343: f"Uid:\t{unknown}\t{unknown}\t{unknown}\t{unknown}\n",
            4444: "Name:\tvirtualbricks\n",
        }
        for pid, status in statuses.items():
            os.makedirs(os.path.join(proc, str(pid)))
            with open(os.path.join(proc, str(pid), "status"), "w") as fp:
                fp.write(status)
        # the real user, a user without a name, a status without one, no
        # such process
        self.assertEqual(locks._user(4242), pwd.getpwuid(0).pw_name)
        self.assertEqual(locks._user(4343), str(unknown))
        self.assertIsNone(locks._user(4444))
        self.assertIsNone(locks._user(4545))


class TestMessages(unittest.TestCase):

    def message(self, policy, holder, holders=()):
        path = "/tmp/virtualbricks.lock"
        return str(locks.Held(policy, holder, path, holders))

    def test_messages(self):
        running_alone = (
            "Another Virtualbricks is running on this machine with --lock "
            "system, the default, which lets only one run at a time."
        )
        self.assertEqual(self.message(SYSTEM, SYSTEM), running_alone)
        self.assertEqual(self.message(USER, SYSTEM), running_alone)
        self.assertEqual(
            self.message(WORKSPACE, SYSTEM),
            f"{running_alone} To run one in each workspace, start that one "
            "with --lock workspace too.",
        )
        self.assertEqual(
            self.message(SYSTEM, USER),
            "Virtualbricks is running on this machine with --lock user or "
            "--lock workspace, which let others run beside it: start this "
            "one with one of them as well.",
        )
        self.assertEqual(
            self.message(USER, USER),
            "Another Virtualbricks of yours is running, and --lock user lets "
            "each user run one.",
        )
        self.assertEqual(
            self.message(WORKSPACE, USER),
            "Another Virtualbricks of yours is running with --lock user, "
            "which lets each user run one: to run one in each workspace, "
            "start both with --lock workspace.",
        )
        self.assertEqual(
            self.message(USER, WORKSPACE),
            "Virtualbricks of yours are running with --lock workspace, one "
            "for each workspace: start this one with --lock workspace as "
            "well.",
        )

    def test_the_workspace(self):
        self.patch(os, "environ", {"HOME": "/home/alice"})
        for policy in (SYSTEM, USER, WORKSPACE):
            held = locks.Held(
                policy,
                WORKSPACE,
                "/home/alice/labs/a/.virtualbricks.lock",
                ((4300, "alice"),),
                "/home/alice/labs/a",
            )
            self.assertEqual(
                str(held),
                "Another Virtualbricks is running in the workspace "
                "~/labs/a: start this one in another, with --workspace. "
                "Held by process 4300 of alice.",
            )

    def test_holders(self):
        yours = (
            "Another Virtualbricks of yours is running, and --lock user lets "
            "each user run one."
        )
        self.assertEqual(
            self.message(USER, USER, ((4242, "bob"),)),
            f"{yours} Held by process 4242 of bob.",
        )
        self.assertEqual(
            self.message(USER, USER, ((4242, None),)),
            f"{yours} Held by process 4242.",
        )
        self.assertEqual(
            self.message(SYSTEM, USER, ((1, "alice"), (2, None), (3, "bob"))),
            "Virtualbricks is running on this machine with --lock user or "
            "--lock workspace, which let others run beside it: start this "
            "one with one of them as well. Held by processes 1 of alice, 2 "
            "and 3 of bob.",
        )
