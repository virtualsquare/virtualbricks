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


class TestDescriptions(unittest.TestCase):

    def refused(self, text):
        return str(self.assertRaises(ValueError, wire.parse_socket, text))

    def test_a_path(self):
        parse = wire.parse_socket
        self.assertEqual(
            parse("unix:/tmp/lab.sock"),
            wire.Socket("/tmp/lab.sock", "text", "unix"),
        )
        self.assertEqual(parse("unix:~/lab.sock"), wire.Socket("~/lab.sock"))
        self.assertEqual(
            parse("unix:address=lab.sock"), wire.Socket("lab.sock")
        )
        self.assertEqual(
            parse("UNIX:/tmp/lab.sock"), wire.Socket("/tmp/lab.sock")
        )

    def test_the_protocol(self):
        parse = wire.parse_socket
        self.assertEqual(
            parse("unix:/tmp/lab.sock:protocol=text"),
            wire.Socket("/tmp/lab.sock"),
        )
        self.assertEqual(
            parse("unix:protocol=TEXT:address=/tmp/lab.sock"),
            wire.Socket("/tmp/lab.sock"),
        )
        self.assertEqual(
            parse("unix:/tmp/lab.amp:protocol=amp"),
            wire.Socket("/tmp/lab.amp", "amp"),
        )
        self.assertEqual(
            parse("unix:/tmp/lab.amp:protocol=AMP"),
            wire.Socket("/tmp/lab.amp", "amp"),
        )
        self.assertEqual(
            self.refused("unix:/tmp/lab.sock:protocol=json"),
            "unix:/tmp/lab.sock:protocol=json: the protocol is text or amp",
        )

    def test_the_rules_of_twisted(self):
        parse = wire.parse_socket
        # a backslash makes the next character plain
        self.assertEqual(
            parse(r"unix:/tmp/a\:b.sock"), wire.Socket("/tmp/a:b.sock")
        )
        self.assertEqual(
            parse(r"unix:/tmp/a\\b.sock"), wire.Socket(r"/tmp/a\b.sock")
        )
        self.assertEqual(
            parse(r"unix:/tmp/a\=b.sock"), wire.Socket("/tmp/a=b.sock")
        )
        # the first = of a part only
        self.assertEqual(
            parse("unix:address=/tmp/a=b.sock"), wire.Socket("/tmp/a=b.sock")
        )
        self.assertEqual(
            self.refused("unix:/tmp/a\\"),
            "unix:/tmp/a\\ ends with a backslash",
        )

    def test_without_its_type(self):
        self.assertEqual(
            self.refused("~/lab.sock"),
            "~/lab.sock needs its type: unix:~/lab.sock",
        )
        self.assertEqual(
            self.refused("/tmp/a:b.sock"),
            "/tmp/a:b.sock needs its type, as unix:PATH",
        )
        self.assertEqual(
            self.refused("protocol=text"),
            "protocol=text needs its type and its path, as"
            " unix:~/labs/lab1.sock",
        )

    def test_another_type(self):
        for text in ("systemd:domain=INET:index=0", "tls:443"):
            self.assertEqual(
                self.refused(text),
                f"{text}: the types are unix, tcp and ssl, as unix:PATH or"
                " tcp:PORT",
            )

    def test_the_path(self):
        for text in ("unix", "unix:", "unix:address="):
            self.assertEqual(
                self.refused(text),
                f"{text} needs a path, as unix:~/labs/lab1.sock",
            )
        for text in ("unix:/tmp/a.sock:666", "unix:/tmp/a:address=/tmp/b"):
            self.assertEqual(
                self.refused(text),
                f"{text}: one path, then the keywords address and protocol",
            )

    def test_the_keywords(self):
        self.assertEqual(
            self.refused("unix:/tmp/a.sock:mode=666"),
            "unix:/tmp/a.sock:mode=666: unknown keyword mode; the keywords"
            " of unix are address and protocol",
        )
        self.assertEqual(
            self.refused("unix:/tmp/a.sock:protocol=text:protocol=text"),
            "unix:/tmp/a.sock:protocol=text:protocol=text: protocol is given"
            " twice",
        )


class TestTcpDescriptions(unittest.TestCase):
    """The tcp sockets to listen on, and those that --command talks to."""

    def refused(self, text, client=False):
        return str(
            self.assertRaises(ValueError, wire.parse_socket, text, client)
        )

    def tcp(self, port, host="127.0.0.1", protocol="text", token_file=None):
        return wire.Socket(None, protocol, "tcp", host, port, token_file)

    def test_to_listen_on(self):
        parse = wire.parse_socket
        self.assertEqual(parse("tcp:8765"), self.tcp(8765))
        self.assertEqual(parse("TCP:port=8765"), self.tcp(8765))
        self.assertEqual(
            parse("tcp:8765:protocol=amp"), self.tcp(8765, protocol="amp")
        )
        self.assertEqual(
            parse(r"tcp:8765:interface=\:\:1"), self.tcp(8765, "::1")
        )
        self.assertEqual(
            parse("tcp:8765:interface=127.0.0.2"), self.tcp(8765, "127.0.0.2")
        )
        self.assertEqual(
            parse("tcp:8765:tokenFile=~/vb/lab1.token"),
            self.tcp(8765, token_file="~/vb/lab1.token"),
        )

    def test_this_machine_only(self):
        for interface in ("0.0.0.0", r"\:\:", "192.0.2.7"):
            text = f"tcp:8765:interface={interface}"
            self.assertEqual(
                self.refused(text),
                f"{text}: tcp listens on this machine only, as"
                " interface=127.0.0.1 or ::1; across the network, ssl",
            )
        self.assertEqual(
            self.refused("tcp:8765:interface=lab.example"),
            "tcp:8765:interface=lab.example: the interface is an IP address,"
            " as 127.0.0.1 or ::1",
        )
        self.assertEqual(
            self.refused("tcp:127.0.0.1:8765"),
            "tcp:127.0.0.1:8765: the address to listen on is"
            " interface=127.0.0.1",
        )

    def test_the_port(self):
        for text in ("tcp", "tcp:", "tcp:port="):
            self.assertEqual(
                self.refused(text), f"{text} needs a port, as tcp:8765"
            )
        for text in ("tcp:http", "tcp:0", "tcp:65536", "tcp:-1", "tcp:８"):
            self.assertEqual(
                self.refused(text),
                f"{text}: the port is a number from 1 to 65535",
            )
        self.assertEqual(wire.parse_socket("tcp:65535").port, 65535)
        self.assertEqual(
            self.refused("tcp:8765:port=8766"),
            "tcp:8765:port=8766: port is given twice",
        )

    def test_the_keywords(self):
        self.assertEqual(
            self.refused("tcp:8765:backlog=5"),
            "tcp:8765:backlog=5: unknown keyword backlog; the keywords of tcp"
            " are port, interface, protocol and tokenFile",
        )
        self.assertEqual(
            self.refused("tcp:8765:host=lab.example"),
            "tcp:8765:host=lab.example: unknown keyword host; the keywords of"
            " tcp are port, interface, protocol and tokenFile",
        )
        self.assertEqual(
            self.refused("tcp:8765:tokenFile="),
            "tcp:8765:tokenFile=: tokenFile needs a file",
        )
        self.assertEqual(
            self.refused("unix:/tmp/a.sock:tokenFile=/tmp/t"),
            "unix:/tmp/a.sock:tokenFile=/tmp/t: unknown keyword tokenFile;"
            " the keywords of unix are address and protocol",
        )

    def test_to_talk_to(self):
        def parse(text):
            return wire.parse_socket(text, client=True)

        # this machine, as the socket it listens on
        self.assertEqual(parse("tcp:8765"), self.tcp(8765))
        self.assertEqual(
            parse("tcp:lab.example:8765"), self.tcp(8765, "lab.example")
        )
        self.assertEqual(
            parse("tcp:host=lab.example:port=8765"),
            self.tcp(8765, "lab.example"),
        )
        self.assertEqual(
            parse("tcp:lab.example:port=8765"), self.tcp(8765, "lab.example")
        )
        self.assertEqual(
            parse("tcp:8765:host=lab.example"), self.tcp(8765, "lab.example")
        )
        self.assertEqual(
            parse(r"tcp:\:\:1:8765:tokenFile=/tmp/t"),
            self.tcp(8765, "::1", token_file="/tmp/t"),
        )
        self.assertEqual(
            self.refused("tcp:8765:interface=192.0.2.7", client=True),
            "tcp:8765:interface=192.0.2.7: --command reaches the machine of"
            " host=, as tcp:lab.example:8765; interface= is where"
            " Virtualbricks listens",
        )
        self.assertEqual(
            self.refused("tcp:lab.example", client=True),
            "tcp:lab.example: the port is a number from 1 to 65535",
        )
        self.assertEqual(
            self.refused("tcp:a:b:8765", client=True),
            "tcp:a:b:8765: one host and one port, as tcp:HOST:PORT",
        )
        self.assertEqual(
            self.refused("tcp::8765", client=True),
            "tcp::8765 needs a host, as tcp:lab.example:8765",
        )

    def test_names(self):
        socket = wire.parse_socket(r"tcp:8765:interface=\:\:1")
        self.assertEqual(socket.where(), "::1 port 8765")
        self.assertEqual(socket.name(), "tcp ::1 port 8765")
        self.assertTrue(socket.uses_token())
        socket = wire.Socket("/tmp/lab.sock")
        self.assertEqual(socket.where(), "/tmp/lab.sock")
        self.assertEqual(socket.name(), "/tmp/lab.sock")
        self.assertFalse(socket.uses_token())


class TestSslDescriptions(unittest.TestCase):
    """The ssl sockets: those of tcp, with certificates."""

    def refused(self, text, client=False):
        return str(
            self.assertRaises(ValueError, wire.parse_socket, text, client)
        )

    def test_to_listen_on(self):
        socket = wire.parse_socket("ssl:8765:privateKey=~/vb/lab.pem")
        self.assertEqual(
            socket,
            wire.Socket(
                None,
                "text",
                "ssl",
                "127.0.0.1",
                8765,
                private_key="~/vb/lab.pem",
            ),
        )
        self.assertTrue(socket.uses_token())
        self.assertEqual(socket.files(), {"privateKey": "~/vb/lab.pem"})
        # across the network, and certificates in place of the token
        socket = wire.parse_socket(
            "ssl:8765:interface=0.0.0.0:privateKey=/vb/lab.key"
            ":certKey=/vb/lab.pem:extraCertChain=/vb/chain.pem"
            ":caCertsDir=/vb/clients:protocol=amp"
        )
        self.assertEqual(
            socket,
            wire.Socket(
                None,
                "amp",
                "ssl",
                "0.0.0.0",
                8765,
                None,
                "/vb/lab.key",
                "/vb/lab.pem",
                "/vb/chain.pem",
                "/vb/clients",
            ),
        )
        self.assertFalse(socket.uses_token())
        self.assertEqual(socket.name(), "ssl 0.0.0.0 port 8765")

    def test_its_key(self):
        self.assertEqual(
            self.refused("ssl:8765"),
            "ssl:8765 needs privateKey=FILE, the key of its certificate",
        )
        self.assertEqual(
            self.refused("ssl:8765:privateKey="),
            "ssl:8765:privateKey=: privateKey needs a file",
        )
        self.assertEqual(
            self.refused("ssl:8765:privateKey=/k:sslmethod=TLSv1_METHOD"),
            "ssl:8765:privateKey=/k:sslmethod=TLSv1_METHOD: unknown keyword"
            " sslmethod; the keywords of ssl are port, interface, protocol,"
            " tokenFile, privateKey, certKey, extraCertChain and caCertsDir",
        )

    def test_to_talk_to(self):
        def parse(text):
            return wire.parse_socket(text, client=True)

        self.assertEqual(
            parse("ssl:lab.example:8765:caCertsDir=/vb/lab"),
            wire.Socket(
                None, "text", "ssl", "lab.example", 8765, ca_dir="/vb/lab"
            ),
        )
        self.assertEqual(
            parse("ssl:8765:privateKey=/vb/alice.key:certKey=/vb/alice.pem"),
            wire.Socket(
                None,
                "text",
                "ssl",
                "127.0.0.1",
                8765,
                private_key="/vb/alice.key",
                cert="/vb/alice.pem",
            ),
        )
        self.assertEqual(
            self.refused("ssl:lab:8765:extraCertChain=/c", client=True),
            "ssl:lab:8765:extraCertChain=/c: unknown keyword extraCertChain;"
            " the keywords of ssl are host, port, protocol, tokenFile,"
            " caCertsDir, privateKey and certKey",
        )


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
        self.assertTrue(wire.in_runtime_dir(locations.control_socket()))
        self.assertTrue(wire.in_runtime_dir(os.path.join(folder, "a.sock")))
        self.assertFalse(
            wire.in_runtime_dir(os.path.join(folder, "lab1", "a"))
        )
        self.assertFalse(wire.in_runtime_dir("/tmp/lab.sock"))
