# -*- test-case-name: virtualbricks.tests.remote.test_follower -*-
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
The side of the Virtualbricks that runs the bricks, for the programs that
follow it, as the windows of another machine do (page 19 §4, §7).

A connection that calls ``Follow`` gets a ``Follower``. It sends the project:
``Opened``, a ``Changed`` for each image, brick and event, and ``Synced``.
Then it listens to the factory, the workspace, the settings and the log,
and gathers what changes until the end of the reactor's turn: each object
goes once, with what it is then. A rename goes first, as ``Renamed``, and
a delete as ``Removed``, in the order they came; then the objects changed,
the images, the bricks, each after those it plugs into, and the events;
then the settings, the messages of the log, and ``Quitting``. Before the
connection answers a command, the pushes that wait go out, so that the
answer comes after what the command changed.

``keeper`` keeps the last 500 messages of the log, info and above, while
Virtualbricks listens on an AMP socket; a program that follows gets them
first, then each new one.
"""

import collections
import json
import os
import threading

from twisted.logger import (
    ILogObserver,
    LogLevel,
    Logger,
    formatEvent,
    globalLogPublisher,
)
from twisted.protocols import amp
from zope.interface import implementer

from virtualbricks import __version__, ksm
from virtualbricks.bricks import Base, is_running
from virtualbricks.bricks.brickinfo import NEW_KINDS, issue
from virtualbricks.bricks.event import is_event
from virtualbricks.bricks.virtualmachine import (
    is_disk_image,
    is_virtualmachine,
)
from virtualbricks.config import settings
from virtualbricks.config.projectfile import brick_table
from virtualbricks.config.schema import dump_record, field_names
from virtualbricks.config.workspace import projects
from virtualbricks.programs import missing_programs, qemu_programs
from virtualbricks.remote import commands
from virtualbricks.remote.commands import BRICK, EVENT, IMAGE

logger = Logger()
too_long = "Not sent to {who}: {command} of {about} is too long for AMP"

# The messages of the log that the keeper keeps.
KEPT = 500
STREAMS = ("stdout", "stderr")


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def message_of(event) -> dict:
    """A message of the log, as a program shows it: JSON's types only."""

    level = event.get("log_level", LogLevel.info)
    stream = event.get("stream")
    source = event.get("log_source")
    if not isinstance(source, Base):
        # the process of a brick, a plug, a socket...
        source = getattr(source, "brick", None)
    failure = event.get("log_failure")
    traceback = None
    if failure is not None:
        try:
            traceback = failure.getTraceback()
        except Exception:
            pass
    pid = event.get("pid")
    return {
        "time": float(event.get("log_time") or 0.0),
        "level": level.name,
        "stream": stream if stream in STREAMS else None,
        "namespace": str(event.get("log_namespace") or ""),
        "pid": pid if isinstance(pid, int) else None,
        "source": source.name if isinstance(source, Base) else None,
        "source_type": (
            source.get_type().lower() if isinstance(source, Base) else None
        ),
        "text": formatEvent(event),
        "traceback": traceback,
    }


@implementer(ILogObserver)
class LogKeeper:
    """The last messages of the log, info and above, and who wants the next."""

    def __init__(self, size=KEPT, reactor=None):
        self.messages = collections.deque(maxlen=size)
        self.listeners = []
        self.reactor = reactor
        self.observing = None
        # the sockets that listen, which want it to keep the log
        self.users = 0
        # the thread of the reactor, which makes it
        self.thread = threading.get_ident()

    def start(self, publisher=None) -> None:
        """
        Keep the messages of publisher, the global one if None, until each
        start() has its stop().
        """

        self.users += 1
        if self.observing is None:
            self.observing = publisher or globalLogPublisher
            self.observing.addObserver(self)

    def stop(self) -> None:
        self.users = max(0, self.users - 1)
        if not self.users and self.observing is not None:
            self.observing.removeObserver(self)
            self.observing = None

    def __call__(self, event) -> None:
        if event.get("log_level", LogLevel.info) == LogLevel.debug:
            return
        if threading.get_ident() == self.thread:
            self._keep(event)
        else:
            # a message of a thread: the listeners send it in the reactor
            reactor = self.reactor
            if reactor is None:
                from twisted.internet import reactor
            reactor.callFromThread(self._keep, event)

    def _keep(self, event) -> None:
        message = message_of(event)
        self.messages.append(message)
        for listener in list(self.listeners):
            listener(message)


keeper = LogKeeper()


def settings_table() -> dict:
    """The settings of Virtualbricks and of the open project, by name."""

    names = field_names(settings.AppSettings) + field_names(
        settings.ProjectSettings
    )
    return {name: settings.get_setting(name) for name in names}


def machine_table(factory, workspace) -> dict:
    """What the machine of the bricks has, for the windows."""

    vde = settings.get_setting("vde_path")
    qemu = settings.get_setting("qemu_path")
    lacks = {}
    for kind in NEW_KINDS:
        found = issue(kind, vde, qemu)
        lacks[kind.type] = (
            None if found is None else {"line": found.line, "text": found.text}
        )
    current = workspace.current
    return {
        "version": __version__,
        "workspace": workspace.path,
        # where the private copies of the machines are
        "project_folder": None if current is None else current.path,
        "runtime_dir": factory.runtime_dir,
        "missing": [str(missing) for missing in missing_programs(vde, qemu)],
        "qemu_programs": qemu_programs(qemu),
        "lacks": lacks,
        "ksm": ksm.check_ksm(),
    }


def kind_of(item) -> str:
    if is_disk_image(item):
        return IMAGE
    if is_event(item):
        return EVENT
    return BRICK


def table_of(item) -> dict:
    """What the project file writes of an image, a brick or an event."""

    if is_disk_image(item):
        return {"path": item.path, "description": item.description}
    if is_event(item):
        return dump_record(item.config)
    return brick_table(item)


def file_facts(path: str) -> dict | None:
    """
    What the windows show of a file: its size, the time it changed, in
    nanoseconds, and the space it takes; None if it isn't there.
    """

    try:
        stat = os.stat(path)
    except OSError:
        return None
    return {
        "size": stat.st_size,
        "mtime": stat.st_mtime_ns,
        "taken": stat.st_blocks * 512,
    }


def state_of(item) -> dict:
    """
    What the project file doesn't write: the file of an image, the process
    of a brick and the private copies of a machine, the seconds an event
    still waits.
    """

    if is_disk_image(item):
        return {"file": file_facts(item.path)}
    if is_event(item):
        call = item.scheduled
        left = None
        if call is not None and call.active():
            left = max(0.0, call.getTime() - call.seconds())
        return {"left": left}
    state = {"pid": item.pid if is_running(item) else None}
    if is_virtualmachine(item) and item.project_folder() is not None:
        state["copies"] = {
            disk.device: file_facts(disk.get_cow_path())
            for disk in item.disks()
            if disk.is_cow()
        }
    return state


def _targets(brick) -> list:
    """The bricks that brick plugs into."""

    return [
        plug.sock.brick
        for plug in getattr(brick, "plugs", ())
        if plug.sock is not None and getattr(plug.sock, "brick", None)
    ]


def in_order(items) -> list:
    """
    The items, images first, then the bricks, each after those it plugs
    into, then the events; in their order otherwise.
    """

    kinds = {IMAGE: [], BRICK: [], EVENT: []}
    for item in items:
        kinds[kind_of(item)].append(item)
    images, bricks, events = kinds[IMAGE], kinds[BRICK], kinds[EVENT]
    ordered = []
    waiting = list(bricks)
    while waiting:
        placed = False
        for brick in waiting:
            if all(
                target in ordered or target not in waiting
                for target in _targets(brick)
                if target is not brick
            ):
                ordered.append(brick)
                waiting.remove(brick)
                placed = True
                break
        if not placed:
            # a loop: the rest as they came
            ordered.extend(waiting)
            break
    return images + ordered + events


class Follower:
    """
    What a connection that follows this Virtualbricks gets: the project,
    then what changes, once a turn, and the messages of the log.

    send(command, **arguments) calls a push on the program.
    """

    def __init__(self, send, factory, workspace, keeper, clock, who=None):
        self.send = send
        self.factory = factory
        self.workspace = workspace
        self.keeper = keeper
        self.clock = clock
        # the program, for the log
        self.who = who or "a program"
        # the objects the program knows, with the name it knows them by
        self.known = {}
        # renames and deletes, in the order they came
        self.queue = []
        # the objects changed, in the order they first changed
        self.changed = {}
        self.logs = []
        # the whole project is sent again
        self.project = True
        self.settings = False
        self.quitting = False
        self.call = None
        self.signals = []

    def start(self) -> None:
        """Follow the factory, the workspace, the settings and the log."""

        factory = self.factory
        for signal, callback in (
            (factory.brick_added, self.on_changed),
            (factory.brick_changed, self.on_changed),
            (factory.brick_removed, self.on_removed),
            (factory.event_added, self.on_changed),
            (factory.event_changed, self.on_changed),
            (factory.event_removed, self.on_removed),
            (factory.image_added, self.on_changed),
            (factory.image_changed, self.on_changed),
            (factory.image_removed, self.on_removed),
            (factory.quitting, self.on_quitting),
            (self.workspace.opened, self.on_opened),
            (settings.changed, self.on_setting),
        ):
            signal.connect(callback)
            self.signals.append((signal, callback))
        self.logs.extend(self.keeper.messages)
        self.keeper.listeners.append(self.on_message)

    def stop(self) -> None:
        """The connection is lost: nothing more to send."""

        for signal, callback in self.signals:
            signal.disconnect(callback)
        self.signals = []
        if self.on_message in self.keeper.listeners:
            self.keeper.listeners.remove(self.on_message)
        if self.call is not None and self.call.active():
            self.call.cancel()
        self.call = None

    def again(self) -> None:
        """Send the whole project again, at the next flush."""

        self.project = True
        self._later()

    # What changes

    def on_changed(self, item) -> None:
        # while the whole project waits, _send_project() drops these
        kind = kind_of(item)
        known = self.known.get(item)
        if known is not None and known != item.name:
            self.queue.append(("renamed", kind, known, item.name))
            self.known[item] = item.name
        self.changed.setdefault(item, None)
        if kind == BRICK and is_virtualmachine(item):
            # a machine that runs or stops changes the files of its images
            for disk in item.disks():
                if disk.image is not None:
                    self.changed.setdefault(disk.image, None)
        self._later()

    def on_removed(self, item) -> None:
        self.changed.pop(item, None)
        known = self.known.pop(item, None)
        if known is not None:
            self.queue.append(("removed", kind_of(item), known))
        self._later()

    def on_opened(self, workspace) -> None:
        self.again()

    def on_setting(self, name) -> None:
        self.settings = True
        self._later()

    def on_message(self, message) -> None:
        self.logs.append(message)
        self._later()

    def on_quitting(self, factory) -> None:
        self.quitting = True
        self.flush()

    def _later(self) -> None:
        if self.call is None:
            self.call = self.clock.callLater(0, self.flush)

    # What goes out

    def flush(self) -> None:
        """Send what waits: before an answer, or at the end of the turn."""

        if self.call is not None and self.call.active():
            self.call.cancel()
        self.call = None
        if self.project:
            self._send_project()
        else:
            queue, self.queue = self.queue, []
            for what, kind, *names in queue:
                if what == "renamed":
                    self._push(
                        commands.Renamed,
                        names[1],
                        kind=kind,
                        old=names[0],
                        new=names[1],
                    )
                else:
                    self._push(
                        commands.Removed, names[0], kind=kind, name=names[0]
                    )
            changed, self.changed = list(self.changed), {}
            for item in in_order(changed):
                self._send_item(item)
            if self.settings:
                self.settings = False
                self._push(
                    commands.SettingsChanged,
                    "settings",
                    settings=_json(settings_table()),
                )
        logs, self.logs = self.logs, []
        for message in logs:
            self._push(commands.Logged, "a message", message=_json(message))
        if self.quitting:
            self.quitting = False
            self._push(commands.Quitting, "Virtualbricks")

    def _send_project(self) -> None:
        self.project = False
        self.settings = False
        self.queue = []
        self.changed = {}
        self.known = {}
        current = self.workspace.current
        self._push(
            commands.Opened,
            "the project",
            project=current.name if current is not None else None,
            settings=_json(settings_table()),
            machine=_json(machine_table(self.factory, self.workspace)),
        )
        items = (
            list(self.factory.images)
            + list(self.factory.bricks)
            + list(self.factory.events)
        )
        for item in in_order(items):
            self._send_item(item)
        self._push(commands.Synced, "the project")

    def _send_item(self, item) -> None:
        self.known[item] = item.name
        self._push(
            commands.Changed,
            item.name,
            kind=kind_of(item),
            name=item.name,
            table=_json(table_of(item)),
            state=_json(state_of(item)),
        )

    def _push(self, command, about, **arguments) -> None:
        """Call command on the program; about is what it's about, for the log."""

        try:
            self.send(command, **arguments)
        except amp.TooLong:
            logger.warn(
                too_long,
                who=self.who,
                command=command.commandName.decode(),
                about=about,
            )


class Following(amp.CommandLocator):
    """
    The answer to Follow, which the AMP connections of the control sockets
    take on; they have brickfactory, reactor, requests and who.
    """

    follower = None
    workspace = projects

    @commands.Follow.responder
    def follow(self):
        return self.requests.add(self._follow)

    def _follow(self):
        if self.follower is None:
            self.follower = Follower(
                self.callRemote,
                self.brickfactory,
                self.workspace,
                keeper,
                self.reactor,
                self.who,
            )
            self.follower.start()
        else:
            self.follower.again()
        self.follower.flush()
        current = self.workspace.current
        return {
            "project": current.name if current is not None else None,
            "version": __version__,
        }

    def pushes_first(self, result):
        """Send the pushes that wait, before the answer of result."""

        if self.follower is not None:
            self.follower.flush()
        return result

    def unfollow(self) -> None:
        if self.follower is not None:
            self.follower.stop()
            self.follower = None
