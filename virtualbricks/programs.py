# -*- test-case-name: virtualbricks.tests.test_programs -*-
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
What the installed programs of the bricks can do.

QEMU changes from one version to the next, and each distribution builds it its
own way: an option goes, a display or a network backend is left out. So
Virtualbricks asks the program itself, with the questions of
``QEMU_QUESTIONS``: its version, its options, its machines, CPU models,
devices, displays, audio drivers, network backends and accelerators. The
answers are kept for the session, for each program file: a program that an
update replaces is asked again.

The VDE programs change little. What matters is which of them are installed
and, for a Netemu, the options of ``vde-netemu`` or of ``wirefilter``.

Nothing here imports GTK.
"""

from __future__ import annotations

import locale
import os
import re
from collections.abc import Callable, Iterable, Mapping
from typing import Any, Generic, NamedTuple, TypeVar

import attr
from twisted.internet import defer
from twisted.internet.utils import getProcessOutputAndValue
from twisted.python.failure import Failure

__all__ = [
    "PACKAGES",
    "QEMU_QUESTIONS",
    "VDE_PROGRAMS",
    "VDE_QUESTIONS",
    "Answer",
    "Device",
    "Entry",
    "Missing",
    "ProgramError",
    "Programs",
    "QemuInfo",
    "VdeInfo",
    "Version",
    "decode_output",
    "find_program",
    "machine_question",
    "missing_programs",
    "parse_machine_properties",
    "programs",
    "qemu_info",
    "qemu_programs",
]

# The questions asked to a QEMU program, by the name of their answer.
QEMU_QUESTIONS: dict[str, tuple[str, ...]] = {
    "version": ("--version",),
    "options": ("-help",),
    "machines": ("-machine", "help"),
    "cpus": ("-cpu", "help"),
    "devices": ("-device", "help"),
    "displays": ("-display", "help"),
    "audio_drivers": ("-audiodev", "help"),
    "netdevs": ("-netdev", "help"),
    "accelerators": ("-accel", "help"),
}

# The VDE programs whose options matter, and how to ask for them.
VDE_QUESTIONS: dict[str, tuple[str, ...]] = {
    "vde-netemu": ("--help",),
    "wirefilter": ("--help",),
}

# The programs of the bricks, and the package of Debian and Ubuntu that has
# each; None for a program that no distribution ships.
PACKAGES: dict[str, str | None] = {
    "vde_switch": "vde2",
    "vde_plug": "vde2",
    "dpipe": "vde2",
    "vde_plug2tap": "vde2",
    "vde_pcapplug": "vde2",
    "wirefilter": "vde2",
    "vdeterm": "vde2",
    "unixterm": "vde2",
    "vde_cryptcab": "vde2-cryptcab",
    "vde-netemu": "vde-netemu",
    "vde_router": None,
    "qemu-img": "qemu-utils",
    "qemu-system-x86_64": "qemu-system-x86",
    "qemu-system-i386": "qemu-system-x86",
}
VDE_PROGRAMS = tuple(name for name in PACKAGES if not name.startswith("qemu"))


def machine_question(machine: str) -> tuple[str, ...]:
    """The question that lists the properties of a machine type."""

    return ("-machine", f"{machine},help")


class ProgramError(Exception):
    """A program is missing, or doesn't answer as expected."""


class Version(NamedTuple):

    major: int
    minor: int
    micro: int = 0

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.micro}"


class Answer(NamedTuple):
    """What a program wrote, and how it exited."""

    out: str
    err: str = ""
    status: int = 0


@attr.define(frozen=True)
class Entry:
    """A machine type or a CPU model, and what QEMU says of it."""

    name: str
    description: str = ""


@attr.define(frozen=True)
class Device:

    name: str
    # the heading of the device in "-device help", as "Network devices"
    category: str = ""
    bus: str = ""
    alias: str = ""
    description: str = ""


@attr.define(frozen=True)
class QemuInfo:
    """What a QEMU program says it has."""

    path: str
    version: Version
    options: frozenset[str]
    machines: tuple[Entry, ...]
    # the machine type that QEMU uses when none is given
    default_machine: str
    cpus: tuple[Entry, ...]
    devices: tuple[Device, ...]
    displays: frozenset[str]
    # None when the program can't list them, as QEMU 6.2
    audio_drivers: frozenset[str] | None
    netdevs: frozenset[str]
    accelerators: frozenset[str]

    def has_machine(self, name: str) -> bool:
        return any(entry.name == name for entry in self.machines)

    def has_cpu(self, name: str) -> bool:
        return any(entry.name == name for entry in self.cpus)

    def device(self, name: str) -> Device | None:
        """The device of that name or alias, as the card ac97 for AC97."""

        for device in self.devices:
            if name in (device.name, device.alias):
                return device
        return None


@attr.define(frozen=True)
class VdeInfo:
    """Which VDE programs there are, and the options of some of them."""

    folder: str
    # the programs found, by name: their path
    programs: Mapping[str, str]
    # the options of the programs of VDE_QUESTIONS, among those found
    options: Mapping[str, frozenset[str]]


@attr.define(frozen=True)
class Missing:
    """A program that isn't installed, and the package that has it."""

    program: str
    package: str | None

    def __str__(self) -> str:
        if self.package is None:
            return self.program
        return f"{self.program} ({self.package})"


# Reading the answers


_VERSION = re.compile(r"\bversion (\d+)\.(\d+)(?:\.(\d+))?")
_OPTION = re.compile(r"^(-[\w-]+)(?: or (-[\w-]+))?")
_DEVICE = re.compile(r'^name "([^"]+)"(.*)$')
_DEVICE_FIELD = re.compile(r', (\w+) (?:"([^"]*)"|([^,]*))')
_PROPERTY = re.compile(r"^\s+([\w.-]+)=")
_VDE_OPTION = re.compile(r"(?:^|[\s|])(--?[A-Za-z][\w-]*)")
_DEFAULT = "(default)"


def _items(text: str) -> list[str]:
    """The lines under the first heading, up to a blank line."""

    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.endswith(":"):
            break
    else:
        return []
    items = []
    for line in lines[index + 1 :]:
        if not line.strip():
            break
        # the messages of a module left out, as QEMU 6.2 writes them
        if not line.startswith("qemu:"):
            items.append(line)
    return items


def parse_version(text: str) -> Version:
    """The version in ``--version``, as "QEMU emulator version 10.0.11"."""

    match = _VERSION.search(text)
    if match is None:
        first = text.strip().splitlines()[0] if text.strip() else "nothing"
        raise ProgramError(f"no version in {first!r}")
    major, minor, micro = match.groups()
    return Version(int(major), int(minor), int(micro or 0))


def parse_options(text: str) -> frozenset[str]:
    """The options of ``-help``, as "-machine" and "-no-acpi"."""

    options: set[str] = set()
    for line in text.splitlines():
        match = _OPTION.match(line)
        if match is not None:
            options.update(filter(None, match.groups()))
    return frozenset(options)


def parse_names(text: str) -> frozenset[str]:
    """The names listed by the help of a display, netdev or accelerator."""

    return frozenset(line.split()[0] for line in _items(text))


def parse_machines(text: str) -> tuple[tuple[Entry, ...], str]:
    """The machine types of ``-machine help``, and the default one."""

    entries = []
    default = ""
    for line in _items(text):
        name, _, description = line.strip().partition(" ")
        description = description.strip()
        if description.endswith(_DEFAULT):
            default = name
            description = description[: -len(_DEFAULT)].rstrip()
        entries.append(Entry(name, description))
    return tuple(entries), default


def parse_cpus(text: str) -> tuple[Entry, ...]:
    """
    The CPU models of ``-cpu help``.

    Up to QEMU 8 a line starts with the architecture, as "x86 486"; from
    QEMU 9 it's indented instead.
    """

    entries = []
    for line in _items(text):
        if not line[:1].isspace():
            line = line.partition(" ")[2]
        name, _, description = line.strip().partition(" ")
        entries.append(Entry(name, description.strip()))
    return tuple(entries)


def parse_devices(text: str) -> tuple[Device, ...]:
    """The devices of ``-device help``, each under its heading."""

    devices: dict[str, Device] = {}
    category = ""
    for line in text.splitlines():
        match = _DEVICE.match(line)
        if match is None:
            if line.endswith(":"):
                category = line[:-1]
            continue
        name, rest = match.groups()
        fields = {
            key: quoted or plain.strip()
            for key, quoted, plain in _DEVICE_FIELD.findall(rest)
        }
        # a device can be listed under two headings: the first one wins
        devices.setdefault(
            name,
            Device(
                name,
                category,
                fields.get("bus", ""),
                fields.get("alias", ""),
                fields.get("desc", ""),
            ),
        )
    return tuple(devices.values())


def parse_machine_properties(text: str) -> frozenset[str]:
    """The properties of ``-machine TYPE,help``, as "acpi"."""

    return frozenset(
        match.group(1)
        for match in map(_PROPERTY.match, text.splitlines())
        if match is not None
    )


def parse_vde_options(text: str) -> frozenset[str]:
    """The options in the help of a VDE program, as "--nofifo" and "-N"."""

    return frozenset(
        option
        for line in text.splitlines()
        for option in _VDE_OPTION.findall(line)
    )


def qemu_info(path: str, answers: Mapping[str, Answer]) -> QemuInfo:
    """What the answers to QEMU_QUESTIONS say about the program."""

    machines, default = parse_machines(answers["machines"].out)
    audio = answers["audio_drivers"]
    return QemuInfo(
        path=path,
        version=parse_version(answers["version"].out),
        options=parse_options(answers["options"].out),
        machines=machines,
        default_machine=default,
        cpus=parse_cpus(answers["cpus"].out),
        devices=parse_devices(answers["devices"].out),
        displays=parse_names(answers["displays"].out),
        audio_drivers=parse_names(audio.out) if audio.status == 0 else None,
        netdevs=parse_names(answers["netdevs"].out),
        accelerators=parse_names(answers["accelerators"].out),
    )


def vde_info(
    folder: str, found: Mapping[str, str], answers: Mapping[str, Answer]
) -> VdeInfo:
    """
    What the VDE programs found and their answers say.

    The programs write their help to stdout or to stderr, and exit with 0 or
    not: both streams are read.
    """

    return VdeInfo(
        folder,
        dict(found),
        {
            name: parse_vde_options(answer.out + answer.err)
            for name, answer in answers.items()
        },
    )


# Finding the programs


def find_program(name: str, folder: str) -> str | None:
    """The path of a program, in folder or else in PATH; None if missing."""

    folders = [folder] + os.environ.get("PATH", "").split(os.pathsep)
    for directory in filter(None, folders):
        path = os.path.join(directory, name)
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return None


def qemu_programs(folder: str) -> list[str]:
    """The names of the QEMU system emulators, in folder and in PATH."""

    folders = [folder] + os.environ.get("PATH", "").split(os.pathsep)
    names: set[str] = set()
    for directory in filter(None, folders):
        try:
            entries = os.listdir(directory)
        except OSError:
            continue
        names.update(
            name
            for name in entries
            if name.startswith("qemu-system-")
            and os.access(os.path.join(directory, name), os.X_OK)
        )
    return sorted(names)


# The programs that Virtualbricks warns about at start when they're missing:
# vde-netemu has wirefilter to stand in, and vde_router no package.
REQUIRED = (
    "vde_switch",
    "vde_plug",
    "dpipe",
    "vde_plug2tap",
    "vde_pcapplug",
    "wirefilter",
    "vdeterm",
    "unixterm",
    "vde_cryptcab",
)


# The QEMU program that answers for a folder, if it has one.
QEMU_OF_A_FOLDER = "qemu-system-x86_64"


@attr.define(frozen=True)
class FolderPrograms:
    """
    What a folder of the settings holds of the programs of the bricks: the
    programs found, by name, with their path, in the folder or else in PATH;
    and those that are missing. An empty folder is PATH alone.
    """

    folder: str
    exists: bool
    found: Mapping[str, str]
    missing: tuple[Missing, ...]

    def elsewhere(self) -> list[str]:
        """The programs found in PATH, not in the folder, by name."""

        folder = os.path.normpath(self.folder) if self.folder else None
        return [
            name
            for name, path in self.found.items()
            if os.path.dirname(path) != folder
        ]

    def emulators(self) -> list[str]:
        """The QEMU system emulators found, by name."""

        return [name for name in self.found if name.startswith("qemu-system-")]

    def qemu(self) -> str | None:
        """
        The path of the QEMU that answers for the folder: QEMU_OF_A_FOLDER,
        else the first of the emulators; None if it has none.
        """

        emulators = self.emulators()
        if not emulators:
            return None
        name = QEMU_OF_A_FOLDER if QEMU_OF_A_FOLDER in emulators else None
        return self.found[name or emulators[0]]

    def to_data(self) -> dict:
        """As JSON has it."""

        return {
            "folder": self.folder,
            "exists": self.exists,
            "found": dict(self.found),
            "missing": [[m.program, m.package] for m in self.missing],
        }

    @classmethod
    def from_data(cls, data: dict) -> FolderPrograms:
        return cls(
            str(data["folder"]),
            bool(data["exists"]),
            {str(name): str(path) for name, path in data["found"].items()},
            tuple(Missing(*pair) for pair in data["missing"]),
        )


def _found(folder: str, names: Iterable[str]) -> dict[str, str]:
    found = {}
    for name in names:
        path = find_program(name, folder)
        if path is not None:
            found[name] = path
    return found


def _exists(folder: str) -> bool:
    return not folder or os.path.isdir(folder)


def vde_found(folder: str) -> FolderPrograms:
    """What folder holds of the VDE programs of the bricks."""

    found = _found(folder, REQUIRED)
    missing = tuple(
        Missing(name, PACKAGES[name]) for name in REQUIRED if name not in found
    )
    return FolderPrograms(folder, _exists(folder), found, missing)


def qemu_found(folder: str) -> FolderPrograms:
    """
    What folder holds of the QEMU programs: qemu-img and the system
    emulators, as qemu-system-x86_64, of which the bricks need one.
    """

    found = _found(folder, ["qemu-img", *qemu_programs(folder)])
    missing = []
    if "qemu-img" not in found:
        missing.append(Missing("qemu-img", PACKAGES["qemu-img"]))
    if not any(name.startswith("qemu-system-") for name in found):
        missing.append(Missing(QEMU_OF_A_FOLDER, PACKAGES[QEMU_OF_A_FOLDER]))
    return FolderPrograms(folder, _exists(folder), found, tuple(missing))


def missing_programs(vde_folder: str, qemu_folder: str) -> list[Missing]:
    """The programs of the bricks that aren't installed."""

    return [*vde_found(vde_folder).missing, *qemu_found(qemu_folder).missing]


# Asking the programs


def decode_output(output: bytes) -> str:
    """What a program printed, in the encoding of the locale."""

    return output.decode(locale.getpreferredencoding())


Run = Callable[[str, Iterable[str]], "defer.Deferred[Answer]"]


def run(path: str, args: Iterable[str]) -> defer.Deferred[Answer]:
    """Run a program, in the C locale, for its answer."""

    env = dict(os.environ, LC_ALL="C")
    args = list(args)
    command = " ".join([path] + args)

    def answer(result: tuple[bytes, bytes, int]) -> Answer:
        out, err, status = result
        return Answer(
            out.decode(errors="replace"), err.decode(errors="replace"), status
        )

    def failed(failure: Failure) -> Failure:
        reason = failure.value
        # what getProcessOutputAndValue gives for a program killed
        if isinstance(reason, tuple) and len(reason) == 3:
            reason = f"killed by signal {reason[2]}"
        raise ProgramError(f"{command}: {reason}")

    try:
        deferred = getProcessOutputAndValue(path, args, env=env)
    except OSError as exc:
        return defer.fail(ProgramError(f"{command}: {exc.strerror}"))
    return deferred.addCallbacks(answer, failed)


Key = tuple[str, int, int]


def _key(path: str) -> Key:
    """A program file, as it is now: a program updated is another key."""

    stat = os.stat(path)
    return (os.path.realpath(path), stat.st_size, stat.st_mtime_ns)


_T = TypeVar("_T")


class _Once(Generic[_T]):
    """One result, given to everyone who waits for it."""

    def __init__(
        self, deferred: defer.Deferred[_T], forget: Callable[[], object]
    ) -> None:
        self.done = False
        # once done
        self.result: _T | Failure
        self.waiting: list[defer.Deferred[_T]] = []
        self.forget = forget
        deferred.addBoth(self._fire)

    def _fire(self, result: _T | Failure) -> None:
        self.done = True
        self.result = result
        if isinstance(result, Failure):
            # a failure isn't kept: the next one who asks asks again
            self.forget()
        waiting, self.waiting = self.waiting, []
        for deferred in waiting:
            self._give(deferred)

    def _give(self, deferred: defer.Deferred[_T]) -> None:
        if isinstance(self.result, Failure):
            deferred.errback(self.result)
        else:
            deferred.callback(self.result)

    def wait(self) -> defer.Deferred[_T]:
        deferred: defer.Deferred[_T] = defer.Deferred()
        if self.done:
            self._give(deferred)
        else:
            self.waiting.append(deferred)
        return deferred


def _first_error(failure: Failure) -> Failure:
    """The failure of the question that failed first."""

    failure.trap(defer.FirstError)
    first = failure.value
    assert isinstance(first, defer.FirstError), "trapped"
    return first.subFailure


class Programs:
    """
    Asks the programs what they have, once per program file.

    ``run`` runs a program for its answer; the tests give their own.
    """

    def __init__(self, run: Run = run) -> None:
        self._run = run
        # the results of the questions, each of its own type
        self._asked: dict[object, _Once[Any]] = {}

    def _once(
        self, key: object, ask: Callable[[], defer.Deferred[_T]]
    ) -> defer.Deferred[_T]:
        once = self._asked.get(key)
        if once is None:
            once = _Once(ask(), lambda: self._asked.pop(key, None))
            if not once.done or not isinstance(once.result, Failure):
                self._asked[key] = once
        return once.wait()

    def _gather(
        self, path: str, questions: Mapping[str, tuple[str, ...]]
    ) -> defer.Deferred[dict[str, Answer]]:
        names = list(questions)
        deferred = defer.gatherResults(
            [self._run(path, questions[name]) for name in names],
            consumeErrors=True,
        )
        answered = deferred.addCallback(
            lambda answers: dict(zip(names, answers))
        )
        return answered.addErrback(_first_error)

    def qemu_answers(self, path: str) -> defer.Deferred[dict[str, Answer]]:
        """What the QEMU program at path answers to QEMU_QUESTIONS."""

        try:
            key = ("answers", _key(path))
        except OSError as exc:
            return defer.fail(ProgramError(f"{path}: {exc.strerror}"))
        return self._once(key, lambda: self._gather(path, QEMU_QUESTIONS))

    def qemu(self, path: str) -> defer.Deferred[QemuInfo]:
        """What the QEMU program at path has."""

        try:
            key = ("qemu", _key(path))
        except OSError as exc:
            return defer.fail(ProgramError(f"{path}: {exc.strerror}"))

        def ask() -> defer.Deferred[QemuInfo]:
            deferred = self.qemu_answers(path)
            return deferred.addCallback(lambda a: qemu_info(path, a))

        return self._once(key, ask)

    def machine_answer(
        self, path: str, machine: str
    ) -> defer.Deferred[Answer]:
        """What the QEMU program at path says of the machine type machine."""

        try:
            key = ("machine", _key(path), machine)
        except OSError as exc:
            return defer.fail(ProgramError(f"{path}: {exc.strerror}"))
        return self._once(
            key, lambda: self._run(path, machine_question(machine))
        )

    def machine_properties(
        self, info: QemuInfo, machine: str = ""
    ) -> defer.Deferred[frozenset[str]]:
        """The properties of a machine type; the default one if empty."""

        deferred = self.machine_answer(
            info.path, machine or info.default_machine
        )
        return deferred.addCallback(
            lambda answer: parse_machine_properties(answer.out)
        )

    def vde(self, folder: str) -> defer.Deferred[VdeInfo]:
        """Which VDE programs there are, in folder and else in PATH."""

        found = {}
        for name in VDE_PROGRAMS:
            path = find_program(name, folder)
            if path is not None:
                found[name] = path
        try:
            key = ("vde", folder, tuple(_key(path) for path in found.values()))
        except OSError as exc:
            return defer.fail(ProgramError(f"{folder}: {exc.strerror}"))
        asked = [name for name in VDE_QUESTIONS if name in found]

        def ask() -> defer.Deferred[VdeInfo]:
            deferreds = [
                self._run(found[name], VDE_QUESTIONS[name]) for name in asked
            ]
            deferred = defer.gatherResults(deferreds, consumeErrors=True)
            answered = deferred.addCallback(
                lambda answers: vde_info(
                    folder, found, dict(zip(asked, answers))
                )
            )
            return answered.addErrback(_first_error)

        return self._once(key, ask)


programs = Programs()
