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
protocol of :mod:`virtualbricks.console.wire`.

:func:`listen` listens on a socket of ``--socket``, ``.control`` in the
runtime folder or the path of its description, while it holds the lock
beside it: the first Virtualbricks that takes the lock listens, the others
go without. Each connection runs its requests one after the other;
connections don't wait for each other, nor for the terminal or the events.
At the end, each connection is closed once its last answer is written, so
that ``quit`` answers too.
"""

from __future__ import annotations

import os

from twisted.internet import defer, error, protocol
from twisted.logger import Logger
from twisted.protocols import basic

from virtualbricks import __version__, locations, locks
from virtualbricks.config.workspace import projects
from virtualbricks.console import wire
from virtualbricks.console.dispatch import run

logger = Logger()
listening = "Listening on {path}, protocol {protocol}"
no_socket = "{reason}: no control socket"
answered_by = "{holder} answers on {path}; this one doesn't"
command_received = "Command from the control socket: {line}"
command_failed = "The command from the control socket failed: {error}"

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


class ControlProtocol(basic.LineOnlyReceiver):
    """A connection of the text protocol: its requests and their answers."""

    delimiter = b"\n"
    MAX_LENGTH = wire.MAX_LINE

    def __init__(self, brickfactory, reactor):
        # not factory: Twisted sets that, the ControlFactory
        self.brickfactory = brickfactory
        self.reactor = reactor
        self.requests = InOrder()

    def connectionMade(self):
        self.factory.connections.add(self)
        current = projects.current
        name = current.name if current is not None else None
        self.send(wire.greeting(__version__, os.getpid(), name))

    def connectionLost(self, reason):
        # the command that runs goes on; its answer is dropped. Twisted
        # doesn't reset connected.
        self.connected = False
        self.requests.stop()
        self.factory.lost(self)

    def send(self, message):
        if self.connected:
            self.transport.write(wire.encode(message))

    def lineReceived(self, line):
        if line.strip():
            self.requests.add(lambda: self.handle(line))

    def handle(self, line):
        try:
            text, cwd = wire.read_request(line)
        except wire.BadRequest as exc:
            self.send(wire.refusal(str(exc)))
            return defer.succeed(None)
        logger.info(command_received, line=text)
        done = run(self.brickfactory, text, self.reactor, cwd=cwd)
        done.addCallbacks(self._answer, self._refuse)
        return done

    def _answer(self, lines):
        self.send(wire.answer(lines))

    def _refuse(self, failure):
        # run() fails with a CommandError, and logs the failures of bugs
        exc = failure.value
        message = str(exc) or type(exc).__name__
        logger.info(command_failed, error=message)
        self.send(wire.refusal(message, getattr(exc, "lines", [])))


class ControlFactory(protocol.Factory):
    """The connections of a control socket, of the protocol it speaks."""

    # listen() logs what the log needs: not the address of the object
    noisy = False

    def __init__(self, brickfactory, reactor, protocol=ControlProtocol):
        self.brickfactory = brickfactory
        self.reactor = reactor
        self.protocol = protocol
        self.connections = set()
        # fired once every connection is closed, while closing
        self._closed = None

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
    """The socket that this Virtualbricks listens on, and its lock."""

    def __init__(self, path, port, lock, factory):
        self.path = path
        self.port = port
        self.lock = lock
        self.factory = factory
        self.closed = False

    def close(self):
        """Stop listening, close the connections, release the lock."""

        if self.closed:
            return defer.succeed(None)
        self.closed = True
        # Twisted removes the socket as it stops listening
        done = defer.maybeDeferred(self.port.stopListening)
        done.addCallback(lambda _: self.factory.close())

        def release(result):
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
PROTOCOLS = {wire.TEXT: ControlProtocol}


def listen(brickfactory, socket=None, reactor=None):
    """
    Answer the commands of socket, a wire.Socket of --socket: the text
    socket at ``.control`` in the runtime folder if None.

    Return the Control, None if this Virtualbricks goes without: another
    one answers there, or the socket can't be there; the log says which.
    It stops at the end of the reactor.
    """

    if reactor is None:
        from twisted.internet import reactor
    if socket is None:
        socket = wire.Socket(locations.control_socket())
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
    factory = ControlFactory(brickfactory, reactor, PROTOCOLS[socket.protocol])
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
    control = Control(path, port, lock, factory)
    reactor.addSystemEventTrigger("before", "shutdown", control.close)
    logger.info(listening, path=path, protocol=socket.protocol)
    return control
