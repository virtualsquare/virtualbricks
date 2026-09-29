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


TOKEN = "0123456789abcdef"


class FakeVirtualbricks:
    """
    A Virtualbricks that listens on path in a thread, or on a free tcp port
    of this machine without it: it greets, keeps the requests, and gives the
    answers in order; it closes when they are over.

    With a token, it asks for the proof first, and refuses a wrong one; with
    lie too, it doesn't know the token and sends a proof of its own.
    """

    def __init__(
        self, test, path, *answers, greeting=GREETING, token=None, lie=False
    ):
        self.answers = list(answers)
        self.greeting = greeting
        self.token = token
        self.lie = lie
        self.requests = []
        if path is None:
            self.server = socket.socket(socket.AF_INET)
            self.server.bind(("127.0.0.1", 0))
            self.port = self.server.getsockname()[1]
            self.target = wire.Socket(
                None, "text", "tcp", "127.0.0.1", self.port
            )
        else:
            self.server = socket.socket(socket.AF_UNIX)
            self.server.bind(path)
            self.target = wire.Socket(path)
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
            greeting = self.greeting
            if self.token is not None:
                greeting = self.prove(conn, reader)
                if greeting is None:
                    return
            if isinstance(greeting, bytes):
                conn.sendall(greeting)
            else:
                conn.sendall(wire.encode(greeting))
            while self.answers:
                line = reader.readline()
                if not line:
                    return
                self.requests.append(wire.decode(line))
                conn.sendall(wire.encode(self.answers.pop(0)))

    def prove(self, conn, reader):
        nonce = wire.new_nonce()
        conn.sendall(wire.encode(wire.challenge(nonce)))
        line = reader.readline()
        if not line:
            return None
        self.requests.append(wire.decode(line))
        theirs, given = wire.read_proof(line)
        if given != wire.proof(self.token, "client", nonce, theirs):
            conn.sendall(wire.encode(wire.refusal("Wrong token")))
            return None
        proof = wire.proof(self.token, "server", nonce, theirs)
        if self.lie:
            proof = wire.proof("fedcba9876543210", "server", nonce, theirs)
        return dict(self.greeting, proof=proof)

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

    def main(self, *words, stdin="", path=None, target=None):
        if path is not None:
            target = wire.Socket(path)
        return client.main(
            list(words), target, io.StringIO(stdin), self.stdout, self.stderr
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
            "No Virtualbricks of yours runs. Start one with a socket, as"
            " virtualbricks --no-gui --socket\n",
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
            f" {self.path}: it was started without --socket or with another"
            " one, or its log says why\n",
        )

    def test_the_default_path_given(self):
        # --socket alone gives the path in the runtime folder: the messages
        # are those of no --socket
        self.assertEqual(
            self.unanswered(path=self.path),
            "No Virtualbricks of yours runs. Start one with a socket, as"
            " virtualbricks --no-gui --socket\n",
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
            "No Virtualbricks of yours runs. Start one with a socket, as"
            " virtualbricks --no-gui --socket\n",
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


class TestTcp(ClientTestCase):
    """--command over tcp, with the token."""

    def setUp(self):
        super().setUp()
        self.token_file = locations.token_file()
        self.write_token(self.token_file)

    def write_token(self, path, text=TOKEN, mode=0o600):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as file:
            file.write(text + "\n")
        os.chmod(path, mode)

    def unanswered(self, target, *words):
        status = self.main(*(words or ["status"]), target=target)
        self.assertEqual(status, client.UNANSWERED)
        self.assertEqual(self.stdout.getvalue(), "")
        return self.stderr.getvalue()

    def test_the_proof(self):
        server = FakeVirtualbricks(
            self, None, wire.answer(["sw1 runs"]), token=TOKEN
        )
        status = self.main("brick", "start", "sw1", target=server.target)
        self.assertOutput(status, "sw1 runs\n")
        proof, request = server.requests
        self.assertEqual(sorted(proof), ["nonce", "proof"])
        self.assertNotIn(TOKEN, str(proof))
        # this machine: the folder goes with the request
        self.assertEqual(request, wire.request("brick start sw1", os.getcwd()))

    def test_another_token_file(self):
        path = os.path.join(self.mktemp(), "lab1.token")
        self.write_token(path, "fedcba9876543210")
        server = FakeVirtualbricks(
            self, None, wire.answer([]), token="fedcba9876543210"
        )
        target = server.target._replace(token_file=path)
        self.assertOutput(self.main("status", target=target), "")

    def test_no_token_asked(self):
        # a socket that doesn't ask for it, as ssl with certificates
        server = FakeVirtualbricks(self, None, wire.answer(["Nothing runs"]))
        status = self.main("status", target=server.target)
        self.assertOutput(status, "Nothing runs\n")

    def test_another_token(self):
        server = FakeVirtualbricks(
            self, None, wire.answer([]), token="fedcba9876543210"
        )
        self.assertEqual(
            self.unanswered(server.target),
            f"The Virtualbricks on 127.0.0.1 port {server.port} has another"
            " token\n",
        )

    def test_an_end_without_the_token(self):
        server = FakeVirtualbricks(
            self, None, wire.answer([]), token=TOKEN, lie=True
        )
        self.assertEqual(
            self.unanswered(server.target),
            f"What answers on 127.0.0.1 port {server.port} doesn't know your"
            " token: it isn't your Virtualbricks\n",
        )
        server.stop()
        # the command never went
        self.assertEqual(len(server.requests), 1)

    def test_no_token(self):
        os.remove(self.token_file)
        server = FakeVirtualbricks(self, None, wire.answer([]), token=TOKEN)
        self.assertEqual(
            self.unanswered(server.target),
            f"No token: {self.token_file} doesn't exist. Copy the one of the"
            " machine where Virtualbricks runs, or name another with"
            " tokenFile=\n",
        )

    def test_a_token_that_others_can_read(self):
        os.chmod(self.token_file, 0o644)
        server = FakeVirtualbricks(self, None, wire.answer([]), token=TOKEN)
        self.assertEqual(
            self.unanswered(server.target),
            f"Others can read or change {self.token_file}: chmod 600"
            f" {self.token_file}: no command sent\n",
        )

    def test_nothing_listens(self):
        free = socket.socket(socket.AF_INET)
        free.bind(("127.0.0.1", 0))
        port = free.getsockname()[1]
        free.close()
        target = wire.parse_socket(f"tcp:{port}", client=True)
        self.assertEqual(
            self.unanswered(target),
            f"Nothing listens on 127.0.0.1 port {port}. Start Virtualbricks"
            f" with --socket tcp:{port}\n",
        )

    def refuse(self, error):
        def create_connection(address, timeout):
            self.assertEqual(timeout, client.CONNECT_TIMEOUT)
            raise error

        self.patch(socket, "create_connection", create_connection)

    def test_another_machine(self):
        target = wire.parse_socket("tcp:lab.example:8765", client=True)
        self.refuse(ConnectionRefusedError(111, "Connection refused"))
        self.assertEqual(
            self.unanswered(target),
            "Nothing listens on lab.example port 8765\n",
        )
        self.stderr.truncate(0)
        self.stderr.seek(0)
        self.refuse(socket.gaierror(-2, "Name or service not known"))
        self.assertEqual(
            self.unanswered(target),
            "Can't find lab.example: Name or service not known\n",
        )
        self.stderr.truncate(0)
        self.stderr.seek(0)
        self.refuse(TimeoutError())
        self.assertEqual(
            self.unanswered(target),
            "lab.example port 8765 didn't answer in 10 seconds\n",
        )

    def test_no_greeting(self):
        # it connects, and says nothing
        self.patch(client, "CONNECT_TIMEOUT", 0.1)
        server = socket.socket(socket.AF_INET)
        self.addCleanup(server.close)
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]
        target = wire.parse_socket(f"tcp:{port}", client=True)
        self.assertEqual(
            self.unanswered(target),
            f"127.0.0.1 port {port} didn't answer in 0.1 seconds\n",
        )

    def test_the_folder_stays_here(self):
        # another machine reads the paths from its own folder
        server = FakeVirtualbricks(self, None, wire.answer([]), token=TOKEN)
        self.patch(client.Connection, "local", lambda self: False)
        self.assertOutput(self.main("status", target=server.target), "")
        self.assertEqual(server.requests[1], wire.request("status"))


class TestTheProcess(unittest.TestCase):

    def test_no_reactor_and_no_gtk(self):
        # virtualbricks --command, up to the answer: here there is none
        path = os.path.join(short_folder(self), "lab.sock")
        code = (
            "import sys\n"
            "from virtualbricks.scripts import virtualbricks\n"
            f"sys.argv = ['virtualbricks', '--socket', 'unix:{path}',"
            " '--command',"
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
