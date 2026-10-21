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

import collections
import functools
import io
import locale
import os
import re
import shlex
from collections.abc import Collection
from contextlib import AbstractContextManager
from typing import TYPE_CHECKING, Any, ClassVar, Protocol, TypeVar, cast

from twisted.internet import defer, error, protocol, reactor
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
from virtualbricks.bricks.plug import Plug
from virtualbricks.config.report import Report
from virtualbricks.config.schema import (
    Path,
    Ref,
    check_value,
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
from virtualbricks.programs import vde_info
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
    "must_stop",
    "terminal_command",
]


system_encoding = locale.getpreferredencoding(do_setlocale=True)
_T = TypeVar("_T")

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
calling_off = "Stopping {name} before its program runs"
attribute_set = "Attribute {attr} set in {brick} with value {value}."
start_brick = "Starting: {args}"
# not {warning}: twisted.python.log takes that field for a warning of Python
left_out = "{text}"
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


# The places of the setting terminal: the console and the brick (page 32).
CONSOLE_PLACE = "{command}"
TERMINAL_PLACES = re.compile(r"\{(command|name)\}")


def _typed_words(setting: str) -> list[tuple[str, str]]:
    """
    The words of setting, split as the shell splits them, each with its
    text as typed, quotes included. ValueError if they don't split.
    """

    stream = io.StringIO(setting)
    lexer = shlex.shlex(stream, posix=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    words = []
    start = 0
    # the lexer reads a character at a time: what it read for a word is
    # the word, with the spaces around it
    for word in lexer:
        end = stream.tell()
        words.append((word, setting[start:end].strip()))
        start = end
    return words


def terminal_command(setting: str, command: list[str], name: str) -> list[str]:
    """
    The words that open, in the terminal of setting, the console of the
    brick name, which runs command. {command} typed as a word of its own
    becomes the words of command; inside another word or in quotes, command
    quoted for the shell, as one word. {name} becomes the name. A setting
    without {command} gets "-e {command}" at its end, as the terminal used
    to be run.
    """

    try:
        words = _typed_words(setting)
    except ValueError as exc:
        raise errors.BadConfigError(
            _("The setting terminal can't be read: {error}").format(error=exc)
        ) from None
    if not words:
        raise errors.BadConfigError(_("The setting terminal is empty"))
    if not any(CONSOLE_PLACE in word for word, _typed in words):
        words += [("-e", "-e"), (CONSOLE_PLACE, CONSOLE_PLACE)]
    places = {"command": shlex.join(command), "name": name}
    line: list[str] = []
    for word, typed in words:
        if typed == CONSOLE_PLACE:
            line += command
        else:
            line.append(
                TERMINAL_PLACES.sub(lambda place: places[place[1]], word)
            )
    return line


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
        Set the settings in changes, a mapping of names to values, all or
        none: KeyError for a name the config doesn't have, ValueError for a
        value its field refuses, before anything changes. The values that
        change are all set, then each goes to the ``cbset_<name>`` method of
        the brick, if it has one, which sees the whole new config; and the
        brick says it changed, once.
        """

        for name, value in changes.items():
            self._check_option(name)
            check_value(self.config, name, value)
        changed = {
            name: value
            for name, value in changes.items()
            if value != getattr(self.config, name)
        }
        for name, value in changed.items():
            logger.info(attribute_set, attr=name, brick=self, value=value)
            setattr(self.config, name, value)
        for name, value in changed.items():
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


def must_stop(brick: Brick) -> bool:
    """
    Whether brick runs a program of Virtualbricks, or is starting one, which
    has to stop before the brick is deleted or renamed, the project closes or
    Virtualbricks quits. A switch wrapper runs while another program runs its
    switch.
    """

    return brick.runs_program and (brick.is_running() or brick.starting())


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
    # Whether a stop came during the start under way: its program won't run.
    _called_off = False
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
    # The programs it runs.
    programs: tuple[str, ...] = ()
    # Whether Virtualbricks runs and stops the program of the brick, or
    # another program does: a switch wrapper.
    runs_program: ClassVar[bool] = True

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

    def start(
        self, resume: str = "", *, chain: tuple[Brick, ...] = ()
    ) -> defer.Deferred[Brick]:
        """
        Start the brick, in stages.

        A brick that isn't configured or connected is refused. The bricks it
        plugs into start first, and a loop is refused: a brick that its links
        lead back to. Then prepare() gathers what the command line needs,
        command() writes it, and spawn() starts the program; once it runs,
        the event of the brick's start runs. A call while a start is under
        way waits for it, as when Start All starts a switch and the wire that
        plugs into it; a stop calls it off. The brick says it changed when the
        start begins, when its program runs and when the start fails.

        resume is the saved state that a virtual machine starts from; the
        other bricks have none. chain is the bricks whose starts led to this
        one through their plugs, in order: a brick already in it is on a
        loop, and the error names the bricks of the loop. Return a Deferred
        that fires with the brick once its program runs.
        """

        if self.is_running():
            return defer.succeed(self)
        if self in chain:
            loop = chain[chain.index(self) :] + (self,)
            return defer.fail(
                errors.LinkLoopError([brick.name for brick in loop])
            )
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
        self._called_off = False
        self._exited_d = defer.Deferred()
        self.changed.notify(self)
        chain += (self,)
        d = defer.DeferredList(
            [plug.connected(chain) for plug in self.plugs],
            fireOnOneErrback=True,
            consumeErrors=True,
        )

        def go_on(passthru: _T) -> _T:
            if self._called_off:
                raise errors.StartCalledOffError(self.name)
            return passthru

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
            # stopped, before those who wait hear of it
            self.changed.notify(self)
            for waiter in waiting:
                waiter.errback(failure)
            return None

        # a stop that comes while the start waits calls it off
        prepared = d.addCallback(go_on).addCallback(
            lambda _: self.prepare(resume)
        )
        spawned = (
            prepared.addCallback(go_on)
            .addCallback(self.command)
            .addCallback(self.spawn)
        )
        spawned.addCallback(start_related_events).addErrback(eb)
        return started

    def starting(self) -> bool:
        """Whether a start of the brick is under way."""

        return self._waiting is not None

    def stop(self, kill: bool = False) -> defer.Deferred[tuple[Brick, object]]:
        """
        Stop the program of the brick, with SIGTERM, or SIGKILL if kill.

        A brick that is starting doesn't run its program: the start fails
        with StartCalledOffError once it has waited for the bricks it plugs
        into and for prepare(). Return a Deferred that fires with the brick
        and how its program ended, once it ended or the start did.
        """

        if self.proc is None:
            if self._waiting is not None:
                return self._call_off(self._waiting, kill)
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

    def _call_off(
        self, waiting: list[defer.Deferred[Brick]], kill: bool
    ) -> defer.Deferred[tuple[Brick, object]]:
        self.logger.info(calling_off, name=self.name)
        self._called_off = True
        waiter: defer.Deferred[Brick] = defer.Deferred()
        waiting.append(waiter)
        # the start fails, as it should; a program that ran is stopped
        return waiter.addCallbacks(
            lambda _: self.stop(kill), lambda _: (self, self._last_status)
        )

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

        vde = vde_info(str(get_setting("vde_path")))
        return defer.succeed(Prepared(vde=vde))

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
            self.logger.warn(left_out, text=warning)
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
        args = terminal_command(
            str(get_setting("terminal")),
            [which(self.term_command), self.console()],
            self.name,
        )
        self.logger.info(open_console, name=self.name, args=shlex.join(args))
        _reactor().spawnProcess(TermProtocol(), args[0], args, os.environ)

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
