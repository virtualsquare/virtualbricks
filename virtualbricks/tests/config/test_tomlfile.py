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

import os
import textwrap

from twisted.trial import unittest

from virtualbricks.config.tomlfile import DecodeError, dump_toml, load_toml
from virtualbricks.config import tomlfile
from virtualbricks.config.tomlfile import Note, dumps_toml, loads_toml

DOCUMENT = {
    "format": 1,
    "settings": {"cow_format": "qcow2", "allow_female_plugs": False},
    "images": {"deb": {"path": "/i/deb.qcow2", "description": "a\nb"}},
    "events": {
        "boot": {
            "delay": 5,
            "actions": [
                {"kind": "vb", "command": "vm on"},
                {"kind": "shell", "command": "logger hi"},
            ],
        }
    },
    "bricks": {
        "vm": {
            "type": "qemu",
            "disks": {"hda": {"image": "deb", "private": True}},
            "nics": [
                {"kind": "plug", "connect": "sw", "model": "e1000", "mac": ""}
            ],
            "usb_devices": [],
        },
        "wan": {"type": "netemu", "transitions": [[0.0, 0.2], [0.5, 0.0]]},
        "vm.2": {"type": "switch"},
    },
}

EXPECTED = """\
format = 1

[settings]
cow_format = "qcow2"
allow_female_plugs = false

[images.deb]
path = "/i/deb.qcow2"
description = "a\\nb"

[events.boot]
delay = 5
actions = [
    {kind = "vb", command = "vm on"},
    {kind = "shell", command = "logger hi"},
]

[bricks.vm]
type = "qemu"
usb_devices = []

[bricks.vm.disks.hda]
image = "deb"
private = true

[[bricks.vm.nics]]
kind = "plug"
connect = "sw"
model = "e1000"
mac = ""

[bricks.wan]
type = "netemu"
transitions = [[0.0, 0.2], [0.5, 0.0]]

[bricks."vm.2"]
type = "switch"
"""


class TestDumps(unittest.TestCase):

    def test_layout(self):
        self.assertEqual(dumps_toml(DOCUMENT), EXPECTED)

    def test_round_trip(self):
        self.assertEqual(loads_toml(dumps_toml(DOCUMENT)), DOCUMENT)

    def test_table_with_values_and_tables(self):
        text = dumps_toml({"a": {"x": 1, "b": {"y": 2}}})
        self.assertEqual(text, "[a]\nx = 1\n\n[a.b]\ny = 2\n")

    def test_empty_table(self):
        self.assertEqual(dumps_toml({"a": {}}), "[a]\n")

    def test_space_tables(self):
        self.assertEqual(
            tomlfile._space_tables("\n\n[a]\nx = 1\n\n\n[b]\n"),
            "[a]\nx = 1\n\n[b]\n",
        )
        # some versions of tomlkit put no blank line before a table
        self.assertEqual(
            tomlfile._space_tables("a = 1\n[b]\nx = 1\n[[c]]\n"),
            "a = 1\n\n[b]\nx = 1\n\n[[c]]\n",
        )


class TestNotes(unittest.TestCase):
    """The comments of the keys: above them, and # default beside them."""

    def test_above_the_key(self):
        notes = {("a",): Note("What a is")}
        self.assertEqual(dumps_toml({"a": 1}, notes), "# What a is\na = 1\n")

    def test_default(self):
        notes = {("a",): Note("What a is", default=True)}
        self.assertEqual(
            dumps_toml({"a": 1}, notes), "# What a is\na = 1  # default\n"
        )

    def test_detail_at_the_end(self):
        notes = {("a",): Note("Ports", "1-128; default 32")}
        self.assertEqual(
            dumps_toml({"a": 16}, notes),
            "# Ports (1-128; default 32)\na = 16\n",
        )

    def test_wrapped(self):
        text = " ".join(["word"] * 40)
        lines = tomlfile.comment_lines(Note(text))
        # 15 words make 74 columns, and "# " before them 76: one more is 81
        self.assertEqual(lines[0], " ".join(["word"] * 15))
        self.assertEqual(len(lines), 3)
        self.assertEqual(" ".join(lines), text)

    def test_never_at_a_hyphen(self):
        # "vde-" would still fit on the first line
        text = "x" * 70 + " vde-netemu-program"
        self.assertEqual(
            tomlfile.comment_lines(Note(text)),
            ["x" * 70, "vde-netemu-program"],
        )

    def test_detail_whole_on_a_line_of_its_own(self):
        text = "y" * 70
        self.assertEqual(
            tomlfile.comment_lines(Note(text, "default empty")),
            [text, "(default empty)"],
        )
        # it fits on the last line up to the width
        text = "y" * (77 - len(" (default empty)"))
        self.assertEqual(
            tomlfile.comment_lines(Note(text, "default empty")),
            [text + " (default empty)"],
        )

    def test_nothing_to_say(self):
        self.assertEqual(tomlfile.comment_lines(Note("")), [])
        self.assertEqual(tomlfile.comment_lines(Note("", "x")), ["(x)"])
        self.assertEqual(dumps_toml({"a": 1}, {("a",): Note("")}), "a = 1\n")

    def test_by_path(self):
        data = {
            "t": {"x": 1, "u": {"y": 2}},
            "l": [{"z": 1, "w": 2, "v": 3}, {"z": 4, "w": 5, "v": 6}],
        }
        notes = {
            ("t", "x"): Note("x"),
            ("t", "u", "y"): Note("y", default=True),
            ("l", 1, "z"): Note("the second z"),
        }
        self.assertEqual(
            dumps_toml(data, notes),
            textwrap.dedent("""\
                [t]
                # x
                x = 1

                [t.u]
                # y
                y = 2  # default

                [[l]]
                z = 1
                w = 2
                v = 3

                [[l]]
                # the second z
                z = 4
                w = 5
                v = 6
                """),
        )

    def test_no_note_on_a_table(self):
        notes = {("t",): Note("a table"), ("l",): Note("tables")}
        data = {"t": {"x": 1}, "l": [{"a": 1, "b": 2, "c": 3}]}
        self.assertEqual(dumps_toml(data, notes), dumps_toml(data))

    def test_header(self):
        text = dumps_toml(
            {"a": 1}, {("a",): Note("a")}, "Line one\nLine two\n"
        )
        self.assertEqual(text, "# Line one\n# Line two\n\n# a\na = 1\n")

    def test_header_before_a_table(self):
        text = dumps_toml({"t": {"x": 1}}, header="Head")
        self.assertEqual(text, "# Head\n\n[t]\nx = 1\n")

    def test_read_back(self):
        notes = {
            ("format",): Note("The version", default=True),
            ("events", "boot", "actions"): Note("Actions " * 20, "x"),
            ("bricks", "vm", "disks", "hda", "image"): Note("i", "d", True),
            ("bricks", "vm", "nics", 0, "mac"): Note("m", default=True),
            ("bricks", "vm", "usb_devices"): Note("u", default=True),
            ("bricks", "wan", "transitions"): Note("t", default=True),
        }
        text = dumps_toml(DOCUMENT, notes, "Header")
        self.assertEqual(loads_toml(text), DOCUMENT)
        self.assertEqual(text.count("  # default"), 5)
        self.assertTrue(all(len(line) <= 79 for line in text.splitlines()))

    def test_file(self):
        path = self.mktemp()
        dump_toml({"a": 1}, path, {("a",): Note("a", default=True)}, "H")
        with open(path, encoding="utf-8") as fp:
            self.assertEqual(fp.read(), "# H\n\n# a\na = 1  # default\n")


class TestFiles(unittest.TestCase):

    def test_dump_and_load(self):
        path = self.mktemp()
        dump_toml(DOCUMENT, path)
        self.assertEqual(load_toml(path), DOCUMENT)
        self.assertEqual(
            os.listdir(os.path.dirname(os.path.abspath(path))),
            [os.path.basename(path)],
        )

    def test_dump_replaces_the_file_only_when_complete(self):
        directory = self.mktemp()
        os.makedirs(directory)
        path = os.path.join(directory, "x.toml")
        dump_toml({"a": 1}, path)

        def fail(src, dst):
            raise OSError("disk full")

        self.patch(os, "replace", fail)
        self.assertRaises(OSError, dump_toml, {"a": 2}, path)
        self.assertEqual(load_toml(path), {"a": 1})
        self.assertEqual(os.listdir(directory), ["x.toml"])

    def test_load_invalid(self):
        path = self.mktemp()
        with open(path, "w") as fp:
            fp.write("a = \n")
        self.assertRaises(DecodeError, load_toml, path)

    def test_loads(self):
        text = textwrap.dedent("""\
            a = 1
            [b]
            c = "d"
            """)
        self.assertEqual(loads_toml(text), {"a": 1, "b": {"c": "d"}})
