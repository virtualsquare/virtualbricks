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

from __future__ import annotations

import os
import re
from collections import defaultdict
from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING

from twisted.internet import defer

from virtualbricks import errors, locations
from virtualbricks.config.projectfile import (
    DEFAULT_MODEL,
    SOCKET_NAME,
    describe_action,
    old_action,
    project_document,
)
from virtualbricks.config.settings import (
    PROJECT_KEYS,
    AppSettings,
    ProjectSettings,
)
from virtualbricks.config.schema import (
    Bool,
    Float,
    Int,
    Kind,
    ListOf,
    Mac,
    field_default,
    field_names,
    kind_of,
)
from virtualbricks.migrate import legacy
from virtualbricks.nic import random_mac

if TYPE_CHECKING:  # pragma: no cover
    from virtualbricks.brickfactory import BrickFactory
    from virtualbricks.bricks import Brick
    from virtualbricks.bricks.netemu import MarkovConfig, Netemu
    from virtualbricks.config.report import Report
    from virtualbricks.config.settings import SettingValue
    from virtualbricks.config.tomlfile import Table
    from virtualbricks.bricks.sock import Sock

SETTINGS_DROPPED = frozenset(("alt-term", "cdroms", "kvm", "python", "sudo"))
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
# The names of 2.1 and older, and those of today: the keys of every brick,
# and those of each type.
EVERY_BRICK = {"pon_vbevent": "on_start", "poff_vbevent": "on_stop"}
RENAMED_KEYS = {
    "qemu": {
        **{f"base{dev}": f"{dev}_image" for dev in DISK_DEVICES},
        **{dev: f"{dev}_image" for dev in DISK_DEVICES},
        **{f"private{dev}": f"{dev}_private" for dev in DISK_DEVICES},
        "argv0": "qemu_program",
        "machine": "machine_type",
        "cpu": "cpu_model",
        "kvm": "use_kvm",
        "smp": "cpus",
        "ram": "memory",
        "kvmsm": "use_kvm_shadow_memory",
        "kvmsmem": "kvm_shadow_memory",
        "boot": "boot_order",
        "snapshot": "forget_disk_changes",
        "use_virtio": "virtio_disks",
        "cdrom": "cdrom_image",
        "device": "cdrom_device",
        "novga": "headless",
        "vga": "standard_vga",
        "vnc": "use_vnc",
        "vncN": "vnc_display",
        "sdl": "sdl_window",
        "soundhw": "sound_card",
        "usbmode": "use_usb",
        "usbdevlist": "usb_devices",
        "keyboard": "keyboard_layout",
        "rtc": "clock_local_time",
        "tdf": "clock_drift_fix",
        "serial": "serial_socket",
        "kernelenbl": "use_kernel",
        "initrdenbl": "use_initrd",
        "kopt": "kernel_command_line",
        "gdb": "use_gdb",
        "gdbport": "gdb_port",
    },
    "switch": {
        "numports": "ports",
        "hub": "hub_mode",
        "fstp": "fast_spanning_tree",
    },
    "switchwrapper": {"path": "socket_path"},
    "tap": {
        "mode": "address_mode",
        "ip": "ip_address",
        "nm": "netmask",
        "gw": "gateway",
    },
    "capture": {"iface": "interface"},
    "tunnellisten": {"port": "listen_port"},
    "tunnelconnect": {
        "host": "server_host",
        "port": "server_port",
        "localport": "local_port",
    },
    # the keys of a state
    "netemu": {
        "bandwidthr": "bandwidth_right_to_left",
        "bandwidthsymm": "bandwidth_symmetric",
        "delayr": "delay_right_to_left",
        "delaysymm": "delay_symmetric",
        "chanbufsize": "buffer_size",
        "chanbufsizer": "buffer_size_right_to_left",
        "chanbufsizesymm": "buffer_size_symmetric",
        "lossr": "loss_right_to_left",
        "losssymm": "loss_symmetric",
    },
}
# The keys of a virtual machine that became others: the two switches of the
# CD-ROM are one choice, where the image wins as it did, and "*" in noacpi
# turned ACPI off.
CDROM_SWITCHES = {"cdromen": "image", "deviceen": "device"}
NOACPI = "noacpi"
# The program an empty argv0 ran.
EMPTY_ARGV0 = "qemu-system-x86_64"
SETTINGS_RENAMED = {
    "term": "terminal",
    "ksm": "kernel_samepage_merging",
    "systray": "tray_icon",
    "show_missing": "warn_missing_programs",
    "erroronloop": "log_link_loops",
    "femaleplugs": "allow_female_plugs",
    "qemupath": "qemu_path",
    "vdepath": "vde_path",
}
DROPPED_KEYS = {
    "qemu": {
        "name": "it repeats the brick name",
        "loadvm": "a machine resumes when it's started so, not by a key",
        "stdout": "nothing read it",
        "portrait": "QEMU 9 and later have no such option",
    },
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


def convert_settings(
    options: legacy.Options, filename: str, report: Report
) -> tuple[AppSettings, ProjectSettings, str]:
    """
    Convert the options read by :func:`legacy.read_settings`.

    Return the settings of the application, the settings of the projects,
    which the migrated projects take, and the name of the current project.
    """

    app = AppSettings()
    project = ProjectSettings()
    current_project = locations.DEFAULT_PROJECT
    app_names = field_names(AppSettings)
    for key, (text, lineno) in options.items():
        where = legacy.where(filename, lineno)
        if key == "current_project":
            if text:
                current_project = text
            continue
        if key in SETTINGS_DROPPED:
            report.info(f"{key}: not used any more, dropped", where)
            continue
        if key == "cowfmt":
            # private copies are always qcow2 now (page 23 S7)
            if text != "qcow2":
                report.info(
                    f"{key}: private copies are always qcow2 now, dropped",
                    where,
                )
            continue
        name = SETTINGS_RENAMED.get(key, key)
        target: AppSettings | ProjectSettings
        if name in PROJECT_KEYS:
            target = project
        elif name in app_names:
            target = app
        else:
            report.warning(f"{key}: unknown setting, dropped", where)
            continue
        kind = kind_of(target, name)
        value: SettingValue
        try:
            if isinstance(kind, Bool):
                value = legacy.parse_settings_bool(text)
            else:
                value = text
            kind.check(value)
        except ValueError as exc:
            default = kind.format(field_default(target, name))
            report.warning(f"{key}: {exc}, using the default {default}", where)
        else:
            setattr(target, name, value)
    _check_programs(app, project, options, filename, report)
    return app, project, current_project


def _check_programs(
    app: AppSettings,
    project: ProjectSettings,
    options: legacy.Options,
    filename: str,
    report: Report,
) -> None:
    checks: tuple[tuple[object, str, Callable[[str], bool]], ...] = (
        (app, "term", os.path.isfile),
        (project, "qemupath", os.path.isdir),
        (project, "vdepath", os.path.isdir),
    )
    for settings, key, exists in checks:
        path = getattr(settings, SETTINGS_RENAMED[key])
        if path and os.path.isabs(path) and not exists(path):
            lineno = options.get(key, ("", 0))[1]
            report.warning(
                f"{key}: {path} doesn't exist on this machine, kept",
                legacy.where(filename, lineno),
            )


# Values


def convert_value(kind: Kind[object], text: str) -> object:
    """Convert a value as the old versions wrote it; ValueError if invalid."""

    if isinstance(kind, Bool):
        return legacy.parse_bool(text)
    if isinstance(kind, (Int, Float)):
        number = kind.types[0]
        try:
            return number(text.strip())
        except ValueError:
            raise ValueError(f'"{text}" is not {kind.type_name}') from None
    return text


def _convert_item(kind: Kind[object], text: str) -> object:
    from virtualbricks.bricks.eventaction import (
        ConsoleAction,
        EventAction,
        ShellAction,
    )
    from virtualbricks.bricks.virtualmachine import (
        USB_ID,
        UsbDevice,
        UsbDeviceKind,
    )

    if isinstance(kind, EventAction):
        command, _, rest = text.partition(" ")
        if command == "add":
            # a command of the old console, which commands() reads
            return ConsoleAction(rest)
        if command == "addsh":
            return ShellAction(rest)
        raise ValueError(f'"{text}" is not an event action')
    if isinstance(kind, UsbDeviceKind):
        if not USB_ID.fullmatch(text):
            raise ValueError(f'"{text}" is not a USB id')
        return UsbDevice(text, "")
    return text


def _apply(
    instance: object,
    items: Iterable[legacy.Item],
    brick_type: str,
    label: str,
    filename: str,
    report: Report,
) -> None:
    """Set the values of the items on an instance; report what's dropped."""

    renamed = {**EVERY_BRICK, **RENAMED_KEYS.get(brick_type, {})}
    dropped = DROPPED_KEYS.get(brick_type, {})
    for item in items:
        where = legacy.where(filename, item.lineno)
        key = renamed.get(item.key, item.key)
        if key in dropped:
            report.info(f"{label} {item.key}: {dropped[key]}, dropped", where)
            continue
        try:
            kind = kind_of(instance, key)
        except KeyError:
            report.warning(f"{label} {item.key}: unknown, dropped", where)
            continue
        if isinstance(kind, ListOf):
            _apply_list(instance, key, kind, item, label, where, report)
            continue
        try:
            value = convert_value(kind, item.value)
            kind.check(value)
        except ValueError as exc:
            default = kind.format(getattr(instance, key))
            report.warning(
                f"{label} {item.key}: {exc}, using the default {default}",
                where,
            )
        else:
            setattr(instance, key, value)


def _apply_list(
    instance: object,
    key: str,
    kind: ListOf[object],
    item: legacy.Item,
    label: str,
    where: str,
    report: Report,
) -> None:
    # A bad item is dropped, the others are kept.
    try:
        texts = legacy.parse_list(item.value)
    except ValueError as exc:
        default = kind.format(getattr(instance, key))
        report.warning(
            f"{label} {item.key}: {exc}, using the default {default}", where
        )
        return
    values: list[object] = []
    for text in texts:
        try:
            values.append(_convert_item(kind.item, text))
        except ValueError as exc:
            report.warning(f"{label} {item.key}: {exc}, dropped", where)
    setattr(instance, key, values)


# Projects


class _Converter:

    def __init__(
        self,
        legacy_project: legacy.LegacyProject,
        report: Report,
        directory: str,
    ) -> None:
        from virtualbricks.brickfactory import BrickFactory

        self.project = legacy_project
        self.filename = legacy_project.filename
        self.report = report
        self.directory = directory
        self.factory = BrickFactory(defer.Deferred())
        # the images that are the same file as another, and that other
        self.image_aliases: dict[str, str] = {}
        # the line of each name, by kind
        self.seen: defaultdict[str, dict[str, int]] = defaultdict(dict)

    def where(self, lineno: int) -> str:
        return legacy.where(self.filename, lineno)

    def check_unique(self, kind: str, section: legacy.Section) -> None:
        first = self.seen[kind].get(section.name)
        if first is not None:
            raise MigrationError(
                f"{self.where(section.lineno)} {section.label()} defined twice "
                f"(first at line {first})"
            )
        self.seen[kind][section.name] = section.lineno

    def convert(self, project_settings: ProjectSettings) -> Table:
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
        self.commands()
        self.sockets()
        self.plugs()
        self.follow_image_aliases()
        return project_document(self.factory, project_settings)

    def image(self, section: legacy.Section) -> None:
        where = self.where(section.lineno)
        values: dict[str, str] = {}
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
            self.factory.new_image(section.name, path, description)
        except errors.ImageAlreadyInUseError:
            same = self.factory.get_image_by_path(os.path.abspath(path))
            self.image_aliases[section.name] = same.name
            self.report.warning(
                f"{section.label()} is the same file as {same.name}; "
                f"its disks now use {same.name}",
                where,
            )
        except errors.InvalidNameError as exc:
            self.report.warning(f"{section.label()} {exc}, dropped", where)

    def event(self, section: legacy.Section) -> None:
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

    def brick(self, section: legacy.Section) -> None:
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
        elif brick_type == "qemu":
            self.qemu(brick, section)
        else:
            _apply(
                brick.config,
                section.items,
                brick_type,
                section.label(),
                self.filename,
                self.report,
            )

    def netemu(self, brick: Netemu, section: legacy.Section) -> None:
        label = section.label()
        flat: list[legacy.Item] = []
        states: list[legacy.Item] = []
        count = 1
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
        from virtualbricks.bricks.netemu import BRICK_KEYS

        # the events and the icon are the brick's, the same in every state
        for state in markov.states:
            for name in BRICK_KEYS:
                setattr(state, name, getattr(markov.states[0], name))

    def qemu(self, brick: Brick, section: legacy.Section) -> None:
        """The keys of a machine, with those that became others."""

        label = section.label()
        plain: list[legacy.Item] = []
        switches: dict[str, legacy.Item] = {}
        for item in section.items:
            if item.key in CDROM_SWITCHES or item.key == NOACPI:
                switches[item.key] = item
            elif item.key == "argv0" and not item.value.strip():
                brick.config.qemu_program = EMPTY_ARGV0
                self.report.info(
                    f"{label} argv0: empty, which ran {EMPTY_ARGV0}",
                    self.where(item.lineno),
                )
            else:
                plain.append(item)
        _apply(brick.config, plain, "qemu", label, self.filename, self.report)
        for key, choice in CDROM_SWITCHES.items():
            item = switches.get(key)
            if item is not None and legacy.parse_bool(item.value):
                brick.config.cdrom = choice
                break
        item = switches.get(NOACPI)
        if item is not None and item.value.strip():
            brick.config.acpi = False

    def state_item(
        self, markov: MarkovConfig, item: legacy.Item, count: int, label: str
    ) -> None:
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
        # netemu() kept only the keys of a state or of a probability
        assert match is not None
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

    def mac(self, link: legacy.Link) -> str:
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

    def sockets(self) -> None:
        for link in self.project.links:
            if link.kind != "sock":
                continue
            where = self.where(link.lineno)
            vm = self.factory.get_brick(link.owner)
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
            valid = SOCKET_NAME.fullmatch(name) is not None
            if not valid:
                self.report.warning(
                    f'"{link.socket}" is not a socket name, using a default',
                    where,
                )
            model = link.model or DEFAULT_MODEL
            # None gives the card its default name
            vm.add_sock(self.mac(link), model, name if valid else None)

    def plugs(self) -> None:
        # the plugs used by each brick, in order
        used: defaultdict[str, int] = defaultdict(int)
        for link in self.project.links:
            if link.kind != "link":
                continue
            where = self.where(link.lineno)
            brick = self.factory.get_brick(link.owner)
            if brick is None:
                self.report.warning(
                    f'link of "{link.owner}", which does not exist, dropped',
                    where,
                )
                continue
            sock: Sock | None = None
            if link.socket:
                sock = self.factory.get_sock(link.socket)
                if sock is None:
                    self.report.warning(
                        f'no socket "{link.socket}", left unconnected', where
                    )
            if brick.connections == "nics":
                model = link.model or DEFAULT_MODEL
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

    def follow_image_aliases(self) -> None:
        for brick in self.factory.bricks:
            if brick.connections != "nics":
                continue
            for dev in DISK_DEVICES:
                key = f"{dev}_image"
                name = getattr(brick.config, key)
                if name in self.image_aliases:
                    setattr(brick.config, key, self.image_aliases[name])

    def commands(self) -> None:
        """
        Give the commands of the events the names of today, and the words
        of the console of today: start and stop become actions.
        """

        from virtualbricks.bricks.eventaction import ConsoleAction, EventAction

        bricks = {brick.name for brick in self.factory.bricks}
        events = {event.name for event in self.factory.events}
        for event in self.factory.events:
            where = self.where(self.seen["event"][event.name])
            actions: list[object] = []
            for action in event.config.actions:
                if isinstance(action, ConsoleAction):
                    old = action.command
                    text = convert_command(self.factory, old)
                    table, read = old_action(text, bricks, events)
                    if read:
                        self.report.info(
                            f"[Event:{event.name}] {old!r} is now"
                            f" {describe_action(table)}",
                            where,
                        )
                    else:
                        self.report.warning(
                            f"[Event:{event.name}] {old!r} is a command"
                            " of the old console, which the console may not"
                            " read",
                            where,
                        )
                    action = EventAction().from_data(table, self.report, where)
                actions.append(action)
            event.config.actions = actions


def _convert_setting(brick_type: str, config: object, word: str) -> list[str]:
    """
    A key=value of the config command, with the name of today.

    What became another key is converted, what's dropped is left out, and a
    boolean written as the old versions did, "*" for true, is true or false.
    """

    key, sep, value = word.partition("=")
    if not sep:
        return [word]
    if key in DROPPED_KEYS.get(brick_type, {}):
        return []
    if brick_type == "qemu":
        if key in CDROM_SWITCHES:
            choice = (
                CDROM_SWITCHES[key] if legacy.parse_bool(value) else "none"
            )
            return [f"cdrom={choice}"]
        if key == NOACPI:
            return ["acpi=false" if value.strip() else "acpi=true"]
        if key == "argv0" and not value.strip():
            return [f"qemu_program={EMPTY_ARGV0}"]
    name = {**EVERY_BRICK, **RENAMED_KEYS.get(brick_type, {})}.get(key, key)
    try:
        kind = kind_of(config, name)
    except KeyError:
        # the brick doesn't know it: the event says so when it runs
        return [word]
    if isinstance(kind, Bool):
        value = "true" if legacy.parse_bool(value) else "false"
    return [f"{name}={value}"]


def convert_command(factory: BrickFactory, text: str) -> str:
    """
    A console command of an event, with the names of today.

    Only "BRICK config KEY=VALUE..." changes, for a brick of the project;
    anything else stays as it is.
    """

    words = text.split()
    if len(words) < 3 or words[1] != "config":
        return text
    brick = factory.get_brick(words[0])
    if brick is None:
        return text
    brick_type = brick.get_type().lower()
    settings = [
        converted
        for word in words[2:]
        for converted in _convert_setting(brick_type, brick.config, word)
    ]
    return " ".join(words[:2] + settings)


def convert_project(
    legacy_project: legacy.LegacyProject,
    project_settings: ProjectSettings,
    report: Report,
    directory: str,
) -> tuple[Table, int]:
    """
    Return the data of the new project file and the number of bricks.

    Raise MigrationError if the project can't be represented.
    """

    converter = _Converter(legacy_project, report, directory)
    data = converter.convert(project_settings)
    return data, len(list(converter.factory.bricks))
