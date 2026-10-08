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
The consoles of the bricks there, carried over a connection: the relay of
the bytes, the console of a brick, Attach at both ends, the terminal here.
"""

import os
import stat

from twisted.internet import defer, endpoints, error, reactor
from twisted.internet.testing import StringTransport
from twisted.protocols import amp
from twisted.test import iosim
from twisted.trial import unittest


from virtualbricks.bricks import FakeProcess
from virtualbricks.config import settings
from virtualbricks.console import ampcommands, ampwire, control
from virtualbricks.remote import client, commands, follower, tunnel
from virtualbricks.remote.client import NotYet, RemoteEngine
from virtualbricks.remote.follower import LogKeeper
from virtualbricks.remote.mirror import MirrorFactory
from virtualbricks.remote.tunnel import (
    MONITOR,
    SERIAL,
    Consoles,
    Relay,
    Terminal,
    console_path,
    join,
)
from virtualbricks.tests import (
    FakeLogger,
    isolate,
    reset_settings,
    short_folder,
    use_workspace,
)
from virtualbricks.tests.console import ConsoleTestCase
from virtualbricks.tests.remote.test_mirror import Project


def connected():
    """A relay with a transport that keeps what it writes."""

    relay = Relay()
    relay.makeConnection(StringTransport())
    return relay


def written(relay):
    return relay.transport.value()


class TestRelay(unittest.TestCase):

    def test_both_ways(self):
        one, other = connected(), connected()
        join(one, other)
        one.dataReceived(b"info status\n")
        other.dataReceived(b"VM status: running\n")
        self.assertEqual(written(other), b"info status\n")
        self.assertEqual(written(one), b"VM status: running\n")

    def test_what_comes_before_the_join(self):
        one, other = connected(), connected()
        one.dataReceived(b"help\n")
        self.assertEqual(written(other), b"")
        join(one, other)
        self.assertEqual(written(other), b"help\n")

    def test_what_waits_for_the_connection(self):
        one, other = connected(), Relay()
        join(one, other)
        one.dataReceived(b"QEMU monitor\n")
        other.makeConnection(StringTransport())
        self.assertEqual(written(other), b"QEMU monitor\n")

    def test_one_end_goes(self):
        one, other = connected(), connected()
        join(one, other)
        one.connectionLost(error.ConnectionDone())
        self.assertTrue(other.transport.disconnecting)
        self.successResultOf(one.lost)
        # nothing more to write
        one.write(b"x")
        self.assertEqual(written(one), b"")

    def test_gone_before_the_join(self):
        one, other = connected(), connected()
        one.connectionLost(error.ConnectionDone())
        join(one, other)
        self.assertTrue(other.transport.disconnecting)

    def test_closed_before_it_connects(self):
        one, other = connected(), Relay()
        join(one, other)
        one.dataReceived(b"bye\n")
        one.connectionLost(error.ConnectionDone())
        other.makeConnection(StringTransport())
        # what it had to write, then it closes
        self.assertEqual(written(other), b"bye\n")
        self.assertTrue(other.transport.disconnecting)


class TestConsolePath(ConsoleTestCase):

    def setUp(self):
        super().setUp()
        self.factory.runtime_dir = "/run/vb/ospf"
        self.switch = self.factory.new_brick("switch", "sw1")
        self.vm = self.factory.new_brick("qemu", "vm1")
        self.tap = self.factory.new_brick("tap", "tap1")
        for brick in (self.switch, self.vm, self.tap):
            brick.proc = FakeProcess(brick)

    def test_the_monitor(self):
        self.assertEqual(
            console_path(self.factory, "sw1", MONITOR), "/run/vb/ospf/sw1.mgmt"
        )
        self.assertEqual(
            console_path(self.factory, "vm1", MONITOR), "/run/vb/ospf/vm1.mgmt"
        )

    def test_the_serial_socket(self):
        with self.assertRaises(ValueError) as cm:
            console_path(self.factory, "vm1", SERIAL)
        self.assertEqual(str(cm.exception), "vm1 has no serial socket")
        self.vm.update_config({"serial_socket": True})
        self.assertEqual(
            console_path(self.factory, "vm1", SERIAL),
            "/run/vb/ospf/vm1_serial",
        )
        with self.assertRaises(ValueError):
            console_path(self.factory, "sw1", SERIAL)

    def test_refused(self):
        with self.assertRaises(LookupError):
            console_path(self.factory, "sw9", MONITOR)
        with self.assertRaises(ValueError) as cm:
            console_path(self.factory, "tap1", MONITOR)
        self.assertEqual(str(cm.exception), "tap1 has no control monitor")
        with self.assertRaises(ValueError) as cm:
            console_path(self.factory, "sw1", "keyboard")
        self.assertEqual(str(cm.exception), "The console is monitor or serial")
        self.switch.proc = None
        with self.assertRaises(ValueError) as cm:
            console_path(self.factory, "sw1", MONITOR)
        self.assertEqual(str(cm.exception), "sw1 doesn't run: start it first")


class AttachTestCase(ConsoleTestCase):
    """The Virtualbricks there, and connections to it that agreed on 2."""

    def setUp(self):
        super().setUp()
        self.factory.runtime_dir = "/run/vb/ospf"
        self.logger = FakeLogger()
        self.patch(control, "logger", self.logger)
        self.patch(follower, "logger", FakeLogger())
        self.patch(amp, "_log", FakeLogger())
        self.workspace = use_workspace(self)
        self.workspace.current = Project("/lab/ospf")
        self.patch(follower, "keeper", LogKeeper())
        self.server = control.ControlFactory(
            self.factory, self.clock(), control.AMPControl
        )
        self.vm = self.factory.new_brick("qemu", "vm1")
        self.vm.proc = FakeProcess(self.vm)
        # the consoles there, each a relay with a transport of its own
        self.consoles = []
        self.patch(tunnel, "connect_console", self.connect_console)
        self.pumps = []

    def connect_console(self, reactor, path, relay):
        if path.endswith("broken.mgmt"):
            return defer.fail(error.ConnectError(string="No such file"))
        if path.endswith("buggy.mgmt"):
            return defer.fail(RuntimeError("a bug"))
        relay.makeConnection(StringTransport())
        self.consoles.append((path, relay))
        return defer.succeed(relay)

    def connection(self, agree=True):
        program, server, pump = iosim.connectedServerAndClient(
            lambda: self.server.buildProtocol(None), amp.AMP
        )
        self.pumps.append(pump)
        if agree:
            self.done(program.callRemote(ampwire.Hello, protocols=[2]))
        return program

    def flush(self):
        for pump in self.pumps:
            pump.flush()

    def quiet(self, deferred):
        answer = defer.Deferred()
        deferred.chainDeferred(answer)
        self.flush()
        return answer

    def done(self, deferred):
        return self.successResultOf(self.quiet(deferred))

    def refused(self, deferred, *errors):
        return self.failureResultOf(self.quiet(deferred), *errors)


class TestAttach(AttachTestCase):

    def attach(self, program, brick="vm1", console=MONITOR):
        switched = tunnel._Switched()
        answer = program.callRemote(
            commands.Attach, switched, brick=brick, console=console
        )
        return switched, answer

    def test_the_bytes_both_ways(self):
        program = self.connection()
        switched, answer = self.attach(program)
        self.done(answer)
        [(path, console)] = self.consoles
        self.assertEqual(path, "/run/vb/ospf/vm1.mgmt")
        here = switched.relay
        # what the console says first comes through
        console.dataReceived(b"QEMU 10.0 monitor\n(qemu) ")
        here_end = connected()
        join(here_end, here)
        self.flush()
        self.assertEqual(written(here_end), b"QEMU 10.0 monitor\n(qemu) ")
        here_end.dataReceived(b"info status\n")
        self.flush()
        self.assertEqual(written(console), b"info status\n")
        self.assertIn("attach vm1 monitor", " ".join(self.logger.formatted()))

    def test_the_console_goes(self):
        program = self.connection()
        switched, answer = self.attach(program)
        self.done(answer)
        [(_path, console)] = self.consoles
        console.connectionLost(error.ConnectionDone())
        self.flush()
        # the connection closes, and the end here with it
        self.successResultOf(switched.relay.lost)

    def test_refused(self):
        program = self.connection()
        _switched, answer = self.attach(program, brick="vm9")
        failure = self.refused(answer, ampcommands.NotFound)
        self.assertEqual(failure.getErrorMessage(), "No brick named vm9")
        # the connection goes on, as AMP
        self.vm.proc = None
        _switched, answer = self.attach(program)
        self.refused(answer, ampcommands.BadArgument)
        self.assertEqual(self.consoles, [])

    def test_a_console_it_cant_reach(self):
        self.factory.new_brick("switch", "broken").proc = FakeProcess(None)
        program = self.connection()
        _switched, answer = self.attach(program, brick="broken")
        failure = self.refused(answer, ampwire.CommandFailed)
        self.assertEqual(
            failure.getErrorMessage(),
            "Can't reach the console of broken: An error occurred while"
            " connecting: No such file.",
        )

    def test_a_bug_on_the_way(self):
        tunnel_log = FakeLogger()
        self.patch(tunnel, "logger", tunnel_log)
        self.factory.new_brick("switch", "buggy").proc = FakeProcess(None)
        program = self.connection()
        _switched, answer = self.attach(program, brick="buggy")
        failure = self.refused(answer, ampwire.CommandFailed)
        self.assertEqual(failure.getErrorMessage(), "a bug")
        self.assertEqual(
            tunnel_log.formatted(),
            ["The console of buggy for the windows failed"],
        )

    def test_protocol_2_first(self):
        program = self.connection(agree=False)
        _switched, answer = self.attach(program)
        self.refused(answer, ampcommands.ProtocolNeeded)
        self.assertEqual(self.consoles, [])


class TestTheTerminal(AttachTestCase):
    """The windows' end: the terminal joined to the console there."""

    def setUp(self):
        super().setUp()
        self.windows_log = FakeLogger()
        self.patch(tunnel, "logger", self.windows_log)
        self.made = []

        def connect():
            self.made.append(True)
            return defer.succeed(self.connection())

        self.consoles_here = Consoles(connect, "lab", reactor)

    def test_attach(self):
        terminal = connected()
        terminal.dataReceived(b"info status\n")
        attaching = defer.ensureDeferred(
            self.consoles_here.attach(terminal, "vm1", MONITOR)
        )
        self.done(attaching)
        [(_path, console)] = self.consoles
        self.flush()
        self.assertEqual(written(console), b"info status\n")
        console.dataReceived(b"VM status: running\n")
        self.flush()
        self.assertEqual(written(terminal), b"VM status: running\n")

    def test_refused(self):
        terminal = connected()
        self.vm.proc = None
        attaching = defer.ensureDeferred(
            self.consoles_here.attach(terminal, "vm1", MONITOR)
        )
        self.done(attaching)
        self.assertTrue(terminal.transport.disconnecting)
        self.assertEqual(
            self.windows_log.formatted(),
            [
                "Cannot open the console of vm1: vm1 doesn't run: start it first"
            ],
        )

    def test_it_cant_connect(self):
        def connect():
            return defer.fail(client.Refused("Can't reach lab"))

        consoles = Consoles(connect, "lab", reactor)
        terminal = connected()
        self.done(
            defer.ensureDeferred(consoles.attach(terminal, "vm1", MONITOR))
        )
        self.assertTrue(terminal.transport.disconnecting)
        self.assertEqual(
            self.windows_log.formatted(),
            ["Cannot open the console of vm1: Can't reach lab"],
        )

    def test_one_terminal(self):
        attached = []

        class Here:
            async def attach(self, relay, name, console):
                attached.append((relay, name, console))

        class Port:
            stopped = False

            def stopListening(self):
                self.stopped = True

        terminal = Terminal(Here(), "vm1", MONITOR)
        port = terminal.port = Port()
        relay = terminal.buildProtocol(None)
        self.assertEqual(attached, [(relay, "vm1", MONITOR)])
        # no other connects
        self.assertTrue(port.stopped)
        self.assertIsNone(terminal.port)


class TestConsoles(unittest.TestCase):
    """The socket and the terminal of a console, on this computer."""

    def setUp(self):
        root = isolate(self)
        # short enough for the path of a socket
        self.runtime = short_folder(self)
        os.environ["XDG_RUNTIME_DIR"] = self.runtime
        self.logger = FakeLogger()
        self.patch(tunnel, "logger", self.logger)
        reset_settings(self)
        settings.set_setting("terminal", "/usr/bin/xterm")
        # the VDE programs of this computer, and none else
        self.bin = os.path.join(root, "bin")
        os.makedirs(self.bin)
        os.environ["PATH"] = self.bin
        settings.use_project(settings.ProjectSettings(vde_path=self.bin))
        self.spawned = []
        self.consoles = Consoles(
            lambda: defer.fail(AssertionError("no connection")),
            "lab",
            reactor,
            spawn=lambda *args: self.spawned.append(args),
        )
        self.addCleanup(self.consoles.close)
        self.vm = MirrorFactory(None).new_brick("qemu", "vm1")

    def program(self, name):
        path = os.path.join(self.bin, name)
        with open(path, "w"):
            pass
        os.chmod(path, 0o755)
        return path

    def test_what_it_lacks(self):
        self.assertEqual(
            self.consoles.lacks(self.vm), "needs unixterm of vde2"
        )
        self.program("unixterm")
        self.assertIsNone(self.consoles.lacks(self.vm))

    @defer.inlineCallbacks
    def test_open(self):
        unixterm = self.program("unixterm")
        yield defer.ensureDeferred(self.consoles.open(self.vm))
        [(_protocol, term, args, _env)] = self.spawned
        self.assertEqual(term, "/usr/bin/xterm")
        path = args[-1]
        self.assertEqual(args, ["/usr/bin/xterm", "-e", unixterm, path])
        folder = os.path.join(
            self.runtime, "virtualbricks", f".connect-{os.getpid()}"
        )
        self.assertEqual(path, os.path.join(folder, "1-vm1.monitor"))
        self.assertEqual(stat.S_IMODE(os.stat(folder).st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
        # the terminal connects: one connection, then no other
        attached = []

        async def attach(relay, name, console):
            attached.append((name, console))

        self.consoles.attach = attach
        endpoint = endpoints.UNIXClientEndpoint(reactor, path)
        terminal = yield endpoints.connectProtocol(endpoint, Relay())
        yield deferLater(0.05)
        self.assertEqual(attached, [("vm1", MONITOR)])
        terminal.transport.loseConnection()
        with self.assertRaises(error.ConnectError):
            yield endpoints.connectProtocol(endpoint, Relay())
        self.consoles.close()
        self.assertFalse(os.path.exists(folder))

    @defer.inlineCallbacks
    def test_no_terminal_program(self):
        with self.assertRaises(FileNotFoundError):
            yield defer.ensureDeferred(self.consoles.open(self.vm))
        self.assertEqual(self.spawned, [])


def deferLater(seconds):
    from twisted.internet import task

    return task.deferLater(reactor, seconds, lambda: None)


class TestTheEngine(unittest.TestCase):

    def test_without_consoles(self):
        engine = RemoteEngine(MirrorFactory(None), None, "lab")
        vm = engine.factory.new_brick("qemu", "vm1")
        self.failureResultOf(engine.open_console(vm), NotYet)
        self.assertEqual(
            engine.console_lacks(vm), "Not over a connection, for now"
        )

    def test_with_consoles(self):
        class Here:
            opened = []

            def lacks(self, brick):
                return None

            async def open(self, brick):
                self.opened.append(brick)

        here = Here()
        engine = RemoteEngine(MirrorFactory(None), None, "lab", consoles=here)
        vm = engine.factory.new_brick("qemu", "vm1")
        self.assertIsNone(engine.console_lacks(vm))
        self.successResultOf(engine.open_console(vm))
        self.assertEqual(here.opened, [vm])

    def test_this_machine(self):
        from virtualbricks.engine import LocalEngine

        self.assertIsNone(LocalEngine(None).console_lacks(None))
