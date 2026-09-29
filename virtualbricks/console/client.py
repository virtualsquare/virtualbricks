# -*- test-case-name: virtualbricks.tests.console.test_client -*-
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
``virtualbricks --command``: a command of the console, sent to the
Virtualbricks that runs through its control socket, and its answer.

The words after ``--command`` are the command, quoted again for the
console; without words, the lines of the standard input are, each sent
after the answer to the one before, up to the first error. The answer goes
to the standard output, an error to the standard error. It loads neither
Twisted's reactor nor GTK, takes no lock and opens no project.
"""

from __future__ import annotations

import os
import pwd
import shlex
import socket
import sys

from virtualbricks import locations, locks
from virtualbricks.console import wire
from virtualbricks.i18n import _, ngettext

# The exit statuses: the command was done, it failed, nothing answered it.
DONE = 0
FAILED = 1
UNANSWERED = 2
# as a shell reports SIGINT
INTERRUPTED = 130


class Unanswered(Exception):
    """No Virtualbricks answered; str() says why, to the user."""


def _closed() -> str:
    return _(
        "Virtualbricks closed the connection before it answered: it may have"
        " ended"
    )


class Connection:
    """A connection to the control socket: requests and their answers."""

    def __init__(self, sock: socket.socket):
        self.sock = sock
        self.reader = sock.makefile("rb")
        try:
            self.greeting = self.receive()
            if self.greeting.get("protocol") != wire.PROTOCOL:
                raise Unanswered(
                    _(
                        "The Virtualbricks that runs, version {version},"
                        " speaks another protocol: restart it"
                    ).format(version=self.greeting.get("version"))
                )
        except BaseException:
            self.reader.close()
            raise

    def close(self):
        self.reader.close()
        self.sock.close()

    def receive(self) -> dict:
        try:
            line = self.reader.readline()
        except ConnectionResetError:
            line = b""
        if not line.endswith(b"\n"):
            raise Unanswered(_closed())
        try:
            return wire.decode(line)
        except ValueError:
            raise Unanswered(
                _("What answers on the socket doesn't speak its protocol")
            ) from None

    def ask(self, line: str, cwd: str | None = None) -> dict:
        """The answer to the command of line, whose paths are read in cwd."""

        try:
            self.sock.sendall(wire.encode(wire.request(line, cwd)))
        except (BrokenPipeError, ConnectionResetError):
            raise Unanswered(_closed()) from None
        return self.receive()


def _processes(holders) -> str:
    names = [f"{pid} of {user}" for pid, user in holders]
    if len(names) > 1:
        names[-2:] = [
            _("{one} and {other}").format(one=names[-2], other=names[-1])
        ]
    return ", ".join(names)


def _nobody(path: str, default: bool) -> str:
    """Why nothing answers on path: the Virtualbricks that runs, if any."""

    if not default:
        return _("No Virtualbricks listens on {path}").format(path=path)
    try:
        me = pwd.getpwuid(os.getuid()).pw_name
    except KeyError:
        # as locks names a user without a name
        me = str(os.getuid())
    holders = locks.holders(locations.SYSTEM_LOCK_FILE)
    holders += locks.holders(locations.user_lock_file())
    mine = [pid for pid, user in holders if user == me]
    if mine:
        return _(
            "Your Virtualbricks, process {pid}, doesn't listen on {path}: it"
            " has another --socket, or its log says why"
        ).format(pid=mine[0], path=path)
    theirs = [(pid, user) for pid, user in holders if user is not None]
    if theirs:
        return ngettext(
            "No Virtualbricks of yours runs; the one on this machine is"
            " process {processes}",
            "No Virtualbricks of yours runs; those on this machine are"
            " processes {processes}",
            len(theirs),
        ).format(processes=_processes(theirs))
    return _(
        "No Virtualbricks of yours runs. Start one, as virtualbricks --no-gui"
    )


def connect(path: str | None = None) -> Connection:
    """
    Connect to the Virtualbricks that listens on path, the socket in the
    runtime folder if None; raise Unanswered if none can be reached.
    """

    default = path is None
    if default:
        path = locations.control_socket()
    try:
        wire.check_length(path)
        there = wire.check_socket(path)
        if there:
            wire.check_path(path, default)
    except wire.Unusable as exc:
        raise Unanswered(
            _("{reason}: no command sent").format(reason=exc)
        ) from None
    if not there:
        raise Unanswered(_nobody(path, default))
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.connect(path)
        return Connection(sock)
    except (ConnectionRefusedError, FileNotFoundError):
        # a socket left by a crash
        sock.close()
        raise Unanswered(_nobody(path, default)) from None
    except OSError as exc:
        sock.close()
        raise Unanswered(f"{path}: {exc.strerror}") from None
    except BaseException:
        sock.close()
        raise


def _commands(words, stdin):
    """The commands to send, with the number of their line of input."""

    if words:
        yield None, shlex.join(words)
        return
    for number, line in enumerate(stdin, start=1):
        line = line.rstrip("\n")
        if line.strip():
            yield number, line


def main(words, path=None, stdin=None, stdout=None, stderr=None) -> int:
    """
    Send the command of words, or the lines of stdin without words, to the
    Virtualbricks that listens on path, the default socket if None; write
    the answers and return the exit status.
    """

    stdin = sys.stdin if stdin is None else stdin
    stdout = sys.stdout if stdout is None else stdout
    stderr = sys.stderr if stderr is None else stderr
    cwd = os.getcwd()
    connection = None
    try:
        connection = connect(path)
        for number, line in _commands(words, stdin):
            answer = connection.ask(line, cwd)
            for text in answer.get("lines", []):
                stdout.write(f"{text}\n")
            stdout.flush()
            if not answer.get("ok"):
                error = str(answer.get("error"))
                if number is not None:
                    error = _("line {number}: {error}").format(
                        number=number, error=error
                    )
                stderr.write(
                    _("Error: {message}").format(message=error) + "\n"
                )
                return FAILED
        return DONE
    except Unanswered as exc:
        stderr.write(f"{exc}\n")
        return UNANSWERED
    except KeyboardInterrupt:
        # the command goes on in Virtualbricks, as after Ctrl+C in its console
        return INTERRUPTED
    finally:
        if connection is not None:
            connection.close()
