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
ends, even on a crash: a lock is never left behind. Their files stay. When a
start is refused, /proc/locks tells which processes hold the lock, and their
status which user runs them.
"""

import fcntl
import os
import pwd

from virtualbricks import locations

SYSTEM = "system"
USER = "user"
NONE = "none"
POLICIES = (SYSTEM, USER, NONE)
PROC = "/proc"

# A process that holds a lock, and the name of its user, None if hidden.
Holder = tuple[int, "str | None"]


class Held(Exception):
    """
    Another Virtualbricks holds a lock that policy needs.

    holder is the policy the other runs with, as the lock at path tells it;
    holders are the processes that hold the lock, as far as they are known.
    """

    def __init__(
        self,
        policy: str,
        holder: str,
        path: str,
        holders: tuple[Holder, ...] = (),
    ):
        super().__init__(policy, holder, path, holders)
        self.policy = policy
        self.holder = holder
        self.path = path
        self.holders = holders

    def __str__(self) -> str:
        if self.holder == SYSTEM:
            text = (
                "Another Virtualbricks is running on this machine with "
                "--lock system, the default, which lets only one run at a "
                "time."
            )
        elif self.policy == SYSTEM:
            text = (
                "Virtualbricks is running on this machine with --lock user, "
                "one for each user: start this one with --lock user as well."
            )
        else:
            text = (
                "Another Virtualbricks of yours is running, and --lock user "
                "lets each user run one."
            )
        if not self.holders:
            return text
        names = [
            str(pid) if user is None else f"{pid} of {user}"
            for pid, user in self.holders
        ]
        noun = "process" if len(names) == 1 else "processes"
        if len(names) > 1:
            names[-2:] = [f"{names[-2]} and {names[-1]}"]
        return f"{text} Held by {noun} {', '.join(names)}."


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


def holders(path: str) -> tuple[Holder, ...]:
    """
    The processes that hold a flock of the file at path, with their users.

    Empty when /proc/locks can't be read, or the file is gone.
    """

    try:
        info = os.stat(path)
        with open(os.path.join(PROC, "locks")) as fp:
            text = fp.read()
    except OSError:
        return ()
    major, minor = os.major(info.st_dev), os.minor(info.st_dev)
    key = f"{major:02x}:{minor:02x}:{info.st_ino}"
    return tuple((pid, _user(pid)) for pid in _lock_pids(text, key))


def _lock_pids(text: str, key: str) -> list[int]:
    """The processes of the flocks of /proc/locks on the file key."""

    # "1: FLOCK  ADVISORY  WRITE 4242 103:02:398395 0 EOF", the device in hex
    # and the inode; a process that waits for the lock has "->" after "1:".
    # The process is the one that took the lock, 0 if in another namespace.
    pids: list[int] = []
    for line in text.splitlines():
        fields = line.split()
        if len(fields) > 5 and fields[1] == "FLOCK" and fields[5] == key:
            pid = int(fields[4])
            if pid > 0 and pid not in pids:
                pids.append(pid)
    return pids


def _user(pid: int) -> str | None:
    """The name of the user that runs pid; None if /proc hides it."""

    uid = None
    try:
        with open(os.path.join(PROC, str(pid), "status")) as fp:
            for line in fp:
                # real, effective, saved and filesystem user: the real one
                # started it
                if line.startswith("Uid:"):
                    uid = int(line.split()[1])
                    break
    except (OSError, ValueError, IndexError):
        return None
    if uid is None:
        return None
    try:
        return pwd.getpwuid(uid).pw_name
    except KeyError:
        return str(uid)


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


def hold(path: str) -> Lock | None:
    """
    Lock the file at path alone, without waiting, as the control socket's.

    Return the lock, None if another process holds it; raise OSError if the
    file can't be opened.
    """

    # the lock of a file of its own, of no policy
    lock = Lock(NONE)
    if not lock._take(path, fcntl.LOCK_EX):
        return None
    return lock


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
        # a refused lock asks its holders once this process holds none of it
        if policy == SYSTEM and not lock._take(path, fcntl.LOCK_EX):
            raise Held(policy, _system_holder(), path, holders(path))
        if policy == USER:
            if not lock._take(path, fcntl.LOCK_SH):
                raise Held(policy, SYSTEM, path, holders(path))
            locations.ensure_private_dir(locations.runtime_dir())
            path = locations.user_lock_file()
            if not lock._take(path, fcntl.LOCK_EX):
                raise Held(policy, USER, path, holders(path))
    except BaseException:
        lock.unlock()
        raise
    return lock
