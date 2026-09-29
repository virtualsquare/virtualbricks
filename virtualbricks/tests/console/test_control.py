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

"""The control socket: the Virtualbricks that listens, its protocol."""

import os
import stat

from twisted.internet import defer, endpoints, reactor
from twisted.internet.testing import StringTransport
from twisted.protocols import amp, basic
from twisted.test import iosim

from virtualbricks import __version__, locations, locks
from virtualbricks.console import ampwire, control, wire
from virtualbricks.console.command import Arg, CommandError, command
from virtualbricks.tests import (
    FakeLogger,
    make_socket,
    short_folder,
    use_workspace,
)
from virtualbricks.tests.console import ConsoleTestCase, own_commands


class Project:
    name = "lab1"


class TestProtocol(ConsoleTestCase):
    """A connection, on a transport that keeps what is written."""

    def setUp(self):
        super().setUp()
        self.factory.runtime_dir = "/run/vb"
        self.logger = FakeLogger()
        self.patch(control, "logger", self.logger)
        use_workspace(self).current = Project()
        self.server = control.ControlFactory(self.factory, self.clock())
        self.connection, self.transport = self.connect()

    def connect(self):
        connection = self.server.buildProtocol(None)
        transport = StringTransport()
        connection.makeConnection(transport)
        return connection, transport

    def send(self, *messages, connection=None):
        connection = connection or self.connection
        for message in messages:
            if isinstance(message, dict):
                message = wire.encode(message)
            connection.dataReceived(message)

    def received(self, transport=None):
        """The messages written since the last call."""

        transport = transport or self.transport
        lines = transport.value().splitlines()
        transport.clear()
        return [wire.decode(line) for line in lines]

    def declare(self):
        """Commands of the test's own: wait NAME, and cwd."""

        own_commands(self)
        self.waiting = {}

        @command(None, "wait", Arg("NAME"), help="Wait")
        def wait(context, name):
            self.waiting[name] = done = defer.Deferred()
            return done

        @command(None, "cwd", help="The folder")
        def cwd(context):
            return [str(context.cwd)]

    def test_the_greeting(self):
        self.assertEqual(
            self.received(),
            [
                {
                    "protocol": 1,
                    "version": __version__,
                    "pid": os.getpid(),
                    "project": "lab1",
                }
            ],
        )

    def test_a_command(self):
        self.received()
        self.send(b'{"line": "brick new switch"}\n')
        self.assertEqual(self.received(), [{"ok": True, "lines": ["sw1"]}])
        self.assertEqual([b.name for b in self.factory.bricks], ["sw1"])
        self.assertEqual(
            self.logger.formatted(),
            ["Command from the control socket: brick new switch"],
        )

    def test_a_command_that_fails(self):
        self.received()
        self.send(wire.request("brick start vm9"))
        self.assertEqual(
            self.received(),
            [{"ok": False, "lines": [], "error": "No brick named vm9"}],
        )
        self.assertEqual(
            self.logger.formatted()[1],
            "The command from the control socket failed: No brick named vm9",
        )

    def test_what_it_did_first(self):
        own_commands(self)

        @command(None, "half", help="Half")
        def half(context):
            raise CommandError("vm2: no image", ["vm1 runs"])

        self.received()
        self.send(wire.request("half"))
        self.assertEqual(
            self.received(), [wire.refusal("vm2: no image", ["vm1 runs"])]
        )

    def test_not_a_request(self):
        self.received()
        self.send(b"status\n", b"\n", b"  \n", wire.request("status"))
        # blank lines are skipped; the connection stays
        self.assertEqual(
            self.received(),
            [
                wire.refusal(
                    'Not a request: a line of JSON, as {"line": "brick list"}'
                ),
                wire.answer(["Nothing runs"]),
            ],
        )

    def test_a_line_too_long(self):
        self.send(b"x" * (wire.MAX_LINE + 1))
        self.assertTrue(self.transport.disconnecting)

    def test_the_folder_of_the_request(self):
        self.declare()
        self.received()
        self.send(wire.request("cwd", "/srv/labs"), wire.request("cwd"))
        self.assertEqual(
            self.received(),
            [wire.answer(["/srv/labs"]), wire.answer(["None"])],
        )

    def test_in_order(self):
        self.declare()
        self.received()
        self.send(wire.request("wait a"), wire.request("wait b"))
        self.assertEqual(list(self.waiting), ["a"])
        # another connection doesn't wait for this one
        other, transport = self.connect()
        self.received(transport)
        self.send(wire.request("wait c"), connection=other)
        self.assertEqual(list(self.waiting), ["a", "c"])
        self.waiting["a"].callback(["a done"])
        self.assertEqual(list(self.waiting), ["a", "c", "b"])
        self.waiting["b"].callback(["b done"])
        self.assertEqual(
            self.received(), [wire.answer(["a done"]), wire.answer(["b done"])]
        )
        self.assertEqual(self.received(transport), [])

    def test_lost_while_it_runs(self):
        self.declare()
        self.send(wire.request("wait a"), wire.request("wait b"))
        self.connection.connectionLost(None)
        self.assertEqual(self.server.connections, set())
        # the command goes on; its answer, and the requests after it, drop
        self.transport.clear()
        self.waiting["a"].callback(["a done"])
        self.assertEqual(self.transport.value(), b"")
        self.assertEqual(list(self.waiting), ["a"])

    def test_closed_after_the_last_answer(self):
        self.received()
        self.send(wire.request("status"))
        closed = self.server.close()
        # the transport writes what it has, then closes
        self.assertTrue(self.transport.disconnecting)
        self.assertEqual(self.received(), [wire.answer(["Nothing runs"])])
        self.assertNoResult(closed)
        self.connection.connectionLost(None)
        self.successResultOf(closed)

    def test_a_client_that_doesnt_read(self):
        closed = self.server.close()
        self.clock().advance(control.CLOSE_TIMEOUT - 0.1)
        self.assertFalse(self.transport.disconnected)
        self.clock().advance(0.1)
        # StringTransport doesn't call connectionLost: the reactor would
        self.assertTrue(self.transport.disconnecting)
        self.connection.connectionLost(None)
        self.successResultOf(closed)

    def test_nothing_to_close(self):
        self.connection.connectionLost(None)
        self.successResultOf(self.server.close())


class TestAMP(ConsoleTestCase):
    """A connection of the AMP socket, to a program on fake transports."""

    def setUp(self):
        super().setUp()
        self.factory.runtime_dir = "/run/vb"
        self.logger = FakeLogger()
        self.patch(control, "logger", self.logger)
        self.amp_log = FakeLogger()
        self.patch(amp, "_log", self.amp_log)
        self.workspace = use_workspace(self)
        self.workspace.current = Project()
        self.server = control.ControlFactory(
            self.factory, self.clock(), control.AMPControl
        )
        self.program, self.connection, self.pump = self.connect()

    def connect(self):
        """A program, the connection that answers it, and their pump."""

        return iosim.connectedServerAndClient(
            lambda: self.server.buildProtocol(None), amp.AMP
        )

    def call(self, command, program=None, pump=None, **arguments):
        """The answer to command, once the pump is done."""

        # AMP drops a connection whose failed call has no errback when the
        # answer comes: the answer has its callbacks first
        answer = defer.Deferred()
        called = (program or self.program).callRemote(command, **arguments)
        called.chainDeferred(answer)
        (pump or self.pump).flush()
        return answer

    def declare(self):
        """Commands of the test's own: wait NAME, cwd and long."""

        own_commands(self)
        self.waiting = {}

        @command(None, "wait", Arg("NAME"), help="Wait")
        def wait(context, name):
            self.waiting[name] = done = defer.Deferred()
            return done

        @command(None, "cwd", help="The folder")
        def cwd(context):
            return [str(context.cwd)]

        @command(None, "long", help="An answer too long")
        def long(context):
            return ["x" * 1000] * 70

    def test_hello(self):
        hello = {
            "protocol": 1,
            "version": __version__,
            "pid": os.getpid(),
            "project": "lab1",
        }
        self.assertEqual(self.successResultOf(self.call(ampwire.Hello)), hello)
        self.workspace.current = None
        self.assertEqual(
            self.successResultOf(self.call(ampwire.Hello)),
            {**hello, "project": None},
        )

    def test_a_command(self):
        answer = self.call(ampwire.Run, line="brick new switch")
        self.assertEqual(self.successResultOf(answer), {"lines": ["sw1"]})
        self.assertEqual([b.name for b in self.factory.bricks], ["sw1"])
        self.assertEqual(
            self.logger.formatted(),
            ["Command from the AMP socket: brick new switch"],
        )
        # AMP's own lines for each connection are left out; the program's
        # are its own
        self.assertEqual(
            [
                line
                for line in self.amp_log.formatted()
                if "AMPControl" in line
            ],
            [],
        )

    def test_a_command_that_fails(self):
        failure = self.failureResultOf(
            self.call(ampwire.Run, line="brick start vm9"),
            ampwire.CommandFailed,
        )
        self.assertEqual(str(failure.value), "No brick named vm9")
        self.assertEqual(
            self.logger.formatted()[1],
            "The command from the AMP socket failed: No brick named vm9",
        )

    def test_what_it_did_first(self):
        # dropped: the program asks status
        own_commands(self)

        @command(None, "half", help="Half")
        def half(context):
            raise CommandError("vm2: no image", ["vm1 runs"])

        failure = self.failureResultOf(
            self.call(ampwire.Run, line="half"), ampwire.CommandFailed
        )
        self.assertEqual(str(failure.value), "vm2: no image")

    def test_the_folder_of_the_request(self):
        self.declare()
        answer = self.call(ampwire.Run, line="cwd", cwd="/srv/labs")
        self.assertEqual(
            self.successResultOf(answer), {"lines": ["/srv/labs"]}
        )
        answer = self.call(ampwire.Run, line="cwd")
        self.assertEqual(self.successResultOf(answer), {"lines": ["None"]})
        failure = self.failureResultOf(
            self.call(ampwire.Run, line="cwd", cwd="labs"),
            ampwire.CommandFailed,
        )
        self.assertEqual(
            str(failure.value), 'Not a request: "cwd" is not an absolute path'
        )

    def test_an_answer_too_long(self):
        self.declare()
        failure = self.failureResultOf(
            self.call(ampwire.Run, line="long"), ampwire.AnswerTooLong
        )
        self.assertEqual(
            str(failure.value),
            "The command was done, but its answer, 70140 bytes, is longer than"
            " the 65535 that AMP carries; a text socket carries it",
        )
        self.assertEqual(
            self.logger.formatted()[1],
            "The answer to the AMP socket is 70140 bytes, longer than AMP"
            " carries",
        )
        # the connection stays
        answer = self.call(ampwire.Run, line="cwd")
        self.assertEqual(self.successResultOf(answer), {"lines": ["None"]})

    def test_in_order(self):
        self.declare()
        first = self.call(ampwire.Run, line="wait a")
        second = self.call(ampwire.Run, line="wait b")
        self.assertEqual(list(self.waiting), ["a"])
        # another connection doesn't wait for this one
        program, _, pump = self.connect()
        self.call(ampwire.Run, program, pump, line="wait c")
        self.assertEqual(list(self.waiting), ["a", "c"])
        self.waiting["a"].callback(["a done"])
        self.pump.flush()
        self.assertEqual(self.successResultOf(first), {"lines": ["a done"]})
        self.assertEqual(list(self.waiting), ["a", "c", "b"])
        self.assertNoResult(second)
        self.waiting["b"].callback(["b done"])
        self.pump.flush()
        self.assertEqual(self.successResultOf(second), {"lines": ["b done"]})

    def test_lost_while_it_runs(self):
        self.declare()
        first = self.call(ampwire.Run, line="wait a")
        self.call(ampwire.Run, line="wait b")
        self.program.transport.loseConnection()
        self.pump.flush()
        self.assertEqual(self.server.connections, set())
        self.failureResultOf(first)
        # the command goes on; its answer, and the requests after it, drop
        self.waiting["a"].callback(["a done"])
        self.assertEqual(list(self.waiting), ["a"])

    def test_closed_after_the_last_answer(self):
        answer = self.program.callRemote(ampwire.Run, line="status")
        # the request arrives, and its answer waits to be written
        self.pump.pump()
        closed = self.server.close()
        self.assertNoResult(closed)
        self.pump.flush()
        self.assertEqual(
            self.successResultOf(answer), {"lines": ["Nothing runs"]}
        )
        self.successResultOf(closed)


class Reactor:
    """The reactor of the tests, whose shutdown triggers are only kept."""

    def __init__(self):
        self.triggers = []

    def listenUNIX(self, *args, **kwargs):
        return reactor.listenUNIX(*args, **kwargs)

    def callLater(self, *args, **kwargs):
        return reactor.callLater(*args, **kwargs)

    def addSystemEventTrigger(self, phase, event, callable, *args):
        self.triggers.append((phase, event, callable))


class Client(basic.LineOnlyReceiver):
    """A client of the tests, over a real socket."""

    delimiter = b"\n"

    def __init__(self):
        self.messages = defer.DeferredQueue()
        self.lost = defer.Deferred()

    def lineReceived(self, line):
        self.messages.put(wire.decode(line))

    def connectionLost(self, reason):
        self.lost.callback(None)


class AMPProgram(amp.AMP):
    """A program of the tests, over a real socket."""

    def __init__(self):
        super().__init__()
        self.lost = defer.Deferred()

    def connectionLost(self, reason):
        super().connectionLost(reason)
        self.lost.callback(None)


class TestListen(ConsoleTestCase):
    """The socket, in a runtime folder of the test."""

    def setUp(self):
        super().setUp()
        self.factory.runtime_dir = "/run/vb"
        self.logger = FakeLogger()
        self.patch(control, "logger", self.logger)
        use_workspace(self)
        folder = short_folder(self)
        os.environ["XDG_RUNTIME_DIR"] = folder
        locations.ensure_private_dir(locations.runtime_dir())
        self.path = locations.control_socket()
        self.lock_file = locations.control_lock_file(self.path)
        self.reactor = Reactor()

    def listen(self, path=None, protocol=wire.TEXT):
        socket = None if path is None else wire.Socket(path, protocol)
        found = control.listen(self.factory, socket, self.reactor)
        if found is not None:
            self.addCleanup(found.close)
        return found

    def connect(self, path):
        endpoint = endpoints.UNIXClientEndpoint(reactor, path)
        return endpoints.connectProtocol(endpoint, Client())

    def assertListening(self, found, path):
        self.assertEqual(found.path, path)
        mode = os.stat(path).st_mode
        self.assertTrue(stat.S_ISSOCK(mode))
        self.assertEqual(stat.S_IMODE(mode), 0o600)
        self.assertIsNone(locks.hold(locations.control_lock_file(path)))
        self.assertIn(
            ("before", "shutdown", found.close), self.reactor.triggers
        )

    @defer.inlineCallbacks
    def test_listen(self):
        found = self.listen()
        self.assertListening(found, self.path)
        self.assertEqual(
            self.logger.formatted(),
            [f"Listening on {self.path}, protocol text"],
        )
        client = yield self.connect(self.path)
        greeting = yield client.messages.get()
        self.assertEqual(greeting["pid"], os.getpid())
        client.sendLine(wire.encode(wire.request("brick new switch"))[:-1])
        answer = yield client.messages.get()
        self.assertEqual(answer, wire.answer(["sw1"]))
        # the end: the connection closes, the socket goes, the lock is free
        yield found.close()
        yield client.lost
        self.assertFalse(os.path.exists(self.path))
        lock = locks.hold(self.lock_file)
        self.assertIsNotNone(lock)
        lock.unlock()

    @defer.inlineCallbacks
    def test_amp(self):
        path = os.path.join(os.path.dirname(self.path), ".control.amp")
        found = self.listen(path, wire.AMP)
        self.assertListening(found, path)
        self.assertEqual(
            self.logger.formatted(), [f"Listening on {path}, protocol amp"]
        )
        endpoint = endpoints.UNIXClientEndpoint(reactor, path)
        program = yield endpoints.connectProtocol(endpoint, AMPProgram())
        hello = yield program.callRemote(ampwire.Hello)
        self.assertEqual(hello["pid"], os.getpid())
        answer = yield program.callRemote(ampwire.Run, line="brick new switch")
        self.assertEqual(answer, {"lines": ["sw1"]})
        # the end: the connection closes, the socket goes, the lock is free
        yield found.close()
        yield program.lost
        self.assertFalse(os.path.exists(path))
        locks.hold(locations.control_lock_file(path)).unlock()

    def test_both(self):
        # a text socket and an AMP one, a lock each; a crash left the second
        path = os.path.join(short_folder(self), "lab.amp")
        make_socket(path)
        self.assertListening(self.listen(), self.path)
        self.assertListening(self.listen(path, wire.AMP), path)
        # another Virtualbricks goes without both
        self.assertIsNone(self.listen())
        self.assertIsNone(self.listen(path, wire.AMP))
        self.assertEqual(
            self.logger.formatted()[2:],
            [
                f"Process {os.getpid()} answers on {self.path}; this one"
                " doesn't",
                f"Process {os.getpid()} answers on {path}; this one doesn't",
            ],
        )

    def test_another_path(self):
        path = os.path.join(short_folder(self), "lab.sock")
        self.assertListening(self.listen(path), path)
        self.assertTrue(os.path.isfile(path + ".lock"))
        self.assertFalse(os.path.exists(self.path))

    def test_one_listens(self):
        first = self.listen()
        self.assertIsNone(self.listen())
        self.assertEqual(
            self.logger.formatted()[1],
            f"Process {os.getpid()} answers on {self.path}; this one"
            " doesn't",
        )
        self.assertEqual(self.logger.levels(), ["info", "info"])
        # the first one still does
        self.assertTrue(os.path.exists(first.path))

    def test_left_by_a_crash(self):
        make_socket(self.path)
        self.assertListening(self.listen(), self.path)

    def test_not_a_socket(self):
        with open(self.path, "w") as fp:
            fp.write("notes\n")
        self.assertIsNone(self.listen())
        with open(self.path) as fp:
            self.assertEqual(fp.read(), "notes\n")
        self.assertEqual(
            self.logger.formatted(),
            [f"{self.path} isn't a socket: no control socket"],
        )
        self.assertEqual(self.logger.levels(), ["warn"])
        # the lock is free again
        locks.hold(self.lock_file).unlock()

    def test_a_folder_others_can_write_in(self):
        folder = os.path.dirname(self.path)
        os.chmod(folder, 0o777)
        self.assertIsNone(self.listen())
        self.assertEqual(
            self.logger.formatted(),
            [
                f"Others can write in the runtime folder {folder}:"
                " no control socket"
            ],
        )
        self.assertFalse(os.path.exists(self.lock_file))

    def test_too_long(self):
        path = os.path.join(os.path.dirname(self.path), "a" * 107)
        self.assertIsNone(self.listen(path))
        self.assertEqual(self.logger.levels(), ["warn"])
