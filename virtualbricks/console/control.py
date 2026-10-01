# -*- test-case-name: virtualbricks.tests.console.test_control -*-
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
The control sockets: the Virtualbricks that runs answers the commands of
``virtualbricks --command``, and of any program that speaks the text
protocol of :mod:`virtualbricks.console.wire`, or the AMP commands of
:mod:`virtualbricks.console.ampwire`, and, once a connection agrees on
protocol 2, the typed commands of :mod:`virtualbricks.console.ampcommands`.

:func:`listen` listens on a socket of ``--listen``. A unix socket is
``.control`` in the runtime folder or the path of its description, while it
holds the lock beside it: the first Virtualbricks that takes the lock
listens, the others go without. A tcp socket listens on a port of this
machine, and its clients prove first that they know the token of
:func:`virtualbricks.locations.token_file`, or of its own file; the others
are shut out. An ssl socket listens on any address; its clients prove the
token too, or show a certificate that it trusts, by
:mod:`virtualbricks.console.tls`. Each connection runs its requests one
after the other;
connections don't wait for each other, nor for the terminal or the events.
At the end, each connection is closed once its last answer is written, so
that ``quit`` answers too.
"""

from __future__ import annotations

import os

from twisted.internet import defer, error, protocol
from twisted.internet.interfaces import IHandshakeListener
from twisted.logger import Logger
from twisted.protocols import amp, basic
from zope.interface import implementer

from virtualbricks import __version__, locations, locks
from virtualbricks.config.workspace import projects
from virtualbricks.console import ampcommands, ampgen, ampwire, wire
from virtualbricks.console.command import COMMANDS, CommandError, NotFound
from virtualbricks.console.dispatch import run, run_command
from virtualbricks.console.parser import line_of
from virtualbricks.i18n import _
from virtualbricks.remote import (
    answers,
    commands as remote_commands,
    facts,
    follower,
    tunnel,
)

logger = Logger()
listening = "Listening on {path}, protocol {protocol}"
listening_token = (
    "Listening on {where}, protocol {protocol}, with the token of {path}"
)
listening_certificates = (
    "Listening on {where}, protocol {protocol}, with the certificates of"
    " {path}"
)
made_token = "Made the token {path}"
no_socket = "{reason}: no control socket"
answered_by = "{holder} answers on {path}; this one doesn't"
command_received = "Command from the control socket: {line}"
command_failed = "The command from the control socket failed: {error}"
command_from = "Command from {who}: {line}"
command_from_failed = "The command from {who} failed: {error}"
proved = "{who} connected to {socket} with the token"
wrong_token = "{who} on {socket}: wrong token"
not_a_proof = "{who} on {socket}: not a proof"
too_slow = "{who} on {socket}: no proof in {seconds} seconds"
connected_as = "{who} connected to {socket} as {name}"
handshake_failed = "{who} on {socket}: the TLS handshake failed: {reason}"
amp_command_received = "Command from the AMP socket: {line}"
amp_command_failed = "The command from the AMP socket failed: {error}"
answer_too_long = (
    "The answer to the AMP socket is {size} bytes, longer than AMP carries"
)

# How long the end waits for a client to read its last answer, in seconds.
CLOSE_TIMEOUT = 2


class InOrder:
    """The requests of a connection, each run after the one before."""

    def __init__(self):
        self.waiting = []
        # a request runs, and the loop of _next() runs
        self.busy = False
        self.looping = False
        self.stopped = False

    def add(self, call):
        """
        Run call() once the requests before it are done: a Deferred of its
        result, which never fires if the connection is lost first.
        """

        done = defer.Deferred()
        self.waiting.append((call, done))
        self._next()
        return done

    def stop(self):
        """The connection is lost: drop the requests that wait."""

        self.stopped = True
        self.waiting = []

    def _next(self):
        if self.looping:
            return
        self.looping = True
        try:
            while self.waiting and not self.busy and not self.stopped:
                self.busy = True
                call, done = self.waiting.pop(0)
                result = defer.maybeDeferred(call)
                result.chainDeferred(done)
                result.addBoth(self._finished)
        finally:
            self.looping = False

    def _finished(self, _):
        self.busy = False
        self._next()


def _peer(transport):
    """Who is at the other end of a network socket, for the log."""

    address = transport.getPeer()
    return f"{address.host} port {address.port}"


@implementer(IHandshakeListener)
class Visitor:
    """
    What a connection of either protocol knows of its client, on a network
    socket: who it is, for the log, the time it has to prove the token, and
    the certificate that it showed over ssl.
    """

    # who connects, for the log; None on a unix socket
    who = None
    # what closes the connection when the proof of the token is late
    timer = None
    handshaken = False

    def arrive(self):
        """The connection is made: who it is, and the time to prove."""

        if self.factory.network():
            self.who = _peer(self.transport)
        if self.factory.token is not None:
            self.timer = self.reactor.callLater(
                wire.PROOF_TIMEOUT, self._too_slow
            )

    def leave(self, reason):
        """The connection is lost; over ssl, maybe before its handshake."""

        self._stop_timer()
        socket = self.factory.socket
        if socket is not None and socket.kind == "ssl" and not self.handshaken:
            from virtualbricks.console import tls

            logger.warn(
                handshake_failed,
                who=self.who,
                socket=self.factory.label(),
                reason=tls.describe(reason),
            )

    def handshakeCompleted(self):
        self.handshaken = True
        if self.factory.token is not None:
            # the proof of the token says who it is
            return
        from virtualbricks.console import tls

        name = tls.common_name(self.transport.getPeerCertificate())
        logger.info(
            connected_as, who=self.who, socket=self.factory.label(), name=name
        )
        self.who = f"{name} at {self.transport.getPeer().host}"

    def _stop_timer(self):
        if self.timer is not None and self.timer.active():
            self.timer.cancel()
        self.timer = None

    def _too_slow(self):
        self.timer = None
        logger.warn(
            too_slow,
            who=self.who,
            socket=self.factory.label(),
            seconds=wire.PROOF_TIMEOUT,
        )
        self._shut_out(
            _("No proof in {seconds} seconds").format(
                seconds=wire.PROOF_TIMEOUT
            )
        )

    def _shut_out(self, error):
        raise NotImplementedError()


class ControlProtocol(Visitor, basic.LineOnlyReceiver):
    """A connection of the text protocol: its requests and their answers."""

    delimiter = b"\n"
    MAX_LENGTH = wire.MAX_LINE

    def __init__(self, brickfactory, reactor):
        # not factory: Twisted sets that, the ControlFactory
        self.brickfactory = brickfactory
        self.reactor = reactor
        self.requests = InOrder()
        # the nonce of the proof that a client of a socket with a token
        # owes, until it gives it; once shut out, nothing it sends counts
        self.nonce = None
        self.shut = False

    def connectionMade(self):
        self.factory.connections.add(self)
        self.arrive()
        if self.factory.token is None:
            self.greet()
            return
        self.nonce = wire.new_nonce()
        self.send(wire.challenge(self.nonce))

    def greet(self, proof=None):
        current = projects.current
        name = current.name if current is not None else None
        self.send(wire.greeting(__version__, os.getpid(), name, proof))

    def connectionLost(self, reason):
        # the command that runs goes on; its answer is dropped. Twisted
        # doesn't reset connected.
        self.connected = False
        self.leave(reason)
        self.requests.stop()
        self.factory.lost(self)

    def send(self, message):
        if self.connected:
            self.transport.write(wire.encode(message))

    def lineReceived(self, line):
        if self.shut or not line.strip():
            return
        if self.nonce is not None:
            self.prove(line)
        else:
            self.requests.add(lambda: self.handle(line))

    def prove(self, line):
        """The first line of a client of a socket with a token: its proof."""

        token = self.factory.token
        socket = self.factory.label()
        try:
            nonce, given = wire.read_proof(line)
        except wire.BadRequest as exc:
            logger.warn(not_a_proof, who=self.who, socket=socket)
            self._shut_out(str(exc))
            return
        if not wire.same_proof(
            given, wire.proof(token, "client", self.nonce, nonce)
        ):
            logger.warn(wrong_token, who=self.who, socket=socket)
            self._shut_out(_("Wrong token"))
            return
        self._stop_timer()
        mine, self.nonce = self.nonce, None
        logger.info(proved, who=self.who, socket=socket)
        self.greet(wire.proof(token, "server", mine, nonce))

    def _shut_out(self, error):
        self._stop_timer()
        self.shut = True
        self.send(wire.refusal(error))
        self.transport.loseConnection()

    def handle(self, line):
        try:
            text, cwd = wire.read_request(line)
        except wire.BadRequest as exc:
            self.send(wire.refusal(str(exc)))
            return defer.succeed(None)
        if self.who is None:
            logger.info(command_received, line=text)
        else:
            logger.info(command_from, who=self.who, line=text)
        done = run(self.brickfactory, text, self.reactor, cwd=cwd)
        done.addCallbacks(self._answer, self._refuse)
        return done

    def _answer(self, lines):
        self.send(wire.answer(lines))

    def _refuse(self, failure):
        # run() fails with a CommandError, and logs the failures of bugs
        exc = failure.value
        message = str(exc) or type(exc).__name__
        if self.who is None:
            logger.info(command_failed, error=message)
        else:
            logger.info(command_from_failed, who=self.who, error=message)
        self.send(wire.refusal(message, getattr(exc, "lines", [])))


# The typed commands, by their names: the command of the console, and the
# AMP command of ampcommands.
TYPED = {
    ampgen.name(found).encode(): (
        found,
        getattr(ampcommands, ampgen.name(found)),
    )
    for found in COMMANDS
}


def _responder(found, typed):
    def respond(self, cwd, **given):
        running = self.requests.add(lambda: self.run_typed(found, given, cwd))
        return running.addBoth(self.pushes_first)

    return typed.responder(respond)


# The responders of the typed commands, which AMP finds by their commands;
# Twisted collects them when the class is made.
TypedCommands = type(
    "TypedCommands",
    (amp.CommandLocator,),
    {
        f"typed_{name.decode()}": _responder(found, typed)
        for name, (found, typed) in TYPED.items()
    },
)


# The commands of the windows of another machine, which have the checks of
# the typed ones.
WINDOWS = {
    command.commandName: command for command in remote_commands.FROM_PROGRAM
}


class AMPControl(
    Visitor,
    TypedCommands,
    follower.Following,
    answers.Answers,
    facts.Facts,
    tunnel.Attaching,
    amp.AMP,
):
    """
    A connection of the AMP protocol: the commands of ampwire, and, once
    Hello agrees on protocol 2, the typed commands of ampcommands and those
    of the windows of another machine, as Follow. On a socket with a token,
    they wait for the proof, by Challenge and Authenticate. A connection
    that follows sends the pushes that wait before each answer.
    """

    # how Run writes its answer, to measure it first
    LINES = amp.ListOf(amp.Unicode())

    def __init__(self, brickfactory, reactor):
        super().__init__()
        # not factory: Twisted sets that, the ControlFactory
        self.brickfactory = brickfactory
        self.reactor = reactor
        self.requests = InOrder()
        # whether the program owes the proof of the token, and the nonce of
        # its Challenge
        self.owes_proof = False
        self.nonce = None
        # the protocol that Hello agreed on
        self.agreed = 1

    def makeConnection(self, transport):
        # AMP logs each connection with the addresses of its objects: listen()
        # logs what the log needs
        amp.BinaryBoxProtocol.makeConnection(self, transport)

    def connectionMade(self):
        self.factory.connections.add(self)
        self.arrive()
        self.owes_proof = self.factory.token is not None

    def connectionLost(self, reason):
        # the command that runs goes on; its answer is dropped
        amp.BinaryBoxProtocol.connectionLost(self, reason)
        self.transport = None
        self.leave(reason)
        self.unfollow()
        self.requests.stop()
        self.factory.lost(self)

    def _check_proved(self):
        if self.owes_proof:
            raise ampwire.TokenNeeded(
                _("Prove the token first: Challenge, then Authenticate")
            )

    @ampwire.Challenge.responder
    def challenge(self):
        if self.factory.token is None:
            raise ampwire.WrongToken(_("This socket takes no token"))
        self.nonce = wire.new_nonce()
        return {"nonce": self.nonce}

    @ampwire.Authenticate.responder
    def authenticate(self, nonce, proof):
        token = self.factory.token
        if token is None:
            raise ampwire.WrongToken(_("This socket takes no token"))
        mine, self.nonce = self.nonce, None
        socket = self.factory.label()
        if mine is None or not wire.NONCE.fullmatch(nonce):
            logger.warn(not_a_proof, who=self.who, socket=socket)
            message = _("Challenge first, then Authenticate")
            self._shut_out(message)
            raise ampwire.WrongToken(message)
        if not wire.same_proof(
            proof, wire.proof(token, "client", mine, nonce)
        ):
            logger.warn(wrong_token, who=self.who, socket=socket)
            self._shut_out(_("Wrong token"))
            raise ampwire.WrongToken(_("Wrong token"))
        self._stop_timer()
        self.owes_proof = False
        logger.info(proved, who=self.who, socket=socket)
        return {"proof": wire.proof(token, "server", mine, nonce)}

    def _shut_out(self, error):
        """Close the connection once the error, if any, is written."""

        self._stop_timer()
        self.owes_proof = True

        def close():
            if self.transport is not None:
                self.transport.loseConnection()

        self.reactor.callLater(0, close)

    def locateResponder(self, name):
        responder = super().locateResponder(name)
        typed = TYPED[name][1] if name in TYPED else WINDOWS.get(name)
        if responder is None or typed is None:
            return responder

        def checked(box):
            # what AMP would drop, or close the connection on
            try:
                self._check_proved()
                self._check_agreed()
                _check_keys(typed, box)
            except (ampwire.TokenNeeded, ampcommands.ProtocolNeeded) as exc:
                raise amp.RemoteAmpError(
                    ampcommands.ERRORS[type(exc)], str(exc)
                ) from None
            except ampcommands.BadArgument as exc:
                self._log_failed(str(exc))
                raise amp.RemoteAmpError(
                    ampcommands.ERRORS[type(exc)], str(exc)
                ) from None
            return responder(box)

        return checked

    def _check_agreed(self):
        if self.agreed != ampcommands.PROTOCOL:
            raise ampcommands.ProtocolNeeded(
                _(
                    "The typed commands need protocol {protocol}: call Hello"
                    " with protocols [{protocol}] first"
                ).format(protocol=ampcommands.PROTOCOL)
            )

    @ampwire.Hello.responder
    def hello(self, protocols):
        self._check_proved()
        asked = {1, *(protocols or ())}
        self.agreed = max(
            (number for number in ampwire.PROTOCOLS if number in asked),
            default=ampwire.PROTOCOLS[0],
        )
        current = projects.current
        return {
            "protocol": self.agreed,
            "version": __version__,
            "pid": os.getpid(),
            "project": current.name if current is not None else None,
        }

    @ampwire.Run.responder
    def run_line(self, line, cwd):
        self._check_proved()
        running = self.requests.add(lambda: self.handle(line, cwd))
        return running.addBoth(self.pushes_first)

    def handle(self, line, cwd):
        try:
            wire.check_cwd(cwd)
        except wire.BadRequest as exc:
            raise ampwire.CommandFailed(str(exc)) from None
        self._log_line(line)
        done = run(self.brickfactory, line, self.reactor, cwd=cwd)
        done.addCallbacks(self._answer, self._refuse)
        return done

    def run_typed(self, found, given, cwd):
        """Run the typed command of found, a command of the console."""

        try:
            wire.check_cwd(cwd)
        except wire.BadRequest as exc:
            raise ampcommands.BadArgument(str(exc)) from None
        self._log_line(line_of(found, given))
        try:
            done = run_command(
                self.brickfactory, found, given, self.reactor, cwd
            )
        except NotFound as exc:
            self._log_failed(str(exc))
            raise ampcommands.NotFound(str(exc)) from None
        except CommandError as exc:
            self._log_failed(str(exc))
            raise ampcommands.BadArgument(str(exc)) from None
        done.addCallbacks(self._answer, self._refuse)
        return done

    def _log_line(self, line):
        if self.who is None:
            logger.info(amp_command_received, line=line)
        else:
            logger.info(command_from, who=self.who, line=line)

    def _log_failed(self, message):
        if self.who is None:
            logger.info(amp_command_failed, error=message)
        else:
            logger.info(command_from_failed, who=self.who, error=message)

    def _answer(self, lines):
        size = len(self.LINES.toString(lines))
        if size > amp.MAX_VALUE_LENGTH:
            logger.info(answer_too_long, size=size)
            raise ampwire.AnswerTooLong(
                _(
                    "The command was done, but its answer, {size} bytes, is"
                    " longer than the {most} that AMP carries; a text socket"
                    " carries it"
                ).format(size=size, most=amp.MAX_VALUE_LENGTH)
            )
        return {"lines": lines}

    def _refuse(self, failure):
        # run() fails with a CommandError, and logs the failures of bugs;
        # what the command did first is dropped
        exc = failure.value
        message = str(exc) or type(exc).__name__
        self._log_failed(message)
        raise ampwire.CommandFailed(message)


def _check_keys(typed, box):
    """
    BadArgument if box has a key that typed doesn't declare, or lacks one it
    needs: AMP drops the first, and closes the connection on the second.
    """

    declared = {key for key, _ in typed.arguments}
    extra = sorted(
        key.decode("utf-8", "replace")
        for key in set(box) - declared - {amp.ASK, amp.COMMAND}
    )
    if extra:
        raise ampcommands.BadArgument(
            _("{command} has no argument {names}").format(
                command=typed.commandName.decode(), names=", ".join(extra)
            )
        )
    missing = sorted(
        key.decode()
        for key, argument in typed.arguments
        if not argument.optional and key not in box
    )
    if missing:
        raise ampcommands.BadArgument(
            _("{command} needs {names}").format(
                command=typed.commandName.decode(), names=", ".join(missing)
            )
        )


class ControlFactory(protocol.Factory):
    """
    The connections of a control socket, a wire.Socket, of the protocol it
    speaks; with a token, each client proves first that it knows it.
    """

    # listen() logs what the log needs: not the address of the object
    noisy = False

    def __init__(
        self,
        brickfactory,
        reactor,
        protocol=ControlProtocol,
        socket=None,
        token=None,
    ):
        self.brickfactory = brickfactory
        self.reactor = reactor
        self.protocol = protocol
        self.socket = socket
        self.token = token
        self.connections = set()
        # fired once every connection is closed, while closing
        self._closed = None

    def network(self):
        """Whether it listens on a port, where anyone can connect."""

        return self.socket is not None and self.socket.kind != "unix"

    def label(self):
        """A network socket, as the log names it after a client."""

        return f"{self.socket.kind} port {self.socket.port}"

    def buildProtocol(self, addr):
        connection = self.protocol(self.brickfactory, self.reactor)
        connection.factory = self
        return connection

    def lost(self, connection):
        self.connections.discard(connection)
        if self._closed is not None and not self.connections:
            closed, self._closed = self._closed, None
            closed.callback(None)

    def close(self):
        """
        Close the connections once their answers are written; a Deferred.

        A client that doesn't read them is cut off after CLOSE_TIMEOUT.
        """

        if not self.connections:
            return defer.succeed(None)
        self._closed = closed = defer.Deferred()
        timer = self.reactor.callLater(CLOSE_TIMEOUT, self._abort)

        def stop_timer(result):
            if timer.active():
                timer.cancel()
            return result

        closed.addBoth(stop_timer)
        for connection in list(self.connections):
            connection.transport.loseConnection()
        return closed

    def _abort(self):
        for connection in list(self.connections):
            connection.transport.abortConnection()


class Control:
    """
    The socket that this Virtualbricks listens on, a wire.Socket, and the
    lock of a unix one.
    """

    def __init__(self, socket, port, lock, factory):
        self.socket = socket
        self.port = port
        self.lock = lock
        self.factory = factory
        self.closed = False
        if socket.protocol == wire.AMP:
            # the log, for the programs that follow, while it listens
            follower.keeper.start()

    @property
    def path(self):
        return self.socket.path

    def close(self):
        """Stop listening, close the connections, release the lock."""

        if self.closed:
            return defer.succeed(None)
        self.closed = True
        if self.socket.protocol == wire.AMP:
            follower.keeper.stop()
        # Twisted removes the socket as it stops listening
        done = defer.maybeDeferred(self.port.stopListening)
        done.addCallback(lambda _: self.factory.close())

        def release(result):
            if self.lock is not None:
                self.lock.unlock()
            return result

        done.addBoth(release)
        return done


def _holder(lock_file):
    """Who holds the lock of a socket, for the log."""

    pids = [pid for pid, _ in locks.holders(lock_file)]
    if not pids:
        return "Another Virtualbricks"
    if len(pids) == 1:
        return f"Process {pids[0]}"
    return "Processes " + ", ".join(map(str, pids))


def _listen_unix(reactor, path, factory):
    # nobody else can connect between the bind and the chmod of Twisted
    umask = os.umask(0o177)
    try:
        return reactor.listenUNIX(path, factory, mode=0o600)
    finally:
        os.umask(umask)


# The protocol of the connections of a socket, by the protocol it speaks.
PROTOCOLS = {wire.TEXT: ControlProtocol, wire.AMP: AMPControl}


def listen(brickfactory, socket=None, reactor=None):
    """
    Answer the commands of socket, a wire.Socket of --listen: the text
    socket at ``.control`` in the runtime folder of the workspace if None,
    or if a unix socket without a path, as --listen alone.

    Return the Control, None if this Virtualbricks goes without: another
    one answers there, or the socket can't be there; the log says which.
    It stops at the end of the reactor.
    """

    if reactor is None:
        from twisted.internet import reactor
    if socket is None:
        socket = wire.Socket(None)
    if socket.kind == "unix" and socket.path is None:
        socket = socket._replace(path=locations.control_socket(projects.path))
    if socket.kind != "unix":
        return _listen_network(brickfactory, socket, reactor)
    path = socket.path
    lock_file = locations.control_lock_file(path)
    try:
        wire.check_path(path, wire.in_runtime_dir(path))
        lock = locks.hold(lock_file)
    except wire.Unusable as exc:
        logger.warn(no_socket, reason=str(exc))
        return None
    except OSError as exc:
        logger.warn(no_socket, reason=f"{lock_file}: {exc.strerror}")
        return None
    if lock is None:
        logger.info(answered_by, holder=_holder(lock_file), path=path)
        return None
    factory = ControlFactory(
        brickfactory, reactor, PROTOCOLS[socket.protocol], socket
    )
    try:
        # holding the lock, nobody answers on a socket left there: a crash
        if wire.check_socket(path):
            os.remove(path)
        port = _listen_unix(reactor, path, factory)
    except wire.Unusable as exc:
        lock.unlock()
        logger.warn(no_socket, reason=str(exc))
        return None
    except OSError as exc:
        lock.unlock()
        logger.warn(no_socket, reason=f"{path}: {exc.strerror}")
        return None
    except error.CannotListenError as exc:
        lock.unlock()
        logger.warn(no_socket, reason=f"{path}: {exc.socketError}")
        return None
    control = Control(socket, port, lock, factory)
    reactor.addSystemEventTrigger("before", "shutdown", control.close)
    logger.info(listening, path=path, protocol=socket.protocol)
    return control


def _token(path):
    """The token of the file at path, made if it isn't there."""

    try:
        return wire.read_token(path)
    except wire.NoToken:
        pass
    if path == locations.token_file():
        os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    try:
        token = wire.make_token(path)
    except FileExistsError:
        # another Virtualbricks made it first
        return wire.read_token(path)
    logger.info(made_token, path=path)
    return token


def _strerror(exc):
    return getattr(exc, "strerror", None) or str(exc)


def _listen_network(brickfactory, socket, reactor):
    """
    listen() on the port of a tcp or ssl socket, with its token, or with
    the certificates that its clients show.
    """

    where = socket.name()
    token = token_file = options = None
    try:
        if socket.kind == "ssl":
            from virtualbricks.console import tls

            options = tls.server_options(socket)
        if socket.uses_token():
            token_file = socket.token_file or locations.token_file()
            token = _token(token_file)
    except wire.Unusable as exc:
        logger.warn(no_socket, reason=f"{where}: {exc}")
        return None
    except OSError as exc:
        logger.warn(no_socket, reason=f"{where}: {token_file}: {exc.strerror}")
        return None
    factory = ControlFactory(
        brickfactory, reactor, PROTOCOLS[socket.protocol], socket, token
    )
    try:
        if options is None:
            port = reactor.listenTCP(
                socket.port, factory, interface=socket.host
            )
        else:
            port = reactor.listenSSL(
                socket.port, factory, options, interface=socket.host
            )
    except error.CannotListenError as exc:
        logger.warn(no_socket, reason=f"{where}: {_strerror(exc.socketError)}")
        return None
    # the port taken, when the socket asked for any
    socket = factory.socket = socket._replace(port=port.getHost().port)
    control = Control(socket, port, None, factory)
    reactor.addSystemEventTrigger("before", "shutdown", control.close)
    if token is None:
        logger.info(
            listening_certificates,
            where=socket.name(),
            protocol=socket.protocol,
            path=socket.ca_dir,
        )
    else:
        logger.info(
            listening_token,
            where=socket.name(),
            protocol=socket.protocol,
            path=token_file,
        )
    return control
