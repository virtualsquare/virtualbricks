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

import textwrap

from twisted.trial import unittest

from virtualbricks.migrate import (
    Link,
    looks_like_project,
    parse_bool,
    parse_list,
    parse_project,
    parse_settings_bool,
    read_project,
    read_settings,
    where,
)
from virtualbricks.config import Report
from virtualbricks.tests.migrate.fixtures import CONFIG1

NETEMU = """\
[Netemu:wan]
#Syntax used by the old versions (only one state)

delay=10

- #Syntax used by newer versions
states=2
state1.probability[0]=0.5
"""

SETTINGS = """\
[DEFAULT]
inherited = 1

[Main]
term = /usr/bin/xterm
Sudo : /usr/bin/gksu
term = /usr/bin/other

[Other]
cowfmt = qed
"""


def write(test, text, mode="w"):
    path = test.mktemp()
    with open(path, mode) as fp:
        fp.write(text)
    return path


class TestParseProject(unittest.TestCase):

    def test_config1(self):
        report = Report()
        project = parse_project(CONFIG1, ".project", report)
        self.assertEqual(len(report), 0)
        self.assertEqual(project.filename, ".project")
        self.assertEqual(
            [(s.type, s.name, s.lineno) for s in project.sections],
            [
                ("Image", "martin", 2),
                ("Qemu", "sender", 5),
                ("Wirefilter", "wf", 12),
                ("Switch", "sw1", 14),
            ],
        )
        sender = project.sections[1]
        self.assertEqual(sender.label(), "[Qemu:sender]")
        self.assertEqual(
            [(i.key, i.value, i.lineno) for i in sender.items],
            [
                ("hda", "martin", 6),
                ("kvm", "*", 7),
                ("name", "sender", 8),
                ("privatehda", "*", 9),
                ("tdf", "*", 10),
            ],
        )
        self.assertEqual(
            project.links,
            [
                Link(
                    "link",
                    "sender",
                    "sw1_port",
                    "rtl8139",
                    "00:aa:79:71:be:61",
                    16,
                )
            ],
        )

    def test_netemu_states(self):
        report = Report()
        project = parse_project(NETEMU, "f", report)
        self.assertEqual(len(report), 0)
        self.assertEqual(
            [i.key for i in project.sections[0].items],
            ["delay", "states", "state1.probability[0]"],
        )

    def test_empty_values_and_spaces(self):
        text = "[Qemu:vm 1]\nhda =  \nkopt = a = b\n"
        project = parse_project(text, "f", Report())
        section = project.sections[0]
        self.assertEqual(section.name, "vm 1")
        self.assertEqual(
            [(i.key, i.value) for i in section.items],
            [("hda", ""), ("kopt", "a = b")],
        )

    def test_sock_line(self):
        text = "[Qemu:vm]\nsock|vm|vm_sock_eth0|e1000|00:11:22:33:44:55\n"
        project = parse_project(text, "f", Report())
        link = project.links[0]
        self.assertEqual(
            (link.kind, link.owner, link.socket, link.model, link.mac),
            ("sock", "vm", "vm_sock_eth0", "e1000", "00:11:22:33:44:55"),
        )

    def test_not_understood(self):
        long_line = "x" * 50
        text = f"key=before any section\n- nothing\n[Switch:sw]\n{long_line}\n"
        report = Report()
        project = parse_project(text, "f", report)
        self.assertEqual([s.name for s in project.sections], ["sw"])
        self.assertEqual(
            [str(m) for m in report],
            [
                'f:1: "key=before any section" is not understood, ignored',
                'f:2: "- nothing" is not understood, ignored',
                f'f:4: "{"x" * 40}…" is not understood, ignored',
            ],
        )
        self.assertEqual(report.warnings, 3)

    def test_read_project(self):
        path = write(self, CONFIG1)
        project = read_project(path, ".project", Report())
        self.assertEqual(len(project.sections), 4)

    def test_read_project_not_text(self):
        path = write(self, b"\xff\xfe[", "wb")
        self.assertRaises(
            UnicodeDecodeError, read_project, path, "f", Report()
        )

    def test_where(self):
        self.assertEqual(where("a/.project", 3), "a/.project:3")


class TestLooksLikeProject(unittest.TestCase):

    def test_project(self):
        self.assertTrue(looks_like_project(write(self, CONFIG1)))

    def test_comment_first(self):
        path = write(self, "# a comment\n\n[Switch:sw]\n")
        self.assertTrue(looks_like_project(path))

    def test_other_files(self):
        texts = (
            "",
            "\n# only comments\n",
            "[Main]\nterm = x\n",
            "[Unknown:x]\n",
            "hello\n[Switch:sw]\n",
        )
        for text in texts:
            self.assertFalse(looks_like_project(write(self, text)), text)

    def test_binary_and_missing(self):
        self.assertFalse(looks_like_project(write(self, b"\xff\xfe", "wb")))
        self.assertFalse(looks_like_project(self.mktemp()))


class TestReadSettings(unittest.TestCase):

    def test_values_and_lines(self):
        report = Report()
        options = read_settings(write(self, SETTINGS), "vb.conf", report)
        self.assertEqual(len(report), 0)
        self.assertEqual(
            options,
            {
                # the last value wins
                "term": ("/usr/bin/other", 7),
                "sudo": ("/usr/bin/gksu", 6),
                # from [DEFAULT], it has no line of its own in [Main]
                "inherited": ("1", 0),
            },
        )

    def test_invalid(self):
        report = Report()
        path = write(self, "term = x\n")
        self.assertEqual(read_settings(path, "vb.conf", report), {})
        self.assertEqual(report.errors, 1)
        self.assertTrue(
            str(list(report)[0]).startswith("vb.conf: can't be read:")
        )

    def test_no_main_section(self):
        report = Report()
        path = write(self, "[Other]\nterm = x\n")
        self.assertEqual(read_settings(path, "vb.conf", report), {})
        self.assertEqual(
            [str(m) for m in report], ["vb.conf: has no [Main] section"]
        )

    def test_missing(self):
        self.assertRaises(
            OSError, read_settings, self.mktemp(), "vb.conf", Report()
        )


class TestValues(unittest.TestCase):

    def test_parse_bool(self):
        for text in ("*", "True", " yes ", "true"):
            self.assertIs(parse_bool(text), True, text)
        for text in ("", "False", "no", "0", "anything"):
            self.assertIs(parse_bool(text), False, text)

    def test_parse_settings_bool(self):
        for text, value in (("True", True), (" on", True), ("0", False)):
            self.assertIs(parse_settings_bool(text), value)
        error = self.assertRaises(ValueError, parse_settings_bool, "maybe")
        self.assertEqual(str(error), '"maybe" is not true or false')

    def test_parse_list(self):
        self.assertEqual(parse_list(""), [])
        self.assertEqual(parse_list("  "), [])
        self.assertEqual(parse_list("['a', \"b c\"]"), ["a", "b c"])
        self.assertEqual(parse_list("('a',)"), ["a"])

    def test_parse_list_does_not_run_code(self):
        text = "__import__('os').system('false')"
        error = self.assertRaises(ValueError, parse_list, text)
        self.assertEqual(str(error), f"{text!r} is not a list")
        self.assertRaises(ValueError, parse_list, "['a'")

    def test_parse_list_of_strings_only(self):
        for text in ("[1]", "'a'", "{'a': 1}"):
            error = self.assertRaises(ValueError, parse_list, text)
            self.assertEqual(str(error), f"{text!r} is not a list of strings")


class TestFixtures(unittest.TestCase):
    """The layouts written by the old versions, as found in the wild."""

    def test_old_format(self):
        text = textwrap.dedent("""\
            [Project:/home/user/.virtualbricks.vbl]
            id=1
            [DiskImage:vtatpa.qcow2]
            path=/vimages/vtatpa.qcow2
            [SwitchWrapper:sw1]
            numports=32
            path=/var/run/switch/sck
            """)
        report = Report()
        project = parse_project(text, "f", report)
        self.assertEqual(len(report), 0)
        self.assertEqual(
            [s.type for s in project.sections],
            ["Project", "DiskImage", "SwitchWrapper"],
        )
