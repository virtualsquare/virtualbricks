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
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING, TypeAlias, TypedDict, cast

from virtualbricks import errors, tools
from virtualbricks.config import schema, settings, tomlfile
from virtualbricks.config.schema import Choice, Mac, Path, Str

if TYPE_CHECKING:
    from virtualbricks.brickfactory import BrickFactory
    from virtualbricks.bricks import Brick
    from virtualbricks.bricks.virtualmachine import (
        VirtualMachine,
        VMPlug,
        VMSock,
    )
    from virtualbricks.config.report import Report
    from virtualbricks.config.settings import ProjectSettings
    from virtualbricks.config.tomlfile import Table, Value
    from virtualbricks.bricks.plug import Plug
    from virtualbricks.bricks.sock import Sock

FORMAT = 1
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

# Steps that rewrite the data of format N into the data of format N + 1.
UPGRADES: dict[int, Callable[[Table, Report], Table]] = {}


class ProjectFormatError(Exception):
    """The project file can't be read: it's not TOML or a newer format."""


@schema.define
class ImageTable:

    path: str = schema.field(Path(), default="")
    description: str = schema.field(Str(), default="")


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


def document(
    factory: BrickFactory, project_settings: ProjectSettings
) -> Table:
    """Return the data of the project file for the bricks of factory."""

    data: Table = {"format": FORMAT, "settings": schema.dump(project_settings)}
    images: Table = {
        image.get_name(): {
            "path": image.get_path(),
            "description": image.get_description(),
        }
        for image in factory.iter_disk_images()
    }
    if images:
        data["images"] = images
    events: Table = {
        event.get_name(): schema.dump(event.config)
        for event in factory.iter_events()
    }
    if events:
        data["events"] = events
    bricks: Table = {
        brick.get_name(): brick_table(brick) for brick in factory.bricks
    }
    if bricks:
        data["bricks"] = bricks
    return data


def save(
    factory: BrickFactory, project_settings: ProjectSettings, path: str
) -> None:
    tomlfile.dump(document(factory, project_settings), path)


def create(path: str, project_settings: ProjectSettings) -> None:
    """Write the project file of a new, empty project."""

    tomlfile.dump(
        {"format": FORMAT, "settings": schema.dump(project_settings)}, path
    )


# Reading


def upgrade(data: Table, report: Report) -> Table:
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
        sock = factory.get_sock_by_name(f"{brick_name}_{socket_name}")
        if sock is not None and sock.brick.name == brick_name:
            return sock
        return None
    brick = factory.get_brick_by_name(target)
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
        nic["mac"] = tools.random_mac()
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
                sock = factory.get_sock_by_name(HOSTONLY)
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
        image = schema.load(ImageTable, table, report, where)
        path = image.path
        if not path:
            report.warning("has no path, image dropped", where)
            continue
        if not os.path.isabs(path):
            path = os.path.join(directory, path)
        if not os.path.exists(path):
            report.warning(f"{path} not found, kept in the library", where)
        try:
            factory.new_disk_image(name, path, image.description)
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
        event.config = schema.load(EventConfig, table, report, where)


def _read_bricks(factory: BrickFactory, data: Table, report: Report) -> None:
    connections: list[tuple[Brick, Targets, str]] = []
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
        brick.set_restore(True)
        ignore = {"type"} | CONNECTION_KEYS[brick.connections]
        brick.load_config_table(table, report, where, ignore)
        targets = _read_connections(brick, table, report, where)
        connections.append((brick, targets, where))
    # Connect once every socket exists.
    for brick, targets, where in connections:
        _connect(factory, brick, targets, report, where)
        brick.set_restore(False)


def _check_references(factory: BrickFactory, report: Report) -> None:
    lookups: dict[str, Callable[[str], object]] = {
        "event": factory.get_event_by_name,
        "image": factory.get_image_by_name,
    }
    objects = [("bricks", brick) for brick in factory.bricks]
    objects += [("events", event) for event in factory.iter_events()]
    for kind, obj in objects:
        for name, target, value in schema.references(obj.config):
            if lookups[target](value) is None:
                where = f"{kind}.{obj.get_name()}.{name}"
                report.warning(f'no {target} named "{value}"', where)


def _read_settings(data: Table, report: Report) -> ProjectSettings:
    app_values = schema.dump(settings.new_project_settings())
    table = data.get("settings")
    if not isinstance(table, dict):
        problem = "missing" if table is None else "is not a table"
        report.warning(f"{problem}, using the app settings", "settings")
        table = {}
    elif table:
        for key in app_values.keys() - table.keys():
            value = schema.kind_of(settings.ProjectSettings, key).format(
                app_values[key]
            )
            report.warning(
                f"missing, using the app setting {value}", f"settings.{key}"
            )
    return schema.load(
        settings.ProjectSettings, {**app_values, **table}, report, "settings"
    )


def restore(
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


def read(path: str) -> Table:
    """Return the data of a project file; ProjectFormatError if not TOML."""

    try:
        return tomlfile.load(path)
    except tomlfile.DecodeError as exc:
        raise ProjectFormatError(f"{path}: {exc}") from None


def load(factory: BrickFactory, path: str, report: Report) -> ProjectSettings:
    """Read a project file into factory; return the project's settings."""

    data = upgrade(read(path), report)
    return restore(factory, data, report, os.path.dirname(path))


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
