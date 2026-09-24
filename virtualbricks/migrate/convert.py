# -*- test-case-name: virtualbricks.tests.migrate.test_convert -*-
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
Convert the settings and projects of Virtualbricks 2.1 and older.

A project is rebuilt in a scratch brick factory, value by value, and then
written by the same code that saves projects. A value the old file left out
keeps today's default, so a migrated project behaves as it did.
"""

import os
import re
from collections import defaultdict

from twisted.internet import defer

from virtualbricks import errors, locations
from virtualbricks.config import projectfile, schema, settings
from virtualbricks.migrate import legacy
from virtualbricks.config.schema import Mac
from virtualbricks.tools import random_mac

SETTINGS_DROPPED = frozenset(("alt-term", "cdroms", "kvm", "python"))
BRICK_TYPES = {
    "Capture": "capture",
    "Netemu": "netemu",
    "Qemu": "qemu",
    "Router": "router",
    "Switch": "switch",
    "SwitchWrapper": "switchwrapper",
    "Tap": "tap",
    "TunnelConnect": "tunnelconnect",
    "TunnelListen": "tunnellisten",
    "Wire": "wire",
    "Wirefilter": "netemu",
}
IMAGE_TYPES = frozenset(("Image", "DiskImage"))
DISK_DEVICES = ("hda", "hdb", "hdc", "hdd", "fda", "fdb", "mtdblock")
# Keys that older versions wrote with another name.
RENAMED_KEYS = {"qemu": {f"base{dev}": dev for dev in DISK_DEVICES}}
DROPPED_KEYS = {
    "qemu": {"name": "it repeats the brick name"},
    "router": {"name": "it repeats the brick name"},
    "switchwrapper": {"numports": "a switch wrapper has no ports of its own"},
}
STATE_KEY = re.compile(r"^state(?P<state>\d+)\.(?P<key>\w+)$")
PROBABILITY_KEY = re.compile(
    r"^state(?P<state>\d+)\.probability\[(?P<to>\d+)\]$"
)


class MigrationError(Exception):
    """The project can't be represented in the new format."""


# Settings


def convert_settings(options, filename, report):
    """
    Convert the options read by :func:`legacy.read_settings`.

    Return the new settings and the name of the current project.
    """

    app = settings.AppSettings()
    current_project = locations.DEFAULT_PROJECT
    names = schema.names(settings.AppSettings)
    for key, (text, lineno) in options.items():
        where = legacy.where(filename, lineno)
        if key == "current_project":
            if text:
                current_project = text
            continue
        if key in SETTINGS_DROPPED:
            report.info(f"{key}: not used any more, dropped", where)
            continue
        if key not in names:
            report.warning(f"{key}: unknown setting, dropped", where)
            continue
        kind = schema.kind_of(settings.AppSettings, key)
        try:
            if isinstance(kind, schema.Bool):
                value = legacy.parse_settings_bool(text)
            else:
                value = text
            kind.check(value)
        except ValueError as exc:
            default = kind.format(schema.default(settings.AppSettings, key))
            report.warning(f"{key}: {exc}, using the default {default}", where)
        else:
            setattr(app, key, value)
    _check_programs(app, options, filename, report)
    return app, current_project


def _check_programs(app, options, filename, report):
    checks = (
        ("term", os.path.isfile),
        ("sudo", os.path.isfile),
        ("qemupath", os.path.isdir),
        ("vdepath", os.path.isdir),
    )
    for key, exists in checks:
        path = getattr(app, key)
        if path and os.path.isabs(path) and not exists(path):
            lineno = options.get(key, ("", 0))[1]
            report.warning(
                f"{key}: {path} doesn't exist on this machine, kept",
                legacy.where(filename, lineno),
            )


# Values


def convert_value(kind, text):
    """Convert a value as the old versions wrote it; ValueError if invalid."""

    if isinstance(kind, schema.Bool):
        return legacy.parse_bool(text)
    if isinstance(kind, (schema.Int, schema.Float)):
        number = kind.types[0]
        try:
            return number(text.strip())
        except ValueError:
            raise ValueError(f'"{text}" is not {kind.type_name}') from None
    return text


def _convert_item(kind, text):
    from virtualbricks import console
    from virtualbricks.events import EventAction
    from virtualbricks.bricks.virtualmachine import (
        USB_ID,
        UsbDevice,
        UsbDeviceKind,
    )

    if isinstance(kind, EventAction):
        command, _, rest = text.partition(" ")
        if command == "add":
            return console.VbShellCommand(rest)
        if command == "addsh":
            return console.ShellCommand(rest)
        raise ValueError(f'"{text}" is not an event action')
    if isinstance(kind, UsbDeviceKind):
        if not USB_ID.fullmatch(text):
            raise ValueError(f'"{text}" is not a USB id')
        return UsbDevice(text, "")
    return text


def _apply(config, items, brick_type, label, filename, report):
    """Set the values of the items on a config; report what's dropped."""

    renamed = RENAMED_KEYS.get(brick_type, {})
    dropped = DROPPED_KEYS.get(brick_type, {})
    for item in items:
        where = legacy.where(filename, item.lineno)
        key = renamed.get(item.key, item.key)
        if key in dropped:
            report.info(f"{label} {item.key}: {dropped[key]}, dropped", where)
            continue
        try:
            kind = schema.kind_of(config, key)
        except KeyError:
            report.warning(f"{label} {item.key}: unknown, dropped", where)
            continue
        if isinstance(kind, schema.ListOf):
            _apply_list(config, key, kind, item, label, where, report)
            continue
        try:
            value = convert_value(kind, item.value)
            kind.check(value)
        except ValueError as exc:
            default = kind.format(getattr(config, key))
            report.warning(
                f"{label} {item.key}: {exc}, using the default {default}",
                where,
            )
        else:
            setattr(config, key, value)


def _apply_list(config, key, kind, item, label, where, report):
    # A bad item is dropped, the others are kept.
    try:
        texts = legacy.parse_list(item.value)
    except ValueError as exc:
        default = kind.format(getattr(config, key))
        report.warning(
            f"{label} {item.key}: {exc}, using the default {default}", where
        )
        return
    values = []
    for text in texts:
        try:
            values.append(_convert_item(kind.item, text))
        except ValueError as exc:
            report.warning(f"{label} {item.key}: {exc}, dropped", where)
    setattr(config, key, values)


# Projects


class _Converter:

    def __init__(self, legacy_project, report, directory):
        from virtualbricks.brickfactory import BrickFactory

        self.project = legacy_project
        self.filename = legacy_project.filename
        self.report = report
        self.directory = directory
        self.factory = BrickFactory(defer.Deferred())
        self.image_aliases = {}
        self.seen = defaultdict(dict)

    def where(self, lineno):
        return legacy.where(self.filename, lineno)

    def check_unique(self, kind, section):
        first = self.seen[kind].get(section.name)
        if first is not None:
            raise MigrationError(
                f"{self.where(section.lineno)} {section.label()} defined twice "
                f"(first at line {first})"
            )
        self.seen[kind][section.name] = section.lineno

    def convert(self, project_settings):
        for section in self.project.sections:
            if section.type == "Project":
                self.report.info(
                    f"{section.label()} older project metadata, dropped",
                    self.where(section.lineno),
                )
            elif section.type in IMAGE_TYPES:
                self.check_unique("image", section)
                self.image(section)
            elif section.type == "Event":
                self.check_unique("event", section)
                self.event(section)
            elif section.type in BRICK_TYPES:
                self.check_unique("brick", section)
                self.brick(section)
            else:
                self.report.warning(
                    f"{section.label()} unknown type, dropped",
                    self.where(section.lineno),
                )
        self.sockets()
        self.plugs()
        self.follow_image_aliases()
        return projectfile.document(self.factory, project_settings)

    def image(self, section):
        where = self.where(section.lineno)
        values = {}
        for item in section.items:
            if item.key in ("path", "description"):
                values[item.key] = item.value
            else:
                self.report.warning(
                    f"{section.label()} {item.key}: unknown, dropped",
                    self.where(item.lineno),
                )
        if section.type == "DiskImage":
            self.report.info(f"{section.label()} became an image", where)
        path = values.get("path", "")
        description = values.get("description", "").replace("<nl>", "\n")
        if not path:
            self.report.warning(
                f"{section.label()} has no path, dropped", where
            )
            return
        if not os.path.isabs(path):
            path = os.path.join(self.directory, path)
        if not os.path.exists(path):
            self.report.warning(
                f"{section.label()} {path} not found, kept in the library",
                where,
            )
        try:
            self.factory.new_disk_image(section.name, path, description)
        except errors.ImageAlreadyInUseError:
            same = self.factory.get_image_by_path(os.path.abspath(path))
            self.image_aliases[section.name] = same.get_name()
            self.report.warning(
                f"{section.label()} is the same file as {same.get_name()}; "
                f"its disks now use {same.get_name()}",
                where,
            )
        except errors.InvalidNameError as exc:
            self.report.warning(f"{section.label()} {exc}, dropped", where)

    def event(self, section):
        try:
            event = self.factory.new_event(section.name)
        except errors.InvalidNameError as exc:
            self.report.warning(
                f"{section.label()} {exc}, dropped", self.where(section.lineno)
            )
            return
        _apply(
            event.config,
            section.items,
            "event",
            section.label(),
            self.filename,
            self.report,
        )

    def brick(self, section):
        brick_type = BRICK_TYPES[section.type]
        where = self.where(section.lineno)
        try:
            brick = self.factory.new_brick(brick_type, section.name)
        except errors.InvalidNameError as exc:
            self.report.warning(f"{section.label()} {exc}, dropped", where)
            return
        if section.type == "Wirefilter":
            self.report.info(f"{section.label()} became netemu", where)
        if brick_type == "netemu":
            self.netemu(brick, section)
        else:
            _apply(
                brick.config,
                section.items,
                brick_type,
                section.label(),
                self.filename,
                self.report,
            )

    def netemu(self, brick, section):
        label = section.label()
        flat, states, count = [], [], 1
        for item in section.items:
            if item.key in ("states", "transperiod"):
                try:
                    value = int(item.value)
                    if value < 1:
                        raise ValueError
                except ValueError:
                    self.report.warning(
                        f"{label} {item.key}: {item.value!r} is not a positive "
                        "integer, ignored",
                        self.where(item.lineno),
                    )
                    continue
                if item.key == "states":
                    count = value
                else:
                    brick.transPeriod = value
            elif STATE_KEY.match(item.key) or PROBABILITY_KEY.match(item.key):
                states.append(item)
            else:
                flat.append(item)
        _apply(brick.config, flat, "netemu", label, self.filename, self.report)
        markov = brick.markov_manager
        for index in range(1, count):
            markov.add(index)
        for item in states:
            self.state_item(markov, item, count, label)
        for state in markov.states:
            state.pon_vbevent = markov.states[0].pon_vbevent
            state.poff_vbevent = markov.states[0].poff_vbevent

    def state_item(self, markov, item, count, label):
        where = self.where(item.lineno)
        match = PROBABILITY_KEY.match(item.key)
        if match:
            source, target = int(match["state"]), int(match["to"])
            if source >= count or target >= count or source == target:
                self.report.warning(
                    f"{label} {item.key}: no such transition, ignored", where
                )
                return
            try:
                markov.weights[source][target] = float(item.value)
            except ValueError:
                self.report.warning(
                    f"{label} {item.key}: {item.value!r} is not a number, "
                    "ignored",
                    where,
                )
            return
        match = STATE_KEY.match(item.key)
        index = int(match["state"])
        if index >= count:
            self.report.warning(
                f"{label} {item.key}: no such state, ignored", where
            )
            return
        state_item = legacy.Item(match["key"], item.value, item.lineno)
        _apply(
            markov.states[index],
            [state_item],
            "netemu",
            f"{label} state {index}",
            self.filename,
            self.report,
        )

    def mac(self, link):
        try:
            Mac().check(link.mac)
            if link.mac:
                return link.mac
        except ValueError:
            pass
        mac = random_mac()
        self.report.warning(
            f'"{link.mac}" is not a MAC address, using {mac}',
            self.where(link.lineno),
        )
        return mac

    def sockets(self):
        for link in self.project.links:
            if link.kind != "sock":
                continue
            where = self.where(link.lineno)
            vm = self.factory.get_brick_by_name(link.owner)
            if vm is None or vm.connections != "nics":
                self.report.warning(
                    f'socket card of "{link.owner}", which is not a virtual '
                    "machine, dropped",
                    where,
                )
                continue
            prefix = f"{link.owner}_"
            name = link.socket
            if name.startswith(prefix):
                name = name[len(prefix) :]
            if not projectfile.SOCKET_NAME.fullmatch(name):
                self.report.warning(
                    f'"{link.socket}" is not a socket name, using a default',
                    where,
                )
                name = None
            model = link.model or projectfile.DEFAULT_MODEL
            vm.add_sock(self.mac(link), model, name)

    def plugs(self):
        used = defaultdict(int)
        for link in self.project.links:
            if link.kind != "link":
                continue
            where = self.where(link.lineno)
            brick = self.factory.get_brick_by_name(link.owner)
            if brick is None:
                self.report.warning(
                    f'link of "{link.owner}", which does not exist, dropped',
                    where,
                )
                continue
            sock = None
            if link.socket:
                sock = self.factory.get_sock_by_name(link.socket)
                if sock is None:
                    self.report.warning(
                        f'no socket "{link.socket}", left unconnected', where
                    )
            if brick.connections == "nics":
                model = link.model or projectfile.DEFAULT_MODEL
                brick.add_plug(sock, self.mac(link), model)
                continue
            index = used[link.owner]
            used[link.owner] += 1
            if index >= len(brick.plugs):
                self.report.warning(
                    f'"{link.owner}" has no plug left, link dropped', where
                )
            elif sock is not None:
                brick.plugs[index].connect(sock)

    def follow_image_aliases(self):
        for brick in self.factory.bricks:
            if brick.connections != "nics":
                continue
            for dev in DISK_DEVICES:
                name = getattr(brick.config, dev)
                if name in self.image_aliases:
                    setattr(brick.config, dev, self.image_aliases[name])


def convert_project(legacy_project, project_settings, report, directory):
    """
    Return the data of the new project file and the number of bricks.

    Raise MigrationError if the project can't be represented.
    """

    converter = _Converter(legacy_project, report, directory)
    data = converter.convert(project_settings)
    return data, len(converter.factory.bricks)
