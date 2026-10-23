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

"""The descriptions of the sockets of --listen and --connect."""

from twisted.trial import unittest

from virtualbricks import sockets


class TestDescriptions(unittest.TestCase):

    def refused(self, text):
        return str(self.assertRaises(ValueError, sockets.parse_socket, text))

    def test_a_path(self):
        parse = sockets.parse_socket
        self.assertEqual(
            parse("unix:/tmp/lab.sock"),
            sockets.Socket("/tmp/lab.sock", "amp", "unix"),
        )
        self.assertEqual(
            parse("unix:~/lab.sock"), sockets.Socket("~/lab.sock")
        )
        self.assertEqual(
            parse("unix:address=lab.sock"), sockets.Socket("lab.sock")
        )
        self.assertEqual(
            parse("UNIX:/tmp/lab.sock"), sockets.Socket("/tmp/lab.sock")
        )

    def test_the_protocol(self):
        parse = sockets.parse_socket
        self.assertEqual(
            parse("unix:/tmp/lab.sock:protocol=json"),
            sockets.Socket("/tmp/lab.sock", "json"),
        )
        self.assertEqual(
            parse("unix:protocol=JSON:address=/tmp/lab.sock"),
            sockets.Socket("/tmp/lab.sock", "json"),
        )
        self.assertEqual(
            parse("unix:/tmp/lab.amp:protocol=amp"),
            sockets.Socket("/tmp/lab.amp", "amp"),
        )
        self.assertEqual(
            parse("unix:/tmp/lab.amp:protocol=AMP"),
            sockets.Socket("/tmp/lab.amp", "amp"),
        )
        self.assertEqual(
            self.refused("unix:/tmp/lab.sock:protocol=text"),
            "unix:/tmp/lab.sock:protocol=text: the protocol is json or amp",
        )

    def test_the_rules_of_twisted(self):
        parse = sockets.parse_socket
        # a backslash makes the next character plain
        self.assertEqual(
            parse(r"unix:/tmp/a\:b.sock"), sockets.Socket("/tmp/a:b.sock")
        )
        self.assertEqual(
            parse(r"unix:/tmp/a\\b.sock"), sockets.Socket(r"/tmp/a\b.sock")
        )
        self.assertEqual(
            parse(r"unix:/tmp/a\=b.sock"), sockets.Socket("/tmp/a=b.sock")
        )
        # the first = of a part only
        self.assertEqual(
            parse("unix:address=/tmp/a=b.sock"),
            sockets.Socket("/tmp/a=b.sock"),
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
            self.refused("protocol=json"),
            "protocol=json needs its type and its path, as"
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
            self.refused("unix:/tmp/a.sock:protocol=json:protocol=json"),
            "unix:/tmp/a.sock:protocol=json:protocol=json: protocol is given"
            " twice",
        )


class TestTcpDescriptions(unittest.TestCase):
    """The tcp sockets to listen on, and those that --command talks to."""

    def refused(self, text, client=False):
        return str(
            self.assertRaises(ValueError, sockets.parse_socket, text, client)
        )

    def tcp(self, port, host="127.0.0.1", protocol="amp", token_file=None):
        return sockets.Socket(None, protocol, "tcp", host, port, token_file)

    def test_to_listen_on(self):
        parse = sockets.parse_socket
        self.assertEqual(parse("tcp:8765"), self.tcp(8765))
        self.assertEqual(parse("TCP:port=8765"), self.tcp(8765))
        self.assertEqual(
            parse("tcp:8765:protocol=json"), self.tcp(8765, protocol="json")
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
        self.assertEqual(sockets.parse_socket("tcp:65535").port, 65535)
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
            return sockets.parse_socket(text, client=True)

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
            "tcp:8765:interface=192.0.2.7: --connect reaches the machine of"
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
        socket = sockets.parse_socket(r"tcp:8765:interface=\:\:1")
        self.assertEqual(socket.where(), "::1 port 8765")
        self.assertEqual(socket.name(), "tcp ::1 port 8765")
        self.assertTrue(socket.uses_token())
        socket = sockets.Socket("/tmp/lab.sock")
        self.assertEqual(socket.where(), "/tmp/lab.sock")
        self.assertEqual(socket.name(), "/tmp/lab.sock")
        self.assertFalse(socket.uses_token())


class TestSslDescriptions(unittest.TestCase):
    """The ssl sockets: those of tcp, with certificates."""

    def refused(self, text, client=False):
        return str(
            self.assertRaises(ValueError, sockets.parse_socket, text, client)
        )

    def test_to_listen_on(self):
        socket = sockets.parse_socket("ssl:8765:privateKey=~/vb/lab.pem")
        self.assertEqual(
            socket,
            sockets.Socket(
                None,
                "amp",
                "ssl",
                "127.0.0.1",
                8765,
                private_key="~/vb/lab.pem",
            ),
        )
        self.assertTrue(socket.uses_token())
        self.assertEqual(socket.files(), {"privateKey": "~/vb/lab.pem"})
        # across the network, and certificates in place of the token
        socket = sockets.parse_socket(
            "ssl:8765:interface=0.0.0.0:privateKey=/vb/lab.key"
            ":certKey=/vb/lab.pem:extraCertChain=/vb/chain.pem"
            ":caCertsDir=/vb/clients:protocol=json"
        )
        self.assertEqual(
            socket,
            sockets.Socket(
                None,
                "json",
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
            return sockets.parse_socket(text, client=True)

        self.assertEqual(
            parse("ssl:lab.example:8765:caCertsDir=/vb/lab"),
            sockets.Socket(
                None, "amp", "ssl", "lab.example", 8765, ca_dir="/vb/lab"
            ),
        )
        self.assertEqual(
            parse("ssl:8765:privateKey=/vb/alice.key:certKey=/vb/alice.pem"),
            sockets.Socket(
                None,
                "amp",
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
