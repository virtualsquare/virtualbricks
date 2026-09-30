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

"""The commands of the AMP socket, for the programs that import them."""

import subprocess
import sys

from twisted.internet import defer
from twisted.protocols import amp
from twisted.test import iosim
from twisted.trial import unittest

from virtualbricks.console import ampcommands, ampwire, wire


class TestTheImport(unittest.TestCase):

    def test_what_it_loads(self):
        # a program imports the commands: no reactor, no GTK, and nothing of
        # Virtualbricks but its packages
        code = (
            "import sys\n"
            "from virtualbricks.console import ampwire\n"
            "print('twisted.internet.reactor' in sys.modules,"
            " 'gi' in sys.modules)\n"
            "print(sorted(name for name in sys.modules"
            " if name.startswith('virtualbricks')))\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            encoding="utf-8",
            check=True,
        )
        self.assertEqual(
            result.stdout.splitlines(),
            [
                "False False",
                "['virtualbricks', 'virtualbricks.console',"
                " 'virtualbricks.console.ampwire']",
            ],
        )


class TestTheProof(unittest.TestCase):

    def test_as_the_text_socket(self):
        nonce, mine = wire.new_nonce(), wire.new_nonce()
        for side in ("client", "server"):
            self.assertEqual(
                ampwire.proof("0123456789abcdef", side, nonce, mine),
                wire.proof("0123456789abcdef", side, nonce, mine),
            )


class Liar(amp.AMP):
    """An end that doesn't know the token, and proves something else."""

    @ampwire.Challenge.responder
    def challenge(self):
        return {"nonce": wire.new_nonce()}

    @ampwire.Authenticate.responder
    def authenticate(self, nonce, proof):
        return {"proof": wire.new_nonce()}


class TestAuthenticate(unittest.TestCase):

    def test_an_end_without_the_token(self):
        program, liar, pump = iosim.connectedServerAndClient(Liar, amp.AMP)
        done = defer.ensureDeferred(
            ampwire.authenticate(program, "0123456789abcdef")
        )
        pump.flush()
        failure = self.failureResultOf(done, ampwire.WrongToken)
        self.assertEqual(
            failure.getErrorMessage(), "The other end doesn't know the token"
        )


class OlderHello(amp.Command):
    """Hello as Virtualbricks 2.1 declares it: no arguments."""

    commandName = b"Hello"
    response = ampwire.Hello.response


class Older(amp.AMP):
    """A Virtualbricks that speaks protocol 1 only."""

    @OlderHello.responder
    def hello(self):
        return {"protocol": 1, "version": "2.1.0", "pid": 1, "project": None}


class TestTheProtocols(unittest.TestCase):

    def test_the_typed_commands(self):
        self.assertEqual(ampwire.PROTOCOLS, (1, ampcommands.PROTOCOL))

    def test_an_older_virtualbricks(self):
        # it ignores the protocols of the program, and answers 1
        program, older, pump = iosim.connectedServerAndClient(Older, amp.AMP)
        answer = program.callRemote(ampwire.Hello, protocols=[2])
        pump.flush()
        self.assertEqual(self.successResultOf(answer)["protocol"], 1)
