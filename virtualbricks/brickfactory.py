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

import os
import shlex
import sys
import threading
import re
import copy
import itertools

import attr
from twisted.application import app
from twisted.internet import defer, task
from twisted.python import failure
from twisted.logger import (
    FilteringLogObserver,
    LogLevel,
    LogLevelFilterPredicate,
    Logger,
    globalLogBeginner,
    globalLogPublisher,
)

from virtualbricks import errors, locations
from virtualbricks.config.schema import field_values, references
from virtualbricks.config.settings import (
    get_setting,
    load_settings,
    load_state,
    store_settings,
)
from virtualbricks.config.workspace import projects
from virtualbricks import i18n
from virtualbricks.bricks import capture, netemu, router, switch
from virtualbricks.bricks import switchwrapper, tap, tunnelconnect
from virtualbricks.bricks import tunnellisten, virtualmachine, wire
from virtualbricks.errors import NameAlreadyInUseError
from virtualbricks.bricks.event import Event, is_event
from virtualbricks.bricks.eventaction import StartAction, StopAction
from virtualbricks.bricks.sock import Sock
from virtualbricks.i18n import _
from virtualbricks.observable import Observable, Signal
from virtualbricks.bricks import is_running
from virtualbricks.bricks.virtualmachine import is_disk_image

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
    plugs: list
    # (event, action): the actions of the other events that start or stop it
    actions: list
    # (brick or event, field): the settings that name it, as When It Starts
    settings: list


def _starts_or_stops(action, name) -> bool:
    return (
        isinstance(action, (StartAction, StopAction)) and action.target == name
    )


# The class of each type of brick, by its type in lower case: the name that
# new_brick() takes and the project file writes.
BRICK_CLASSES = {
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


def normalize_name(name):
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
    def bricks(self):
        """The bricks, in the order they came in."""

        return iter(self._bricks)

    @property
    def events(self):
        """The events, in the order they came in."""

        return iter(self._events.values())

    @property
    def images(self):
        """The disk images, in the order they came in."""

        return iter(self._disk_images.values())

    def __init__(self, quit):
        self.quit_d = quit
        self._bricks = []
        self._events = {}
        self.socks = []
        self._disk_images = {}
        # Where the sockets of the running bricks are; each open project
        # gets a directory of its own.
        self.runtime_dir = locations.runtime_dir()
        observable = Observable()
        self.changed = Signal(observable, "brick-changed")
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

    def quit(self):
        if any(is_running(brick) for brick in self._bricks):
            msg = _("Cannot close virtualbricks: there are running bricks")
            raise errors.BrickRunningError(msg)
        logger.info(engine_bye)
        for e in self._events.values():
            e.stop()
        self.quitting.notify(self)
        if not self.quit_d.called:
            self.quit_d.callback(None)

    def reset(self):
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

    def new_image(self, name, path, description=""):
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

    def remove_image(self, disk_image):
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

    def get_image(self, name):
        """
        Return a disk image given its name.

        :type name: str
        :rtype: Optional[virtualbricks.bricks.virtualmachine.Image]
        """

        return self._disk_images.get(name)

    def get_image_by_path(self, path):
        """
        Get disk image object from the image library by its path.

        :type path: str
        :rtype: Optional[virtualbricks.bricks.virtualmachine.Image]
        """

        for disk_image in self._disk_images.values():
            if disk_image.path == path:
                return disk_image

    # Bricks

    def new_brick(self, type, name, host="", remote=False):
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

    def _brick_class(self, type):
        try:
            return BRICK_CLASSES[type.lower()]
        except KeyError:
            raise errors.InvalidTypeError(_("Invalid brick type %s") % type)

    def duplicate_brick(self, brick):
        name = self.next_name(brick.name)
        new_brick = self.new_brick(brick.get_type(), name)
        new_brick.update_config(copy.deepcopy(field_values(brick.config)))

        for p in brick.plugs:
            if p.sock is not None:
                new_brick.connect(p.sock)

        return new_brick

    def remove_brick(self, brick):
        """
        Delete a brick that doesn't run. What plugs into it is unplugged,
        and the events lose their actions that start or stop it.
        """

        if is_running(brick):
            msg = f"Cannot delete brick {brick.name}: brick is running"
            raise errors.BrickRunningError(msg)
        self._forget(brick.name, self.users(brick))
        self._remove_brick(brick)

    def _remove_brick(self, brick):
        logger.info(removing_brick, brick=brick.name)
        socks = set(brick.socks)
        if socks:
            logger.info(
                remove_socks, socks=", ".join(s.nickname for s in socks)
            )
            for _brick in self._bricks:
                for plug in _brick.plugs:
                    if plug.configured() and plug.sock in socks:
                        logger.info(disconnect_plug, sock=plug.sock.nickname)
                        plug.disconnect()
            for sock in [s for s in self.socks if s.brick is brick]:
                self.socks.remove(sock)
        for plug in brick.plugs:
            if plug.configured():
                plug.disconnect()
        brick.changed.disconnect(self.brick_changed.notify)
        self._bricks.remove(brick)
        self.brick_removed.notify(brick)

    def get_brick(self, name):
        """
        Return a brick given its name.

        :type name: str
        :rtype: Optional[virtualbricks.bricks.Brick]
        """

        for brick in self._bricks:
            if brick.name == name:
                return brick
        return None

    # Events

    def new_event(self, name):
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

    def duplicate_event(self, event):
        name = self.next_name(event.name)
        new = self.new_event(name)
        new.config = copy.deepcopy(event.config)
        return new

    def remove_event(self, event):
        """
        Delete an event, stopped first if it waits. The other events lose
        their actions that start or stop it, and the bricks that run it
        when they start or stop run nothing then.
        """

        self._forget(event.name, self.users(event))
        self._remove_event(event)

    def _remove_event(self, event):
        event.stop()
        event.changed.disconnect(self.event_changed.notify)
        del self._events[event.name]
        self.event_removed.notify(event)

    def users(self, item) -> Users:
        """What names the brick or the event item, and loses it if it goes."""

        name = item.name
        target = "event" if is_event(item) else "brick"
        bricks = [brick for brick in self._bricks if brick is not item]
        events = [
            event for event in self._events.values() if event is not item
        ]
        plugs = [
            plug
            for brick in bricks
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

    def _forget(self, name, users):
        """The actions of users go, and its settings empty."""

        # one change for each, which tells that it changed
        changes = {}
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

    def get_event(self, name):
        """
        Return an event given its name.

        :type name: str
        :rtype: Optional[virtualbricks.bricks.event.Event]
        """

        return self._events.get(name)

    def unused_name(self, name):
        c = 1
        orig_name = name
        while self.name_in_use(name):
            name = f"{orig_name}.{c}"
            c += 1
        return name

    def next_name(self, name):
        """The name of a copy: the number at the end of name, increased.

        The first free one from there: the copy of sw1 is sw2, or sw3 if sw2
        is in use; a name without a number takes 2, node2 for node. The zeros
        in front stay: vm02 for vm01.
        """

        prefix, digits = re.fullmatch(r"(.*?)(\d*)", name).groups()
        start = int(digits) + 1 if digits else 2
        for number in itertools.count(start):
            candidate = f"{prefix}{number:0{len(digits)}d}"
            if not self.name_in_use(candidate):
                return candidate

    def name_in_use(self, name):
        """Whether a brick, an event or a disk image already has the name."""

        return self._holder(name) is not None

    def _holder(self, name):
        """What has the name: "brick", "event", "image", or None."""

        if self.get_brick(name) is not None:
            return "brick"
        if self.get_event(name) is not None:
            return "event"
        if self.get_image(name) is not None:
            return "image"
        return None

    def rename_item(self, brick, name):
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

    def check_name(self, name):
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

    def check_socket_room(self, name):
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

    def check_brick_name(self, type, name):
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

    def new_sock(self, brick, name=""):
        sock = Sock(brick, name)
        self.socks.append(sock)
        return sock

    def get_sock(self, name):
        if name == "_hostonly":
            return virtualmachine.hostonly_sock
        for sock in self.socks:
            if sock.nickname == name:
                return sock


def AutosaveTimer(factory, interval=180):
    timer = task.LoopingCall(projects.autosave, factory)
    timer.start(interval, now=False)
    return timer


def log_level(verbosity):
    """Return the minimum level logged for the given -v/-q verbosity."""

    if verbosity > 0:
        return LogLevel.debug
    if verbosity == 0:
        return LogLevel.info
    if verbosity == -1:
        return LogLevel.warn
    return LogLevel.error


class AppLogger(app.AppLogger):

    def __init__(self, options):
        self._observer_factory = options.get("logger")
        self._level = log_level(options.get("verbosity", 0))
        self._observers = []

    def get_observers(self):
        if self._observer_factory is None:
            return []
        observer = FilteringLogObserver(
            self._observer_factory(),
            [LogLevelFilterPredicate(self._level)],
        )
        return [observer]

    def start(self, application):
        self._observers = self.get_observers()
        # The standard streams are used by the interactive console.
        globalLogBeginner.beginLoggingTo(
            self._observers, redirectStandardIO=False
        )
        self._initialLog()

    def stop(self):
        logger.info(shut_down)
        for observer in self._observers:
            globalLogPublisher.removeObserver(observer)
        self._observers = []


class Application:

    logger_factory = AppLogger
    factory_factory = BrickFactory

    def __init__(self, config):
        self.config = config
        self.logger = self.logger_factory(config)

    def getComponent(self, interface, default):
        return default

    def install_locale(self):
        i18n.install()

    def install_settings(self):
        load_settings()
        load_state()

    def install_workspace(self):
        # the folder of the command line, for this run only: the setting
        # stays as it is. Either stays for the run, whose lock is that of
        # this folder: a new setting is for the next start.
        projects.path = self.config.get("workspace") or str(
            get_setting("workspace")
        )

    def install_sys_hooks(self):
        sys.excepthook = self.excepthook
        threading.excepthook = self.thread_excepthook

    def thread_excepthook(self, args):
        # Like threading's default hook, a thread may exit silently.
        if args.exc_type is SystemExit:
            return
        self.excepthook(args.exc_type, args.exc_value, args.exc_traceback)

    def excepthook(self, exc_type, exc_value, traceback):
        if exc_type in (SystemExit, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, traceback)
        else:
            fail = failure.Failure(exc_value, exc_type, traceback)
            logger.error(
                uncaught_exception,
                log_failure=fail,
                error=lambda: fail.getErrorMessage(),
            )

    def install_home(self):
        # with the link to the workspace, and room for its socket
        projects.make_runtime_dir()

    def get_namespace(self):
        return {}

    def migrate(self):
        """Convert the files of older versions, once; may return a Deferred."""

        from virtualbricks.migrate import startup_migration

        migration = startup_migration(self.config.get("workspace"))
        if migration is not None:
            migration.run()
            migration.log(logger)

    def run(self, reactor):
        self.install_locale()
        d = defer.maybeDeferred(self.migrate)
        d.addCallback(lambda _: self._start(reactor))
        return d

    def _start(self, reactor):
        self.install_settings()
        self.install_workspace()
        self.logger.start(self)
        self.install_home()
        quit = defer.Deferred()
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
        started = defer.succeed(None)
        if self.config.get("run"):
            started = self.run_script(factory, self.config["run"])
        if not self.config["noterm"]:
            started.addCallback(lambda _: self.start_console(factory))
        # delay as much as possible the installation of hooks because the
        # exception hook can hide errors in the code requiring to start the
        # application again with logging redirected
        self.install_sys_hooks()
        return quit

    def _run(self, factory):
        pass

    def start_console(self, factory):
        """Read the console in the terminal that started Virtualbricks."""

        from virtualbricks.console.terminal import start

        start(factory, self.get_namespace())

    def listen(self, factory, reactor):
        """Answer on the control sockets of --listen; on none without it."""

        sockets = self.config.get("sockets")
        if not sockets:
            return
        from virtualbricks.console.control import listen

        for socket in sockets:
            listen(factory, socket, reactor)

    def run_script(self, factory, path):
        """Run the commands of path, as the console's source does."""

        from virtualbricks.console.dispatch import run
        from virtualbricks.console.terminal import error_lines

        done = run(factory, f"source {shlex.quote(path)}")

        def write(lines, stream):
            for line in lines:
                stream.write(line + "\n")
            stream.flush()

        done.addCallbacks(
            write,
            lambda failure: write(error_lines(failure), sys.stderr),
            (sys.stdout,),
        )
        return done

    def open_last_project(self, factory):
        """Open the project open last, or a new new_project_N."""

        projects.restore_last(factory)
