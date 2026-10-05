# -*- test-case-name: virtualbricks.tests.remote.test_mirror -*-
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
The copy of the project of the Virtualbricks that the windows follow, on
another machine (page 19 §5).

``MirrorFactory`` is a factory of the real bricks, events and images, which
the pushes of ``Follow`` build and keep up to date: the windows read it as
they read the factory of their own process. ``Opened`` empties it, and the
tables of ``Changed`` make each object, or change it in place: its settings,
its plugs, its state. A running brick has a stand-in process, which has its
number; a waiting event a timer of the copy's own clock, which counts down
the seconds left. A rename renames, and the objects whose references moved
come as changes after it; a VM renamed here renames no file.

The copy never starts anything: its bricks and events refuse to start,
stop, signal and open a console, with an error that names the call, so that
a window that forgets the engine fails, rather than run a program here. It
is never saved.

``Mirroring`` gives the pushes of a connection to its ``mirror``.
"""

import functools
import itertools
import json

from twisted.internet import defer
from twisted.logger import Logger
from twisted.protocols import amp

from virtualbricks.brickfactory import BrickFactory
from virtualbricks.bricks import Brick
from virtualbricks.bricks.event import EventConfig
from virtualbricks.bricks.virtualmachine import is_virtualmachine
from virtualbricks.config.projectfile import (
    CONNECTION_KEYS,
    HOSTONLY,
    resolve,
)
from virtualbricks.config.report import Report
from virtualbricks.config.schema import load_record
from virtualbricks.i18n import _
from virtualbricks.observable import Observable, Signal
from virtualbricks.remote import commands
from virtualbricks.remote.commands import BRICK, EVENT, IMAGE

logger = Logger()
not_copied = "The copy didn't take {command} of {name}"

# What the bricks and the events of the copy refuse.
BRICK_CALLS = ("start", "stop", "send", "send_signal", "open_console")
EVENT_CALLS = ("start", "stop", "run_actions")


class NotOnTheCopy(Exception):
    """A call that is for the Virtualbricks of the bricks, not its copy."""


def _refused(call, item, *args, **kwargs):
    raise NotOnTheCopy(
        _(
            "{call} of {name} is for the Virtualbricks of the bricks: here"
            " is its copy"
        ).format(call=call, name=item.name)
    )


def _refuse(item, calls) -> None:
    for call in calls:
        setattr(item, call, functools.partial(_refused, call, item))


class StandIn:
    """The process of a running brick of the copy: its number, no more."""

    def __init__(self, brick, pid):
        self.brick = brick
        self.pid = pid

    def signal_process(self, number):
        _refused("signal_process", self.brick)

    def write(self, data):
        _refused("write", self.brick)


class MirrorFactory(BrickFactory):
    """
    The factory of the copy of the project of another Virtualbricks: the
    project open there, its settings, what its machine has, and its objects.
    """

    def __init__(self, clock=None):
        BrickFactory.__init__(self, defer.Deferred())
        if clock is None:
            from twisted.internet import reactor as clock
        self.clock = clock
        # the project open there, None if none is
        self.project = None
        # the settings of Virtualbricks and of the project, by name
        self.settings = {}
        # what its machine has: version, workspace, runtime_dir, missing,
        # lacks, ksm
        self.machine = {}
        # whether the whole project has come
        self.whole = False
        # the states of the images and the bricks, by kind and name: the
        # facts of their files, their processes
        self._states = {}
        # the plugs whose sockets haven't come yet, and their targets
        self._waiting = []
        observable = Observable()
        # a project opened there: the copy is empty, the project comes
        self.opened = Signal(observable, "opened")
        # the whole project has come
        self.synced = Signal(observable, "synced")
        self.settings_changed = Signal(observable, "settings-changed")
        # the Virtualbricks followed quits
        self.ended = Signal(observable, "ended")

    # The objects, which refuse what runs programs

    def new_brick(self, type, name, host="", remote=False):
        brick = BrickFactory.new_brick(self, type, name, host, remote)
        _refuse(brick, BRICK_CALLS)
        if is_virtualmachine(brick):
            # its private copies are in the project there
            brick.project_folder = lambda: self.machine.get("project_folder")
        return brick

    def state(self, kind, name) -> dict:
        """The last state sent of an image or a brick."""

        return self._states.get((kind, name), {})

    def new_event(self, name):
        event = BrickFactory.new_event(self, name)
        _refuse(event, EVENT_CALLS)
        return event

    def _remove_brick(self, brick):
        # its plugs wait for nothing any more
        self._waiting = [
            (p, t) for p, t in self._waiting if p.brick is not brick
        ]
        BrickFactory._remove_brick(self, brick)

    def _remove_event(self, event):
        # as the factory does, without stopping it: the copy runs nothing
        self._wait(event, None)
        event.changed.disconnect(self.event_changed.notify)
        del self._events[event.name]
        self.event_removed.notify(event)

    def _get(self, kind, name):
        return {
            BRICK: self.get_brick,
            EVENT: self.get_event,
            IMAGE: self.get_image,
        }[kind](name)

    # The pushes

    def take_opened(self, project, settings, machine) -> None:
        """A project opened there: the copy starts again, empty."""

        self.whole = False
        # none of them runs here: the factory removes them all
        for brick in self._bricks:
            brick.proc = None
        self.reset()
        self._waiting = []
        self._states = {}
        self.project = project
        self.settings = settings
        self.machine = machine
        self.runtime_dir = machine.get("runtime_dir", self.runtime_dir)
        self.opened.notify(self)

    def take_synced(self) -> None:
        self.whole = True
        self.synced.notify(self)

    def take_changed(self, kind, name, table, state) -> None:
        """A new object, or one changed: its table and its state."""

        report = Report()
        # before the object: what it tells shows the state
        before = self._states.get((kind, name))
        if kind != EVENT:
            self._states[(kind, name)] = state
        if kind == IMAGE:
            self._change_image(name, table, before != state)
        elif kind == EVENT:
            self._change_event(name, table, state, report)
        else:
            self._change_brick(name, table, state, report)
        report.log(logger)

    def take_renamed(self, kind, old, new) -> None:
        item = self._get(kind, old)
        if item is None:
            return
        if (kind, old) in self._states:
            self._states[(kind, new)] = self._states.pop((kind, old))
        if kind == IMAGE:
            self._disk_images[new] = self._disk_images.pop(old)
        elif kind == EVENT:
            self._events[new] = self._events.pop(old)
        if kind == BRICK and is_virtualmachine(item):
            # its private disks are there, not here
            item.rename_sockets(new)
            Brick.set_name(item, new)
        else:
            item.set_name(new)
        # the others follow as changes; until then they point at the new name
        for other in itertools.chain(self._bricks, self._events.values()):
            other.rename_references(kind, old, new)

    def take_removed(self, kind, name) -> None:
        item = self._get(kind, name)
        if item is None:
            return
        self._states.pop((kind, name), None)
        # what named it follows as changes, as after a rename
        if kind == IMAGE:
            self.remove_image(item)
        elif kind == EVENT:
            self._remove_event(item)
        else:
            self._remove_brick(item)

    def take_settings(self, settings) -> None:
        self.settings = settings
        self.settings_changed.notify(self)

    def take_quitting(self) -> None:
        self.ended.notify(self)

    # Images

    def _change_image(self, name, table, state_changed) -> None:
        path = table.get("path", "")
        description = table.get("description", "")
        image = self.get_image(name)
        if image is None:
            self.new_image(name, path, description)
            return
        if image.path == path and image.description == description:
            # its file changed: what shows it follows
            if state_changed:
                image.changed.notify(image)
            return
        if image.path != path:
            image.set_path(path)
        image.set_description(description)

    # Events

    def _change_event(self, name, table, state, report) -> None:
        event = self.get_event(name)
        if event is None:
            event = self.new_event(name)
        event.config = load_record(
            EventConfig, table, report, f"events.{name}"
        )
        self._wait(event, state.get("left"))
        event.changed.notify(event)

    def _wait(self, event, left) -> None:
        """The timer of a waiting event, on the clock of the copy."""

        call = event.scheduled
        if call is not None and call.active():
            call.cancel()
        event.scheduled = None
        if left is not None:
            event.scheduled = self.clock.callLater(left, self._waited, event)

    def _waited(self, event) -> None:
        # the Virtualbricks of the bricks says what follows
        event.scheduled = None
        event.changed.notify(event)

    # Bricks

    def _change_brick(self, name, table, state, report) -> None:
        brick = self.get_brick(name)
        if brick is None:
            brick = self.new_brick(table.get("type", ""), name)
        where = f"bricks.{name}"
        with brick.muted():
            ignore = {"type"} | CONNECTION_KEYS[brick.connections]
            brick.load_config_table(table, report, where, ignore)
            self._links(brick, table)
            pid = state.get("pid")
            brick.proc = None if pid is None else StandIn(brick, pid)
        brick.changed.notify(brick)
        self._connect_waiting()

    def _links(self, brick, table) -> None:
        style = brick.connections
        if style == "connect":
            self._plug(brick.plugs[0], table.get("connect", ""))
        elif style == "endpoints":
            ends = table.get("endpoints", ["", ""])
            for plug, target in zip(brick.plugs, ends):
                self._plug(plug, target)
        elif style == "nics":
            self._cards(brick, table.get("nics", []))

    def _cards(self, vm, nics) -> None:
        """
        The cards of a machine: the socket cards kept by name, since other
        bricks plug into them; the others made again.
        """

        by_name = {sock.nickname: sock for sock in vm.socks}
        kept = []
        for nic in nics:
            if nic.get("kind") != "socket":
                continue
            sock = by_name.pop(f"{vm.name}_{nic['name']}", None)
            if sock is None:
                sock = vm.add_sock(nic["mac"], nic["model"], nic["name"])
            else:
                sock.mac, sock.model = nic["mac"], nic["model"]
            kept.append(sock)
        for sock in by_name.values():
            vm.remove_plug(sock)
        vm.socks[:] = kept
        for plug in vm.plugs:
            if plug.sock is not None:
                plug.disconnect()
        self._waiting = [(p, t) for p, t in self._waiting if p.brick is not vm]
        del vm.plugs[:]
        for nic in nics:
            if nic.get("kind") == "socket":
                continue
            plug = vm.add_plug(None, nic["mac"], nic["model"])
            if nic.get("kind") == "hostonly":
                plug.connect(self.get_sock(HOSTONLY))
            else:
                self._plug(plug, nic.get("connect", ""))

    def _plug(self, plug, target) -> None:
        """Plug plug into the socket of target; later, if it hasn't come."""

        self._waiting = [(p, t) for p, t in self._waiting if p is not plug]
        sock = resolve(self, target) if target else None
        if target and sock is None:
            self._waiting.append((plug, target))
        if plug.sock is not sock:
            if plug.sock is not None:
                plug.disconnect()
            if sock is not None:
                plug.connect(sock)

    def _connect_waiting(self) -> None:
        waiting, self._waiting = self._waiting, []
        for plug, target in waiting:
            sock = resolve(self, target)
            if sock is None:
                self._waiting.append((plug, target))
            elif plug.sock is not sock:
                if plug.sock is not None:
                    plug.disconnect()
                plug.connect(sock)
                plug.brick.changed.notify(plug.brick)


class Mirroring(amp.CommandLocator):
    """
    The pushes of the Virtualbricks that a connection follows, given to its
    copy, ``mirror``. A push that the copy can't take goes to the log.
    ``Logged`` isn't the copy's: the connection of the windows shows it.
    """

    mirror = None

    def _take(self, command, name, take, *args):
        try:
            take(*args)
        except Exception:
            logger.failure(not_copied, command=command, name=name)
        return {}

    @commands.Opened.responder
    def take_opened(self, project, settings, machine):
        return self._take(
            "Opened",
            project,
            self.mirror.take_opened,
            project,
            json.loads(settings),
            json.loads(machine),
        )

    @commands.Changed.responder
    def take_changed(self, kind, name, table, state):
        return self._take(
            "Changed",
            name,
            self.mirror.take_changed,
            kind,
            name,
            json.loads(table),
            json.loads(state),
        )

    @commands.Renamed.responder
    def take_renamed(self, kind, old, new):
        return self._take(
            "Renamed", old, self.mirror.take_renamed, kind, old, new
        )

    @commands.Removed.responder
    def take_removed(self, kind, name):
        return self._take(
            "Removed", name, self.mirror.take_removed, kind, name
        )

    @commands.Synced.responder
    def take_synced(self):
        return self._take("Synced", "", self.mirror.take_synced)

    @commands.SettingsChanged.responder
    def take_settings(self, settings):
        return self._take(
            "SettingsChanged",
            "",
            self.mirror.take_settings,
            json.loads(settings),
        )

    @commands.Quitting.responder
    def take_quitting(self):
        return self._take("Quitting", "", self.mirror.take_quitting)
