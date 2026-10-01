# -*- test-case-name: virtualbricks.tests.console.test_ampwire -*-
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
The commands of the AMP socket: what a program written with Twisted needs
to drive the Virtualbricks that runs. It loads no reactor and nothing else
of Virtualbricks, so that a program can import it, or copy it.

A Virtualbricks started with ``--listen unix:PATH`` answers them on
PATH::

    endpoint = endpoints.UNIXClientEndpoint(reactor, PATH)
    vb = await endpoints.connectProtocol(endpoint, amp.AMP())
    answer = await vb.callRemote(Run, line="brick start sw1")

``Hello`` says who answers, and agrees on the protocol of the connection:
the highest of ``protocols``, those the program speaks, that Virtualbricks
speaks too; 1 without them. ``Run`` runs a line of the console and answers
its lines; the paths of the command are read from ``cwd``, from the folder
of Virtualbricks without it. The requests of a connection run one after the
other. Protocol 2 adds a typed command for each command of the console, in
:mod:`virtualbricks.console.ampcommands`.

A tcp socket answers once the program proves that it knows the token, with
:func:`authenticate`, which calls ``Challenge`` and ``Authenticate``::

    endpoint = endpoints.TCP4ClientEndpoint(reactor, "127.0.0.1", 8766)
    vb = await endpoints.connectProtocol(endpoint, amp.AMP())
    await authenticate(vb, token)
"""

import hmac
import secrets

from twisted.protocols import amp

# The protocols that Virtualbricks speaks, for Hello to agree on: 1, these
# commands, and the typed commands of ampcommands.PROTOCOL.
PROTOCOLS = (1, 2)


class CommandFailed(Exception):
    """The command wasn't done, or failed on the way."""


class AnswerTooLong(Exception):
    """The command was done; its answer doesn't fit in AMP."""


class TokenNeeded(Exception):
    """The socket answers once the program proves that it knows the token."""


class WrongToken(Exception):
    """The proof doesn't match the token, or the socket takes none."""


class Hello(amp.Command):
    """Who answers, and the protocol the connection speaks from now on."""

    arguments = [(b"protocols", amp.ListOf(amp.Integer(), optional=True))]
    response = [
        (b"protocol", amp.Integer()),
        (b"version", amp.Unicode()),
        (b"pid", amp.Integer()),
        (b"project", amp.Unicode(optional=True)),
    ]
    errors = {TokenNeeded: b"TOKEN_NEEDED"}


class Run(amp.Command):
    """A line of the console, and its answer."""

    arguments = [
        (b"line", amp.Unicode()),
        (b"cwd", amp.Unicode(optional=True)),
    ]
    response = [(b"lines", amp.ListOf(amp.Unicode()))]
    errors = {
        CommandFailed: b"COMMAND_FAILED",
        AnswerTooLong: b"ANSWER_TOO_LONG",
        TokenNeeded: b"TOKEN_NEEDED",
    }


class Challenge(amp.Command):
    """The nonce of Virtualbricks, to prove the token over."""

    response = [(b"nonce", amp.Unicode())]
    errors = {WrongToken: b"WRONG_TOKEN"}


class Authenticate(amp.Command):
    """The nonce and the proof of the program; the proof of Virtualbricks."""

    arguments = [(b"nonce", amp.Unicode()), (b"proof", amp.Unicode())]
    response = [(b"proof", amp.Unicode())]
    errors = {WrongToken: b"WRONG_TOKEN"}


def proof(token, side, server_nonce, client_nonce):
    """
    The proof that side, "client" or "server", knows token: the HMAC-SHA256
    of both nonces under the token, in hex.
    """

    message = f"virtualbricks {side} {server_nonce} {client_nonce}"
    return hmac.new(token.encode(), message.encode(), "sha256").hexdigest()


async def authenticate(vb, token):
    """
    Prove to the Virtualbricks of vb, an AMP connection, that the program
    knows token; raise WrongToken if either end doesn't know it.
    """

    mine = secrets.token_hex(32)
    theirs = (await vb.callRemote(Challenge))["nonce"]
    answer = await vb.callRemote(
        Authenticate, nonce=mine, proof=proof(token, "client", theirs, mine)
    )
    expected = proof(token, "server", theirs, mine)
    if not hmac.compare_digest(answer["proof"].encode(), expected.encode()):
        raise WrongToken("The other end doesn't know the token")
