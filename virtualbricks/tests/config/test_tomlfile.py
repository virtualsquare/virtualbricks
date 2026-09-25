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

from virtualbricks import config
from virtualbricks.config import tomlfile

DOCUMENT = {
    "format": 1,
    "settings": {"cowfmt": "qcow2", "femaleplugs": False},
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
            "usbdevlist": [],
        },
        "wan": {"type": "netemu", "transitions": [[0.0, 0.2], [0.5, 0.0]]},
        "vm.2": {"type": "switch"},
    },
}

EXPECTED = """\
format = 1

[settings]
cowfmt = "qcow2"
femaleplugs = false

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
usbdevlist = []

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
        self.assertEqual(config.dumps(DOCUMENT), EXPECTED)

    def test_round_trip(self):
        self.assertEqual(config.loads(config.dumps(DOCUMENT)), DOCUMENT)

    def test_table_with_values_and_tables(self):
        text = config.dumps({"a": {"x": 1, "b": {"y": 2}}})
        self.assertEqual(text, "[a]\nx = 1\n\n[a.b]\ny = 2\n")

    def test_empty_table(self):
        self.assertEqual(config.dumps({"a": {}}), "[a]\n")

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


class TestFiles(unittest.TestCase):

    def test_dump_and_load(self):
        path = self.mktemp()
        config.dump_toml(DOCUMENT, path)
        self.assertEqual(config.load_toml(path), DOCUMENT)
        self.assertEqual(
            os.listdir(os.path.dirname(os.path.abspath(path))),
            [os.path.basename(path)],
        )

    def test_dump_replaces_the_file_only_when_complete(self):
        directory = self.mktemp()
        os.makedirs(directory)
        path = os.path.join(directory, "x.toml")
        config.dump_toml({"a": 1}, path)

        def fail(src, dst):
            raise OSError("disk full")

        self.patch(os, "replace", fail)
        self.assertRaises(OSError, config.dump_toml, {"a": 2}, path)
        self.assertEqual(config.load_toml(path), {"a": 1})
        self.assertEqual(os.listdir(directory), ["x.toml"])

    def test_load_invalid(self):
        path = self.mktemp()
        with open(path, "w") as fp:
            fp.write("a = \n")
        self.assertRaises(config.DecodeError, config.load_toml, path)

    def test_loads(self):
        text = textwrap.dedent("""\
            a = 1
            [b]
            c = "d"
            """)
        self.assertEqual(config.loads(text), {"a": 1, "b": {"c": "d"}})
