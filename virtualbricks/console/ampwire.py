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

A Virtualbricks started with ``--socket unix:PATH:protocol=amp`` answers
them on PATH::

    endpoint = endpoints.UNIXClientEndpoint(reactor, PATH)
    vb = await endpoints.connectProtocol(endpoint, amp.AMP())
    answer = await vb.callRemote(Run, line="brick start sw1")

``Hello`` says who answers. ``Run`` runs a line of the console and answers
its lines; the paths of the command are read from ``cwd``, from the folder
of Virtualbricks without it. The requests of a connection run one after the
other.
"""

from twisted.protocols import amp

# The version of the commands, in the answer to Hello: a command that
# changes gets a new name, and this number.
PROTOCOL = 1


class CommandFailed(Exception):
    """The command wasn't done, or failed on the way."""


class AnswerTooLong(Exception):
    """The command was done; its answer doesn't fit in AMP."""


class Hello(amp.Command):
    """Who answers."""

    response = [
        (b"protocol", amp.Integer()),
        (b"version", amp.Unicode()),
        (b"pid", amp.Integer()),
        (b"project", amp.Unicode(optional=True)),
    ]


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
    }
