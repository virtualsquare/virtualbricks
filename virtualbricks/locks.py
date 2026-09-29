# -*- test-case-name: virtualbricks.tests.test_locks -*-
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
How many Virtualbricks run at once: the policies of ``--lock``.

system
    One on the machine, the default: it holds the system lock alone.
user
    One for each user: it shares the system lock with the others that run
    with this policy, so it doesn't start while one runs with the system
    policy, nor that one while it runs, and holds the lock of its user alone.
none
    No lock: it starts beside any other, and the others don't see it.

The migration of a user's files holds the locks of the user policy.

The locks are flock(2) locks, which the system releases when the process
ends, even on a crash: a lock is never left behind. Their files stay.
"""

import fcntl
import os

from virtualbricks import locations

SYSTEM = "system"
USER = "user"
NONE = "none"
POLICIES = (SYSTEM, USER, NONE)


class Held(Exception):
    """
    Another Virtualbricks holds a lock that policy needs.

    holder is the policy the other runs with, as the lock at path tells it.
    """

    def __init__(self, policy: str, holder: str, path: str):
        super().__init__(policy, holder, path)
        self.policy = policy
        self.holder = holder
        self.path = path

    def __str__(self) -> str:
        if self.holder == SYSTEM:
            return (
                "Another Virtualbricks is running on this machine with "
                "--lock system, the default, which lets only one run at a "
                "time."
            )
        if self.policy == SYSTEM:
            return (
                "Virtualbricks is running on this machine with --lock user, "
                "one for each user: start this one with --lock user as well."
            )
        return (
            "Another Virtualbricks of yours is running, and --lock user lets "
            "each user run one."
        )


class Lock:
    """The locks that a Virtualbricks holds, released together."""

    def __init__(self, policy: str):
        self.policy = policy
        self._fds: list[int] = []

    @property
    def locked(self) -> bool:
        return bool(self._fds)

    def unlock(self) -> None:
        """Release the locks; nothing if they are released already."""

        while self._fds:
            os.close(self._fds.pop())

    def _take(self, path: str, operation: int) -> bool:
        """Lock the file at path; False if another Virtualbricks holds it."""

        fd = _open(path)
        try:
            fcntl.flock(fd, operation | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            return False
        except BaseException:
            os.close(fd)
            raise
        self._fds.append(fd)
        return True


def _system_holder() -> str:
    """The policy of the Virtualbricks that holds the system lock."""

    # a Virtualbricks of the system policy doesn't share it
    fd = _open(locations.SYSTEM_LOCK_FILE)
    try:
        fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
    except BlockingIOError:
        return SYSTEM
    finally:
        os.close(fd)
    return USER


def _open(path: str) -> int:
    """Open the lock file at path, made readable by everyone if missing."""

    # The fd isn't inherited: the programs of the bricks don't keep the lock.
    # O_CREAT on another user's file of /tmp fails when fs.protected_regular
    # is set, as on Debian, so the file is made only if it isn't there.
    flags = os.O_RDONLY | os.O_NOFOLLOW
    while True:
        try:
            return os.open(path, flags)
        except FileNotFoundError:
            pass
        try:
            fd = os.open(path, flags | os.O_CREAT | os.O_EXCL, 0o644)
        except FileExistsError:
            continue
        # the umask mustn't keep the other users out of the system lock
        os.fchmod(fd, 0o644)
        return fd


def acquire(policy: str = SYSTEM) -> Lock:
    """
    Take the locks of policy and return them.

    Raise Held if another Virtualbricks holds one of them, OSError if a lock
    file can't be opened.
    """

    if policy not in POLICIES:
        raise ValueError(f"unknown lock policy: {policy!r}")
    lock = Lock(policy)
    path = locations.SYSTEM_LOCK_FILE
    try:
        if policy == SYSTEM and not lock._take(path, fcntl.LOCK_EX):
            raise Held(policy, _system_holder(), path)
        if policy == USER:
            if not lock._take(path, fcntl.LOCK_SH):
                raise Held(policy, SYSTEM, path)
            locations.ensure_private_dir(locations.runtime_dir())
            path = locations.user_lock_file()
            if not lock._take(path, fcntl.LOCK_EX):
                raise Held(policy, USER, path)
    except BaseException:
        lock.unlock()
        raise
    return lock
