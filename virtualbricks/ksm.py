# -*- test-case-name: virtualbricks.tests.test_ksm -*-
# Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
# Copyright (C) 2026 Virtualbricks team

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
Kernel Samepage Merging: whether it runs, and turning it on or off.

KSM runs when /sys/kernel/mm/ksm/run holds 1; a Linux without the file has
no KSM. Only root can write the file:
as root Virtualbricks writes it, otherwise it runs ``tee`` with sudo (see
:mod:`virtualbricks.sudo`), which writes what it reads, without a shell.

``set_ksm()`` never fails: it logs why KSM didn't change, and its Deferred
fires with the state of KSM afterwards, read from the file again, which is
what a switch showing it needs.
"""

from __future__ import annotations

import os

from typing import cast

from twisted.internet import defer, error, protocol
from twisted.internet.interfaces import IReactorProcess
from twisted.logger import Logger
from twisted.python.failure import Failure

from virtualbricks.sudo import sudo_command

KSM_PATH = "/sys/kernel/mm/ksm/run"
logger = Logger()
ksm_error = "Cannot turn KSM {state}: {error}"


def ksm_available() -> bool:
    """Whether this Linux has KSM."""

    return os.path.exists(KSM_PATH)


def check_ksm() -> bool:
    """Whether KSM runs."""

    try:
        with open(KSM_PATH) as fp:
            return bool(int(fp.readline()))
    except (OSError, ValueError):
        return False


def _state(enable: bool) -> str:
    return "on" if enable else "off"


class _WriteProtocol(protocol.ProcessProtocol):
    """
    Give tee the value to write; fire done with why it ended, ProcessDone or
    ProcessTerminated.
    """

    def __init__(
        self, value: bytes, done: defer.Deferred[BaseException]
    ) -> None:
        self.value = value
        self.done = done

    def connectionMade(self) -> None:
        assert self.transport is not None, "tee runs"
        self.transport.write(self.value)
        self.transport.closeStdin()

    def processEnded(self, reason: Failure) -> None:
        # the exception: a Failure would fail done
        assert reason.value is not None, "a process ends for a reason"
        self.done.callback(reason.value)


def _ended(reason: BaseException, enable: bool) -> bool:
    if not isinstance(reason, error.ProcessDone):
        logger.error(ksm_error, state=_state(enable), error=reason)
    return check_ksm()


def set_ksm(
    enable: bool, reactor: IReactorProcess | None = None
) -> defer.Deferred[bool]:
    """
    Turn KSM on or off; the Deferred fires with the state of KSM then, and
    never fails.
    """

    enable = bool(enable)
    if check_ksm() == enable:
        return defer.succeed(enable)
    value = b"1\n" if enable else b"0\n"
    if os.geteuid() == 0:
        try:
            with open(KSM_PATH, "wb") as fp:
                fp.write(value)
        except OSError as exc:
            logger.error(ksm_error, state=_state(enable), error=exc)
        return defer.succeed(check_ksm())
    if reactor is None:
        from twisted.internet import reactor as default

        reactor = cast("IReactorProcess", default)
    args = sudo_command(["tee", KSM_PATH])
    done: defer.Deferred[BaseException] = defer.Deferred()
    try:
        reactor.spawnProcess(
            _WriteProtocol(value, done), args[0], args, os.environ
        )
    except OSError as exc:
        logger.error(ksm_error, state=_state(enable), error=exc)
        return defer.succeed(check_ksm())
    return done.addCallback(_ended, enable)
