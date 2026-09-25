# -*- test-case-name: virtualbricks.tests.migrate.test_legacy -*-
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
Readers for the files of Virtualbricks 2.1 and older.

A project file is a list of ``[Type:name]`` sections of ``key=value`` lines,
followed by the connections: ``link|brick|socket|model|mac`` for a plug and
``sock|vm|socket|model|mac`` for a socket card of a virtual machine. The
settings are an INI file with a ``[Main]`` section.
"""

from __future__ import annotations

import ast
import configparser
import re
from typing import TYPE_CHECKING, TypeAlias

import attr

if TYPE_CHECKING:
    from virtualbricks.config import Report

SECTION = re.compile(r"^\[(?P<type>[a-zA-Z0-9_]+):(?P<name>.+)\]$")
ASSIGNMENT = re.compile(r"^(?P<key>[\w.\[\]]+)\s*=\s*(?P<value>.*)$")
LINK = re.compile(
    r"^(?P<kind>link|sock)\|(?P<owner>[^|]*)\|(?P<socket>[^|]*)"
    r"\|(?P<model>[^|]*)\|(?P<mac>[^|]*)$"
)
PROJECT_TYPES = frozenset(
    (
        "Capture",
        "DiskImage",
        "Event",
        "Image",
        "Netemu",
        "Project",
        "Qemu",
        "Router",
        "Switch",
        "SwitchWrapper",
        "Tap",
        "TunnelConnect",
        "TunnelListen",
        "Wire",
        "Wirefilter",
    )
)
SETTINGS_SECTION = "Main"

# The options of an old settings file: {key: (value, line)}.
Options: TypeAlias = dict[str, tuple[str, int]]


@attr.define
class Item:

    key: str = attr.field()
    value: str = attr.field()
    lineno: int = attr.field()


@attr.define
class Section:

    type: str = attr.field()
    name: str = attr.field()
    lineno: int = attr.field()
    items: list[Item] = attr.field(factory=list)

    def label(self) -> str:
        return f"[{self.type}:{self.name}]"


@attr.define
class Link:

    # "link" for a plug, "sock" for a socket card of a virtual machine
    kind: str = attr.field()
    owner: str = attr.field()
    socket: str = attr.field()
    model: str = attr.field()
    mac: str = attr.field()
    lineno: int = attr.field()


@attr.define
class LegacyProject:

    filename: str = attr.field()
    sections: list[Section] = attr.field(factory=list)
    links: list[Link] = attr.field(factory=list)


def where(filename: str, lineno: int) -> str:
    """Where a message is about: the file, and the line if there's one."""

    return f"{filename}:{lineno}" if lineno else filename


def parse_project(text: str, filename: str, report: Report) -> LegacyProject:
    """Parse the text of an old project file; report what's ignored."""

    project = LegacyProject(filename)
    section: Section | None = None
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = SECTION.match(line)
        if match:
            section = Section(match["type"], match["name"], lineno)
            project.sections.append(section)
            continue
        match = LINK.match(line)
        if match:
            project.links.append(Link(**match.groupdict(), lineno=lineno))
            continue
        # A Netemu writes its states after a line starting with "-".
        if line.startswith("-") and section is not None:
            continue
        match = ASSIGNMENT.match(line)
        if match and section is not None:
            section.items.append(Item(match["key"], match["value"], lineno))
            continue
        excerpt = line if len(line) <= 40 else line[:40] + "…"
        report.warning(
            f'"{excerpt}" is not understood, ignored', where(filename, lineno)
        )
    return project


def read_project(path: str, filename: str, report: Report) -> LegacyProject:
    """Read an old project file; UnicodeDecodeError or OSError if it can't."""

    with open(path, encoding="utf-8") as fp:
        return parse_project(fp.read(), filename, report)


def looks_like_project(path: str) -> bool:
    """Whether a file starts like an old project file."""

    try:
        with open(path, encoding="utf-8") as fp:
            head = fp.read(4096)
    except (OSError, UnicodeDecodeError):
        return False
    for line in head.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = SECTION.match(line)
        return match is not None and match["type"] in PROJECT_TYPES
    return False


OPTION = re.compile(r"^\s*(?P<key>[^=:\s]+)\s*[=:]")


def _option_lines(text: str) -> dict[str, int]:
    lines: dict[str, int] = {}
    section = None
    for lineno, line in enumerate(text.splitlines(), 1):
        match = re.match(r"^\s*\[(?P<name>[^]]+)\]", line)
        if match:
            section = match["name"]
            continue
        match = OPTION.match(line)
        if match and section == SETTINGS_SECTION:
            # The last value wins, as with the Python 2 versions.
            lines[match["key"].lower()] = lineno
    return lines


def read_settings(path: str, filename: str, report: Report) -> Options:
    """
    Return the options of an old settings file: ``{key: (value, lineno)}``.

    Raise UnicodeDecodeError or OSError if it can't be read.
    """

    with open(path, encoding="utf-8") as fp:
        text = fp.read()
    parser = configparser.RawConfigParser(strict=False)
    try:
        parser.read_string(text, filename)
    except configparser.Error as exc:
        report.error(f"can't be read: {exc}", filename)
        return {}
    if not parser.has_section(SETTINGS_SECTION):
        report.warning(f"has no [{SETTINGS_SECTION}] section", filename)
        return {}
    lines = _option_lines(text)
    return {
        key: (value, lines.get(key, 0))
        for key, value in parser.items(SETTINGS_SECTION)
    }


# The values, as the old versions wrote them.


def parse_bool(text: str) -> bool:
    return text.strip().lower() in ("true", "*", "yes")


def parse_settings_bool(text: str) -> bool:
    value = text.strip().lower()
    if value in configparser.RawConfigParser.BOOLEAN_STATES:
        return configparser.RawConfigParser.BOOLEAN_STATES[value]
    raise ValueError(f'"{text}" is not true or false')


def parse_list(text: str) -> list[str]:
    """Parse a list of strings written with repr(), without running it."""

    if not text.strip():
        return []
    try:
        value = ast.literal_eval(text)
    except (ValueError, SyntaxError):
        raise ValueError(f"{text!r} is not a list") from None
    if not isinstance(value, (list, tuple)) or not all(
        isinstance(item, str) for item in value
    ):
        raise ValueError(f"{text!r} is not a list of strings")
    return list(value)
