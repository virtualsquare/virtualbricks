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
The man pages against the code.

docs/man/virtualbricks-config.5.md documents every key that Virtualbricks
writes, with its default, by a line such as

    **ram** = *integer* 1-99999, default `64`

where the default is written as in TOML. docs/man/virtualbricks.1.md has
every option of the command line and every command of the console, each as
command_entry() writes it from the table of the commands, and
docs/man/virtualbricks-control.7.md every AMP command of protocols 1 and 2,
as the record of the protocol writes it, and every error code. The tests are
skipped when the sources of the documentation are not there, as in an
installed package.
"""

import os
import re
import shutil
import subprocess
import sys

import tomlkit
from twisted.trial import unittest

from virtualbricks import locations
from virtualbricks.cli import Options
from virtualbricks.console import ampcommands, ampgen, ampwire, dispatch
from virtualbricks.console.command import COMMANDS
from virtualbricks.config.projectfile import DEFAULT_MODEL
from virtualbricks.config.settings import AppSettings, ProjectSettings
from virtualbricks.config.schema import (
    Bool,
    Choice,
    Float,
    Int,
    IPv4,
    ListOf,
    Path,
    Ref,
    dump_record,
    field_names,
)
from virtualbricks.config.projectfile import NIC_KEYS, ImageTable, brick_table
from virtualbricks.config.settings import AppState, WorkspaceState
from virtualbricks.config.schema import field_info, fields
from virtualbricks.bricks.event import EventConfig
from virtualbricks.tests import isolate, make_factory, reset_settings
from virtualbricks.bricks.virtualmachine import DISK_DEVICES
from virtualbricks.bricks.netemu import BRICK_KEYS, STATE_KEYS, NetemuConfig
from virtualbricks.remote import commands as windows

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
MAN = os.path.join(ROOT, "docs", "man")
SOURCE = os.path.join(MAN, "virtualbricks-config.5.md")
PROGRAM = os.path.join(MAN, "virtualbricks.1.md")
CONTROL = os.path.join(MAN, "virtualbricks-control.7.md")
# A line of a code block that names an AMP command, as BrickStart.
SIGNATURE = re.compile(r"[A-Z][A-Za-z]*(?: |$)")
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
COMMON_KEYS = {"type", "icon", "on_start", "on_stop"}


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
        for attribute in fields(cls):
            if names is not None and attribute.name not in names:
                continue
            kind = field_info(attribute).kind
            name = attribute.name
            got_kind, got_range, _ = entries[name]
            self.assertEqual(got_kind, kind_name(kind), f"{heading}: {name}")
            self.assertEqual(got_range, kind_range(kind), f"{heading}: {name}")


class TestSettings(DocsTestCase):

    def test_application_settings(self):
        values = dump_record(AppSettings())
        # the default depends on the home directory
        values["workspace"] = values["workspace"].replace(
            locations.home(), "~", 1
        )
        self.check_defaults("SETTINGS", values, "settings")
        self.check_kinds("SETTINGS", AppSettings)

    def test_project_settings(self):
        values = dump_record(ProjectSettings())
        self.check_defaults("Project settings", values, "settings")
        self.check_kinds("Project settings", ProjectSettings)

    def test_state(self):
        self.check_defaults("STATE", dump_record(AppState()), "state")
        self.check_kinds("STATE", AppState)
        self.check_kinds("Workspaces", WorkspaceState)
        # a workspace has no default folder
        entries = self.entries("Workspaces")
        table = dump_record(WorkspaceState("/srv/labs"))
        self.assertEqual(sorted(entries), sorted(table))
        self.assertIsNone(entries["path"][2])
        self.assertEqual(
            entries["current_project"][2], toml(table["current_project"])
        )


class TestProjects(DocsTestCase):

    def test_images(self):
        table = dump_record(ImageTable())
        self.check_defaults("Images", table, "images")
        self.check_kinds("Images", ImageTable)

    def test_events(self):
        table = dump_record(EventConfig())
        self.check_defaults("Events", table, "events")
        self.check_kinds("Events", EventConfig)

    def test_every_brick_type(self):
        from virtualbricks.bricks import BrickConfig

        factory = make_factory(self)
        types = re.findall(r"\*\*(\w+)\*\*", self._bricks_paragraph())
        self.assertEqual(sorted(types[1:]), sorted(BRICK_TYPES))
        for brick_type in BRICK_TYPES:
            brick = factory.new_brick(brick_type, f"a{brick_type}")
            table = brick_table(brick)
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
                own.update(dump_record(NetemuConfig(), exclude=BRICK_KEYS))
            self.check_defaults(brick_type, own, brick_type)
            config_names = set(field_names(brick.config))
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
        disks = brick_table(vm)["disks"]
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
        keys = set().union(*NIC_KEYS.values())
        self.assertEqual(sorted(entries), sorted(keys))
        self.assertEqual(entries["model"][2], toml(DEFAULT_MODEL))

    def test_netemu_states(self):
        entries = self.entries("netemu")
        state = dump_record(NetemuConfig(), exclude=BRICK_KEYS)
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


def section(path, heading):
    """The text of a section of a page, up to the next one."""

    with open(path, encoding="utf-8") as fp:
        text = fp.read()
    start = text.index(f"\n# {heading}\n")
    end = text.find("\n# ", start + 1)
    return text[start : None if end == -1 else end]


def arg_words(name):
    """An argument's name as the page writes it: *KEY*=*VALUE*."""

    return re.sub(r"[A-Z]+", lambda match: f"*{match[0]}*", name)


def command_usage(command):
    parts = [f"**{command.name}**"]
    for arg in command.args:
        text = arg_words(arg.name) + ("..." if arg.many else "")
        parts.append(f"[{text}]" if arg.optional else text)
    for flag in command.flags:
        text = f"**--{flag.name}**"
        if flag.value is not None:
            text += f" {arg_words(flag.value.name)}"
        parts.append(f"[{text}]")
    return " ".join(parts)


def command_entry(command):
    """A command in the page: its usage, its help and its example."""

    lines = [command_usage(command), f":   {command.help}."]
    if command.example:
        lines.append(f"    For example, **{command.example}**.")
    return "\n".join(lines) + "\n"


class TestTheConsolePage(unittest.TestCase):

    def setUp(self):
        if not os.path.exists(PROGRAM):
            raise unittest.SkipTest("the sources of the documentation")
        # the commands are in the table once their modules are imported
        self.assertTrue(dispatch.run)

    def test_every_command(self):
        text = section(PROGRAM, "COMMANDS")
        for command in COMMANDS:
            self.assertIn(f"\n{command_entry(command)}", text, command.name)
        # and no other
        entries = re.findall(r"^\*\*[a-z]", text, re.MULTILINE)
        self.assertEqual(len(entries), len(COMMANDS))

    def test_every_option(self):
        text = section(PROGRAM, "OPTIONS")
        options = Options()
        for name in {option.rstrip("=") for option in options.longOpt}:
            self.assertIn(f"**--{name}**", text)
        # a letter, on the line of its option: **-l** *file*, **--logfile**
        for letter in options.shortOpt.replace(":", ""):
            long_name = options.synonyms[letter]
            self.assertRegex(
                text, rf"\n\*\*-{letter}\*\*[^\n]*\*\*--{long_name}\*\*"
            )


def signatures(text):
    """
    The AMP commands in the code blocks of text, by name: a line that starts
    with a name, and the lines indented under it, in words.
    """

    found = {}
    for block in re.findall(r"^```\n(.*?)^```$", text, re.S | re.M):
        name = None
        for line in block.splitlines():
            if SIGNATURE.match(line):
                name = line.split()[0]
                found[name] = line.split()
            elif name is not None and line.startswith(" "):
                found[name] += line.split()
            else:
                name = None
    return {name: " ".join(words) for name, words in found.items()}


def declared(command):
    """A command as the page writes it: the record without its errors."""

    return ampgen.class_record(command).partition(" !")[0]


class TestTheControlPage(unittest.TestCase):

    def setUp(self):
        if not os.path.exists(CONTROL):
            raise unittest.SkipTest("the sources of the documentation")
        # the commands are in the table once their modules are imported
        self.assertTrue(dispatch.run)

    def test_protocol_1(self):
        text = section(CONTROL, "AMP PROTOCOL 1")
        protocol = (
            ampwire.Hello,
            ampwire.Run,
            ampwire.Challenge,
            ampwire.Authenticate,
        )
        self.assertEqual(
            signatures(text),
            {
                command.commandName.decode(): declared(command)
                for command in protocol
            },
        )
        for command in protocol:
            for code in command.errors.values():
                self.assertIn(f"\n**{code.decode()}**\n", text)

    def test_protocol_2(self):
        text = section(CONTROL, "AMP PROTOCOL 2")
        expected = {}
        # the typed commands, without the cwd and the lines they all have
        for command in COMMANDS:
            name = ampgen.name(command)
            words = [name] + [
                f"{key}:{kind}{'?' if optional else ''}"
                for key, kind, optional in ampgen.arguments(command)
                if key != "cwd"
            ]
            expected[name] = " ".join(words)
        for command in windows.FROM_PROGRAM:
            expected[command.commandName.decode()] = declared(command)
        # the pushes, without the answer they don't want
        for command in windows.PUSHES:
            expected[command.commandName.decode()] = declared(command)[
                : -len(" ->")
            ]
        self.assertEqual(signatures(text), expected)
        for code in ampcommands.ERRORS.values():
            self.assertIn(f"\n**{code.decode()}**\n", text)
