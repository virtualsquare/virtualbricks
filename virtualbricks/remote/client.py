# -*- test-case-name: virtualbricks.tests.remote.test_client -*-
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
The windows' end of a connection to the Virtualbricks of the bricks, on
another machine or on this one (page 19 §6, §7).

``connect()`` reaches its AMP socket over unix, tcp or ssl, proves the
token when asked, agrees on protocol 2 with ``Hello``, checks that both run
the same version (19 R11), and follows: the copy, a ``MirrorFactory``, is
whole once it returns. ``Windows`` is the connection: it gives the pushes to
the copy and the messages of the log to ``logged``.

``RemoteEngine`` is the engine of the windows over it: what the console
does goes as the typed commands of protocol 2, ``BrickStart(name=["vm1"])``;
the OK of a panel as ``Apply``, a drop as ``Connect``. What the pushes bring
answers first, so once a call is answered the copy has what it changed. A
refusal is the failure of the call, with the message of the Virtualbricks
of the bricks. What it can't do yet over a connection fails with
``NotYet``; the windows grey most of it.
"""

import json
import os

from twisted.internet import defer, endpoints, error
from twisted.protocols import amp
from twisted.python.failure import Failure

from virtualbricks import __version__, locations
from virtualbricks.brickfactory import normalize_name
from virtualbricks.bricks.brickinfo import NEW_KINDS, Issue
from virtualbricks.bricks.virtualmachine import UsbDevice
from virtualbricks.config.images import IMAGE_FOLDER, parse_info
from virtualbricks.config.settings import setting_kind
from virtualbricks.config.schema import kind_of
from virtualbricks.console import ampcommands, ampwire, wire
from virtualbricks.i18n import _
from virtualbricks.programs import Answer, parse_machine_properties, qemu_info
from virtualbricks.remote import commands
from virtualbricks.remote.commands import BRICK, EVENT, IMAGE
from virtualbricks.remote.drafts import what_changed
from virtualbricks.remote.follower import kind_of as kind_of_item
from virtualbricks.remote.mirror import Mirroring

# the words of the console for the kinds of bricks, by their types
WORDS = {kind.type: kind.word for kind in NEW_KINDS}


class Refused(Exception):
    """The connection can't be made, or is lost: str() says why."""


class NotYet(Exception):
    """What the windows can't do over a connection yet."""

    def __init__(self, what=""):
        super().__init__(_("Not over a connection, for now"))
        self.what = what


def where(target) -> str:
    """The Virtualbricks of target, as the windows name it: host or path."""

    if target.kind == "unix":
        return locations.short_path(target.path)
    return target.host


class Windows(Mirroring, amp.AMP):
    """
    The connection of the windows: the pushes go to the copy, mirror, the
    messages of the log to logged(message), and lost fires with the reason,
    an exception, when the connection is lost.
    """

    def __init__(self, mirror):
        super().__init__()
        self.mirror = mirror
        self.logged = None
        self.lost = defer.Deferred()
        self.connected = False

    def makeConnection(self, transport):
        # AMP logs each connection with the addresses of its objects
        amp.BinaryBoxProtocol.makeConnection(self, transport)

    def connectionMade(self):
        self.connected = True

    def connectionLost(self, reason):
        self.connected = False
        amp.BinaryBoxProtocol.connectionLost(self, reason)
        # the exception: a Failure would fire the errbacks
        self.lost.callback(reason.value)

    @commands.Logged.responder
    def take_logged(self, message):
        if self.logged is not None:
            self.logged(json.loads(message))
        return {}


def endpoint_of(target, reactor):
    """The endpoint of target, a wire.Socket of --connect."""

    if target.kind == "unix":
        return endpoints.UNIXClientEndpoint(reactor, target.path)
    endpoint = endpoints.HostnameEndpoint(reactor, target.host, target.port)
    if target.kind == "ssl":
        from virtualbricks.console import tls

        try:
            options = tls.client_options(target)
        except wire.Unusable as exc:
            raise Refused(str(exc)) from None
        endpoint = endpoints.wrapClientTLS(options, endpoint)
    return endpoint


def _token(target) -> str:
    path = target.token_file or locations.token_file()
    try:
        return wire.read_token(path)
    except wire.NoToken:
        raise Refused(
            _(
                "{where} asks for the token, and {path} has none: copy the"
                " token of that Virtualbricks there"
            ).format(where=where(target), path=path)
        ) from None
    except wire.Unusable as exc:
        raise Refused(str(exc)) from None


async def start(windows, target) -> dict:
    """
    Prove the token if asked, agree on protocol 2, check the version and
    follow: the answer of Follow, once the copy is whole.
    """

    name = where(target)
    try:
        hello = await windows.callRemote(
            ampwire.Hello, protocols=[commands.PROTOCOL]
        )
    except ampwire.TokenNeeded:
        try:
            await ampwire.authenticate(windows, _token(target))
        except ampwire.WrongToken:
            raise Refused(
                _("{where} doesn't take your token").format(where=name)
            ) from None
        hello = await windows.callRemote(
            ampwire.Hello, protocols=[commands.PROTOCOL]
        )
    if hello["protocol"] != commands.PROTOCOL:
        raise Refused(
            _(
                "{where} speaks only protocol {protocol} of AMP: its"
                " Virtualbricks is older than these windows"
            ).format(where=name, protocol=hello["protocol"])
        )
    if hello["version"] != __version__:
        raise Refused(
            _(
                "{where} runs Virtualbricks {theirs}, these windows are"
                " {ours}: run the same version on both"
            ).format(where=name, theirs=hello["version"], ours=__version__)
        )
    try:
        return await windows.callRemote(commands.Follow)
    except amp.UnhandledCommand:
        raise Refused(
            _(
                "{where} has no commands for the windows: run the same"
                " Virtualbricks on both"
            ).format(where=name)
        ) from None


async def connect(target, mirror, reactor) -> Windows:
    """The connection to target, following it with the copy mirror."""

    try:
        windows = await endpoints.connectProtocol(
            endpoint_of(target, reactor), Windows(mirror)
        )
    except error.ConnectError as exc:
        reason = exc.osError or exc
        raise Refused(
            _("Can't reach {where}: {reason}").format(
                where=target.where(),
                reason=getattr(reason, "strerror", None) or str(reason),
            )
        ) from None
    try:
        await start(windows, target)
    except BaseException:
        windows.transport.loseConnection()
        raise
    return windows


def _pairs(values: dict) -> list:
    return [{"key": key, "value": value} for key, value in values.items()]


def _text(kind, value) -> str:
    """A value as the console reads it: a text as it is."""

    return value if isinstance(value, str) else kind.format(value)


def _stamp(facts):
    return None if facts is None else (facts["size"], facts["mtime"])


class RemoteInfos:
    """
    What qemu-img info says of the files there, asked with ImageFacts, while
    the facts that the Virtualbricks there sends of a file don't change: the
    calls of images.InfoCache.
    """

    def __init__(self, machine, engine):
        self.machine = machine
        self.engine = engine
        # the files asked, and who waits for them
        self._reading = {}

    def get(self, path):
        found = self.machine.asked.get(path)
        if found is None:
            return None
        if _stamp(found["file"]) != _stamp(self.machine.facts(path)):
            return None
        return found["info"]

    def read(self, path) -> defer.Deferred:
        info = self.get(path)
        if info is not None:
            return defer.succeed(info)
        waiting = defer.Deferred()
        if path in self._reading:
            self._reading[path].append(waiting)
            return waiting
        self._reading[path] = [waiting]
        reading = self.engine.image_facts(path)
        reading.addBoth(self._read, path)
        return waiting

    def _read(self, result, path) -> None:
        for waiting in self._reading.pop(path, []):
            if isinstance(result, Failure):
                waiting.errback(result)
            else:
                waiting.callback(result["info"])


class RemoteMachine:
    """
    What the windows read of the machine of the bricks, from the copy: the
    settings and the facts that the Virtualbricks there sent, those of the
    files of the images and of the private copies with the rest; the facts
    of the other files, once asked.
    """

    def __init__(self, mirror, engine):
        self.mirror = mirror
        # the answers of ImageFacts, by path
        self.asked = {}
        self.infos = RemoteInfos(self, engine)

    def facts(self, path) -> dict | None:
        """What the Virtualbricks there last said of the file path."""

        mirror = self.mirror
        for image in mirror.images:
            if image.path == path:
                return mirror.state(IMAGE, image.name).get("file")
        for brick in mirror.bricks:
            copies = mirror.state(BRICK, brick.name).get("copies", {})
            for device, facts in copies.items():
                if brick.disk(device).get_cow_path() == path:
                    return facts
        found = self.asked.get(path)
        return None if found is None else found["file"]

    def exists(self, path) -> bool:
        return self.facts(path) is not None

    def taken(self, path) -> int | None:
        facts = self.facts(path)
        return None if facts is None else facts["taken"]

    def changed(self, path) -> float | None:
        facts = self.facts(path)
        return None if facts is None else facts["mtime"] / 1e9

    def other_projects(self, path) -> list[tuple[str, str]]:
        found = self.asked.get(path)
        return [] if found is None else found["others"]

    def can_trash(self, path) -> bool:
        return bool(self.mirror.machine.get("trash"))

    def image_folder(self) -> str:
        return os.path.join(
            self.mirror.machine.get("workspace", ""), IMAGE_FOLDER
        )

    def setting(self, name):
        return self.mirror.settings[name]

    def qemu_programs(self) -> list[str]:
        return list(self.mirror.machine.get("qemu_programs", []))


class RemoteEngine:
    """
    The engine of the windows of the Virtualbricks at where, over the
    connection windows: its copy is what the windows read.
    """

    local = False

    def __init__(self, mirror, windows, where, quit=None):
        self.factory = mirror
        self.machine = RemoteMachine(mirror, self)
        # the connection; Reconnect gives another
        self.windows = windows
        self.where = where
        # what closes the windows: the Virtualbricks there goes on (19 R6)
        self._quit = quit

    def call(self, command, **arguments) -> defer.Deferred:
        """The answer of command, or a failure; Refused while unconnected."""

        if self.windows is None or not self.windows.connected:
            return defer.fail(
                Refused(
                    _("The connection to {where} is lost").format(
                        where=self.where
                    )
                )
            )
        return self.windows.callRemote(command, **arguments)

    def _then(self, deferred, result):
        """deferred, answered with result() once it is."""

        return deferred.addCallback(lambda _: result())

    # The bricks

    def start(self, brick):
        return self.call(ampcommands.BrickStart, name=[brick.name])

    def stop(self, brick):
        return self.call(ampcommands.BrickStop, name=[brick.name])

    def terminate(self, brick):
        # the console has no command for SIGTERM yet
        return defer.fail(NotYet("terminate"))

    def kill(self, brick):
        return self.call(ampcommands.BrickKill, name=[brick.name])

    def restart(self, brick):
        return self.call(ampcommands.BrickRestart, name=[brick.name])

    def pause(self, brick):
        return self.call(ampcommands.BrickPause, name=[brick.name])

    def continue_(self, brick):
        return self.call(ampcommands.BrickContinue, name=[brick.name])

    def suspend(self, vm):
        return self.call(ampcommands.BrickSuspend, vm=vm.name)

    def resume(self, vm):
        return self.call(ampcommands.BrickResume, vm=vm.name)

    def reset(self, vm):
        return self.call(ampcommands.BrickReset, vm=vm.name)

    def open_console(self, brick):
        # through the connection, in step 6 of page 19
        return defer.fail(NotYet("open_console"))

    def new_brick(self, type, name):
        making = self.call(ampcommands.BrickNew, kind=WORDS[type], name=name)
        return self._then(
            making, lambda: self.factory.get_brick(normalize_name(name))
        )

    def connect(self, source, destination):
        connecting = self.call(
            commands.Connect, source=source.name, target=destination.name
        )
        return connecting.addCallback(lambda answer: answer["connected"])

    # The bricks, the events and the images

    def rename(self, item, name):
        old = item.name
        command = {
            BRICK: ampcommands.BrickRename,
            EVENT: ampcommands.EventRename,
            IMAGE: ampcommands.ImageRename,
        }[kind_of_item(item)]
        return self._then(self.call(command, name=old, new=name), lambda: old)

    def duplicate(self, item):
        # the answer names the copy, as the Virtualbricks there named it
        if kind_of_item(item) == EVENT:
            copying = self.call(ampcommands.EventDuplicate, name=item.name)
            get = self.factory.get_event
        else:
            copying = self.call(ampcommands.BrickDuplicate, name=item.name)
            get = self.factory.get_brick
        return copying.addCallback(lambda answer: get(answer["lines"][0]))

    def remove(self, item):
        kind = kind_of_item(item)
        if kind == IMAGE:
            return self.call(ampcommands.ImageDelete, name=item.name)
        if kind == EVENT:
            return self.call(ampcommands.EventDelete, name=[item.name])
        return self.call(ampcommands.BrickDelete, name=[item.name])

    def update_config(self, item, changes):
        values = {
            key: _text(kind_of(item.config, key), value)
            for key, value in changes.items()
        }
        command = (
            ampcommands.EventSet
            if kind_of_item(item) == EVENT
            else ampcommands.BrickSet
        )
        return self.call(command, name=item.name, key_value=_pairs(values))

    def apply(self, draft):
        data = what_changed(draft)
        kind = kind_of_item(draft.brick)
        return self.call(
            commands.Apply,
            kind=kind,
            # as the Virtualbricks there knows it now: a new name is a change
            name=draft.brick.name,
            changes=json.dumps(data["changes"]),
            links=json.dumps(data["links"]),
            extras=json.dumps(data["extras"]),
        )

    # The events

    def new_event(self, name, delay):
        new = normalize_name(name)
        making = self.call(ampcommands.EventNew, name=name)
        making.addCallback(
            lambda _: self.call(
                ampcommands.EventSet,
                name=new,
                key_value=_pairs({"delay": str(delay)}),
            )
        )
        return self._then(making, lambda: self.factory.get_event(new))

    def start_event(self, event):
        return self.call(ampcommands.EventStart, name=[event.name])

    def stop_event(self, event):
        return self.call(ampcommands.EventStop, name=[event.name])

    def run_event(self, event):
        return self.call(ampcommands.EventRun, name=[event.name])

    # The images and their files

    def new_image(self, name, path, description=""):
        values = {"description": description} if description else {}
        adding = self.call(
            ampcommands.ImageAdd,
            name=name,
            path=path,
            key_value=_pairs(values),
        )
        return self._then(
            adding, lambda: self.factory.get_image(normalize_name(name))
        )

    def make_image(self, path, fmt, size):
        return self.call(commands.MakeImage, path=path, format=fmt, size=size)

    def image_facts(self, path):
        """
        What the file path is there: file, its facts; info, an ImageInfo;
        others, the images of the other projects with that file.
        """

        asking = self.call(commands.ImageFacts, path=path)

        def read(answer):
            found = {
                "file": json.loads(answer["file"]),
                "info": parse_info(json.loads(answer["info"])),
                "others": [
                    tuple(other) for other in json.loads(answer["others"])
                ],
            }
            self.machine.asked[path] = found
            return found

        return asking.addCallback(read)

    def image_info(self, path):
        return self.image_facts(path).addCallback(lambda found: found["info"])

    def relink(self, image, path):
        return self.call(commands.Relink, name=image.name, path=path)

    def discard_file(self, path):
        trashing = self.call(commands.TrashFile, path=path)

        def gone(answer):
            # what was asked of it is no more
            self.machine.asked.pop(path, None)
            return answer["trashed"]

        return trashing.addCallback(gone)

    def start_over(self, vm, device):
        starting = self.call(commands.StartOver, vm=vm.name, device=device)
        return starting.addCallback(lambda answer: answer["trashed"])

    # The projects

    def project_summaries(self):
        # the Projects window over the connection comes in step 5
        return defer.succeed([])

    def disk_usage(self, name):
        return defer.fail(NotYet("disk_usage"))

    def save_project(self):
        return self.call(ampcommands.ProjectSave)

    def open_project(self, name):
        from virtualbricks.config.report import Report

        # the pushes bring the project before the answer
        return self._then(
            self.call(ampcommands.ProjectOpen, name=name), Report
        )

    def new_project(self, name, description=""):
        from virtualbricks.config.report import Report

        return self._then(self.call(ampcommands.ProjectNew, name=name), Report)

    def restore_last(self):
        # the Virtualbricks there has a project open, or its own way
        return defer.succeed(None)

    def rename_project(self, name, new):
        return self.call(ampcommands.ProjectRename, name=name, new=new)

    def duplicate_project(self, name, new):
        return self.call(ampcommands.ProjectDuplicate, name=name, new=new)

    def remove_project(self, name, trash):
        return self.call(ampcommands.ProjectDelete, name=name, force=not trash)

    def readme(self):
        return defer.succeed("")

    def set_readme(self, text):
        return defer.fail(NotYet("set_readme"))

    # The settings

    def set_settings(self, values):
        texts = {
            key: _text(setting_kind(key), value)
            for key, value in values.items()
        }
        return self.call(ampcommands.SettingSet, key_value=_pairs(texts))

    def set_ksm(self, enable):
        setting = self.set_settings({"kernel_samepage_merging": enable})
        return self._then(setting, lambda: enable)

    # What the machine has

    def lacks(self, kind):
        found = self.factory.machine.get("lacks", {}).get(kind.type)
        return defer.succeed(None if found is None else Issue(**found))

    def qemu(self, program):
        """
        What the QEMU program has there, read here from what it printed;
        FileNotFoundError if there is none.
        """

        asking = self.call(commands.QemuFacts, program=program)

        def read(answer):
            answers = {
                name: Answer(*json.loads(answer[name]))
                for name in commands.QEMU_ANSWERS
            }
            return qemu_info(answer["path"], answers)

        def not_there(failure):
            failure.trap(ampcommands.NotFound)
            raise FileNotFoundError(program)

        return asking.addCallbacks(read, not_there)

    def machine_properties(self, info, machine):
        # the default machine type, if empty, as the Virtualbricks there
        # has it
        asking = self.call(
            commands.MachineProperties, program=info.path, machine=machine
        )
        return asking.addCallback(
            lambda answer: parse_machine_properties(answer["text"])
        )

    def usb(self):
        asking = self.call(commands.UsbDevices)
        return asking.addCallback(
            lambda answer: [
                UsbDevice(device["id"], device["description"])
                for device in json.loads(answer["devices"])
            ]
        )

    def quit(self):
        """Close the windows; the Virtualbricks there goes on."""

        if self._quit is not None:
            self._quit()
        return defer.succeed(None)
