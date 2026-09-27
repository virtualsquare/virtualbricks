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

"""KSM: reading whether it runs, and turning it on or off."""

import os
import shutil

from twisted.internet import error
from twisted.python import failure
from twisted.trial import unittest

from virtualbricks import ksm
from virtualbricks.ksm import check_ksm, set_ksm
from virtualbricks.tests import FakeLogger


class FakeTransport:
    def __init__(self):
        self.written = b""
        self.closed = False

    def write(self, data):
        if not isinstance(data, bytes):
            raise TypeError("Data must be bytes")
        self.written += data

    def closeStdin(self):
        self.closed = True


class FakeReactor:
    """Records the processes spawned; spawning fails when told."""

    def __init__(self, error=None):
        self.spawned = []
        self.error = error

    def spawnProcess(self, protocol, executable, args, env):
        if self.error is not None:
            raise self.error
        self.spawned.append((protocol, executable, args))
        protocol.makeConnection(FakeTransport())


class KSMTestCase(unittest.TestCase):

    def setUp(self):
        self.path = os.path.abspath(self.mktemp())
        self.patch(ksm, "KSM_PATH", self.path)
        self.logger = FakeLogger()
        self.patch(ksm, "logger", self.logger)
        self.patch(
            ksm,
            "sudo_command",
            lambda args: ["/usr/bin/sudo", "-n", "--", *args],
        )

    def run_file(self, text):
        with open(self.path, "w") as fp:
            fp.write(text)

    def as_root(self, root=True):
        self.patch(ksm.os, "geteuid", lambda: 0 if root else 1000)


class TestCheck(KSMTestCase):

    def test_on_and_off(self):
        self.run_file("1\n")
        self.assertTrue(check_ksm())
        self.run_file("0\n")
        self.assertFalse(check_ksm())

    def test_no_ksm(self):
        self.assertFalse(check_ksm())

    def test_a_file_it_cant_read(self):
        self.run_file("on\n")
        self.assertFalse(check_ksm())


class TestSetAsRoot(KSMTestCase):

    def setUp(self):
        super().setUp()
        self.as_root()
        self.run_file("0\n")

    def test_on(self):
        self.assertIs(self.successResultOf(set_ksm(True)), True)
        with open(self.path) as fp:
            self.assertEqual(fp.read(), "1\n")
        self.assertIs(self.successResultOf(set_ksm(False)), False)
        self.assertFalse(check_ksm())

    def test_already(self):
        reactor = FakeReactor()
        self.assertIs(self.successResultOf(set_ksm(0, reactor)), False)
        self.assertEqual(reactor.spawned, [])

    def test_a_file_it_cant_write(self):
        os.remove(self.path)
        self.patch(ksm, "KSM_PATH", os.path.join(self.path, "nowhere", "run"))
        self.assertIs(self.successResultOf(set_ksm(True)), False)
        self.assertEqual(self.logger.levels(), ["error"])
        self.assertIn("Cannot turn KSM on", self.logger.formatted()[0])


class TestSetWithSudo(KSMTestCase):

    def setUp(self):
        super().setUp()
        self.as_root(False)
        self.run_file("0\n")
        self.reactor = FakeReactor()

    def end(self, reason):
        protocol, _executable, _args = self.reactor.spawned[0]
        protocol.processEnded(failure.Failure(reason))

    def test_tee(self):
        result = set_ksm(True, self.reactor)
        protocol, executable, args = self.reactor.spawned[0]
        self.assertEqual(executable, "/usr/bin/sudo")
        self.assertEqual(args, ["/usr/bin/sudo", "-n", "--", "tee", self.path])
        self.assertEqual(protocol.transport.written, b"1\n")
        self.assertTrue(protocol.transport.closed)
        self.assertNoResult(result)
        # tee writes it
        self.run_file("1\n")
        self.end(error.ProcessDone(0))
        self.assertIs(self.successResultOf(result), True)
        self.assertEqual(self.logger.events, [])

    def test_off(self):
        self.run_file("1\n")
        set_ksm(False, self.reactor)
        protocol = self.reactor.spawned[0][0]
        self.assertEqual(protocol.transport.written, b"0\n")

    def test_sudo_fails(self):
        result = set_ksm(True, self.reactor)
        self.end(error.ProcessTerminated(exitCode=1))
        # the state as it is: off
        self.assertIs(self.successResultOf(result), False)
        self.assertEqual(self.logger.levels(), ["error"])
        self.assertIn("exit code 1", self.logger.formatted()[0])

    def test_killed(self):
        result = set_ksm(True, self.reactor)
        self.end(error.ProcessTerminated(signal=15))
        self.assertIs(self.successResultOf(result), False)
        self.assertEqual(self.logger.levels(), ["error"])

    def test_sudo_cant_start(self):
        reactor = FakeReactor(OSError(2, "No such file or directory"))
        self.assertIs(self.successResultOf(set_ksm(True, reactor)), False)
        self.assertEqual(self.logger.levels(), ["error"])


class TestSetInARealProcess(KSMTestCase):
    """tee as it runs, without sudo."""

    def test_tee(self):
        tee = shutil.which("tee")
        if tee is None:  # pragma: no cover
            raise unittest.SkipTest("no tee")
        self.patch(ksm, "sudo_command", lambda args: [tee, *args[1:]])
        self.as_root(False)
        self.run_file("0\n")

        def check(state):
            self.assertIs(state, True)
            with open(self.path) as fp:
                self.assertEqual(fp.read(), "1\n")

        return set_ksm(True).addCallback(check)
