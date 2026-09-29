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

"""virtualbricks --command: a command sent to the Virtualbricks that runs."""

import io
import os
import shlex
import socket
import subprocess
import sys
import threading

from twisted.trial import unittest

from virtualbricks import locations, locks
from virtualbricks.console import client, wire
from virtualbricks.tests import hold_lock, isolate, make_socket, short_folder

GREETING = wire.greeting("2.1.0", 4200, "lab1")


class FakeVirtualbricks:
    """
    A Virtualbricks that listens on path in a thread: it greets, keeps the
    requests, and gives the answers in order; it closes when they are over.
    """

    def __init__(self, test, path, *answers, greeting=GREETING):
        self.answers = list(answers)
        self.greeting = greeting
        self.requests = []
        self.server = socket.socket(socket.AF_UNIX)
        self.server.bind(path)
        self.server.listen(1)
        self.thread = threading.Thread(target=self.serve, daemon=True)
        self.thread.start()
        test.addCleanup(self.stop)

    def serve(self):
        try:
            conn, _ = self.server.accept()
        except OSError:
            # stopped before anyone connected
            return
        with conn, conn.makefile("rb") as reader:
            if isinstance(self.greeting, bytes):
                conn.sendall(self.greeting)
            else:
                conn.sendall(wire.encode(self.greeting))
            while self.answers:
                line = reader.readline()
                if not line:
                    return
                self.requests.append(wire.decode(line))
                conn.sendall(wire.encode(self.answers.pop(0)))

    def stop(self):
        self.server.close()
        self.thread.join(5)


class ClientTestCase(unittest.TestCase):

    def setUp(self):
        isolate(self)
        # the runtime folder, and a socket there, where a path fits
        os.environ["XDG_RUNTIME_DIR"] = short_folder(self)
        locations.ensure_private_dir(locations.runtime_dir())
        self.path = locations.control_socket()
        self.stdout = io.StringIO()
        self.stderr = io.StringIO()

    def main(self, *words, stdin="", path=None):
        return client.main(
            list(words), path, io.StringIO(stdin), self.stdout, self.stderr
        )

    def assertOutput(self, status, stdout, stderr=""):
        self.assertEqual(
            (status, self.stdout.getvalue(), self.stderr.getvalue()),
            (status, stdout, stderr),
        )


class TestCommands(ClientTestCase):

    def test_a_command(self):
        words = [
            "brick",
            "set",
            "vm1",
            "kernel_command_line=console=ttyS0 root=/dev/vda",
        ]
        server = FakeVirtualbricks(self, self.path, wire.answer(["done", "è"]))
        status = self.main(*words)
        self.assertOutput(status, "done\nè\n")
        self.assertEqual(status, client.DONE)
        [request] = server.requests
        self.assertEqual(request["cwd"], os.getcwd())
        # quoted again: the console reads the same words
        self.assertEqual(shlex.split(request["line"]), words)

    def test_a_command_that_fails(self):
        FakeVirtualbricks(
            self, self.path, wire.refusal("vm2: no image", ["vm1 runs"])
        )
        status = self.main("brick", "start", "vm1", "vm2")
        self.assertOutput(status, "vm1 runs\n", "Error: vm2: no image\n")
        self.assertEqual(status, client.FAILED)

    def test_the_standard_input(self):
        server = FakeVirtualbricks(
            self,
            self.path,
            wire.answer(["sw1 runs"]),
            wire.answer([]),
            wire.refusal("No brick named vm9"),
            wire.answer(["never"]),
        )
        stdin = "brick start sw1\n\n# vm1\nbrick start vm9\nbrick start vm2\n"
        status = self.main(stdin=stdin)
        # blank lines aren't sent; the first error stops, with its line
        self.assertEqual(
            [request["line"] for request in server.requests],
            ["brick start sw1", "# vm1", "brick start vm9"],
        )
        self.assertOutput(
            status, "sw1 runs\n", "Error: line 4: No brick named vm9\n"
        )
        self.assertEqual(status, client.FAILED)

    def test_another_path(self):
        path = os.path.join(short_folder(self), "lab.sock")
        FakeVirtualbricks(self, path, wire.answer(["Nothing runs"]))
        self.assertOutput(self.main("status", path=path), "Nothing runs\n")

    def test_interrupted(self):
        FakeVirtualbricks(self, self.path, wire.answer([]))

        def interrupt(*args):
            raise KeyboardInterrupt()

        self.patch(client.Connection, "ask", interrupt)
        status = self.main("brick", "start", "vm1")
        self.assertOutput(status, "")
        self.assertEqual(status, client.INTERRUPTED)


class TestUnanswered(ClientTestCase):

    def unanswered(self, *words, path=None):
        status = self.main(*(words or ["status"]), path=path)
        self.assertEqual(status, client.UNANSWERED)
        self.assertEqual(self.stdout.getvalue(), "")
        return self.stderr.getvalue()

    def test_no_virtualbricks(self):
        self.assertEqual(
            self.unanswered(),
            "No Virtualbricks of yours runs. Start one, as virtualbricks"
            " --no-gui\n",
        )

    def test_another_users(self):
        self.patch(
            locks,
            "holders",
            lambda path: (
                ((4242, "bob"), (4250, "carol"))
                if path == locations.SYSTEM_LOCK_FILE
                else ()
            ),
        )
        self.assertEqual(
            self.unanswered(),
            "No Virtualbricks of yours runs; those on this machine are"
            " processes 4242 of bob and 4250 of carol\n",
        )

    def test_yours_without_the_socket(self):
        # yours runs, with another --socket or none
        hold_lock(self, locks.USER)
        self.assertEqual(
            self.unanswered(),
            f"Your Virtualbricks, process {os.getpid()}, doesn't listen on"
            f" {self.path}: it has another --socket, or its log says why\n",
        )

    def test_nothing_at_another_path(self):
        path = os.path.join(short_folder(self), "lab.sock")
        self.assertEqual(
            self.unanswered(path=path), f"No Virtualbricks listens on {path}\n"
        )

    def test_left_by_a_crash(self):
        make_socket(self.path)
        self.assertEqual(
            self.unanswered(),
            "No Virtualbricks of yours runs. Start one, as virtualbricks"
            " --no-gui\n",
        )

    def test_not_a_socket(self):
        open(self.path, "w").close()
        self.assertEqual(
            self.unanswered(), f"{self.path} isn't a socket: no command sent\n"
        )

    def test_not_yours(self):
        make_socket(self.path)
        uid = os.getuid()
        self.patch(os, "getuid", lambda: uid + 1)
        self.assertEqual(
            self.unanswered(), f"{self.path} isn't yours: no command sent\n"
        )

    def test_a_folder_others_can_write_in(self):
        make_socket(self.path)
        folder = os.path.dirname(self.path)
        os.chmod(folder, 0o777)
        self.assertEqual(
            self.unanswered(),
            f"Others can write in the runtime folder {folder}: no command"
            " sent\n",
        )

    def test_another_protocol(self):
        greeting = dict(GREETING, protocol=2, version="9.0")
        server = FakeVirtualbricks(
            self, self.path, wire.answer([]), greeting=greeting
        )
        self.assertEqual(
            self.unanswered(),
            "The Virtualbricks that runs, version 9.0, speaks another"
            " protocol: restart it\n",
        )
        server.stop()
        self.assertEqual(server.requests, [])

    def test_not_the_protocol(self):
        FakeVirtualbricks(self, self.path, greeting=b"SSH-2.0-OpenSSH\n")
        self.assertEqual(
            self.unanswered(),
            "What answers on the socket doesn't speak its protocol\n",
        )

    def test_closed_before_the_answer(self):
        # it greets, and ends: before the request comes, or after
        for end in (
            socket.socket.close,
            lambda sock: sock.shutdown(socket.SHUT_WR),
        ):
            mine, theirs = socket.socketpair()
            self.addCleanup(mine.close)
            self.addCleanup(theirs.close)
            theirs.sendall(wire.encode(GREETING))
            connection = client.Connection(mine)
            end(theirs)
            error = self.assertRaises(
                client.Unanswered, connection.ask, "status"
            )
            self.assertEqual(
                str(error),
                "Virtualbricks closed the connection before it answered: it"
                " may have ended",
            )


class TestTheProcess(unittest.TestCase):

    def test_no_reactor_and_no_gtk(self):
        # virtualbricks --command, up to the answer: here there is none
        path = os.path.join(short_folder(self), "lab.sock")
        code = (
            "import sys\n"
            "from virtualbricks.scripts import virtualbricks\n"
            f"sys.argv = ['virtualbricks', '--socket', {path!r}, '--command',"
            " 'status']\n"
            "try:\n"
            "    virtualbricks.run()\n"
            "except SystemExit as exc:\n"
            "    print(exc.code, 'twisted.internet.reactor' in sys.modules,"
            " 'gi' in sys.modules)\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            encoding="utf-8",
            check=True,
            stdin=subprocess.DEVNULL,
        )
        self.assertEqual(result.stdout, "2 False False\n")
        self.assertEqual(
            result.stderr, f"No Virtualbricks listens on {path}\n"
        )
