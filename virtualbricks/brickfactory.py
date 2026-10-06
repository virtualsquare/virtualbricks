# -*- test-case-name: virtualbricks.tests.test_brickfactory -*-
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

from __future__ import annotations

import os
import shlex
import sys
import threading
import re
import copy
import itertools
from collections.abc import Iterator, Mapping
from types import TracebackType
from typing import IO, TYPE_CHECKING, Any, TypeVar

import attr
from twisted.application import app
from twisted.internet import defer, task
from twisted.internet.posixbase import PosixReactorBase
from twisted.python import failure
from twisted.logger import (
    FilteringLogObserver,
    ILogObserver,
    LogLevel,
    LogLevelFilterPredicate,
    Logger,
    globalLogBeginner,
    globalLogPublisher,
)

from virtualbricks import errors, locations
from virtualbricks.bricks.plug import Plug
from virtualbricks.config.schema import field_values, references
from virtualbricks.config.settings import (
    get_setting,
    load_settings,
    load_state,
    store_settings,
)
from virtualbricks.config.workspace import projects
from virtualbricks import i18n
from virtualbricks.bricks import Brick, capture, netemu, router, switch
from virtualbricks.bricks import switchwrapper, tap, tunnelconnect
from virtualbricks.bricks import tunnellisten, virtualmachine, wire
from virtualbricks.errors import NameAlreadyInUseError
from virtualbricks.bricks.event import Event, is_event
from virtualbricks.bricks.eventaction import (
    StartAction,
    StopAction,
    StoredAction,
)
from virtualbricks.bricks.sock import Sock
from virtualbricks.i18n import _
from virtualbricks.observable import Observable, Signal
from virtualbricks.bricks import is_running
from virtualbricks.bricks.virtualmachine import (
    Disk,
    HostonlySock,
    Image,
    is_disk_image,
)

if TYPE_CHECKING:  # pragma: no cover
    from virtualbricks.remote.follower import Item

T = TypeVar("T")

logger = Logger()
engine_bye = "Engine: Bye!"
create_image = "Creating new disk image at '{path}'"
remove_socks = "Removing socks: {socks}"
disconnect_plug = "Disconnecting plug to {sock}"
removing_brick = "Removing brick {brick}"
shut_down = "Server Shut Down."
new_event_ok = "New event {name} OK"
uncaught_exception = "Uncaught exception: {error()}"


@attr.frozen
class Users:
    """What names a brick or an event, and loses it when it goes."""

    # the plugs of the other bricks in its sockets
    plugs: list[Plug]
    # (event, action): the actions of the other events that start or stop it
    actions: list[tuple[Event, StoredAction]]
    # (brick or event, field): the settings that name it, as When It Starts
    settings: list[tuple[Brick | Event, str]]


def _starts_or_stops(action: StoredAction, name: str) -> bool:
    return (
        isinstance(action, (StartAction, StopAction)) and action.target == name
    )


# The class of each type of brick, by its type in lower case: the name that
# new_brick() takes and the project file writes.
BRICK_CLASSES: dict[str, type[Brick]] = {
    cls.type.lower(): cls
    for cls in (
        capture.Capture,
        netemu.Netemu,
        router.Router,
        switch.Switch,
        switchwrapper.SwitchWrapper,
        tap.Tap,
        tunnelconnect.TunnelConnect,
        tunnellisten.TunnelListen,
        virtualmachine.VirtualMachine,
        wire.Wire,
    )
}


def normalize_name(name: str) -> str:
    """
    Return the new normalized name or raise InvalidNameError.

    Leading and trailing spaces are trimmed and spaces are replaced with
    underscores.

    :param str name: the chosen name for the brick.
    :raise InvalidNameError: if the name is invalid (malformatted of
        contains invalid characters).
    """

    if not isinstance(name, str):
        raise errors.InvalidNameError(_("Name must be a string"))
    if name == "":
        raise errors.InvalidNameError(_("A name can't be empty"))
    normalized_name = re.sub(r"\s+", "_", name.strip())
    if not re.search(r"\A[a-zA-Z]", normalized_name):
        raise errors.InvalidNameError(_("A name starts with a letter"))
    if not re.search(r"\A[a-zA-Z0-9_\.-]+\Z", normalized_name):
        raise errors.InvalidNameError(
            _(
                "A name has only letters, digits, underscores (_), hyphens"
                " (-) and dots (.)"
            )
        )
    return normalized_name


class BrickFactory:
    """This is the main class for the core engine.

    All the bricks are created and stored in the factory.
    """

    @property
    def bricks(self) -> Iterator[Brick]:
        """The bricks, in the order they came in."""

        return iter(self._bricks)

    @property
    def events(self) -> Iterator[Event]:
        """The events, in the order they came in."""

        return iter(self._events.values())

    @property
    def images(self) -> Iterator[Image]:
        """The disk images, in the order they came in."""

        return iter(self._disk_images.values())

    def __init__(self, quit: defer.Deferred[None]) -> None:
        self.quit_d = quit
        self._bricks: list[Brick] = []
        self._events: dict[str, Event] = {}
        self.socks: list[Sock] = []
        self._disk_images: dict[str, Image] = {}
        # Where the sockets of the running bricks are; each open project
        # gets a directory of its own.
        self.runtime_dir = locations.runtime_dir()
        observable = Observable()
        self.quitting = Signal(observable, "quit")
        self.brick_added = Signal(observable, "brick-added")
        self.brick_removed = Signal(observable, "brick-removed")
        self.brick_changed = Signal(observable, "brick-changed")
        self.event_added = Signal(observable, "event-added")
        self.event_removed = Signal(observable, "event-removed")
        self.event_changed = Signal(observable, "event-changed")
        self.image_added = Signal(observable, "image-added")
        self.image_removed = Signal(observable, "image-removed")
        self.image_changed = Signal(observable, "image-changed")

    def quit(self) -> None:
        if any(is_running(brick) for brick in self._bricks):
            msg = _("Cannot close virtualbricks: there are running bricks")
            raise errors.BrickRunningError(msg)
        logger.info(engine_bye)
        for e in self._events.values():
            e.stop()
        self.quitting.notify(self)
        if not self.quit_d.called:
            self.quit_d.callback(None)

    def reset(self) -> None:
        if any(is_running(brick) for brick in self._bricks):
            msg = _("Project cannot be closed: there are running bricks")
            raise errors.BrickRunningError(msg)
        # all go, so nothing is told that it loses one of them
        # Don't change the list while iterating over it
        for brick in list(self._bricks):
            self._remove_brick(brick)

        # Don't change the list while iterating over it
        for e in list(self._events.values()):
            self._remove_event(e)

        del self.socks[:]
        for image in list(self._disk_images.values()):
            self.remove_image(image)

    # Disk Images

    def new_image(self, name: str, path: str, description: str = "") -> Image:
        """Add one disk image to the library."""

        logger.info(create_image, path=path)
        new_name = normalize_name(name)
        path = os.path.abspath(path)
        if self.get_image(new_name) is not None:
            raise NameAlreadyInUseError(new_name, "image")
        if self.get_image_by_path(path) is not None:
            raise errors.ImageAlreadyInUseError(path)
        disk_image = virtualmachine.Image(new_name, path, description)
        self._disk_images[new_name] = disk_image
        disk_image.changed.connect(self.image_changed.notify)
        self.image_added.notify(disk_image)
        return disk_image

    def remove_image(self, disk_image: Image) -> list[Disk]:
        """
        Remove an image from the library. The disks that used it are left
        without an image, and returned; their private copies stay.
        """

        disks = [
            disk
            for brick in self._bricks
            if virtualmachine.is_virtualmachine(brick)
            for disk in brick.disks()
            if disk.image is disk_image
        ]
        for disk in disks:
            # through the machine, which tells that it changed
            disk.vm.update_config({f"{disk.device}_image": ""})
        disk_image.changed.disconnect(self.image_changed.notify)
        del self._disk_images[disk_image.name]
        self.image_removed.notify(disk_image)
        return disks

    def get_image(self, name: str) -> Image | None:
        """Return a disk image given its name."""

        return self._disk_images.get(name)

    def get_image_by_path(self, path: str) -> Image | None:
        """Get disk image object from the image library by its path."""

        for disk_image in self._disk_images.values():
            if disk_image.path == path:
                return disk_image
        return None

    # Bricks

    def new_brick(
        self, type: str, name: str, host: str = "", remote: bool = False
    ) -> Brick:
        """Return a new brick.

        @param type: The type of new brick.
        @type type: C{str}
        @param name: The name for the new brick. Must contains only letters,
            numbers, underscores, hyphens and points. Must not be already in
            use.
        @type name: C{str}
        @return: the new brick.
        @raises: InvalidNameError, InvalidTypeError
        """

        BrickClass = self._brick_class(type)
        name = normalize_name(name)
        if self.get_brick(name) is not None:
            raise NameAlreadyInUseError(name, "brick")
        brick = BrickClass(self, name)
        self._bricks.append(brick)
        brick.changed.connect(self.brick_changed.notify)
        self.brick_added.notify(brick)
        return brick

    def _brick_class(self, type: str) -> type[Brick]:
        try:
            return BRICK_CLASSES[type.lower()]
        except KeyError:
            raise errors.InvalidTypeError(_("Invalid brick type %s") % type)

    def duplicate_brick(self, brick: Brick) -> Brick:
        name = self.next_name(brick.name)
        new_brick = self.new_brick(brick.get_type(), name)
        new_brick.update_config(copy.deepcopy(field_values(brick.config)))

        for p in brick.plugs:
            if p.sock is not None:
                new_brick.connect(p.sock)

        return new_brick

    def remove_brick(self, brick: Brick) -> None:
        """
        Delete a brick that doesn't run. What plugs into it is unplugged,
        and the events lose their actions that start or stop it.
        """

        if is_running(brick):
            msg = f"Cannot delete brick {brick.name}: brick is running"
            raise errors.BrickRunningError(msg)
        self._forget(brick.name, self.users(brick))
        self._remove_brick(brick)

    def _remove_brick(self, brick: Brick) -> None:
        logger.info(removing_brick, brick=brick.name)
        if brick.socks:
            logger.info(
                remove_socks, socks=", ".join(s.nickname for s in brick.socks)
            )
            for sock in [s for s in self.socks if s.brick is brick]:
                self.remove_sock(sock)
        for plug in brick.plugs:
            if plug.configured():
                plug.disconnect()
        brick.changed.disconnect(self.brick_changed.notify)
        self._bricks.remove(brick)
        self.brick_removed.notify(brick)

    def get_brick(self, name: str) -> Brick | None:
        """Return a brick given its name."""

        for brick in self._bricks:
            if brick.name == name:
                return brick
        return None

    # Events

    def new_event(self, name: str) -> Event:
        """Create a new event.

        @arg name: The event name.
        @type name: C{str}
        @return: The new created event.
        @raises: InvalidNameError, InvalidTypeError
        """

        norm_name = normalize_name(name)
        if self.get_event(norm_name) is not None:
            raise NameAlreadyInUseError(norm_name, "event")
        event = Event(self, norm_name)
        logger.debug(new_event_ok, name=norm_name)
        self._events[norm_name] = event
        event.changed.connect(self.event_changed.notify)
        self.event_added.notify(event)
        return event

    def duplicate_event(self, event: Event) -> Event:
        name = self.next_name(event.name)
        new = self.new_event(name)
        new.config = copy.deepcopy(event.config)
        return new

    def remove_event(self, event: Event) -> None:
        """
        Delete an event, stopped first if it waits. The other events lose
        their actions that start or stop it, and the bricks that run it
        when they start or stop run nothing then.
        """

        self._forget(event.name, self.users(event))
        self._remove_event(event)

    def _remove_event(self, event: Event) -> None:
        event.stop()
        event.changed.disconnect(self.event_changed.notify)
        del self._events[event.name]
        self.event_removed.notify(event)

    def users(self, item: Brick | Event) -> Users:
        """What names the brick or the event item, and loses it if it goes."""

        name = item.name
        target = "event" if is_event(item) else "brick"
        bricks: list[Brick | Event] = [
            brick for brick in self._bricks if brick is not item
        ]
        events = [
            event for event in self._events.values() if event is not item
        ]
        plugs = [
            plug
            for brick in self._bricks
            if brick is not item
            for plug in brick.plugs
            if plug.sock is not None and plug.sock.brick is item
        ]
        actions = [
            (event, action)
            for event in events
            for action in event.config.actions
            if _starts_or_stops(action, name)
        ]
        settings = [
            (other, field)
            for other in bricks + events
            for field, kind, value in references(other.config)
            if kind == target and value == name
        ]
        return Users(plugs, actions, settings)

    def _forget(self, name: str, users: Users) -> None:
        """The actions of users go, and its settings empty."""

        # one change for each, which tells that it changed
        changes: dict[Brick | Event, dict[str, object]] = {}
        for event, _action in users.actions:
            changes[event] = {
                "actions": [
                    action
                    for action in event.config.actions
                    if not _starts_or_stops(action, name)
                ]
            }
        for other, field in users.settings:
            changes.setdefault(other, {})[field] = ""
        for other, values in changes.items():
            other.update_config(values)

    def get_event(self, name: str) -> Event | None:
        """Return an event given its name."""

        return self._events.get(name)

    def unused_name(self, name: str) -> str:
        c = 1
        orig_name = name
        while self.name_in_use(name):
            name = f"{orig_name}.{c}"
            c += 1
        return name

    def next_name(self, name: str) -> str:
        """The name of a copy: the number at the end of name, increased.

        The first free one from there: the copy of sw1 is sw2, or sw3 if sw2
        is in use; a name without a number takes 2, node2 for node. The zeros
        in front stay: vm02 for vm01.
        """

        found = re.fullmatch(r"(.*?)(\d*)", name)
        assert found is not None, "any name matches"
        prefix, digits = found.groups()
        start = int(digits) + 1 if digits else 2
        candidates = (
            f"{prefix}{number:0{len(digits)}d}"
            for number in itertools.count(start)
        )
        return next(c for c in candidates if not self.name_in_use(c))

    def name_in_use(self, name: str) -> bool:
        """Whether a brick, an event or a disk image already has the name."""

        return self._holder(name) is not None

    def _holder(self, name: str) -> str | None:
        """What has the name: "brick", "event", "image", or None."""

        if self.get_brick(name) is not None:
            return "brick"
        if self.get_event(name) is not None:
            return "event"
        if self.get_image(name) is not None:
            return "image"
        return None

    def rename_item(self, brick: Item, name: str) -> str:
        """Rename a brick, event or image, and every reference to it."""

        prev_name = brick.name
        new_name = self.check_name(name)
        # the actions of the events name bricks too
        target = "brick"
        # Update indexes
        if is_disk_image(brick):
            self._disk_images[new_name] = brick
            del self._disk_images[prev_name]
            target = "image"
        elif is_event(brick):
            self._events[new_name] = brick
            del self._events[prev_name]
            target = "event"
        brick.set_name(new_name)
        for obj in itertools.chain(self._bricks, self._events.values()):
            if obj.rename_references(target, prev_name, new_name):
                obj.changed.notify(obj)
        return prev_name

    def check_name(self, name: str) -> str:
        """
        Return the new normalized name or raise InvalidNameError.

        :param str name: the chosen name for the brick.
        :raise InvalidNameError: if the name is invalid (malformatted of
            contains invalid characters).
        :raise NameAlreadyInUseError: if the name is already in use.
        """

        normalized_name = normalize_name(name)
        holder = self._holder(normalized_name)
        if holder is not None:
            raise errors.NameAlreadyInUseError(normalized_name, holder)
        return normalized_name

    def check_socket_room(self, name: str) -> None:
        """
        Raise InvalidNameError if a brick's name is too long for its sockets.

        The sockets are in the runtime directory of the open project, and a
        Unix socket path has at most 107 bytes.
        """

        room = locations.brick_name_room(self.runtime_dir)
        size = len(os.fsencode(name))
        if size > room:
            msg = _(
                "The name is {size} bytes long, and the sockets of this"
                " project leave room for {room}"
            )
            raise errors.InvalidNameError(msg.format(size=size, room=room))

    def check_brick_name(self, type: str, name: str) -> str:
        """
        Return name normalized, or raise InvalidNameError if a brick of type
        can't have it: it is in use, too long for the sockets of the project,
        or refused by the kind, as a tap's longer than an interface's.

        new_brick() doesn't check these, so that a project with such names
        still opens: New Brick, Rename and the console's new ask this first.
        """

        brick_class = self._brick_class(type)
        normalized_name = self.check_name(name)
        self.check_socket_room(normalized_name)
        brick_class.check_name(normalized_name)
        return normalized_name

    def new_sock(self, brick: Brick, name: str = "") -> Sock:
        sock = Sock(brick, name)
        self.socks.append(sock)
        return sock

    def remove_sock(self, sock: Sock) -> None:
        """Forget a socket: what plugs into it is unplugged."""

        for plug in list(sock.plugs):
            logger.info(disconnect_plug, sock=sock.nickname)
            plug.disconnect()
        self.socks.remove(sock)

    def get_sock(self, name: str) -> Sock | HostonlySock | None:
        if name == "_hostonly":
            return virtualmachine.hostonly_sock
        for sock in self.socks:
            if sock.nickname == name:
                return sock
        return None


def AutosaveTimer(
    factory: BrickFactory, interval: float = 180
) -> task.LoopingCall:
    timer = task.LoopingCall(projects.autosave, factory)
    timer.start(interval, now=False)
    return timer


def log_level(verbosity: int) -> LogLevel:
    """Return the minimum level logged for the given -v/-q verbosity."""

    if verbosity > 0:
        return LogLevel.debug
    if verbosity == 0:
        return LogLevel.info
    if verbosity == -1:
        return LogLevel.warn
    return LogLevel.error


class AppLogger(app.AppLogger):

    def __init__(self, options: Mapping[str, Any]) -> None:
        self._observer_factory = options.get("logger")
        self._level = log_level(options.get("verbosity", 0))
        self._observers: list[ILogObserver] = []

    def get_observers(self) -> list[ILogObserver]:
        if self._observer_factory is None:
            return []
        observer = FilteringLogObserver(
            self._observer_factory(),
            [LogLevelFilterPredicate(self._level)],
        )
        return [observer]

    def start(self, application: object) -> None:
        self._observers = self.get_observers()
        # The standard streams are used by the interactive console.
        globalLogBeginner.beginLoggingTo(
            self._observers, redirectStandardIO=False
        )
        self._initialLog()

    def stop(self) -> None:
        logger.info(shut_down)
        for observer in self._observers:
            globalLogPublisher.removeObserver(observer)
        self._observers = []


class Application:

    logger_factory: type[AppLogger] = AppLogger
    factory_factory: type[BrickFactory] = BrickFactory

    def __init__(self, config: Mapping[str, Any]) -> None:
        self.config = config
        self.logger = self.logger_factory(config)

    def getComponent(self, interface: object, default: T) -> T:
        return default

    def install_locale(self) -> None:
        i18n.install()

    def install_settings(self) -> None:
        load_settings()
        load_state()

    def install_workspace(self) -> None:
        # the folder of the command line, for this run only: the setting
        # stays as it is. Either stays for the run, whose lock is that of
        # this folder: a new setting is for the next start.
        projects.path = self.config.get("workspace") or str(
            get_setting("workspace")
        )

    def install_sys_hooks(self) -> None:
        sys.excepthook = self.excepthook
        threading.excepthook = self.thread_excepthook

    def thread_excepthook(self, args: threading.ExceptHookArgs) -> None:
        # Like threading's default hook, a thread may exit silently.
        if args.exc_type is SystemExit:
            return
        self.excepthook(args.exc_type, args.exc_value, args.exc_traceback)

    def excepthook(
        self,
        exc_type: type[BaseException],
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if exc_type in (SystemExit, KeyboardInterrupt):
            assert exc_value is not None, "what is raised is there"
            sys.__excepthook__(exc_type, exc_value, traceback)
        else:
            fail = failure.Failure(exc_value, exc_type, traceback)
            logger.error(
                uncaught_exception,
                log_failure=fail,
                error=lambda: fail.getErrorMessage(),
            )

    def install_home(self) -> None:
        # with the link to the workspace, and room for its socket
        projects.make_runtime_dir()

    def get_namespace(self) -> dict[str, object]:
        return {}

    def migrate(self) -> defer.Deferred[Any] | None:
        """Convert the files of older versions, once; may return a Deferred."""

        from virtualbricks.migrate import startup_migration

        migration = startup_migration(self.config.get("workspace"))
        if migration is not None:
            migration.run()
            migration.log(logger)
        return None

    def run(self, reactor: PosixReactorBase) -> defer.Deferred[None]:
        self.install_locale()
        d = defer.maybeDeferred(self.migrate)
        return d.addCallback(lambda _: self._start(reactor))

    def _start(self, reactor: PosixReactorBase) -> defer.Deferred[None]:
        self.install_settings()
        self.install_workspace()
        self.logger.start(self)
        self.install_home()
        quit: defer.Deferred[None] = defer.Deferred()
        factory = self.factory_factory(quit)
        self._run(factory)
        if self.config["verbosity"] >= 2 and not self.config["noterm"]:
            import signal
            import pdb

            signal.signal(signal.SIGUSR2, lambda *args: pdb.set_trace())
            signal.signal(signal.SIGINT, lambda *args: pdb.set_trace())
            app.fixPdb()
        reactor.addSystemEventTrigger("before", "shutdown", store_settings)
        self.open_last_project(factory)
        self.listen(factory, reactor)
        reactor.addSystemEventTrigger(
            "before", "shutdown", projects.save, factory
        )
        reactor.addSystemEventTrigger("before", "shutdown", self.logger.stop)
        AutosaveTimer(factory)
        started: defer.Deferred[Any] = defer.succeed(None)
        if self.config.get("run"):
            started = self.run_script(factory, self.config["run"])
        if not self.config["noterm"]:
            started.addCallback(lambda _: self.start_console(factory))
        # delay as much as possible the installation of hooks because the
        # exception hook can hide errors in the code requiring to start the
        # application again with logging redirected
        self.install_sys_hooks()
        return quit

    def _run(self, factory: BrickFactory) -> None:
        pass

    def start_console(self, factory: BrickFactory) -> None:
        """Read the console in the terminal that started Virtualbricks."""

        from virtualbricks.console.terminal import start

        start(factory, self.get_namespace())

    def listen(self, factory: BrickFactory, reactor: PosixReactorBase) -> None:
        """Answer on the control sockets of --listen; on none without it."""

        sockets = self.config.get("sockets")
        if not sockets:
            return
        from virtualbricks.console.control import listen

        for socket in sockets:
            listen(factory, socket, reactor)

    def run_script(
        self, factory: BrickFactory, path: str
    ) -> defer.Deferred[list[str]]:
        """Run the commands of path, as the console's source does."""

        from virtualbricks.console.dispatch import run
        from virtualbricks.console.terminal import error_lines

        done = run(factory, f"source {shlex.quote(path)}")

        def write(lines: list[str], stream: IO[str]) -> None:
            for line in lines:
                stream.write(line + "\n")
            stream.flush()

        done.addCallbacks(
            write,
            lambda failure: write(error_lines(failure), sys.stderr),
            callbackArgs=(sys.stdout,),
        )
        return done

    def open_last_project(self, factory: BrickFactory) -> None:
        """Open the project open last, or a new new_project_N."""

        projects.restore_last(factory)
