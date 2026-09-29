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

import io
import os
import stat

from twisted.internet import address, defer, endpoints, reactor, task, threads
from twisted.internet.testing import StringTransport
from twisted.protocols import amp, basic
from twisted.test import iosim

from virtualbricks import __version__, locations, locks
from virtualbricks.console import ampwire, client, control, wire
from virtualbricks.console.command import Arg, CommandError, command
from virtualbricks.tests import (
    DATA,
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


TOKEN = "0123456789abcdef"
TCP = wire.parse_socket("tcp:8765")


def prove(challenge, token=TOKEN):
    """The client's answer to the first line, and the server's proof."""

    mine = wire.new_nonce()
    nonce = challenge["nonce"]
    return (
        wire.token_proof(mine, wire.proof(token, "client", nonce, mine)),
        wire.proof(token, "server", nonce, mine),
    )


class TestTheToken(TestProtocol):
    """A connection of a tcp socket, whose client proves the token first."""

    def setUp(self):
        super().setUp()
        self.server = control.ControlFactory(
            self.factory, self.clock(), socket=TCP, token=TOKEN
        )
        self.connection, self.transport = self.connect()

    def connect(self):
        connection = self.server.buildProtocol(None)
        peer = address.IPv4Address("TCP", "127.0.0.1", 50412)
        transport = StringTransport(peerAddress=peer)
        connection.makeConnection(transport)
        return connection, transport

    def proved(self, challenge=None):
        """Prove the token; the greeting, checked."""

        if challenge is None:
            [challenge] = self.received()
        answer, server_proof = prove(challenge)
        self.send(answer)
        [greeting] = self.received()
        self.assertEqual(greeting.pop("proof"), server_proof)
        return greeting

    def test_the_greeting(self):
        [challenge] = self.received()
        self.assertEqual(challenge, wire.challenge(challenge["nonce"]))
        self.assertRegex(challenge["nonce"], "^[0-9a-f]{64}$")
        self.assertEqual(
            self.proved(challenge),
            {
                "protocol": 1,
                "version": __version__,
                "pid": os.getpid(),
                "project": "lab1",
            },
        )
        self.assertEqual(
            self.logger.formatted(),
            ["127.0.0.1 port 50412 connected to tcp port 8765 with the token"],
        )
        # another connection, another nonce
        other, transport = self.connect()
        [again] = self.received(transport)
        self.assertNotEqual(again["nonce"], challenge["nonce"])

    def test_a_command(self):
        self.proved()
        self.send(wire.request("brick new switch"))
        self.assertEqual(self.received(), [wire.answer(["sw1"])])
        self.assertEqual(
            self.logger.formatted()[1],
            "Command from 127.0.0.1 port 50412: brick new switch",
        )

    def test_a_command_that_fails(self):
        self.proved()
        self.send(wire.request("brick start vm9"))
        self.assertEqual(self.received(), [wire.refusal("No brick named vm9")])
        self.assertEqual(
            self.logger.formatted()[2],
            "The command from 127.0.0.1 port 50412 failed: No brick named"
            " vm9",
        )

    def test_a_wrong_token(self):
        [challenge] = self.received()
        answer, _ = prove(challenge, token="fedcba9876543210")
        self.send(answer, wire.request("brick new switch"))
        self.assertEqual(self.received(), [wire.refusal("Wrong token")])
        self.assertTrue(self.transport.disconnecting)
        self.assertEqual(self.factory.bricks, [])
        self.assertEqual(
            self.logger.formatted(),
            ["127.0.0.1 port 50412 on tcp port 8765: wrong token"],
        )
        self.assertEqual(self.logger.levels(), ["warn"])

    def test_the_proof_of_another_nonce(self):
        # a proof given to another end, which chose its nonce
        self.received()
        answer, _ = prove({"nonce": wire.new_nonce()})
        self.send(answer)
        self.assertEqual(self.received(), [wire.refusal("Wrong token")])

    def test_a_request_first(self):
        self.received()
        self.send(
            b"\n", wire.request("brick new switch"), wire.request("status")
        )
        self.assertEqual(
            self.received(),
            [wire.refusal('Not a proof: "nonce" and "proof" come first')],
        )
        self.assertTrue(self.transport.disconnecting)
        self.assertEqual(self.factory.bricks, [])
        self.assertEqual(
            self.logger.formatted(),
            ["127.0.0.1 port 50412 on tcp port 8765: not a proof"],
        )

    def test_the_proof_and_a_request_together(self):
        [challenge] = self.received()
        answer, _ = prove(challenge)
        self.connection.dataReceived(
            wire.encode(answer) + wire.encode(wire.request("status"))
        )
        greeting, answer = self.received()
        self.assertEqual(greeting["pid"], os.getpid())
        self.assertEqual(answer, wire.answer(["Nothing runs"]))

    def test_ten_seconds(self):
        self.received()
        self.clock().advance(wire.PROOF_TIMEOUT - 0.1)
        self.assertFalse(self.transport.disconnecting)
        self.clock().advance(0.1)
        self.assertEqual(
            self.received(), [wire.refusal("No proof in 10 seconds")]
        )
        self.assertTrue(self.transport.disconnecting)
        self.assertEqual(
            self.logger.formatted(),
            ["127.0.0.1 port 50412 on tcp port 8765: no proof in 10 seconds"],
        )
        self.assertEqual(self.logger.levels(), ["warn"])

    def test_proved_in_time(self):
        self.proved()
        self.clock().advance(wire.PROOF_TIMEOUT)
        self.assertFalse(self.transport.disconnecting)
        self.assertEqual(self.clock().getDelayedCalls(), [])

    def test_lost_before_the_proof(self):
        self.connection.connectionLost(None)
        self.assertEqual(self.clock().getDelayedCalls(), [])

    def test_closed_after_the_last_answer(self):
        self.proved()
        self.send(wire.request("status"))
        closed = self.server.close()
        self.assertTrue(self.transport.disconnecting)
        self.assertEqual(self.received(), [wire.answer(["Nothing runs"])])
        self.connection.connectionLost(None)
        self.successResultOf(closed)

    def test_nothing_to_close(self):
        self.connection.connectionLost(None)
        self.successResultOf(self.server.close())

    def test_a_client_that_doesnt_read(self):
        self.proved()
        super().test_a_client_that_doesnt_read()

    def test_not_a_request(self):
        self.proved()
        self.send(b"status\n", wire.request("status"))
        self.assertEqual(
            self.received(),
            [
                wire.refusal(
                    'Not a request: a line of JSON, as {"line": "brick list"}'
                ),
                wire.answer(["Nothing runs"]),
            ],
        )

    # the tests of the plain socket, once the token is proved
    def test_what_it_did_first(self):
        self.proved()
        super().test_what_it_did_first()

    def test_the_folder_of_the_request(self):
        self.proved()
        super().test_the_folder_of_the_request()

    def test_in_order(self):
        self.proved()
        # the other connection proves it too
        connect = self.connect

        def proving():
            connection, transport = connect()
            [challenge] = self.received(transport)
            self.send(prove(challenge)[0], connection=connection)
            return connection, transport

        self.connect = proving
        super().test_in_order()

    def test_lost_while_it_runs(self):
        self.proved()
        super().test_lost_while_it_runs()


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


class TestAMPToken(ConsoleTestCase):
    """A connection of an AMP socket on tcp, whose program proves the token."""

    def setUp(self):
        super().setUp()
        self.factory.runtime_dir = "/run/vb"
        self.logger = FakeLogger()
        self.patch(control, "logger", self.logger)
        self.patch(amp, "_log", FakeLogger())
        use_workspace(self).current = Project()
        self.server = control.ControlFactory(
            self.factory,
            self.clock(),
            control.AMPControl,
            wire.parse_socket("tcp:8766:protocol=amp"),
            TOKEN,
        )
        self.program, self.connection, self.pump = self.connect()

    def connect(self):
        peer = address.IPv4Address("TCP", "127.0.0.1", 50412)

        def transport(protocol):
            return iosim.FakeTransport(protocol, True, peerAddress=peer)

        return iosim.connectedServerAndClient(
            lambda: self.server.buildProtocol(None),
            amp.AMP,
            serverTransportFactory=transport,
        )

    def call(self, command, **arguments):
        # the answer has its callbacks before it comes, see TestAMP.call
        answer = defer.Deferred()
        self.program.callRemote(command, **arguments).chainDeferred(answer)
        self.pump.flush()
        return answer

    def authenticate(self, token=TOKEN):
        done = defer.ensureDeferred(ampwire.authenticate(self.program, token))
        self.pump.flush()
        return done

    def assertClosed(self):
        # the error goes first, then the connection closes
        self.assertIsNotNone(self.connection.transport)
        self.clock().advance(0)
        self.pump.flush()
        self.assertIsNone(self.connection.transport)

    def test_the_proof(self):
        self.successResultOf(self.authenticate())
        hello = self.successResultOf(self.call(ampwire.Hello))
        self.assertEqual(hello["project"], "lab1")
        answer = self.successResultOf(
            self.call(ampwire.Run, line="brick new switch")
        )
        self.assertEqual(answer, {"lines": ["sw1"]})
        self.assertEqual(
            self.logger.formatted(),
            [
                "127.0.0.1 port 50412 connected to tcp port 8766 with the"
                " token",
                "Command from 127.0.0.1 port 50412: brick new switch",
            ],
        )
        # no timer left to close it
        self.assertEqual(self.clock().getDelayedCalls(), [])

    def test_a_command_that_fails(self):
        self.successResultOf(self.authenticate())
        failure = self.failureResultOf(
            self.call(ampwire.Run, line="brick start vm9"),
            ampwire.CommandFailed,
        )
        self.assertEqual(failure.getErrorMessage(), "No brick named vm9")
        self.assertEqual(
            self.logger.formatted()[-1],
            "The command from 127.0.0.1 port 50412 failed: No brick named"
            " vm9",
        )

    def test_before_the_proof(self):
        for amp_command, arguments in (
            (ampwire.Hello, {}),
            (ampwire.Run, {"line": "brick new switch"}),
        ):
            failure = self.failureResultOf(
                self.call(amp_command, **arguments), ampwire.TokenNeeded
            )
            self.assertEqual(
                failure.getErrorMessage(),
                "Prove the token first: Challenge, then Authenticate",
            )
        self.assertEqual(self.factory.bricks, [])
        # the connection stays, for the proof
        self.successResultOf(self.authenticate())

    def test_a_wrong_token(self):
        failure = self.failureResultOf(
            self.authenticate("fedcba9876543210"), ampwire.WrongToken
        )
        self.assertEqual(failure.getErrorMessage(), "Wrong token")
        self.assertClosed()
        self.assertEqual(
            self.logger.formatted(),
            ["127.0.0.1 port 50412 on tcp port 8766: wrong token"],
        )
        self.assertEqual(self.logger.levels(), ["warn"])

    def test_without_the_challenge(self):
        nonce = wire.new_nonce()
        failure = self.failureResultOf(
            self.call(ampwire.Authenticate, nonce=nonce, proof="8e02"),
            ampwire.WrongToken,
        )
        self.assertEqual(
            failure.getErrorMessage(), "Challenge first, then Authenticate"
        )
        self.assertClosed()
        self.assertEqual(
            self.logger.formatted(),
            ["127.0.0.1 port 50412 on tcp port 8766: not a proof"],
        )

    def test_ten_seconds(self):
        self.clock().advance(wire.PROOF_TIMEOUT - 0.1)
        self.pump.flush()
        self.assertIsNotNone(self.connection.transport)
        self.clock().advance(0.1)
        self.pump.flush()
        self.assertIsNone(self.connection.transport)
        self.assertEqual(
            self.logger.formatted(),
            ["127.0.0.1 port 50412 on tcp port 8766: no proof in 10 seconds"],
        )

    def test_lost_before_the_proof(self):
        self.program.transport.loseConnection()
        self.pump.flush()
        self.assertEqual(self.clock().getDelayedCalls(), [])

    def test_no_token_here(self):
        # a socket without a token has nothing to prove
        self.server.token = None
        self.program, self.connection, self.pump = self.connect()
        for amp_command, arguments in (
            (ampwire.Challenge, {}),
            (ampwire.Authenticate, {"nonce": "c" * 64, "proof": "8e02"}),
        ):
            failure = self.failureResultOf(
                self.call(amp_command, **arguments), ampwire.WrongToken
            )
            self.assertEqual(
                failure.getErrorMessage(), "This socket takes no token"
            )
        self.successResultOf(self.call(ampwire.Hello))


TLS = os.path.join(DATA, "tls")


def tls_file(name):
    return os.path.join(TLS, name)


class Reactor:
    """The reactor of the tests, whose shutdown triggers are only kept."""

    def __init__(self):
        self.triggers = []

    def listenUNIX(self, *args, **kwargs):
        return reactor.listenUNIX(*args, **kwargs)

    def listenTCP(self, *args, **kwargs):
        return reactor.listenTCP(*args, **kwargs)

    def listenSSL(self, *args, **kwargs):
        return reactor.listenSSL(*args, **kwargs)

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


class ListenTestCase(ConsoleTestCase):
    """A socket on a free port of this machine."""

    def setUp(self):
        super().setUp()
        self.factory.runtime_dir = "/run/vb"
        self.logger = FakeLogger()
        self.patch(control, "logger", self.logger)
        use_workspace(self)
        self.reactor = Reactor()
        self.token_file = locations.token_file()

    def listen(self, port=0, **fields):
        socket = wire.Socket(None, wire.TEXT, "tcp", "127.0.0.1", port)
        found = control.listen(
            self.factory, socket._replace(**fields), self.reactor
        )
        if found is not None:
            self.addCleanup(found.close)
        return found

    def connect(self, found):
        endpoint = endpoints.TCP4ClientEndpoint(
            reactor, "127.0.0.1", found.socket.port
        )
        return endpoints.connectProtocol(endpoint, Client())

    def write_token(self, path, mode=0o600):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as file:
            file.write(TOKEN + "\n")
        os.chmod(path, mode)

    def command(self, target, *words, **fields):
        """
        --command to target, a wire.Socket or the Control of a tcp socket,
        in a thread: its status, output and errors.
        """

        if isinstance(target, control.Control):
            target = target.socket
        stdout, stderr = io.StringIO(), io.StringIO()
        done = threads.deferToThread(
            client.main,
            list(words),
            target._replace(**fields),
            io.StringIO(),
            stdout,
            stderr,
        )
        done.addCallback(
            lambda status: (status, stdout.getvalue(), stderr.getvalue())
        )
        return done


class TestListenTcp(ListenTestCase):
    """A tcp socket, on a free port of this machine."""

    @defer.inlineCallbacks
    def test_listen(self):
        found = self.listen()
        # the token is made, only yours, and stays for the next start
        token = wire.read_token(self.token_file)
        self.assertEqual(stat.S_IMODE(os.stat(self.token_file).st_mode), 0o600)
        port = found.socket.port
        self.assertNotEqual(port, 0)
        self.assertEqual(
            self.logger.formatted(),
            [
                f"Made the token {self.token_file}",
                f"Listening on tcp 127.0.0.1 port {port}, protocol text, with"
                f" the token of {self.token_file}",
            ],
        )
        self.assertIn(
            ("before", "shutdown", found.close), self.reactor.triggers
        )
        client = yield self.connect(found)
        challenge = yield client.messages.get()
        answer, server_proof = prove(challenge, token)
        client.sendLine(wire.encode(answer)[:-1])
        greeting = yield client.messages.get()
        self.assertEqual(greeting["proof"], server_proof)
        client.sendLine(wire.encode(wire.request("brick new switch"))[:-1])
        answer = yield client.messages.get()
        self.assertEqual(answer, wire.answer(["sw1"]))
        yield found.close()
        yield client.lost
        self.assertEqual(wire.read_token(self.token_file), token)

    @defer.inlineCallbacks
    def test_command(self):
        # --command proves the token, and sends the folder: this machine
        found = self.listen()
        own_commands(self)

        @command(None, "cwd", help="The folder")
        def cwd(context):
            return [str(context.cwd)]

        result = yield self.command(found, "cwd")
        self.assertEqual(result, (client.DONE, f"{os.getcwd()}\n", ""))

    @defer.inlineCallbacks
    def test_command_with_another_token(self):
        found = self.listen()
        other = os.path.join(self.mktemp(), "token")
        self.write_token(other)
        result = yield self.command(found, "status", token_file=other)
        self.assertEqual(
            result,
            (
                client.UNANSWERED,
                "",
                f"The Virtualbricks on 127.0.0.1 port {found.socket.port} has"
                " another token\n",
            ),
        )
        self.assertEqual(self.logger.levels(), ["info", "info", "warn"])

    @defer.inlineCallbacks
    def test_amp(self):
        found = self.listen(protocol=wire.AMP)
        endpoint = endpoints.TCP4ClientEndpoint(
            reactor, "127.0.0.1", found.socket.port
        )
        program = yield endpoints.connectProtocol(endpoint, AMPProgram())
        token = wire.read_token(self.token_file)
        yield defer.ensureDeferred(ampwire.authenticate(program, token))
        answer = yield program.callRemote(ampwire.Run, line="brick new switch")
        self.assertEqual(answer, {"lines": ["sw1"]})
        yield found.close()
        yield program.lost

    def test_a_token_of_its_own(self):
        path = os.path.join(self.mktemp(), "lab1.token")
        os.makedirs(os.path.dirname(path))
        found = self.listen(token_file=path)
        self.assertIsNotNone(found)
        wire.read_token(path)
        self.assertFalse(os.path.exists(self.token_file))

    def test_a_token_that_others_can_read(self):
        self.write_token(self.token_file, 0o644)
        self.assertIsNone(self.listen())
        self.assertEqual(
            self.logger.formatted(),
            [
                f"tcp 127.0.0.1 port 0: Others can read or change"
                f" {self.token_file}: chmod 600 {self.token_file}: no control"
                " socket"
            ],
        )
        self.assertEqual(self.logger.levels(), ["warn"])

    def test_a_port_in_use(self):
        first = self.listen()
        port = first.socket.port
        self.assertIsNone(self.listen(port))
        self.assertEqual(
            self.logger.formatted()[-1],
            f"tcp 127.0.0.1 port {port}: Address already in use: no control"
            " socket",
        )
        self.assertEqual(self.logger.levels()[-1], "warn")


class TestListenSsl(ListenTestCase):
    """An ssl socket, with the certificates of tests/data/tls."""

    def listen(self, port=0, **fields):
        socket = wire.Socket(
            None,
            wire.TEXT,
            "ssl",
            "127.0.0.1",
            port,
            private_key=tls_file("server.key"),
            cert=tls_file("server.pem"),
        )
        found = control.listen(
            self.factory, socket._replace(**fields), self.reactor
        )
        if found is not None:
            self.addCleanup(found.close)
        return found

    def folder(self, *names):
        """A folder with the certificates of names, as caCertsDir."""

        folder = self.mktemp()
        os.makedirs(folder)
        for name in names:
            with open(tls_file(name), "rb") as source:
                with open(os.path.join(folder, name), "wb") as copy:
                    copy.write(source.read())
        return os.path.abspath(folder)

    def target(self, found, *mine, **fields):
        """--command to found, which trusts its certificate; mine, its own."""

        target = wire.parse_socket(
            f"ssl:127.0.0.1:{found.socket.port}", client=True
        )
        if mine:
            fields.update(
                private_key=tls_file(f"{mine[0]}.key"),
                cert=tls_file(f"{mine[0]}.pem"),
            )
        return target._replace(ca_dir=self.folder("server.pem"), **fields)

    @defer.inlineCallbacks
    def logged(self, count):
        """The log, once it has count lines: the server may be late."""

        for _ in range(500):
            if len(self.logger.events) >= count:
                break
            yield task.deferLater(reactor, 0.01, lambda: None)
        return self.logger.formatted()

    @defer.inlineCallbacks
    def test_the_token(self):
        found = self.listen()
        port = found.socket.port
        result = yield self.command(
            self.target(found), "brick", "new", "switch"
        )
        self.assertEqual(result, (client.DONE, "sw1\n", ""))
        log = yield self.logged(4)
        self.assertEqual(
            log[:2],
            [
                f"Made the token {self.token_file}",
                f"Listening on ssl 127.0.0.1 port {port}, protocol text, with"
                f" the token of {self.token_file}",
            ],
        )
        self.assertRegex(
            log[2],
            rf"^127\.0\.0\.1 port [0-9]+ connected to ssl port {port} with"
            " the token$",
        )

    @defer.inlineCallbacks
    def test_client_certificates(self):
        clients = self.folder("alice.pem")
        found = self.listen(ca_dir=clients)
        port = found.socket.port
        self.assertEqual(
            self.logger.formatted(),
            [
                f"Listening on ssl 127.0.0.1 port {port}, protocol text, with"
                f" the certificates of {clients}"
            ],
        )
        # no token without it
        self.assertFalse(os.path.exists(self.token_file))
        result = yield self.command(self.target(found, "alice"), "status")
        self.assertEqual(result, (client.DONE, "Nothing runs\n", ""))
        log = yield self.logged(3)
        self.assertRegex(
            log[1],
            rf"^127\.0\.0\.1 port [0-9]+ connected to ssl port {port} as"
            " alice$",
        )
        self.assertEqual(log[2], "Command from alice at 127.0.0.1: status")

    @defer.inlineCallbacks
    def test_another_certificate(self):
        found = self.listen(ca_dir=self.folder("alice.pem"))
        result = yield self.command(self.target(found, "bob"), "status")
        self.assertEqual(
            result,
            (client.UNANSWERED, "", "127.0.0.1 refused your certificate\n"),
        )
        log = yield self.logged(2)
        self.assertRegex(
            log[1],
            rf"^127\.0\.0\.1 port [0-9]+ on ssl port {found.socket.port}:"
            " the TLS handshake failed: .*certificate",
        )
        self.assertEqual(self.logger.levels(), ["info", "warn"])

    @defer.inlineCallbacks
    def test_no_certificate(self):
        found = self.listen(ca_dir=self.folder("alice.pem"))
        result = yield self.command(self.target(found), "status")
        self.assertEqual(
            result,
            (
                client.UNANSWERED,
                "",
                "127.0.0.1 asks for your certificate: privateKey= and"
                " certKey=\n",
            ),
        )

    @defer.inlineCallbacks
    def test_a_certificate_not_trusted(self):
        found = self.listen()
        target = self.target(found)._replace(ca_dir=self.folder("alice.pem"))
        result = yield self.command(target, "status")
        self.assertEqual(
            result,
            (
                client.UNANSWERED,
                "",
                "The certificate of 127.0.0.1 isn't one you trust:"
                " self-signed certificate. Name the folder of its certificate"
                " with caCertsDir=\n",
            ),
        )

    @defer.inlineCallbacks
    def test_amp(self):
        # a program with Twisted's tls: client and a certificate
        found = self.listen(protocol=wire.AMP, ca_dir=self.folder("alice.pem"))
        description = (
            f"tls:127.0.0.1:{found.socket.port}"
            f":trustRoots={self.folder('server.pem')}"
            f":certificate={tls_file('alice.pem')}"
            f":privateKey={tls_file('alice.key')}"
        )
        endpoint = endpoints.clientFromString(reactor, description)
        program = yield endpoints.connectProtocol(endpoint, AMPProgram())
        answer = yield program.callRemote(ampwire.Run, line="brick new switch")
        self.assertEqual(answer, {"lines": ["sw1"]})
        yield found.close()
        yield program.lost

    def test_files_that_dont_match(self):
        self.assertIsNone(self.listen(cert=tls_file("alice.pem")))
        self.assertEqual(
            self.logger.formatted(),
            [
                "ssl 127.0.0.1 port 0: The key"
                f" {tls_file('server.key')} isn't that of the certificate"
                f" {tls_file('alice.pem')}: no control socket"
            ],
        )
        self.assertEqual(self.logger.levels(), ["warn"])
