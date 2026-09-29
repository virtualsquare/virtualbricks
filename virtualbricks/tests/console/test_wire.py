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

"""What both ends of the control socket share."""

import os

from twisted.trial import unittest

from virtualbricks.console import wire
from virtualbricks.tests import make_socket, short_folder


class TestMessages(unittest.TestCase):

    def test_a_line_each(self):
        line = wire.encode(wire.answer(["vm1 runs, process 4242", "è"]))
        self.assertEqual(
            line,
            '{"ok": true, "lines": ["vm1 runs, process 4242", "è"]}\n'.encode(),
        )
        self.assertEqual(
            wire.decode(line),
            {"ok": True, "lines": ["vm1 runs, process 4242", "è"]},
        )

    def test_only_objects(self):
        for line in (b"[1]\n", b"nope\n", b"\xff\n"):
            self.assertRaises(ValueError, wire.decode, line)

    def test_the_messages(self):
        self.assertEqual(
            wire.greeting("2.1.0", 4200, "lab1"),
            {
                "protocol": 1,
                "version": "2.1.0",
                "pid": 4200,
                "project": "lab1",
            },
        )
        self.assertEqual(wire.request("status"), {"line": "status"})
        self.assertEqual(
            wire.request("status", "/srv"), {"line": "status", "cwd": "/srv"}
        )
        self.assertEqual(
            wire.refusal("No brick named vm9"),
            {"ok": False, "lines": [], "error": "No brick named vm9"},
        )
        self.assertEqual(
            wire.refusal("vm2: no image", ["vm1 runs"]),
            {"ok": False, "lines": ["vm1 runs"], "error": "vm2: no image"},
        )

    def test_read_a_request(self):
        read = wire.read_request
        self.assertEqual(read(b'{"line": "status"}'), ("status", None))
        self.assertEqual(
            read(b'{"line": "source lab.vb", "cwd": "/srv/labs"}'),
            ("source lab.vb", "/srv/labs"),
        )

    def test_not_a_request(self):
        def refused(line):
            return str(
                self.assertRaises(wire.BadRequest, wire.read_request, line)
            )

        self.assertEqual(
            refused(b"status"),
            'Not a request: a line of JSON, as {"line": "brick list"}',
        )
        self.assertEqual(refused(b'"status"'), refused(b"status"))
        self.assertEqual(
            refused(b'{"cmd": "status"}'),
            'Not a request: "line" is not a text',
        )
        self.assertEqual(refused(b'{"line": 1}'), refused(b"{}"))
        for cwd in (b'"labs"', b"1"):
            self.assertEqual(
                refused(b'{"line": "status", "cwd": ' + cwd + b"}"),
                'Not a request: "cwd" is not an absolute path',
            )


class TestPaths(unittest.TestCase):

    def setUp(self):
        self.folder = short_folder(self)
        os.chmod(self.folder, 0o700)
        self.path = os.path.join(self.folder, ".control")

    def unusable(self, path, default=True):
        return str(
            self.assertRaises(wire.Unusable, wire.check_path, path, default)
        )

    def test_the_runtime_folder(self):
        wire.check_path(self.path, True)
        # readable by the others: they can't write a socket of theirs there
        os.chmod(self.folder, 0o755)
        wire.check_path(self.path, True)

    def test_others_can_write_there(self):
        os.chmod(self.folder, 0o770)
        self.assertEqual(
            self.unusable(self.path),
            f"Others can write in the runtime folder {self.folder}",
        )
        os.chmod(self.folder, 0o1777)
        self.unusable(self.path)
        # another path: the socket's mode keeps the others out
        wire.check_path(self.path, False)

    def test_another_users_folder(self):
        uid = os.getuid()
        self.patch(os, "getuid", lambda: uid + 1)
        self.assertEqual(
            self.unusable(self.path),
            f"The runtime folder {self.folder} isn't yours",
        )
        wire.check_path(self.path, False)

    def test_a_link(self):
        link = os.path.join(self.folder, "link")
        os.symlink(self.folder, link)
        path = os.path.join(link, ".control")
        self.assertEqual(self.unusable(path), f"{link} isn't a folder")
        wire.check_path(path, False)

    def test_no_folder(self):
        folder = os.path.join(self.folder, "nope")
        path = os.path.join(folder, "lab.sock")
        self.assertEqual(
            self.unusable(path, False), f"The folder {folder} doesn't exist"
        )
        open(folder, "w").close()
        self.assertEqual(
            self.unusable(path, False), f"{folder} isn't a folder"
        )

    def test_too_long(self):
        path = os.path.join(self.folder, "a" * 107)
        self.assertEqual(
            self.unusable(path, False),
            f"The socket's path, {path}, is longer than 107 bytes",
        )


class TestSockets(unittest.TestCase):

    def setUp(self):
        self.path = os.path.join(short_folder(self), "lab.sock")

    def test_a_socket(self):
        self.assertFalse(wire.check_socket(self.path))
        make_socket(self.path)
        self.assertTrue(wire.check_socket(self.path))

    def test_not_a_socket(self):
        open(self.path, "w").close()
        error = self.assertRaises(wire.Unusable, wire.check_socket, self.path)
        self.assertEqual(str(error), f"{self.path} isn't a socket")

    def test_not_yours(self):
        make_socket(self.path)
        uid = os.getuid()
        self.patch(os, "getuid", lambda: uid + 1)
        error = self.assertRaises(wire.Unusable, wire.check_socket, self.path)
        self.assertEqual(str(error), f"{self.path} isn't yours")
