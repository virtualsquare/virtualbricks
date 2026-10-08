# -*- test-case-name: virtualbricks.tests.bricks.test_bricks -*-
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
The bricks: the base class of every brick and the processes they run, and
Base, what bricks and events share.

Each brick has its own module: capture, event, netemu (network emulator),
router, switch, switchwrapper, tap, tunnelconnect (tunnel client),
tunnellisten (tunnel server), virtualmachine and wire. The other classes
that go with them have theirs too: eventaction, an action of an event, and
plug and sock, the two ends of a link between bricks.
"""

from __future__ import annotations

import os
import collections
import functools
import locale
import re
from collections.abc import Collection
from contextlib import AbstractContextManager
from typing import TYPE_CHECKING, Any, ClassVar, Protocol, cast

from twisted.internet import protocol, reactor, error, defer
from twisted.internet.interfaces import (
    IProcessTransport,
    IReactorProcess,
    IReactorTime,
)
from twisted.logger import Logger
from twisted.python.failure import Failure

from virtualbricks import errors, observable, terminal
from virtualbricks.bricks.command import Command, Prepared
from virtualbricks.bricks.draft import Draft
from virtualbricks.bricks.plug import Plug, link_loop
from virtualbricks.config.report import Report
from virtualbricks.config.schema import (
    Path,
    Ref,
    define,
    dump_record,
    field,
    field_names,
    load_record,
    notes,
    rename_references,
)
from virtualbricks.config.settings import get_setting
from virtualbricks.config.tomlfile import Notes, Table
from virtualbricks.i18n import N_, _
from virtualbricks.programs import programs
from virtualbricks.sudo import sudo_command
from virtualbricks.vde import which

if TYPE_CHECKING:  # pragma: no cover
    from virtualbricks.brickfactory import BrickFactory
    from virtualbricks.bricks.event import Event
    from virtualbricks.bricks.sock import Sock
    from virtualbricks.bricks.virtualmachine import HostonlySock

__all__ = [
    "Base",
    "BaseConfig",
    "Brick",
    "BrickConfig",
    "PrivilegedBrick",
    "is_running",
]


system_encoding = locale.getpreferredencoding(do_setlocale=True)

logger = Logger(__name__)
process_started = "Process started"
process_terminated = "Process terminated. {status}"
event_unavailable = (
    "Warning. The Event {name} attached to Brick "
    "{brick} is not available. Skipping execution."
)
event_without_actions = (
    "The event {name} of the brick {brick} has no actions: skipping it."
)
shutdown_brick = "Shutting down {name} (pid: {pid})"
attribute_set = "Attribute {attr} set in {brick} with value {value}."
start_brick = "Starting: {args}"
left_out = "{warning}"
open_console = "Opening console for {name}\n%{args}\n"
console_done = "Console terminated\n{status}"
restarting = "Restarting process!"
# restart() kills the process if it hasn't stopped after these seconds.
KILL_AFTER = 2
console_terminated = (
    "Console terminated\n{status}\nProcess stdout:"
    "\n{out}\nProcess stderr:\n{err}\n"
)
invalid_ack = "ACK received but no command sent."


def _decode(data: bytes | str) -> str:
    if isinstance(data, bytes):
        return data.decode(system_encoding, errors="replace")
    return data


class ProcessLogger:

    def __init__(self, logger: Logger) -> None:
        self.logger = logger

    def __get__(self, instance: Process | None, owner: type) -> Logger:
        if instance is not None:
            logger = self.logger.__get__(instance, owner)
            setattr(
                logger,
                "emit",
                functools.partial(logger.emit, pid=instance.pid),
            )
            return logger
        return self.logger.__get__(instance, owner)


class RunningProcess(Protocol):
    """The process of a running brick, as the brick sees it."""

    @property
    def pid(self) -> int | None: ...

    def signal_process(self, signal: str | int) -> None: ...

    def write(self, data: bytes) -> None: ...


class Process(protocol.ProcessProtocol):

    logger = ProcessLogger(Logger())

    def __init__(self, brick: Brick) -> None:
        self.brick = brick
        self.output = {
            "stdout": terminal.Lines(system_encoding),
            "stderr": terminal.Lines(system_encoding),
        }

    def connectionMade(self) -> None:
        self.logger.info(process_started)
        self.brick.process_started(self)

    def processEnded(self, status: Failure) -> None:
        for stream, lines in self.output.items():
            self._log_output(stream, lines.flush())
        # the reason of a process that was terminated, in words
        ended: str | Failure = status
        if status.check(error.ProcessTerminated):
            assert status.value is not None, "checked"
            ended = " ".join(status.value.args)
            self.logger.error(process_terminated, status=ended)
        else:
            assert status.check(error.ProcessDone)
            self.logger.info(process_terminated, status="Done")
        self.brick.process_ended(self, ended)

    # The output of the program, marked with its stream for the messages
    # window: the lines that it ends, as a terminal shows them.

    def outReceived(self, data: bytes) -> None:
        self._log_output("stdout", self.output["stdout"].feed(data))

    def errReceived(self, data: bytes) -> None:
        self._log_output("stderr", self.output["stderr"].feed(data))

    def _log_output(self, stream: str, lines: list[str]) -> None:
        if not lines:
            return
        output = "\n".join(lines)
        if stream == "stdout":
            self.logger.info("{output}", output=output, stream=stream)
        else:
            self.logger.error(
                "{output}", output=output, stream=stream, hide_to_user=True
            )

    # new interface

    def _process(self) -> IProcessTransport:
        assert self.transport is not None, "the process runs"
        return self.transport

    @property
    def pid(self) -> int | None:
        return self._process().pid

    def signal_process(self, signalID: str | int) -> None:
        self._process().signalProcess(signalID)

    def write(self, data: bytes) -> None:
        self._process().write(data)


class FakeProcess:

    pid = -1

    def __init__(self, brick: Brick) -> None:
        self.brick = brick

    def signal_process(self, signo: str | int) -> None:
        pass

    def write(self, data: bytes) -> None:
        pass


class VDEProcessProtocol(Process):
    """
    Handle the VDE management console.

    Commands are serialized, until an ACK is received, the next command is not
    sent.

    @cvar delimiter: The line-ending delimiter to use.
    """

    _buffer = b""
    delimiter = b"\n"
    prompt = re.compile(rb"^vde(?:\[[^]]*\]:|\$) ", re.MULTILINE)
    PIPELINE_SIZE = 1

    def __init__(self, brick: Brick) -> None:
        Process.__init__(self, brick)
        self.queue: collections.deque[bytes] = collections.deque()

    def _data_received(self, data: bytes) -> None:
        """
        Translates bytes into lines, and calls _ack_received.
        """

        assert isinstance(data, bytes)
        acks = self.prompt.split(self._buffer + data)
        self._buffer = acks.pop(-1)
        for ack in acks:
            self._ack_received(ack)

    def _ack_received(self, ack: bytes) -> None:
        self.logger.info("{ack}", ack=_decode(ack))
        try:
            self.queue.popleft()
        except IndexError:
            self.logger.warn(invalid_ack)
            self._process().loseConnection()
        else:
            if len(self.queue):
                self._send_command()

    def _send_command(self) -> None:
        cmd = self.queue[0]
        self.logger.info("{command}", command=_decode(cmd))
        if cmd.endswith(self.delimiter):
            self._process().write(cmd)
        else:
            self._process().writeSequence((cmd, self.delimiter))

    def outReceived(self, data: bytes) -> None:
        self._data_received(data)

    def write(self, cmd: bytes) -> None:
        self.queue.append(cmd)
        if 0 < len(self.queue) <= self.PIPELINE_SIZE:
            self._send_command()


class TermProtocol(protocol.ProcessProtocol):

    logger = Logger()

    def __init__(self) -> None:
        self.out: list[bytes] = []
        self.err: list[bytes] = []

    def connectionMade(self) -> None:
        assert self.transport is not None, "the terminal runs"
        self.transport.closeStdin()

    def outReceived(self, data: bytes) -> None:
        self.out.append(data)

    def errReceived(self, data: bytes) -> None:
        self.err.append(data)

    def processEnded(self, status: Failure) -> None:
        if isinstance(status.value, error.ProcessTerminated):
            self.logger.error(
                console_terminated,
                status=status.value,
                out=_decode(b"".join(self.out)),
                err=_decode(b"".join(self.err)),
            )
        else:
            self.logger.info(console_done, status=status.value)


@define
class BaseConfig:
    """What the configuration of every brick and every event has."""

    # an image file to show instead of the icon of the type; not shown yet
    # but for virtual machines
    icon: str = field(
        Path(),
        default="",
        label=N_("Icon"),
        help=N_("An image file to show instead of the icon of its type"),
    )


class Base:

    # the kind, as the project file names it: "Switch", "Event"
    type: ClassVar[str]
    config_factory: ClassVar[Any]
    config: BaseConfig
    logger = Logger()

    def __init__(self, factory: BrickFactory, name: str) -> None:
        self._observable = observable.Observable()
        self.changed = observable.Signal(self._observable, "changed")
        self.factory = factory
        self._name = name
        self.config = self.config_factory()

    @property
    def name(self) -> str:
        """Read-only: the factory's rename_item() changes it, with set_name()."""

        return self._name

    def set_name(self, name: str) -> None:
        self._name = name
        self.changed.notify(self)

    def get_type(self) -> str:
        return self.type

    def _check_option(self, name: str) -> None:
        if name not in field_names(self.config):
            raise KeyError(
                _("%(config)s config has no %(option)s option.")
                % {"config": self.name, "option": name}
            )

    def update_config(self, changes: dict[str, object]) -> None:
        """
        Set the settings in changes, a mapping of names to values: KeyError
        for a name the config doesn't have. Each value that changes goes to
        the ``cbset_<name>`` method of the brick, if it has one, and the
        brick says it changed, once.
        """

        for name, value in changes.items():
            self._check_option(name)
            if value != getattr(self.config, name):
                logger.info(attribute_set, attr=name, brick=self, value=value)
                setattr(self.config, name, value)
                setter = getattr(self, "cbset_" + name, None)
                if setter:
                    setter(value)
        self.changed.notify(self)

    def rename_references(self, target: str, old: str, new: str) -> bool:
        """Point the references to the image or event ``old`` at ``new``."""

        return rename_references(self.config, target, old, new)

    def muted(self) -> AbstractContextManager[None]:
        """A block in which the object tells no one that it changes."""

        return self._observable.muted()


def is_running(brick: Brick | Event) -> bool:
    """Whether a brick or an event is running."""

    return brick.is_running()


@define
class BrickConfig(BaseConfig):

    # the events to run when the brick starts and when it stops
    on_start: str = field(
        Ref("event"), default="", help="An event to run when the brick starts"
    )
    on_stop: str = field(
        Ref("event"), default="", help="An event to run when the brick stops"
    )


class Brick(Base):

    proc: RunningProcess | None = None
    term_command = "vdeterm"
    # While a start is under way, the Deferreds of those who wait for it:
    # the first is that of the call that began it.
    _waiting: list[defer.Deferred[Brick]] | None = None
    # While start() follows the links to the bricks it plugs into.
    _linking = False
    # While it runs: fires with the brick and how its program ended.
    _exited_d: defer.Deferred[tuple[Brick, object]] | None = None
    _last_status: object = None
    process_protocol: type[Process] = VDEProcessProtocol
    config_factory: ClassVar[type[BrickConfig]] = BrickConfig
    config: BrickConfig
    # what the panel of the brick works on
    draft_factory: type[Draft] = Draft
    # What the brick is, the comment of its type in the project file.
    summary = ""
    # How the plugs are saved: "connect", "endpoints", "nics" or None.
    connections: str | None = None
    # The programs it runs, each a choice of names: any one of them will do.
    programs: tuple[tuple[str, ...], ...] = ()

    @classmethod
    def check_name(cls, name: str) -> None:
        """Raise InvalidNameError if a brick of this kind can't have name."""

    @property
    def pid(self) -> int | None:
        if self.proc is None:
            return -1
        return self.proc.pid

    def __init__(self, factory: BrickFactory, name: str) -> None:
        Base.__init__(self, factory, name)
        self.plugs: list[Plug] = []
        self.socks: list[Sock] = []

    def start(self, resume: str = "") -> defer.Deferred[Brick]:
        """
        Start the brick, in stages.

        A brick that isn't configured or connected is refused. The bricks it
        plugs into start first, and a loop is refused: a brick that its links
        lead back to. Then prepare() gathers what the command line needs,
        command() writes it, and spawn() starts the program; once it runs,
        the event of the brick's start runs. A call while a start is under
        way waits for it, as when Start All starts a switch and the wire that
        plugs into it.

        resume is the saved state that a virtual machine starts from; the
        other bricks have none. Return a Deferred that fires with the brick
        once its program runs.
        """

        if self.is_running():
            return defer.succeed(self)
        if self._linking:
            if get_setting("log_link_loops"):
                self.logger.error(link_loop)
            return defer.fail(errors.LinkLoopError())
        if self._waiting is not None:
            waiter: defer.Deferred[Brick] = defer.Deferred()
            self._waiting.append(waiter)
            return waiter

        if not self.configured():
            return defer.fail(
                errors.BadConfigError(
                    _("Cannot start '%s': not configured") % self.name
                )
            )
        if not self._properly_connected():
            return defer.fail(
                errors.NotConnectedError(
                    _("Cannot start '%s': not connected") % self.name
                )
            )

        started: defer.Deferred[Brick] = defer.Deferred()
        self._waiting = [started]
        self._exited_d = defer.Deferred()
        self._linking = True
        try:
            d = defer.DeferredList(
                [plug.connected() for plug in self.plugs],
                fireOnOneErrback=True,
                consumeErrors=True,
            )
        finally:
            self._linking = False

        def start_related_events(_: None) -> Brick:
            self._start_related_events(on=True)
            return self

        def eb(failure: Failure) -> Failure | None:
            if failure.check(defer.FirstError):
                first = failure.value
                assert isinstance(first, defer.FirstError), "checked"
                failure = first.subFailure
            waiting, self._waiting = self._waiting, None
            if waiting is None:
                # the program runs, and the event of its start failed
                return failure
            for waiter in waiting:
                waiter.errback(failure)
            return None

        prepared = d.addCallback(lambda _: self.prepare(resume))
        spawned = prepared.addCallback(self.command).addCallback(self.spawn)
        spawned.addCallback(start_related_events).addErrback(eb)
        return started

    def starting(self) -> bool:
        """Whether a start of the brick is under way."""

        return self._waiting is not None

    def stop(self, kill: bool = False) -> defer.Deferred[tuple[Brick, object]]:
        if self.proc is None:
            return defer.succeed((self, self._last_status))
        self.logger.info(shutdown_brick, name=self.name, pid=self.proc.pid)
        try:
            self.proc.signal_process("KILL" if kill else "TERM")
        except OSError as e:
            return defer.fail(e)
        except error.ProcessExitedAlready:
            pass
        assert self._exited_d is not None, "the start made it"
        return self._exited_d

    def config_table(self) -> Table:
        """Return the configuration as saved in the project file."""

        return dump_record(self.config)

    @classmethod
    def table_notes(cls, table: Table) -> Notes:
        """The notes of the keys of the configuration, in its table."""

        return notes(cls.config_factory, table)

    def load_config_table(
        self, table: Table, report: Report, where: str, ignore: Collection[str]
    ) -> None:
        """Read the configuration from the table of the project file."""

        self.config = load_record(
            type(self.config), table, report, where, ignore=ignore
        )

    def send_signal(self, signal: str | int) -> None:
        if self.proc is not None:
            self.proc.signal_process(signal)

    # brick <--> process interface

    def process_started(self, proc: Process) -> None:
        waiting, self._waiting = self._waiting, None
        assert waiting is not None, "a start waits for the process"
        for waiter in waiting:
            waiter.callback(self)
        self.changed.notify(self)

    def process_ended(self, proc: Process, status: str | Failure) -> None:
        self.proc = None
        self._start_related_events(on=False, off=True)
        self._last_status = status
        # ovvensive programming, raise an exception instead of hide the error
        # behind a lambda (lambda _: None)
        exited, self._exited_d = self._exited_d, None
        assert exited is not None, "the start made it"
        exited.callback((self, status))
        self.changed.notify(self)

    # Interal interface

    def _properly_connected(self) -> bool:
        return all(plug.configured() for plug in self.plugs)

    def configured(self) -> bool:
        return False

    def prepare(self, resume: str = "") -> defer.Deferred[Prepared]:
        """
        Gather what the command line needs: here, the VDE programs.

        Return a Deferred of a Prepared. resume is for a virtual machine.
        """

        deferred = programs.vde(str(get_setting("vde_path")))
        return deferred.addCallback(lambda vde: Prepared(vde=vde))

    def command(self, prepared: Prepared) -> Command:
        """Return the Command of the brick's program."""

        raise NotImplementedError("Brick.command")

    def need_sudo(self) -> bool:
        """Whether the program of the brick runs through sudo."""

        return False

    def spawn(self, command: Command) -> None:
        """
        Start the program of a Command.

        Its warnings and the command are logged, and a brick that needs root
        runs its program through sudo. The program gets the environment of
        Virtualbricks, with the variables of the Command.
        """

        for warning in command.warnings:
            self.logger.warn(left_out, warning=warning)
        args = command.argv
        self.logger.info(start_brick, args=" ".join(args))
        if self.need_sudo():
            args = sudo_command(args)
        process = self.process_protocol(self)
        self.proc = process
        env = dict(os.environ, **command.env)
        _reactor().spawnProcess(process, args[0], args, env)

    def _start_related_events(
        self, on: bool = True, off: bool = False
    ) -> None:
        if on and self.config.on_start:
            name = self.config.on_start
        elif off and self.config.on_stop:
            name = self.config.on_stop
        else:
            return

        event = self.factory.get_event(name)
        if event is None:
            self.logger.info(event_unavailable, name=name, brick=self.name)
        elif not event.configured():
            # it would raise, and fail the start of the brick
            self.logger.info(event_without_actions, name=name, brick=self.name)
        else:
            event.start()

    #############################
    # Console related operations.
    #############################

    def runtime_path(self, filename: str) -> str:
        return os.path.join(self.factory.runtime_dir, filename)

    def path(self) -> str:
        return self.runtime_path(f"{self.name}.ctl")

    def console(self) -> str:
        return self.runtime_path(f"{self.name}.mgmt")

    def connect(self, endpoint: Sock | HostonlySock, *args: str) -> None:
        for p in self.plugs:
            if not p.configured():
                p.connect(endpoint)
                self.changed.notify(self)
                return

    def disconnect(self) -> None:
        for p in self.plugs:
            if p.configured():
                p.disconnect()
        self.changed.notify(self)

    def open_console(self) -> None:
        term = str(get_setting("terminal"))
        args = [term, "-e", which(self.term_command), self.console()]
        self.logger.info(open_console, name=self.name, args=" ".join(args))
        _reactor().spawnProcess(TermProtocol(), term, args, os.environ)

    def send(self, data: bytes) -> None:
        assert isinstance(data, bytes)
        if self.proc is not None:
            self.proc.write(data)

    def get_state(self) -> str:
        """return state of the brick"""
        if self.is_running():
            state = _("running")
        elif not self._properly_connected():
            state = _("disconnected")
        else:
            state = _("off")
        return state

    def is_running(self) -> bool:
        return self.proc is not None

    def __repr__(self) -> str:
        return "<{0.type} {0.name}>".format(self)


class PrivilegedBrick(Brick):
    """A brick that runs with sudo unless Virtualbricks runs as root."""

    def need_sudo(self) -> bool:
        return os.geteuid() != 0


def _reactor() -> IReactorProcess:
    return cast("IReactorProcess", reactor)


def restart(brick: Brick, clock: IReactorTime) -> defer.Deferred[Any]:
    """Stop brick, killing it if it takes too long, and start it again."""

    logger.debug(restarting)
    stopped = brick.stop()
    call = clock.callLater(KILL_AFTER, brick.stop, kill=True)

    def cancel(passthru: object) -> object:
        if call.active():
            call.cancel()
        return passthru

    stopped.addBoth(cancel)
    stopped.addCallback(lambda _: brick.start())
    return stopped
