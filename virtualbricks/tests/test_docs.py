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
The man page of the files, docs/man/virtualbricks-config.5.md, against the
code: every key that Virtualbricks writes is documented, with its default.

Each key is documented by a line such as

    **ram** = *integer* 1-99999, default `64`

where the default is written as in TOML. The tests are skipped when the
sources of the documentation are not there, as in an installed package.
"""

import os
import re
import shutil
import subprocess
import sys

import tomlkit
from twisted.trial import unittest

from virtualbricks import config, locations
from virtualbricks.config import (
    Bool,
    Choice,
    Float,
    Int,
    IPv4,
    ListOf,
    Path,
    Ref,
)
from virtualbricks.events import EventConfig
from virtualbricks.tests import isolate, make_factory, reset_settings
from virtualbricks.bricks.virtualmachine import DISK_DEVICES
from virtualbricks.bricks.netemu import BRICK_KEYS, STATE_KEYS, NetemuConfig

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
MAN = os.path.join(ROOT, "docs", "man")
SOURCE = os.path.join(MAN, "virtualbricks-config.5.md")
HEADING = re.compile(r"^(#+) (.+)$")
ENTRY = re.compile(
    r"^\*\*(?P<name>.+?)\*\* = \*(?P<kind>[^*]+)\*"
    r"(?: (?P<range>\S+(?: \S+)?))?"
    r"(?:, default `(?P<default>[^`]*)`)?$"
)
BRICK_TYPES = (
    "qemu",
    "switch",
    "switchwrapper",
    "tap",
    "capture",
    "wire",
    "netemu",
    "tunnellisten",
    "tunnelconnect",
    "router",
)
# Keys that are subsections of a brick, documented under their own heading.
NESTED = {"disks": "Disks", "nics": "Network cards", "states": None}
COMMON_KEYS = {"type", "pon_vbevent", "poff_vbevent"}


def parse(path):
    """Return {heading: {name: (kind, range, default)}} of the page."""

    sections = {}
    current = None
    in_code = False
    with open(path, encoding="utf-8") as fp:
        for line in fp:
            line = line.rstrip("\n")
            if line.startswith("```"):
                in_code = not in_code
                continue
            if in_code:
                continue
            match = HEADING.match(line)
            if match:
                current = match.group(2)
                sections.setdefault(current, {})
                continue
            match = ENTRY.match(line)
            if match and current is not None:
                name = match["name"].replace("*", "")
                sections[current][name] = (
                    match["kind"],
                    match["range"],
                    match["default"],
                )
    return sections


def toml(value):
    return tomlkit.item(value).as_string()


def kind_name(kind):
    if isinstance(kind, Bool):
        return "boolean"
    if isinstance(kind, Choice):
        return "choice"
    if isinstance(kind, IPv4):
        return "address"
    if isinstance(kind, Ref):
        return kind.target
    if isinstance(kind, Path):
        return "path"
    if isinstance(kind, Float):
        return "number"
    if isinstance(kind, Int):
        return "integer"
    if isinstance(kind, ListOf):
        return "array"
    return "string"


def kind_range(kind):
    if not isinstance(kind, (Int, Float)):
        return None
    if kind.min is not None and kind.max is not None:
        return f"{kind.min}-{kind.max}"
    if kind.min is not None:
        return f">= {kind.min}"
    return None


class DocsTestCase(unittest.TestCase):

    def setUp(self):
        if not os.path.exists(SOURCE):
            raise unittest.SkipTest("the sources of the documentation")
        isolate(self)
        reset_settings(self)
        self.sections = parse(SOURCE)

    def entries(self, heading):
        self.assertIn(heading, self.sections, "a section of the page")
        return self.sections[heading]

    def check_defaults(self, heading, table, where):
        entries = self.entries(heading)
        self.assertEqual(sorted(entries), sorted(table), where)
        for name, value in table.items():
            default = entries[name][2]
            self.assertEqual(default, toml(value), f"{where}.{name}")

    def check_kinds(self, heading, cls, names=None):
        entries = self.entries(heading)
        for attribute in config.fields(cls):
            if names is not None and attribute.name not in names:
                continue
            kind = config.info(attribute).kind
            name = attribute.name
            got_kind, got_range, _ = entries[name]
            self.assertEqual(got_kind, kind_name(kind), f"{heading}: {name}")
            self.assertEqual(got_range, kind_range(kind), f"{heading}: {name}")


class TestSettings(DocsTestCase):

    def test_application_settings(self):
        values = config.dump_record(config.AppSettings())
        # the default depends on the home directory
        values["workspace"] = values["workspace"].replace(
            locations.home(), "~", 1
        )
        app_only = {
            k: v for k, v in values.items() if k not in config.PROJECT_KEYS
        }
        project = {k: v for k, v in values.items() if k in config.PROJECT_KEYS}
        self.check_defaults("Application settings", app_only, "settings")
        self.check_defaults("Settings of new projects", project, "settings")
        self.check_kinds("Application settings", config.AppSettings, app_only)
        self.check_kinds("Settings of new projects", config.ProjectSettings)

    def test_state(self):
        self.check_defaults(
            "STATE", config.dump_record(config.AppState()), "state"
        )
        self.check_kinds("STATE", config.AppState)


class TestProjects(DocsTestCase):

    def test_images(self):
        table = config.dump_record(config.ImageTable())
        self.check_defaults("Images", table, "images")
        self.check_kinds("Images", config.ImageTable)

    def test_events(self):
        table = config.dump_record(EventConfig())
        self.check_defaults("Events", table, "events")
        self.check_kinds("Events", EventConfig)

    def test_every_brick_type(self):
        from virtualbricks.bricks import BrickConfig

        factory = make_factory(self)
        types = re.findall(r"\*\*(\w+)\*\*", self._bricks_paragraph())
        self.assertEqual(sorted(types[1:]), sorted(BRICK_TYPES))
        for brick_type in BRICK_TYPES:
            brick = factory.new_brick(brick_type, f"a{brick_type}")
            table = config.brick_table(brick)
            self.assertEqual(table["type"], brick_type)
            common = {k: table[k] for k in COMMON_KEYS - {"type"}}
            self.check_defaults("Bricks", common, "bricks")
            own = {
                k: v
                for k, v in table.items()
                if k not in COMMON_KEYS and k not in NESTED
            }
            if "states" in table:
                # the keys of a state are documented with the brick
                own.update(
                    config.dump_record(NetemuConfig(), exclude=BRICK_KEYS)
                )
            self.check_defaults(brick_type, own, brick_type)
            config_names = set(config.names(brick.config))
            self.check_kinds(
                brick_type, type(brick.config), config_names & set(own)
            )
        self.check_kinds("Bricks", BrickConfig)

    def _bricks_paragraph(self):
        with open(SOURCE, encoding="utf-8") as fp:
            text = fp.read()
        start = text.index("Every brick table has a **type**")
        return text[start : text.index("\n\n", start)]

    def test_disks(self):
        vm = make_factory(self).new_brick("qemu", "vm")
        disks = config.brick_table(vm)["disks"]
        self.assertEqual(sorted(disks), sorted(DISK_DEVICES))
        entries = self.entries("Disks")
        for key, value in disks["hda"].items():
            kind, _, default = entries[f"disks.device.{key}"]
            self.assertEqual(default, toml(value), key)
        self.assertEqual(entries["disks.device.image"][0], "image")
        self.assertEqual(entries["disks.device.private"][0], "boolean")
        # every device is named
        with open(SOURCE, encoding="utf-8") as fp:
            text = fp.read()
        for device in DISK_DEVICES:
            self.assertIn(f"**disks.{device}**", text)

    def test_network_cards(self):
        entries = self.entries("Network cards")
        keys = set().union(*config.NIC_KEYS.values())
        self.assertEqual(sorted(entries), sorted(keys))
        self.assertEqual(entries["model"][2], toml(config.DEFAULT_MODEL))

    def test_netemu_states(self):
        entries = self.entries("netemu")
        state = config.dump_record(NetemuConfig(), exclude=BRICK_KEYS)
        for name, value in state.items():
            self.assertEqual(entries[name][2], toml(value), name)
        self.check_kinds("netemu", NetemuConfig, STATE_KEYS)


class TestManPage(DocsTestCase):
    """The committed man page is built from the current source."""

    def test_up_to_date(self):
        try:
            import pypandoc

            pypandoc.get_pandoc_path()
        except (ImportError, OSError):
            if shutil.which("pandoc") is None:
                raise unittest.SkipTest("pandoc") from None
        result = subprocess.run(
            [sys.executable, os.path.join(MAN, "build.py"), "--check"],
            capture_output=True,
            encoding="utf-8",
            check=False,
            env={
                k: v for k, v in os.environ.items() if k != "SOURCE_DATE_EPOCH"
            },
        )
        self.assertEqual(
            result.returncode,
            0,
            f"{result.stdout}{result.stderr}run python docs/man/build.py",
        )
