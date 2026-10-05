# -*- test-case-name: virtualbricks.tests.config.test_projectfile -*-
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
The project file, ``project.toml``.

It holds the project's settings, its image library, its events and its bricks
with their connections. Every field is written, defaults included. Reading is
lenient: a problem is reported and, where possible, the default is used.

A connection names the socket a plug is in: ``"sw1"`` is the only socket of
the brick sw1 and ``"vm2:sock_eth1"`` is the socket card sock_eth1 of the
virtual machine vm2.

The file starts with a header and has a comment above every key, see
:func:`project_notes`.
"""

from __future__ import annotations

import contextlib
import functools
import os
import re
import shlex
from collections.abc import Callable, Collection, Iterator
from typing import TYPE_CHECKING, TypeAlias, TypedDict, cast

from virtualbricks import errors
from virtualbricks.config.schema import (
    Choice,
    Mac,
    Path,
    Str,
    define,
    dump_record,
    field,
    key_of,
    kind_of,
    load_record,
    notes,
    references,
)
from virtualbricks.config.settings import (
    RETIRED_PROJECT_KEYS,
    ProjectSettings,
)
from virtualbricks.config.tomlfile import (
    FORMAT_NOTE,
    DecodeError,
    Note,
    dump_toml,
    load_toml,
)
from virtualbricks.nic import random_mac

if TYPE_CHECKING:  # pragma: no cover
    from virtualbricks.brickfactory import BrickFactory
    from virtualbricks.bricks import Brick
    from virtualbricks.bricks.virtualmachine import (
        VirtualMachine,
        VMPlug,
        VMSock,
    )
    from virtualbricks.config.report import Report
    from virtualbricks.config.tomlfile import Notes, Table, Value
    from virtualbricks.bricks.plug import Plug
    from virtualbricks.bricks.sock import Sock

FORMAT = 2
TOP_KEYS = frozenset(("format", "settings", "images", "events", "bricks"))
HOSTONLY = "_hostonly"
CONNECTION_KEYS = {
    None: frozenset(),
    "connect": frozenset(("connect",)),
    "endpoints": frozenset(("endpoints",)),
    "nics": frozenset(("nics",)),
}
SOCKET_NAME = re.compile(r"[a-zA-Z0-9_.-]+")
NIC_KINDS = Choice("plug", "socket", "hostonly")
NIC_KEYS = {
    "plug": frozenset(("kind", "connect", "model", "mac")),
    "socket": frozenset(("kind", "name", "model", "mac")),
    "hostonly": frozenset(("kind", "model", "mac")),
}
DEFAULT_MODEL = "rtl8139"
HEADER = """\
A Virtualbricks project: its settings, disk images, events and bricks.
Virtualbricks writes this file and its comments, and rewrites it while the
project is open: a comment added by hand is lost.
See virtualbricks-config(5).
"""
# The notes of the keys that no schema declares.
CONNECTION_NOTES = {
    "connect": Note("The socket it's plugged into"),
    "endpoints": Note("The sockets of its two ends, left and right"),
}
NIC_NOTES = {
    "kind": Note("The kind of card: plug, socket or hostonly"),
    "connect": Note("The socket it's plugged into"),
    "name": Note("The name of the socket card, which other bricks plug into"),
    "model": Note("The model of the card, as QEMU names it"),
    "mac": Note("The MAC address"),
}

# The old console's words for its own commands, and the new command.
OLD_COMMANDS = {
    ("quit",): "quit",
    ("q",): "quit",
    ("help",): "help",
    ("h",): "help",
    ("ps",): "status",
    ("list",): "brick list",
    ("images", "list"): "image list",
    ("i", "list"): "image list",
}


def _join(words: Collection[str]) -> str:
    return " ".join(shlex.quote(word) for word in words)


def old_action(
    text: str, bricks: Collection[str], events: Collection[str]
) -> tuple[Table, bool]:
    """
    The action of format 2 of a command of the console of format 1, as
    "sw1 on"; and whether the new console reads it: a command of the old
    console that the new one lacks stays as it is.

    bricks and events are the names of the project, which say whether a
    name is a brick or an event.
    """

    words = text.split()
    if len(words) >= 2 and words[0] in ("brick", "event"):
        # the old console's own forms: brick NAME ARGS...
        words = words[1:]
    if tuple(words) in OLD_COMMANDS:
        return {"kind": "console", "command": OLD_COMMANDS[tuple(words)]}, True
    if len(words) == 3 and words[0] in ("new", "n"):
        if words[1] == "event":
            command = f"event new {shlex.quote(words[2])}"
        else:
            command = f"brick new {_join(words[1:])}"
        return {"kind": "console", "command": command}, True
    if len(words) >= 3 and words[:2] in (["config", "set"], ["cfg", "set"]):
        setting = f"{words[2]}={' '.join(words[3:])}"
        return {
            "kind": "console",
            "command": f"setting set {_join([setting])}",
        }, True
    if len(words) >= 2:
        name, verb, rest = words[0], words[1], words[2:]
        noun = "event" if name in events and name not in bricks else "brick"
        if verb in ("on", "off") and not rest:
            kind = "start" if verb == "on" else "stop"
            return {"kind": kind, "target": name}, True
        if verb == "config" and rest:
            command = f"{noun} set {_join([name] + rest)}"
            return {"kind": "console", "command": command}, True
        if verb in ("remove", "show") and not rest:
            new = "delete" if verb == "remove" else "show"
            return {"kind": "console", "command": f"{noun} {new} {name}"}, True
        if verb == "connect" and len(rest) == 1:
            # a switch's socket was its name and _port
            target = rest[0].removesuffix("_port")
            return {
                "kind": "console",
                "command": f"brick connect {_join([name, target])}",
            }, True
        if verb == "disconnect" and not rest:
            return {
                "kind": "console",
                "command": f"brick disconnect {name}",
            }, True
    return {"kind": "console", "command": text}, False


def _upgrade_actions(data: Table, report: Report) -> Table:
    """
    Format 1 to 2: the events start and stop with actions of their own, and
    their console commands are those of the new console.
    """

    events = data.get("events")
    bricks = data.get("bricks")
    brick_names = set(bricks) if isinstance(bricks, dict) else set()
    event_names = set(events) if isinstance(events, dict) else set()
    for name, table in (events.items() if isinstance(events, dict) else ()):
        actions = table.get("actions") if isinstance(table, dict) else None
        if not isinstance(actions, list):
            continue
        for index, action in enumerate(actions):
            if not isinstance(action, dict) or action.get("kind") != "vb":
                continue
            text = action.get("command")
            if not isinstance(text, str):
                continue
            new, read = old_action(text, brick_names, event_names)
            where = f"events.{name}.actions"
            if read:
                report.info(
                    f"the command {text!r} is now {describe_action(new)}",
                    where,
                )
            else:
                report.warning(
                    f"{text!r} is a command of the old console, which the"
                    " console may not read",
                    where,
                )
            actions[index] = new
    data["format"] = 2
    return data


def describe_action(table: Table) -> str:
    """An action of the project file in words: start sw1, console "…"."""

    kind = table.get("kind")
    if kind in ("start", "stop"):
        return f"{kind} {table.get('target')}"
    return f'{kind} "{table.get("command")}"'


# Steps that rewrite the data of format N into the data of format N + 1.
UPGRADES: dict[int, Callable[[Table, Report], Table]] = {1: _upgrade_actions}


class ProjectFormatError(Exception):
    """The project file can't be read: it's not TOML or a newer format."""


@define
class ImageTable:

    path: str = field(
        Path(),
        default="",
        help=(
            "The image file; a relative path is relative to the project folder"
        ),
    )
    description: str = field(
        Str(), default="", help="A description of the image"
    )


class Nic(TypedDict, total=False):
    """A network card of a virtual machine, as read from the project file."""

    kind: str
    model: str
    mac: str
    # the socket that a plug connects to
    connect: str
    # the name of a socket card
    name: str


# What the plugs of a brick connect to: sockets, or its network cards.
Targets: TypeAlias = list[str] | list[Nic]


# Writing


def socket_target(sock: Sock) -> str:
    """Return how a connection to this socket is written."""

    if sock.brick.connections == "nics":
        vm = sock.brick.name
        return f"{vm}:{sock.nickname[len(vm) + 1:]}"
    return sock.brick.name


def _plug_target(plug: Plug | VMPlug) -> str:
    if plug.sock is None:
        return ""
    return socket_target(plug.sock)


def _nic_table(link: VMPlug | VMSock) -> Table:
    table: Table
    if link.mode == "sock":
        # The socket name is after the name of the virtual machine.
        name = link.nickname[len(link.brick.name) + 1 :]
        table = {"kind": "socket", "name": name}
    elif link.sock is not None and link.sock.nickname == HOSTONLY:
        table = {"kind": "hostonly"}
    else:
        # a card that isn't a socket is a plug
        table = {"kind": "plug", "connect": _plug_target(cast("VMPlug", link))}
    table["model"] = link.model
    table["mac"] = link.mac
    return table


def brick_table(brick: Brick) -> Table:
    table: Table = {"type": brick.get_type().lower()}
    table.update(brick.config_table())
    style = brick.connections
    if style == "connect":
        table["connect"] = _plug_target(brick.plugs[0])
    elif style == "endpoints":
        table["endpoints"] = [_plug_target(plug) for plug in brick.plugs]
    elif style == "nics":
        links = list(brick.plugs) + list(brick.socks)
        table["nics"] = [_nic_table(link) for link in links]
    return table


def project_document(
    factory: BrickFactory, project_settings: ProjectSettings
) -> Table:
    """Return the data of the project file for the bricks of factory."""

    data: Table = {"format": FORMAT, "settings": dump_record(project_settings)}
    images: Table = {
        image.name: {
            "path": image.path,
            "description": image.description,
        }
        for image in factory.images
    }
    if images:
        data["images"] = images
    events: Table = {
        event.name: dump_record(event.config) for event in factory.events
    }
    if events:
        data["events"] = events
    bricks: Table = {
        brick.name: brick_table(brick) for brick in factory.bricks
    }
    if bricks:
        data["bricks"] = bricks
    return data


def _brick_class(brick_type: str) -> type[Brick] | None:
    # the bricks need the settings, which are in this package
    from virtualbricks.brickfactory import BRICK_CLASSES

    return BRICK_CLASSES.get(brick_type.lower())


def _nics_notes(table: Table) -> Notes:
    nics = table.get("nics")
    if not isinstance(nics, list):
        return {}
    return {
        ("nics", index, key): NIC_NOTES[key]
        for index, nic in enumerate(nics)
        if isinstance(nic, dict)
        for key in nic
        if key in NIC_NOTES
    }


def _brick_notes(table: Table) -> Notes:
    brick_type = table.get("type")
    if not isinstance(brick_type, str):
        return {}
    cls = _brick_class(brick_type)
    if cls is None:
        return {}
    result = {("type",): Note(cls.summary), **cls.table_notes(table)}
    if cls.connections in CONNECTION_NOTES:
        key = cls.connections
        result[(key,)] = CONNECTION_NOTES[key]
    elif cls.connections == "nics":
        result.update(_nics_notes(table))
    return result


def project_notes(data: Table) -> Notes:
    """
    The notes of the keys of the data of a project file: those of the
    schemas, and the fixed ones of the format, the types of the bricks and
    their connections. Bricks of unknown types have none.
    """

    from virtualbricks.bricks.event import EventConfig

    result: dict[tuple[str | int, ...], Note] = {("format",): FORMAT_NOTE}

    def nest(prefix: tuple[str, ...], inner: Notes) -> None:
        result.update({prefix + path: note for path, note in inner.items()})

    nest(("settings",), notes(ProjectSettings, _table(data, "settings")))
    sections: list[tuple[str, Callable[[Table], Notes]]] = [
        ("images", functools.partial(notes, ImageTable)),
        ("events", functools.partial(notes, EventConfig)),
        ("bricks", _brick_notes),
    ]
    for section, table_notes in sections:
        for name, table in _table(data, section).items():
            if isinstance(table, dict):
                nest((section, name), table_notes(table))
    return result


def write_project_file(data: Table, path: str) -> None:
    """Write the data of a project file, with its header and comments."""

    dump_toml(data, path, project_notes(data), HEADER)


def save_project(
    factory: BrickFactory, project_settings: ProjectSettings, path: str
) -> None:
    write_project_file(project_document(factory, project_settings), path)


def create_project_file(path: str, project_settings: ProjectSettings) -> None:
    """Write the project file of a new, empty project."""

    write_project_file(
        {"format": FORMAT, "settings": dump_record(project_settings)}, path
    )


# Reading


def upgrade_project(data: Table, report: Report) -> Table:
    """Bring the data to the current format; ProjectFormatError if newer."""

    version = data.get("format")
    if (
        isinstance(version, bool)
        or not isinstance(version, int)
        or version < 1
    ):
        report.warning(
            f"unknown format {version!r}, read as format {FORMAT}", "format"
        )
        return data
    if version > FORMAT:
        raise ProjectFormatError(
            f"written by a newer Virtualbricks (format {version})"
        )
    while version < FORMAT:
        data = UPGRADES[version](data, report)
        version += 1
    return data


def _tables(
    data: Table, key: str, report: Report
) -> Iterator[tuple[str, Table]]:
    value = data.get(key, {})
    if not isinstance(value, dict):
        report.warning("is not a table, ignored", key)
        return
    for name, table in value.items():
        if isinstance(table, dict):
            yield name, table
        else:
            report.warning("is not a table, ignored", f"{key}.{name}")


def resolve(factory: BrickFactory, target: str) -> Sock | None:
    """Return the socket named by a connection, or None."""

    if ":" in target:
        brick_name, _, socket_name = target.partition(":")
        sock = factory.get_sock(f"{brick_name}_{socket_name}")
        if sock is not None and sock.brick.name == brick_name:
            return sock
        return None
    brick = factory.get_brick(target)
    if brick is not None and brick.socks and brick.connections != "nics":
        return brick.socks[0]
    return None


def _read_target(value: Value, report: Report, where: str) -> str:
    if not isinstance(value, str):
        report.warning(
            f"{value!r} is not a connection, left unconnected", where
        )
        return ""
    return value


def _read_nic(
    table: Value, index: int, report: Report, where: str
) -> Nic | None:
    if not isinstance(table, dict):
        report.warning("is not a table, card dropped", where)
        return None
    kind = table.get("kind")
    try:
        NIC_KINDS.check(kind)
    except ValueError as exc:
        report.warning(f"kind: {exc}, card dropped", where)
        return None
    # NIC_KINDS.check() made sure it's a string, as Mac().check() below
    nic: Nic = {"kind": cast(str, kind)}
    model = table.get("model", DEFAULT_MODEL)
    if not isinstance(model, str) or not model:
        report.warning(f"model: {model!r}, using {DEFAULT_MODEL}", where)
        model = DEFAULT_MODEL
    nic["model"] = model
    mac = table.get("mac")
    try:
        Mac().check(mac)
        if not mac:
            raise ValueError("no MAC address")
        nic["mac"] = cast(str, mac)
    except ValueError as exc:
        nic["mac"] = random_mac()
        report.warning(f"mac: {exc}, using {nic['mac']}", where)
    if kind == "plug":
        nic["connect"] = _read_target(
            table.get("connect", ""), report, f"{where}.connect"
        )
    elif kind == "socket":
        name = table.get("name")
        if not isinstance(name, str) or not SOCKET_NAME.fullmatch(name):
            name = f"sock_eth{index}"
            report.warning(f"name: missing or invalid, using {name}", where)
        nic["name"] = name
    for key in table.keys() - NIC_KEYS[nic["kind"]]:
        report.warning("unknown field, dropped", f"{where}.{key}")
    return nic


def _read_connections(
    brick: Brick, table: Table, report: Report, where: str
) -> Targets:
    """Return the targets of the plugs and create the socket cards."""

    style = brick.connections
    if style == "connect":
        where = f"{where}.connect"
        return [_read_target(table.get("connect", ""), report, where)]
    if style == "endpoints":
        ends = table.get("endpoints", ["", ""])
        if not isinstance(ends, list) or len(ends) != 2:
            report.warning(
                "is not a list of two ends, left unconnected", where
            )
            ends = ["", ""]
        return [
            _read_target(end, report, f"{where}.endpoints[{i}]")
            for i, end in enumerate(ends)
        ]
    if style == "nics":
        # only virtual machines have network cards
        vm = cast("VirtualMachine", brick)
        nics = table.get("nics", [])
        if not isinstance(nics, list):
            report.warning("nics: is not a list, cards dropped", where)
            nics = []
        plugs: list[Nic] = []
        for index, item in enumerate(nics):
            nic = _read_nic(item, index, report, f"{where}.nics[{index}]")
            if nic is None:
                continue
            if nic["kind"] == "socket":
                vm.add_sock(nic["mac"], nic["model"], nic["name"])
            else:
                plugs.append(nic)
        return plugs
    return []


def _connect(
    factory: BrickFactory,
    brick: Brick,
    targets: Targets,
    report: Report,
    where: str,
) -> None:
    # the targets are network cards if the brick has them, else sockets
    if brick.connections == "nics":
        vm = cast("VirtualMachine", brick)
        for nic in cast("list[Nic]", targets):
            if nic["kind"] == "hostonly":
                sock = factory.get_sock(HOSTONLY)
            else:
                sock = _find_socket(factory, nic["connect"], report, where)
            vm.add_plug(sock, nic["mac"], nic["model"])
        return
    for plug, target in zip(brick.plugs, cast("list[str]", targets)):
        sock = _find_socket(factory, target, report, where)
        if sock is not None:
            plug.connect(sock)


def _find_socket(
    factory: BrickFactory, target: str, report: Report, where: str
) -> Sock | None:
    if not target:
        return None
    sock = resolve(factory, target)
    if sock is None:
        report.warning(f'no socket "{target}", left unconnected', where)
    return sock


def _read_images(
    factory: BrickFactory, data: Table, report: Report, directory: str
) -> None:
    for name, table in _tables(data, "images", report):
        where = f"images.{name}"
        image = load_record(ImageTable, table, report, where)
        path = image.path
        if not path:
            report.warning("has no path, image dropped", where)
            continue
        if not os.path.isabs(path):
            path = os.path.join(directory, path)
        if not os.path.exists(path):
            report.warning(f"{path} not found, kept in the library", where)
        try:
            factory.new_image(name, path, image.description)
        except errors.ImageAlreadyInUseError:
            report.warning(
                "uses the file of another image, image dropped", where
            )
        except errors.InvalidNameError as exc:
            report.warning(f"{exc}, image dropped", where)


def _read_events(factory: BrickFactory, data: Table, report: Report) -> None:
    from virtualbricks.bricks.event import EventConfig

    for name, table in _tables(data, "events", report):
        where = f"events.{name}"
        try:
            event = factory.new_event(name)
        except errors.InvalidNameError as exc:
            report.warning(f"{exc}, event dropped", where)
            continue
        event.config = load_record(EventConfig, table, report, where)
        # what shows the event learns its configuration
        event.changed.notify(event)


def _read_bricks(factory: BrickFactory, data: Table, report: Report) -> None:
    connections: list[tuple[Brick, Targets, str]] = []
    # the bricks say nothing until they are whole, even if reading fails
    with contextlib.ExitStack() as quiet:
        for name, table in _tables(data, "bricks", report):
            where = f"bricks.{name}"
            brick_type = table.get("type")
            try:
                if not isinstance(brick_type, str):
                    raise errors.InvalidTypeError(f"type {brick_type!r}")
                brick = factory.new_brick(brick_type, name)
            except (errors.InvalidTypeError, errors.InvalidNameError) as exc:
                report.warning(f"{exc}, brick dropped", where)
                continue
            quiet.enter_context(brick.muted())
            ignore = {"type"} | CONNECTION_KEYS[brick.connections]
            brick.load_config_table(table, report, where, ignore)
            targets = _read_connections(brick, table, report, where)
            connections.append((brick, targets, where))
        # Connect once every socket exists.
        for brick, targets, where in connections:
            _connect(factory, brick, targets, report, where)
    for brick, _targets, _where in connections:
        # what shows the brick learns its configuration and its links
        brick.changed.notify(brick)


def _check_references(factory: BrickFactory, report: Report) -> None:
    lookups: dict[str, Callable[[str], object]] = {
        "event": factory.get_event,
        "image": factory.get_image,
    }
    objects = [("bricks", brick) for brick in factory.bricks]
    objects += [("events", event) for event in factory.events]
    for kind, obj in objects:
        for name, target, value in references(obj.config):
            if lookups[target](value) is None:
                key = key_of(obj.config, name)
                where = f"{kind}.{obj.name}.{key}"
                report.warning(f'no {target} named "{value}"', where)


def _read_settings(data: Table, report: Report) -> ProjectSettings:
    defaults = dump_record(ProjectSettings())
    table = data.get("settings")
    if not isinstance(table, dict):
        problem = "missing" if table is None else "is not a table"
        report.warning(f"{problem}, using the defaults", "settings")
        table = {}
    elif table:
        for key in defaults.keys() - table.keys():
            value = kind_of(ProjectSettings, key).format(defaults[key])
            report.warning(
                f"missing, using the default {value}", f"settings.{key}"
            )
    return load_record(
        ProjectSettings,
        {**defaults, **table},
        report,
        "settings",
        ignore=RETIRED_PROJECT_KEYS,
    )


def restore_project(
    factory: BrickFactory, data: Table, report: Report, directory: str
) -> ProjectSettings:
    """
    Build the project described by data in factory; return its settings.

    The data must be of the current format, see :func:`upgrade`. Relative
    image paths are relative to ``directory``.
    """

    for key in data.keys() - TOP_KEYS:
        report.warning("unknown field, dropped", key)
    project_settings = _read_settings(data, report)
    _read_images(factory, data, report, directory)
    _read_events(factory, data, report)
    _read_bricks(factory, data, report)
    _check_references(factory, report)
    return project_settings


def read_project_file(path: str) -> Table:
    """Return the data of a project file; ProjectFormatError if not TOML."""

    try:
        return load_toml(path)
    except DecodeError as exc:
        raise ProjectFormatError(f"{path}: {exc}") from None


def load_project(
    factory: BrickFactory, path: str, report: Report
) -> ProjectSettings:
    """Read a project file into factory; return the project's settings."""

    data = upgrade_project(read_project_file(path), report)
    return restore_project(factory, data, report, os.path.dirname(path))


# Editing, used when a project is imported


def _table(data: Table, key: str) -> Table:
    """The table under key, empty if there's none or it's not a table."""

    table = data.get(key, {})
    return table if isinstance(table, dict) else {}


def image_paths(data: Table) -> dict[str, Value]:
    return {
        name: table.get("path", "")
        for name, table in _table(data, "images").items()
        if isinstance(table, dict)
    }


def remap_image(data: Table, name: str, path: str) -> None:
    table = _table(data, "images").get(name)
    if isinstance(table, dict):
        table["path"] = path


def devices_for_image(data: Table, name: str) -> Iterator[tuple[str, str]]:
    """Yield ``(vm, device)`` for each disk that uses the image."""

    for vm, table in _table(data, "bricks").items():
        if not isinstance(table, dict) or table.get("type") != "qemu":
            continue
        for device, disk in _table(table, "disks").items():
            if isinstance(disk, dict) and disk.get("image") == name:
                yield vm, device
