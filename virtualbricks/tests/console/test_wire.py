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

"""What both ends of the control socket share."""

import os
import stat

from twisted.trial import unittest

from virtualbricks import locations
from virtualbricks.console import wire
from virtualbricks.tests import isolate, make_socket, short_folder


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


class TestTokens(unittest.TestCase):

    def setUp(self):
        self.path = os.path.join(self.mktemp())
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)

    def write(self, text, mode=0o600):
        with open(self.path, "w") as file:
            file.write(text)
        os.chmod(self.path, mode)

    def unusable(self):
        return str(
            self.assertRaises(wire.Unusable, wire.read_token, self.path)
        )

    def test_read(self):
        self.write("  0123456789abcdef\n\n")
        self.assertEqual(wire.read_token(self.path), "0123456789abcdef")

    def test_not_there(self):
        error = self.assertRaises(wire.NoToken, wire.read_token, self.path)
        self.assertEqual(str(error), f"{self.path} doesn't exist")

    def test_others_can_read_it(self):
        for mode in (0o640, 0o604, 0o620, 0o602):
            self.write("0123456789abcdef", mode)
            self.assertEqual(
                self.unusable(),
                f"Others can read or change {self.path}: chmod 600"
                f" {self.path}",
            )

    def test_not_yours(self):
        self.write("0123456789abcdef")
        uid = os.getuid()
        self.patch(os, "getuid", lambda: uid + 1)
        self.assertEqual(self.unusable(), f"{self.path} isn't yours")

    def test_too_short(self):
        self.write("1234\n")
        self.assertEqual(
            self.unusable(),
            f"The token of {self.path} has 4 characters; a token has at"
            " least 16",
        )

    def test_not_a_token(self):
        with open(self.path, "wb") as file:
            file.write(b"\xff" * 20)
        os.chmod(self.path, 0o600)
        self.assertEqual(
            self.unusable(), f"{self.path} isn't a token: a line of text"
        )
        os.remove(self.path)
        os.mkdir(self.path)
        self.assertEqual(self.unusable(), f"{self.path}: Is a directory")

    def test_make(self):
        token = wire.make_token(self.path)
        self.assertEqual(len(token), 43)
        self.assertEqual(stat.S_IMODE(os.stat(self.path).st_mode), 0o600)
        self.assertEqual(wire.read_token(self.path), token)
        # never over another
        self.assertRaises(FileExistsError, wire.make_token, self.path)
        self.assertNotEqual(wire.make_token(self.path + "2"), token)


class TestProof(unittest.TestCase):

    TOKEN = "0123456789abcdef"

    def test_proof(self):
        # as openssl dgst -sha256 -hmac computes them
        self.assertEqual(
            wire.proof(self.TOKEN, "client", "a" * 64, "b" * 64),
            "b99e31eea8a5c8b88c9d68b22d9b76154e61e83bc23b236759c27a5cb7af3008",
        )
        self.assertEqual(
            wire.proof(self.TOKEN, "server", "a" * 64, "b" * 64),
            "02ebd92b18e11829709e1fec912ea34c183cc0ef2b09233d76c478b8c7edfe41",
        )

    def test_the_messages(self):
        nonce = wire.new_nonce()
        self.assertRegex(nonce, "^[0-9a-f]{64}$")
        self.assertNotEqual(wire.new_nonce(), nonce)
        self.assertEqual(
            wire.challenge(nonce),
            {"protocol": 1, "auth": "token", "nonce": nonce},
        )
        self.assertEqual(
            wire.greeting("2.1.0", 4200, None, "51b7"),
            {
                "protocol": 1,
                "version": "2.1.0",
                "pid": 4200,
                "project": None,
                "proof": "51b7",
            },
        )
        self.assertEqual(
            wire.token_proof("c41d", "8e02"),
            {"nonce": "c41d", "proof": "8e02"},
        )

    def test_read_a_proof(self):
        nonce = "c" * 64
        line = wire.encode(wire.token_proof(nonce, "8e02"))
        self.assertEqual(wire.read_proof(line), (nonce, "8e02"))
        for line in (
            b"status",
            b'{"line": "status"}',
            b'{"nonce": "c41d", "proof": "8e02"}',
            b'{"nonce": "' + b"C" * 64 + b'", "proof": "8e02"}',
            b'{"nonce": "' + b"c" * 64 + b'", "proof": 1}',
        ):
            error = self.assertRaises(wire.BadRequest, wire.read_proof, line)
            self.assertEqual(
                str(error), 'Not a proof: "nonce" and "proof" come first'
            )

    def test_same_proof(self):
        self.assertTrue(wire.same_proof("8e02", "8e02"))
        self.assertFalse(wire.same_proof("8e03", "8e02"))
        self.assertFalse(wire.same_proof(None, "8e02"))
        self.assertFalse(wire.same_proof("è", "8e02"))


class TestRequestFolders(unittest.TestCase):

    def test_check_cwd(self):
        wire.check_cwd(None)
        wire.check_cwd("/srv/labs")
        for cwd in ("labs", 1, ""):
            error = self.assertRaises(wire.BadRequest, wire.check_cwd, cwd)
            self.assertEqual(
                str(error), 'Not a request: "cwd" is not an absolute path'
            )


class TestTheRuntimeFolder(unittest.TestCase):

    def test_in_it(self):
        isolate(self)
        folder = locations.runtime_dir()
        # the socket of a workspace, in its folder there
        self.assertTrue(wire.in_runtime_dir(locations.control_socket("/w")))
        self.assertTrue(wire.in_runtime_dir(os.path.join(folder, "a.sock")))
        # a project's runtime folder, one deeper
        self.assertFalse(
            wire.in_runtime_dir(os.path.join(folder, "key", "lab1", "a"))
        )
        self.assertFalse(wire.in_runtime_dir("/tmp/lab.sock"))
