# -*- test-case-name: virtualbricks.tests.remote.test_tunnel -*-
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
The consoles of the bricks of another Virtualbricks, carried over a
connection (page 19 §9, R8).

The windows listen on a unix socket of their own, 0600, in a folder of
their own in the runtime folder, ``.connect-PID``: the folders there without
a dot are those of the workspaces. They start the terminal of their
settings on it, with vdeterm or unixterm, as the brick would. When the
terminal connects, they open a new connection to the Virtualbricks of the
bricks, agree on protocol 2 and call ``Attach``: the Virtualbricks there
connects to the console of the brick, its control monitor or the serial
socket of a machine, and answers; from then on the connection carries the
bytes of the console both ways, AMP's ProtocolSwitchCommand, and the
windows join it to the terminal.
"""

import os
import shutil

from twisted.internet import defer, endpoints, error, protocol
from twisted.logger import Logger
from twisted.protocols import amp

from virtualbricks import locations
from virtualbricks.bricks import TermProtocol, is_running
from virtualbricks.bricks.brickinfo import NO_CONSOLE
from virtualbricks.bricks.virtualmachine import is_virtualmachine
from virtualbricks.config.settings import get_setting
from virtualbricks.console import ampcommands, ampwire
from virtualbricks.i18n import _
from virtualbricks.remote import commands

logger = Logger()
console_failed = "Cannot open the console of {name}: {error}"
console_open = "Console of {name} on {where}: {args}"
attach_failed = "The console of {name} for the windows failed"

# The consoles of a brick.
MONITOR = "monitor"
SERIAL = "serial"


class Relay(protocol.Protocol):
    """
    One end of a console carried over a connection: what it receives, the
    other end writes, once the two are joined; when one end goes, so does
    the other. What it gets to write before it's connected waits.
    """

    def __init__(self):
        self.other = None
        # what it received before the join, what it must write once
        # connected
        self.received = []
        self.writing = []
        self.gone = False
        # closed before it was connected: it closes once it is
        self.closing = False
        self.lost = defer.Deferred()

    def connectionMade(self):
        writing, self.writing = self.writing, []
        for data in writing:
            self.transport.write(data)
        if self.closing:
            self.transport.loseConnection()

    def dataReceived(self, data):
        if self.other is None:
            self.received.append(data)
        else:
            self.other.write(data)

    def write(self, data):
        if self.gone:
            return
        if self.transport is None:
            self.writing.append(data)
        else:
            self.transport.write(data)

    def close(self):
        if self.gone:
            return
        if self.transport is None:
            self.closing = True
        else:
            self.transport.loseConnection()

    def connectionLost(self, reason):
        self.gone = True
        if self.other is not None:
            self.other.close()
        self.lost.callback(None)


def join(one, other):
    """Join the two ends: what each received goes to the other."""

    one.other, other.other = other, one
    for source, target in ((one, other), (other, one)):
        received, source.received = source.received, []
        for data in received:
            target.write(data)
    # an end gone before the join
    for end in (one, other):
        if end.gone:
            end.other.close()


# The Virtualbricks of the bricks


def console_path(factory, name, console):
    """
    The socket of console of the brick name: LookupError if there's no
    brick, ValueError if it has no such console or doesn't run.
    """

    brick = factory.get_brick(name)
    if brick is None:
        raise LookupError(_("No brick named {name}").format(name=name))
    if not is_running(brick):
        raise ValueError(
            _("{name} doesn't run: start it first").format(name=name)
        )
    if console == MONITOR:
        if brick.get_type() in NO_CONSOLE:
            raise ValueError(
                _("{name} has no control monitor").format(name=name)
            )
        return brick.console()
    if console == SERIAL:
        if not is_virtualmachine(brick) or not brick.config.serial_socket:
            raise ValueError(
                _("{name} has no serial socket").format(name=name)
            )
        return brick.runtime_path(f"{name}_serial")
    raise ValueError(
        _("The console is {monitor} or {serial}").format(
            monitor=MONITOR, serial=SERIAL
        )
    )


def connect_console(reactor, path, relay):
    """Connect relay to the console at path: a Deferred of it."""

    endpoint = endpoints.UNIXClientEndpoint(reactor, path)
    return endpoints.connectProtocol(endpoint, relay)


class Attaching(amp.CommandLocator):
    """
    The answer to Attach; the connection has brickfactory, reactor,
    _log_line() and _log_failed().
    """

    @commands.Attach.responder
    def attach(self, brick, console):
        try:
            path = console_path(self.brickfactory, brick, console)
        except LookupError as exc:
            self._log_failed(str(exc.args[0]))
            raise ampcommands.NotFound(str(exc.args[0])) from None
        except ValueError as exc:
            self._log_failed(str(exc))
            raise ampcommands.BadArgument(str(exc)) from None
        self._log_line(f"attach {brick} {console}")
        console_end = Relay()

        def connected(_):
            # the end of the connection, once the answer is written
            connection_end = Relay()
            join(connection_end, console_end)
            return connection_end

        def not_connected(failure):
            if not failure.check(error.ConnectError):
                logger.failure(attach_failed, failure, name=brick)
                raise ampwire.CommandFailed(failure.getErrorMessage())
            message = _("Can't reach the console of {name}: {error}").format(
                name=brick, error=failure.getErrorMessage()
            )
            self._log_failed(message)
            raise ampwire.CommandFailed(message)

        connecting = connect_console(self.reactor, path, console_end)
        return connecting.addCallbacks(connected, not_connected)


# The windows


class _Switched(protocol.ClientFactory):
    """The end of the connection of the windows, once Attach answers."""

    def __init__(self):
        self.relay = None

    def buildProtocol(self, addr):
        self.relay = Relay()
        return self.relay

    def clientConnectionFailed(self, connector, reason):
        # Attach failed: its errback says why
        pass

    def clientConnectionLost(self, connector, reason):
        pass


class Terminal(protocol.Factory):
    """The socket of a terminal: one connection, which a console joins."""

    def __init__(self, consoles, name, console):
        self.consoles = consoles
        self.name = name
        self.console = console
        self.port = None

    def buildProtocol(self, addr):
        relay = Relay()
        # one terminal: no other may connect
        if self.port is not None:
            self.port.stopListening()
            self.port = None
        defer.ensureDeferred(
            self.consoles.attach(relay, self.name, self.console)
        )
        return relay


class Consoles:
    """
    The consoles of the bricks of the Virtualbricks at target that the
    windows open: connect(target) is a Deferred of a new connection that
    agreed on protocol 2. A socket of their own for each, and the terminal
    of the settings on it.
    """

    def __init__(self, connect, where, reactor, spawn=None):
        self.connect = connect
        self.where = where
        self.reactor = reactor
        # how the terminal starts: the reactor's, unless a test gives one
        self.spawn = spawn
        # the folder of the sockets, made when first needed
        self.folder = None
        self.count = 0

    def lacks(self, brick):
        """
        Why this computer can't open the console of brick: the program
        that the terminal needs, and its package; None if it can.
        """

        from virtualbricks.programs import PACKAGES
        from virtualbricks.vde import which

        program = brick.term_command
        try:
            which(program)
        except FileNotFoundError:
            return _("needs {program} of {package}").format(
                program=program, package=PACKAGES.get(program) or program
            )
        return None

    def _folder(self):
        if self.folder is None:
            self.folder = locations.ensure_private_dir(
                os.path.join(
                    locations.runtime_dir(), f".connect-{os.getpid()}"
                )
            )
        return self.folder

    async def open(self, brick, console=MONITOR):
        """
        Listen for the terminal, and start it: the Deferred fires once it
        runs; the console joins it when it connects.
        """

        from virtualbricks.vde import which

        program = which(brick.term_command)
        self.count += 1
        path = os.path.join(
            self._folder(), f"{self.count}-{brick.name}.{console}"
        )
        terminal = Terminal(self, brick.name, console)
        endpoint = endpoints.UNIXServerEndpoint(self.reactor, path, mode=0o600)
        terminal.port = await endpoint.listen(terminal)
        term = get_setting("terminal")
        args = [term, "-e", program, path]
        logger.info(
            console_open,
            name=brick.name,
            where=self.where,
            args=" ".join(args),
        )
        spawn = self.reactor.spawnProcess if self.spawn is None else self.spawn
        spawn(TermProtocol(), term, args, os.environ)

    async def attach(self, terminal, name, console):
        """Join terminal to the console of the brick name there."""

        connection = None
        try:
            connection = await self.connect()
            switched = _Switched()
            await connection.callRemote(
                commands.Attach, switched, brick=name, console=console
            )
        except Exception as exc:
            logger.error(console_failed, name=name, error=exc)
            terminal.close()
            if connection is not None and connection.transport is not None:
                connection.transport.loseConnection()
            return
        join(terminal, switched.relay)

    def close(self):
        """The windows close: their folder goes."""

        if self.folder is not None:
            shutil.rmtree(self.folder, ignore_errors=True)
            self.folder = None
