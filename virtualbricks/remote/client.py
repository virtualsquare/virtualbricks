# -*- test-case-name: virtualbricks.tests.remote.test_client -*-
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
The windows' end of a connection to the Virtualbricks of the bricks, on
another machine or on this one (page 19 §6, §7).

``connect()`` reaches its AMP socket over unix, tcp or ssl, proves the
token when asked, agrees on protocol 2 with ``Hello``, checks that both run
the same version (19 R11), and follows: the copy, a ``MirrorFactory``, is
whole once it returns. ``Windows`` is the connection: it gives the pushes to
the copy and the messages of the log to ``logged``. ``resolve()`` finds the
socket of ``--connect`` alone, where a Virtualbricks of yours listens.

``RemoteEngine`` is the engine of the windows over it: what the console
does goes as the typed commands of protocol 2, ``BrickStart(name=["vm1"])``;
the OK of a panel as ``Apply``, a drop as ``Connect``. What the pushes bring
answers first, so once a call is answered the copy has what it changed. A
refusal is the failure of the call, with the message of the Virtualbricks
of the bricks. What it can't do yet over a connection fails with
``NotYet``; the windows grey most of it.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING, Any, Literal, NoReturn, TypeVar

from twisted.internet import defer, endpoints, error
from twisted.internet.interfaces import IStreamClientEndpoint, ITransport
from twisted.internet.posixbase import PosixReactorBase
from twisted.internet.protocol import connectionDone
from twisted.protocols import amp
from twisted.python.failure import Failure

from virtualbricks import __version__, locations
from virtualbricks.brickfactory import normalize_name
from virtualbricks.bricks import Brick
from virtualbricks.bricks.brickinfo import NEW_KINDS, Issue, Kind
from virtualbricks.bricks.draft import Draft
from virtualbricks.bricks.event import Event
from virtualbricks.bricks.virtualmachine import (
    Image,
    UsbDevice,
    VirtualMachine,
    is_virtualmachine,
)
from virtualbricks.config.images import ImageInfo, parse_info
from virtualbricks.config.report import Report
from virtualbricks.config.workspace import (
    TAKEN,
    DiskUsage,
    ImageSummary,
    ProjectSummary,
    free_name,
    name_problem,
    room_problem,
)
from virtualbricks.config.settings import SettingValue, setting_kind
from virtualbricks.config.schema import Kind as FieldKind, kind_of
from virtualbricks.console import ampcommands, ampwire, wire
from virtualbricks.console import client as console_client
from virtualbricks.i18n import _
from virtualbricks.programs import (
    Answer,
    FolderPrograms,
    QemuInfo,
    parse_machine_properties,
    qemu_info,
)
from virtualbricks.remote import commands
from virtualbricks.remote.commands import BRICK, EVENT, IMAGE
from virtualbricks.remote.drafts import what_changed
from virtualbricks.remote.follower import Item, kind_of as kind_of_item
from virtualbricks.remote.mirror import Json, MirrorFactory, Mirroring

if TYPE_CHECKING:  # pragma: no cover
    from virtualbricks.remote.tunnel import Consoles

_T = TypeVar("_T")


def _there(get: Callable[[str], _T | None], name: str) -> _T:
    """What get finds of name in the copy, which a command's answer follows."""

    found = get(name)
    assert found is not None, f"the copy has {name}"
    return found


_P = TypeVar("_P", bound=amp.AMP)

# the words of the console for the kinds of bricks, by their types
WORDS = {kind.type: kind.word for kind in NEW_KINDS}


class Refused(Exception):
    """The connection can't be made, or is lost: str() says why."""


class NotYet(Exception):
    """What the windows can't do over a connection yet."""

    def __init__(self, what: str = "") -> None:
        super().__init__(_("Not over a connection, for now"))
        self.what = what


def where(target: wire.Socket) -> str:
    """
    The Virtualbricks of target, as the windows name it: host or path, or
    this computer for --connect alone, before resolve() finds its path.
    """

    if target.kind == "unix":
        if target.path is None:
            return _("this computer")
        return locations.short_path(target.path)
    assert target.host is not None, "parse_socket() sets it"
    return target.host


def resolve(target: wire.Socket, workspace: str | None = None) -> wire.Socket:
    """
    target, with a path if it is --connect alone: the socket of --listen
    alone of workspace, or else of the only Virtualbricks of yours that
    listens on one. Refused says why none can be reached.
    """

    if target.kind != "unix" or target.path is not None:
        return target
    try:
        path = console_client.listening_socket(workspace)
    except console_client.Unanswered as exc:
        raise Refused(str(exc)) from None
    return target._replace(path=path)


class Windows(Mirroring, amp.AMP):
    """
    The connection of the windows: the pushes go to the copy, mirror, the
    messages of the log to logged(message), and lost fires with the reason,
    an exception, when the connection is lost.
    """

    def __init__(self, mirror: MirrorFactory) -> None:
        super().__init__()
        self.mirror = mirror
        self.logged: Callable[[Json], object] | None = None
        self.lost: defer.Deferred[BaseException] = defer.Deferred()
        self.connected = False

    def makeConnection(self, transport: ITransport) -> None:
        # AMP logs each connection with the addresses of its objects
        amp.BinaryBoxProtocol.makeConnection(self, transport)

    def connectionMade(self) -> None:
        self.connected = True

    def connectionLost(self, reason: Failure = connectionDone) -> None:
        self.connected = False
        amp.BinaryBoxProtocol.connectionLost(self, reason)
        # the exception: a Failure would fire the errbacks
        assert reason.value is not None, "a connection is lost for a reason"
        self.lost.callback(reason.value)

    @commands.Logged.responder
    def take_logged(self, message: str) -> dict[str, object]:
        if self.logged is not None:
            self.logged(json.loads(message))
        return {}


def endpoint_of(
    target: wire.Socket, reactor: PosixReactorBase
) -> IStreamClientEndpoint:
    """The endpoint of target, a wire.Socket of --connect."""

    if target.kind == "unix":
        assert target.path is not None, "resolve() gives it"
        return endpoints.UNIXClientEndpoint(reactor, target.path)
    assert target.host is not None, "parse_socket() sets it"
    assert target.port is not None, "parse_socket() sets it"
    endpoint: IStreamClientEndpoint = endpoints.HostnameEndpoint(
        reactor, target.host, target.port
    )
    if target.kind == "ssl":
        from virtualbricks.console import tls

        try:
            options = tls.client_options(target)
        except wire.Unusable as exc:
            raise Refused(str(exc)) from None
        endpoint = endpoints.wrapClientTLS(options, endpoint)
    return endpoint


def _token(target: wire.Socket) -> str:
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


async def start(windows: Windows, target: wire.Socket) -> Json:
    """
    Prove the token if asked, agree on protocol 2, check the version and
    follow: the answer of Follow, once the copy is whole.
    """

    await agree(windows, target)
    try:
        return await windows.callRemote(commands.Follow)
    except amp.UnhandledCommand:
        raise Refused(
            _(
                "{where} has no commands for the windows: run the same"
                " Virtualbricks on both"
            ).format(where=where(target))
        ) from None


async def agree(windows: amp.AMP, target: wire.Socket) -> None:
    """
    Prove the token if asked, agree on protocol 2 and check the version:
    Refused says why it can't.
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


async def _reach(
    target: wire.Socket, reactor: PosixReactorBase, connection: _P
) -> _P:
    try:
        return await endpoints.connectProtocol(
            endpoint_of(target, reactor), connection
        )
    except error.ConnectError as exc:
        reason = exc.osError or exc
        raise Refused(
            _("Can't reach {where}: {reason}").format(
                where=target.where(),
                reason=getattr(reason, "strerror", None) or str(reason),
            )
        ) from None


async def connect(
    target: wire.Socket,
    mirror: MirrorFactory,
    reactor: PosixReactorBase,
    made: Callable[[Windows], object] | None = None,
) -> Windows:
    """
    The connection to target, following it with the copy mirror. made, if
    given, is called with the connection before it follows: what comes with
    the project, as the messages of the log, goes where it says.
    """

    windows = await _reach(target, reactor, Windows(mirror))
    if made is not None:
        made(windows)
    try:
        await start(windows, target)
    except BaseException:
        assert windows.transport is not None, "it is connected"
        windows.transport.loseConnection()
        raise
    return windows


async def connect_again(
    target: wire.Socket, reactor: PosixReactorBase
) -> amp.AMP:
    """
    Another connection to target, which agreed on protocol 2 and follows
    nothing: for a console.
    """

    connection = await _reach(target, reactor, amp.AMP())
    try:
        await agree(connection, target)
    except BaseException:
        assert connection.transport is not None, "it is connected"
        connection.transport.loseConnection()
        raise
    return connection


def _pairs(values: dict[str, str]) -> list[dict[str, str]]:
    return [{"key": key, "value": value} for key, value in values.items()]


def _text(kind: FieldKind[Any], value: object) -> str:
    """A value as the console reads it: a text as it is."""

    return value if isinstance(value, str) else kind.format(value)


def _stamp(facts: Json | None) -> tuple[int, int] | None:
    return None if facts is None else (facts["size"], facts["mtime"])


class RemoteInfos:
    """
    What qemu-img info says of the files there, asked with ImageFacts, while
    the facts that the Virtualbricks there sends of a file don't change: the
    calls of images.InfoCache.
    """

    def __init__(self, machine: RemoteMachine, engine: RemoteEngine) -> None:
        self.machine = machine
        self.engine = engine
        # the files asked, and who waits for them
        self._reading: dict[str, list[defer.Deferred[ImageInfo]]] = {}

    def get(self, path: str) -> ImageInfo | None:
        found = self.machine.asked.get(path)
        if found is None:
            return None
        if _stamp(found["file"]) != _stamp(self.machine.facts(path)):
            return None
        return found["info"]

    def read(self, path: str) -> defer.Deferred[ImageInfo]:
        info = self.get(path)
        if info is not None:
            return defer.succeed(info)
        waiting: defer.Deferred[ImageInfo] = defer.Deferred()
        if path in self._reading:
            self._reading[path].append(waiting)
            return waiting
        self._reading[path] = [waiting]
        reading = self.engine.image_facts(path)
        reading.addBoth(self._read, path)
        return waiting

    def _read(self, result: Json | Failure, path: str) -> None:
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

    def __init__(self, mirror: MirrorFactory, engine: RemoteEngine) -> None:
        self.mirror = mirror
        # the answers of ImageFacts, by path
        self.asked: dict[str, Json] = {}
        self.infos = RemoteInfos(self, engine)

    def facts(self, path: str) -> Json | None:
        """What the Virtualbricks there last said of the file path."""

        mirror = self.mirror
        for image in mirror.images:
            if image.path == path:
                return mirror.state(IMAGE, image.name).get("file")
        for brick in mirror.bricks:
            if not is_virtualmachine(brick):
                continue
            copies = mirror.state(BRICK, brick.name).get("copies", {})
            for device, facts in copies.items():
                if brick.disk(device).get_cow_path() == path:
                    return facts
        found = self.asked.get(path)
        return None if found is None else found["file"]

    def exists(self, path: str) -> bool:
        return self.facts(path) is not None

    def taken(self, path: str) -> int | None:
        facts = self.facts(path)
        return None if facts is None else facts["taken"]

    def changed(self, path: str) -> float | None:
        facts = self.facts(path)
        return None if facts is None else facts["mtime"] / 1e9

    def other_projects(self, path: str) -> list[tuple[str, str]]:
        found = self.asked.get(path)
        return [] if found is None else found["others"]

    def can_trash(self, path: str) -> bool:
        return bool(self.mirror.machine.get("trash"))

    def image_folder(self) -> str:
        return os.path.join(
            self.mirror.machine.get("workspace", ""), locations.SHARED_IMAGES
        )

    def setting(self, name: str) -> SettingValue:
        return self.mirror.settings[name]

    def qemu_programs(self) -> list[str]:
        return list(self.mirror.machine.get("qemu_programs", []))


class OpenThere:
    """The project open there: its name and its folder."""

    def __init__(self, name: str, path: str | None) -> None:
        self.name = name
        self.path = path


def summary_of(table: Json) -> ProjectSummary:
    """The summary of a project, from the JSON of ProjectSummary."""

    return ProjectSummary(
        **dict(
            table,
            images=tuple(ImageSummary(**image) for image in table["images"]),
        )
    )


class RemoteWorkspace:
    """
    The workspace of the Virtualbricks there, as the windows read it: its
    folder, the project open, the names of its projects as ProjectNames
    said them last, the checks of a name, whether it has a trash. What
    changes it goes through the engine, and the Virtualbricks there checks
    the names again.
    """

    def __init__(self, mirror: MirrorFactory) -> None:
        self.mirror = mirror
        self.names: list[str] = []

    @property
    def path(self) -> str:
        return self.mirror.machine.get("workspace", "")

    @property
    def current(self) -> OpenThere | None:
        if self.mirror.project is None:
            return None
        return OpenThere(
            self.mirror.project, self.mirror.machine.get("project_folder")
        )

    def runtime_dir(self, name: str) -> str:
        """The runtime folder of the project name there."""

        return os.path.join(
            self.mirror.machine.get("workspace_runtime_dir", ""), name
        )

    def can_trash(self, name: str) -> bool:
        return bool(self.mirror.machine.get("trash"))

    def check_name(
        self,
        name: str,
        renaming: str | None = None,
        bricks: Iterable[str] | None = None,
    ) -> str | None:
        message = name_problem(name)
        if message is not None:
            return message
        if name != renaming and name in self.names:
            return _(TAKEN)
        # the bricks of a project that isn't open are known there only
        return room_problem(self.runtime_dir(name), bricks)

    def free_name(self, name: str) -> str:
        return free_name(name, lambda name: name in self.names)


class RemoteEngine:
    """
    The engine of the windows of the Virtualbricks at where, over the
    connection windows: its copy is what the windows read.
    """

    local: Literal[False] = False

    def __init__(
        self,
        mirror: MirrorFactory,
        windows: Windows | None,
        where: str,
        quit: Callable[[], object] | None = None,
        consoles: Consoles | None = None,
    ) -> None:
        self.factory = mirror
        # the consoles of the bricks there, carried over connections
        self.consoles = consoles
        self.machine = RemoteMachine(mirror, self)
        self.workspace = RemoteWorkspace(mirror)
        # the connection; Reconnect gives another
        self.windows = windows
        self.where = where
        # what closes the windows: the Virtualbricks there goes on (19 R6)
        self._quit = quit

    def call(
        self, command: type[amp.Command], **arguments: object
    ) -> defer.Deferred[Any]:
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

    def _then(
        self, deferred: defer.Deferred[Any], result: Callable[[], _T]
    ) -> defer.Deferred[_T]:
        """deferred, answered with result() once it is."""

        return deferred.addCallback(lambda _: result())

    # The bricks

    def start(self, brick: Brick) -> defer.Deferred[Any]:
        return self.call(ampcommands.BrickStart, name=[brick.name])

    def stop(self, brick: Brick) -> defer.Deferred[Any]:
        return self.call(ampcommands.BrickStop, name=[brick.name])

    def terminate(self, brick: VirtualMachine) -> defer.Deferred[Any]:
        # the console has no command for SIGTERM yet
        return defer.fail(NotYet("terminate"))

    def kill(self, brick: Brick) -> defer.Deferred[Any]:
        return self.call(ampcommands.BrickKill, name=[brick.name])

    def restart(self, brick: Brick) -> defer.Deferred[Any]:
        return self.call(ampcommands.BrickRestart, name=[brick.name])

    def pause(self, brick: Brick) -> defer.Deferred[Any]:
        return self.call(ampcommands.BrickPause, name=[brick.name])

    def continue_(self, brick: Brick) -> defer.Deferred[Any]:
        return self.call(ampcommands.BrickContinue, name=[brick.name])

    def suspend(self, vm: VirtualMachine) -> defer.Deferred[Any]:
        return self.call(ampcommands.BrickSuspend, vm=vm.name)

    def resume(self, vm: VirtualMachine) -> defer.Deferred[Any]:
        return self.call(ampcommands.BrickResume, vm=vm.name)

    def reset(self, vm: VirtualMachine) -> defer.Deferred[Any]:
        return self.call(ampcommands.BrickReset, vm=vm.name)

    def open_console(self, brick: Brick) -> defer.Deferred[None]:
        """Open the control monitor of brick there, in a terminal here."""

        if self.consoles is None:
            return defer.fail(NotYet("open_console"))
        return defer.ensureDeferred(self.consoles.open(brick))

    def console_lacks(self, brick: Brick) -> str | None:
        """Why this computer can't open a console of brick; None if it can."""

        if self.consoles is None:
            return NotYet().args[0]
        return self.consoles.lacks(brick)

    def new_brick(self, type: str, name: str) -> defer.Deferred[Brick]:
        making = self.call(ampcommands.BrickNew, kind=WORDS[type], name=name)
        return self._then(
            making,
            lambda: _there(self.factory.get_brick, normalize_name(name)),
        )

    def connect(
        self, source: Brick, destination: Brick
    ) -> defer.Deferred[bool]:
        connecting = self.call(
            commands.Connect, source=source.name, target=destination.name
        )
        return connecting.addCallback(lambda answer: answer["connected"])

    # The bricks, the events and the images

    def rename(self, item: Item, name: str) -> defer.Deferred[str]:
        old = item.name
        command = {
            BRICK: ampcommands.BrickRename,
            EVENT: ampcommands.EventRename,
            IMAGE: ampcommands.ImageRename,
        }[kind_of_item(item)]
        return self._then(self.call(command, name=old, new=name), lambda: old)

    def duplicate(self, item: Brick | Event) -> defer.Deferred[Brick | Event]:
        # the answer names the copy, as the Virtualbricks there named it
        get: Callable[[str], Brick | Event | None]
        if kind_of_item(item) == EVENT:
            copying = self.call(ampcommands.EventDuplicate, name=item.name)
            get = self.factory.get_event
        else:
            copying = self.call(ampcommands.BrickDuplicate, name=item.name)
            get = self.factory.get_brick

        def copy(answer: Json) -> Brick | Event:
            name = answer["lines"][0]
            found = get(name)
            assert found is not None, f"the copy has {name}"
            return found

        return copying.addCallback(copy)

    def remove(self, item: Item) -> defer.Deferred[Any]:
        kind = kind_of_item(item)
        if kind == IMAGE:
            return self.call(ampcommands.ImageDelete, name=item.name)
        if kind == EVENT:
            return self.call(ampcommands.EventDelete, name=[item.name])
        return self.call(ampcommands.BrickDelete, name=[item.name])

    def update_config(
        self, item: Brick | Event, changes: dict[str, object]
    ) -> defer.Deferred[Any]:
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

    def apply(self, draft: Draft) -> defer.Deferred[Any]:
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

    def new_event(self, name: str, delay: int) -> defer.Deferred[Event]:
        new = normalize_name(name)
        making = self.call(ampcommands.EventNew, name=name)
        setting = making.addCallback(
            lambda _: self.call(
                ampcommands.EventSet,
                name=new,
                key_value=_pairs({"delay": str(delay)}),
            )
        )
        return self._then(setting, lambda: _there(self.factory.get_event, new))

    def start_event(self, event: Event) -> defer.Deferred[Any]:
        return self.call(ampcommands.EventStart, name=[event.name])

    def stop_event(self, event: Event) -> defer.Deferred[Any]:
        return self.call(ampcommands.EventStop, name=[event.name])

    def run_event(self, event: Event) -> defer.Deferred[Any]:
        return self.call(ampcommands.EventRun, name=[event.name])

    # The images and their files

    def new_image(
        self, name: str, path: str, description: str = ""
    ) -> defer.Deferred[Image]:
        values = {"description": description} if description else {}
        adding = self.call(
            ampcommands.ImageAdd,
            name=name,
            path=path,
            key_value=_pairs(values),
        )
        return self._then(
            adding,
            lambda: _there(self.factory.get_image, normalize_name(name)),
        )

    def make_image(
        self, path: str, fmt: str, size: int
    ) -> defer.Deferred[Any]:
        return self.call(commands.MakeImage, path=path, format=fmt, size=size)

    def image_facts(self, path: str) -> defer.Deferred[Json]:
        """
        What the file path is there: file, its facts; info, an ImageInfo;
        others, the images of the other projects with that file.
        """

        asking = self.call(commands.ImageFacts, path=path)

        def read(answer: Json) -> Json:
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

    def image_info(self, path: str) -> defer.Deferred[ImageInfo]:
        return self.image_facts(path).addCallback(lambda found: found["info"])

    def relink(self, image: Image, path: str) -> defer.Deferred[Any]:
        return self.call(commands.Relink, name=image.name, path=path)

    def discard_file(self, path: str) -> defer.Deferred[bool]:
        trashing = self.call(commands.TrashFile, path=path)

        def gone(answer: Json) -> bool:
            # what was asked of it is no more
            self.machine.asked.pop(path, None)
            return answer["trashed"]

        return trashing.addCallback(gone)

    def start_over(
        self, vm: VirtualMachine, device: str
    ) -> defer.Deferred[bool]:
        starting = self.call(commands.StartOver, vm=vm.name, device=device)
        return starting.addCallback(lambda answer: answer["trashed"])

    # The projects

    def project_names(self) -> defer.Deferred[list[str]]:
        """The names of the projects there, which the workspace keeps."""

        asking = self.call(commands.ProjectNames)

        def keep(answer: Json) -> list[str]:
            self.workspace.names = list(answer["names"])
            return self.workspace.names

        return asking.addCallback(keep)

    def _then_names(self, deferred: defer.Deferred[_T]) -> defer.Deferred[_T]:
        """deferred, with the names of the projects asked again after it."""

        def again(result: _T) -> defer.Deferred[_T]:
            asking = self.project_names()
            # the names are for the checks: the change is done anyway
            asking.addErrback(lambda failure: None)
            return asking.addCallback(lambda _: result)

        return deferred.addCallback(again)

    def project_summaries(self) -> defer.Deferred[list[ProjectSummary]]:
        """The summaries of the projects there, the most recently used first."""

        def gone(failure: Failure) -> None:
            # a project gone meanwhile isn't listed
            failure.trap(ampcommands.NotFound)
            return None

        def summary(name: str) -> defer.Deferred[Json | None]:
            asking = self.call(commands.ProjectSummary, name=name)
            reading = asking.addCallback(
                lambda answer: json.loads(answer["summary"])
            )
            return reading.addErrback(gone)

        def first(failure: Failure) -> Failure:
            # the failure of the summary that failed first
            failure.trap(defer.FirstError)
            first = failure.value
            assert isinstance(first, defer.FirstError), "trapped"
            return first.subFailure

        def each(names: list[str]) -> defer.Deferred[list[Json | None]]:
            summaries = [summary(name) for name in names]
            gathering = defer.gatherResults(summaries, consumeErrors=True)
            return gathering.addErrback(first)

        def listed(tables: list[Json | None]) -> list[ProjectSummary]:
            summaries = [
                summary_of(table) for table in tables if table is not None
            ]
            # as the Virtualbricks there sorts them
            return sorted(summaries, key=lambda s: (-s.modified, s.name))

        return self.project_names().addCallback(each).addCallback(listed)

    def disk_usage(self, name: str) -> defer.Deferred[DiskUsage]:
        asking = self.call(commands.DiskUsage, name=name)
        return asking.addCallback(
            lambda answer: DiskUsage(
                answer["private_disks"], answer["other_files"]
            )
        )

    def save_project(self) -> defer.Deferred[Any]:
        return self.call(ampcommands.ProjectSave)

    def open_project(self, name: str) -> defer.Deferred[Report]:
        # the pushes bring the project before the answer
        return self._then(
            self.call(ampcommands.ProjectOpen, name=name), Report
        )

    def new_project(
        self, name: str, description: str = ""
    ) -> defer.Deferred[Report]:
        making = self.call(ampcommands.ProjectNew, name=name)
        if description:
            # its README, once it is open there
            making = making.addCallback(
                lambda _: self.call(commands.SetReadme, text=description)
            )
        return self._then_names(self._then(making, Report))

    def restore_last(self) -> defer.Deferred[None]:
        # the Virtualbricks there has a project open, or its own way
        return defer.succeed(None)

    def rename_project(self, name: str, new: str) -> defer.Deferred[Any]:
        return self._then_names(
            self.call(ampcommands.ProjectRename, name=name, new=new)
        )

    def duplicate_project(self, name: str, new: str) -> defer.Deferred[Any]:
        return self._then_names(
            self.call(ampcommands.ProjectDuplicate, name=name, new=new)
        )

    def remove_project(self, name: str, trash: bool) -> defer.Deferred[Any]:
        return self._then_names(
            self.call(ampcommands.ProjectDelete, name=name, force=not trash)
        )

    def readme(self) -> defer.Deferred[str]:
        return self.call(commands.Readme).addCallback(
            lambda answer: answer["text"]
        )

    def set_readme(self, text: str) -> defer.Deferred[Any]:
        size = len(text.encode("utf-8"))
        if size > amp.MAX_VALUE_LENGTH:
            # more than AMP carries: said here, before it's sent
            return defer.fail(
                ampwire.AnswerTooLong(
                    _(
                        "The README is {size} bytes, longer than the {most}"
                        " that AMP carries"
                    ).format(size=size, most=amp.MAX_VALUE_LENGTH)
                )
            )
        return self.call(commands.SetReadme, text=text)

    def picture(self, name: str, path: str) -> defer.Deferred[bytes]:
        # in pieces, each as much as a value carries
        pieces: list[bytes] = []

        def ask(offset: int) -> defer.Deferred[bytes]:
            asking = self.call(
                commands.ReadmePicture, name=name, path=path, offset=offset
            )
            return asking.addCallback(more)

        def more(answer: Json) -> bytes | defer.Deferred[bytes]:
            pieces.append(answer["data"])
            got = sum(len(piece) for piece in pieces)
            if answer["data"] and got < answer["size"]:
                return ask(got)
            return b"".join(pieces)

        return ask(0)

    # The settings

    def set_settings(
        self, values: dict[str, SettingValue]
    ) -> defer.Deferred[Any]:
        texts = {
            key: _text(setting_kind(key), value)
            for key, value in values.items()
        }
        return self.call(ampcommands.SettingSet, key_value=_pairs(texts))

    def set_ksm(self, enable: bool) -> defer.Deferred[bool]:
        setting = self.call(commands.SetKsm, enable=enable)
        return setting.addCallback(lambda answer: answer["enabled"])

    # What the machine has

    def lacks(self, kind: Kind) -> defer.Deferred[Issue | None]:
        found = self.factory.machine.get("lacks", {}).get(kind.type)
        return defer.succeed(None if found is None else Issue(**found))

    def qemu(self, program: str) -> defer.Deferred[QemuInfo]:
        """
        What the QEMU program has there, read here from what it printed;
        FileNotFoundError if there is none.
        """

        asking = self.call(commands.QemuFacts, program=program)

        def read(answer: Json) -> QemuInfo:
            answers = {
                name: Answer(*json.loads(answer[name]))
                for name in commands.QEMU_ANSWERS
            }
            return qemu_info(answer["path"], answers)

        def not_there(failure: Failure) -> NoReturn:
            failure.trap(ampcommands.NotFound)
            raise FileNotFoundError(program)

        return asking.addCallbacks(read, not_there)

    def machine_properties(
        self, info: QemuInfo, machine: str
    ) -> defer.Deferred[frozenset[str]]:
        # the default machine type, if empty, as the Virtualbricks there
        # has it
        asking = self.call(
            commands.MachineProperties, program=info.path, machine=machine
        )
        return asking.addCallback(
            lambda answer: parse_machine_properties(answer["text"])
        )

    def folder(self, path: str) -> defer.Deferred[tuple[list[str], bool]]:
        asking = self.call(commands.Folder, path=path)
        return asking.addCallback(
            lambda answer: (list(answer["entries"]), answer["more"])
        )

    def programs_found(
        self, vde_path: str, qemu_path: str
    ) -> defer.Deferred[tuple[FolderPrograms, FolderPrograms]]:
        asking = self.call(
            commands.ProgramsFound, vde_path=vde_path, qemu_path=qemu_path
        )
        return asking.addCallback(
            lambda answer: (
                FolderPrograms.from_data(json.loads(answer["vde"])),
                FolderPrograms.from_data(json.loads(answer["qemu"])),
            )
        )

    def usb(self) -> defer.Deferred[list[UsbDevice]]:
        asking = self.call(commands.UsbDevices)
        return asking.addCallback(
            lambda answer: [
                UsbDevice(device["id"], device["description"])
                for device in json.loads(answer["devices"])
            ]
        )

    def quit(self) -> defer.Deferred[None]:
        """Close the windows; the Virtualbricks there goes on."""

        if self._quit is not None:
            self._quit()
        return defer.succeed(None)
