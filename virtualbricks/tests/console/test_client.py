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

from twisted.protocols import amp
from twisted.trial import unittest

from virtualbricks import locations, locks
from virtualbricks.config.workspace import Workspace
from virtualbricks.console import ampbox, client, wire
from virtualbricks.tests import (
    DATA,
    hold_lock,
    isolate,
    make_socket,
    release,
    short_folder,
)

GREETING = wire.greeting("2.1.0", 4200, "lab1")
# The lines of the answer of Run.
LINES = amp.ListOf(amp.Unicode())


TOKEN = "0123456789abcdef"


class FakeVirtualbricks:
    """
    A Virtualbricks that listens on path in a thread, or on a free tcp port
    of this machine without it: it greets, keeps the requests, and gives the
    answers in order, in AMP or in the JSON protocol; it closes when they
    are over. A greeting of bytes is what something else sends first.

    With a token, the JSON protocol asks for the proof first, and refuses a
    wrong one; with lie too, it doesn't know the token and sends a proof of
    its own.
    """

    def __init__(
        self,
        test,
        path,
        *answers,
        greeting=GREETING,
        token=None,
        lie=False,
        protocol=wire.AMP,
    ):
        self.answers = list(answers)
        self.greeting = greeting
        self.token = token
        self.lie = lie
        self.protocol = protocol
        self.requests = []
        if path is None:
            self.server = socket.socket(socket.AF_INET)
            self.server.bind(("127.0.0.1", 0))
            self.port = self.server.getsockname()[1]
            self.target = wire.Socket(
                None, protocol, "tcp", "127.0.0.1", self.port
            )
        else:
            self.server = socket.socket(socket.AF_UNIX)
            self.server.bind(path)
            self.target = wire.Socket(path, protocol)
            # as a Virtualbricks that listens: the lock of the socket
            self.lock = locks.hold(locations.control_lock_file(path))
            test.addCleanup(release, self.lock)
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
            if self.protocol == wire.AMP:
                self.serve_amp(conn, reader)
            else:
                self.serve_text(conn, reader)

    def serve_text(self, conn, reader):
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

    def serve_amp(self, conn, reader):
        """Hello, then Run, each request a request of the JSON protocol."""

        if isinstance(self.greeting, bytes):
            conn.sendall(self.greeting)
            # as a JSON socket, it waits for a line until the client goes:
            # closed now, it could refuse the Hello that comes after
            reader.read()
            return
        while self.answers:
            try:
                box = ampbox.read(reader.read)
            except ampbox.Closed:
                return
            tag = box[ampbox.ASK]
            if box[ampbox.COMMAND] == b"Hello":
                conn.sendall(
                    ampbox.encode(
                        {
                            ampbox.ANSWER: tag,
                            b"protocol": b"%d" % self.greeting["protocol"],
                            b"version": self.greeting["version"].encode(),
                            b"pid": b"%d" % self.greeting["pid"],
                        }
                    )
                )
                continue
            cwd = box.get(b"cwd")
            self.requests.append(
                wire.request(box[b"line"].decode(), cwd and cwd.decode())
            )
            answer = self.answers.pop(0)
            if answer["ok"]:
                reply = {
                    ampbox.ANSWER: tag,
                    b"lines": LINES.toString(answer["lines"]),
                }
            else:
                reply = {
                    ampbox.ERROR: tag,
                    ampbox.ERROR_CODE: b"COMMAND_FAILED",
                    ampbox.ERROR_DESCRIPTION: answer["error"].encode(),
                }
            conn.sendall(ampbox.encode(reply))

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
        # wakes an accept() that waits: nobody connected
        try:
            self.server.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.server.close()
        self.thread.join(5)


class ClientTestCase(unittest.TestCase):

    def setUp(self):
        self.root = isolate(self)
        # the runtime folder, and a socket of a workspace there, where a
        # path fits
        os.environ["XDG_RUNTIME_DIR"] = short_folder(self)
        self.workspace = os.path.join(self.root, "labs")
        Workspace(self.workspace).make_runtime_dir()
        self.path = locations.control_socket(self.workspace)
        self.stdout = io.StringIO()
        self.stderr = io.StringIO()

    def main(self, *words, stdin="", path=None, target=None, workspace=None):
        if path is not None:
            target = wire.Socket(path)
        return client.main(
            list(words),
            target,
            io.StringIO(stdin),
            self.stdout,
            self.stderr,
            workspace=workspace,
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
        # what it did first doesn't come over AMP
        self.assertOutput(status, "", "Error: vm2: no image\n")
        self.assertEqual(status, client.FAILED)

    def test_a_command_that_fails_over_text(self):
        server = FakeVirtualbricks(
            self,
            self.path,
            wire.refusal("vm2: no image", ["vm1 runs"]),
            protocol=wire.JSON,
        )
        status = self.main(
            "brick", "start", "vm1", "vm2", target=server.target
        )
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

    def test_a_script(self):
        script = self.mktemp() + ".vb"
        with open(script, "w", encoding="utf-8") as fp:
            fp.write("brick start sw1\n\n# vm1\nbrick start vm9\nstatus\n")
        server = FakeVirtualbricks(
            self,
            self.path,
            wire.answer(["sw1 runs"]),
            wire.answer([]),
            wire.refusal("No brick named vm9"),
            wire.answer(["never"]),
        )
        status = client.main(
            [],
            None,
            io.StringIO("never read\n"),
            self.stdout,
            self.stderr,
            script=script,
        )
        # the lines of the file, not of the standard input; the first
        # error stops, where source says it
        self.assertEqual(
            [request["line"] for request in server.requests],
            ["brick start sw1", "# vm1", "brick start vm9"],
        )
        self.assertOutput(
            status, "sw1 runs\n", f"Error: {script}:4: No brick named vm9\n"
        )
        self.assertEqual(status, client.FAILED)

    def test_a_script_that_cannot_be_read(self):
        server = FakeVirtualbricks(self, self.path, wire.answer([]))
        script = os.path.join(self.mktemp(), "lab.vb")
        status = client.main(
            [], None, io.StringIO(), self.stdout, self.stderr, script=script
        )
        self.assertOutput(
            status,
            "",
            f"{script} can't be read: No such file or directory\n",
        )
        self.assertEqual(status, client.FAILED)
        self.assertEqual(server.requests, [])

    def test_another_path(self):
        path = os.path.join(short_folder(self), "lab.sock")
        FakeVirtualbricks(self, path, wire.answer(["Nothing runs"]))
        self.assertOutput(self.main("status", path=path), "Nothing runs\n")

    def test_interrupted(self):
        FakeVirtualbricks(self, self.path, wire.answer([]))

        def interrupt(*args):
            raise KeyboardInterrupt()

        self.patch(client.AMPConnection, "ask", interrupt)
        status = self.main("brick", "start", "vm1")
        self.assertOutput(status, "")
        self.assertEqual(status, client.INTERRUPTED)


class TestUnanswered(ClientTestCase):

    def unanswered(self, *words, path=None, workspace=None):
        status = self.main(
            *(words or ["status"]), path=path, workspace=workspace
        )
        self.assertEqual(status, client.UNANSWERED)
        self.assertEqual(self.stdout.getvalue(), "")
        return self.stderr.getvalue()

    def test_no_virtualbricks(self):
        self.assertEqual(
            self.unanswered(),
            "No Virtualbricks of yours runs. Start one with a socket, as"
            " virtualbricks --no-gui --listen\n",
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
        # yours runs, with another --listen or none
        hold_lock(self, locks.USER)
        self.assertEqual(
            self.unanswered(),
            f"Your Virtualbricks, process {os.getpid()}, doesn't listen: it"
            " was started without --listen or with another one, or its log"
            " says why\n",
        )
        # at the path of the socket of --listen alone
        self.stderr = io.StringIO()
        self.assertEqual(
            self.unanswered(path=self.path),
            f"Your Virtualbricks, process {os.getpid()}, doesn't listen on"
            f" {self.path}: it was started without --listen or with another"
            " one, or its log says why\n",
        )

    def test_the_default_path_given(self):
        # --listen alone gives the path in the runtime folder: the messages
        # are those of no --listen
        self.assertEqual(
            self.unanswered(path=self.path),
            "No Virtualbricks of yours runs. Start one with a socket, as"
            " virtualbricks --no-gui --listen\n",
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
            " virtualbricks --no-gui --listen\n",
        )

    def test_not_a_socket(self):
        open(self.path, "w").close()
        self.assertEqual(
            self.unanswered(workspace=self.workspace),
            f"{self.path} isn't a socket: no command sent\n",
        )

    def test_not_yours(self):
        make_socket(self.path)
        uid = os.getuid()
        self.patch(os, "getuid", lambda: uid + 1)
        self.assertEqual(
            self.unanswered(workspace=self.workspace),
            f"{self.path} isn't yours: no command sent\n",
        )

    def test_a_folder_others_can_write_in(self):
        make_socket(self.path)
        folder = os.path.dirname(self.path)
        os.chmod(folder, 0o777)
        self.assertEqual(
            self.unanswered(workspace=self.workspace),
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
            f"What answers on {self.path} doesn't speak AMP: if it speaks the"
            " JSON protocol, add protocol=json\n",
        )

    def test_a_text_socket(self):
        greeting = wire.encode(GREETING)
        FakeVirtualbricks(self, self.path, greeting=greeting)
        self.assertEqual(
            self.unanswered(),
            f"What answers on {self.path} doesn't speak AMP: if it speaks the"
            " JSON protocol, add protocol=json\n",
        )

    def test_not_the_text_protocol(self):
        server = FakeVirtualbricks(
            self, self.path, greeting=b"SSH-2.0-OpenSSH\n", protocol=wire.JSON
        )
        status = self.main("status", target=server.target)
        self.assertEqual(status, client.UNANSWERED)
        self.assertEqual(
            self.stderr.getvalue(),
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


class TestWorkspaces(ClientTestCase):
    """The socket of --listen alone of each workspace, and --workspace."""

    def setUp(self):
        super().setUp()
        self.other = os.path.join(self.root, "other")
        os.makedirs(self.other)
        Workspace(self.other).make_runtime_dir()
        self.other_path = locations.control_socket(self.other)

    def test_the_only_one_that_listens(self):
        # the other workspace has a socket left by a crash
        make_socket(self.other_path)
        FakeVirtualbricks(self, self.path, wire.answer(["Nothing runs"]))
        self.assertOutput(self.main("status"), "Nothing runs\n")

    def test_the_one_of_workspace(self):
        FakeVirtualbricks(self, self.path, wire.answer(["labs"]))
        FakeVirtualbricks(self, self.other_path, wire.answer(["other"]))
        status = self.main("status", workspace=self.other)
        self.assertOutput(status, "other\n")

    def test_several_listen(self):
        FakeVirtualbricks(self, self.path, wire.answer([]))
        FakeVirtualbricks(self, self.other_path, wire.answer([]))
        self.patch(sys, "argv", ["virtualbricks", "--command", "status"])
        status = self.main("status")
        self.assertEqual(status, client.UNANSWERED)
        # in the order of their keys
        places = sorted(
            [(self.path, "~/labs"), (self.other_path, "~/other")],
            key=lambda place: os.path.dirname(place[0]),
        )
        pid = os.getpid()
        self.assertOutput(
            status,
            "",
            "Virtualbricks of yours listen in 2 workspaces:"
            f" {places[0][1]} (process {pid}) and {places[1][1]} (process"
            f" {pid}). Name one with --workspace, as virtualbricks"
            f" --workspace {places[0][1]} --command status\n",
        )

    def test_the_socket_of_the_windows(self):
        # the only one that listens, or that of workspace
        FakeVirtualbricks(self, self.path)
        self.assertEqual(client.listening_socket(), self.path)
        FakeVirtualbricks(self, self.other_path)
        self.assertEqual(client.listening_socket(self.other), self.other_path)

    def test_no_socket_for_the_windows(self):
        error = self.assertRaises(
            client.Unanswered, client.listening_socket, self.other
        )
        self.assertEqual(
            str(error),
            "No Virtualbricks runs in ~/other. Start one with a socket, as"
            " virtualbricks --workspace ~/other --no-gui --listen",
        )
        # no command to speak of
        open(self.other_path, "w").close()
        error = self.assertRaises(
            client.Unanswered, client.listening_socket, self.other
        )
        self.assertEqual(str(error), f"{self.other_path} isn't a socket")

    def test_several_for_the_windows(self):
        FakeVirtualbricks(self, self.path)
        FakeVirtualbricks(self, self.other_path)
        self.patch(sys, "argv", ["virtualbricks", "--connect"])
        error = self.assertRaises(client.Unanswered, client.listening_socket)
        self.assertIn(
            "Name one with --workspace, as virtualbricks --workspace ~/",
            str(error),
        )
        self.assertTrue(str(error).endswith(" --connect"))

    def test_listening(self):
        server = FakeVirtualbricks(self, self.path)
        # a workspace whose link is gone, and files of the runtime folder
        os.unlink(os.path.join(os.path.dirname(self.other_path), ".workspace"))
        FakeVirtualbricks(self, self.other_path)
        hold_lock(self, locks.USER)
        found = sorted(client.listening())
        expected = sorted(
            [
                (self.path, self.workspace, [os.getpid()]),
                (self.other_path, None, [os.getpid()]),
            ]
        )
        self.assertEqual(found, expected)
        server.stop()
        release(server.lock)
        self.assertEqual(len(client.listening()), 1)

    def test_several_without_their_links(self):
        found = [
            ("/run/vb/aaaaaaaa/.control", None, []),
            ("/run/vb/bbbbbbbb/.control", None, [4300, 4400]),
        ]
        self.assertEqual(
            client._several(found, ["--command", "status"]),
            "Virtualbricks of yours listen in 2 workspaces: /run/vb/aaaaaaaa"
            " and /run/vb/bbbbbbbb (processes 4300, 4400)",
        )

    def test_nobody_in_the_workspace(self):
        status = self.main("status", workspace=self.other)
        self.assertOutput(
            status,
            "",
            "No Virtualbricks runs in ~/other. Start one with a socket, as"
            " virtualbricks --workspace ~/other --no-gui --listen\n",
        )
        self.assertEqual(status, client.UNANSWERED)

    def test_yours_in_the_workspace_without_the_socket(self):
        FakeVirtualbricks(self, self.path, wire.answer([]))
        hold_lock(self, locks.WORKSPACE, workspace=self.other)
        status = self.main("status", workspace=self.other)
        self.assertOutput(
            status,
            "",
            f"Your Virtualbricks in ~/other, process {os.getpid()}, doesn't"
            " listen: it was started without --listen, or its log says"
            " why\n",
        )

    def test_another_users_in_the_workspace(self):
        lock_file = locations.workspace_lock_file(self.other)
        self.patch(
            locks,
            "holders",
            lambda path: ((4242, "bob"),) if path == lock_file else (),
        )
        status = self.main("status", workspace=self.other)
        self.assertOutput(
            status,
            "",
            "No Virtualbricks of yours runs in ~/other; the one there is"
            " process 4242 of bob\n",
        )


class TestTcp(ClientTestCase):
    """
    --command over tcp, with the token of the JSON protocol; test_control
    proves it over AMP, to a Virtualbricks that listens.
    """

    def setUp(self):
        super().setUp()
        self.token_file = locations.token_file()
        self.write_token(self.token_file)

    def write_token(self, path, text=TOKEN, mode=0o600):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as file:
            file.write(text + "\n")
        os.chmod(path, mode)

    def fake(self, *answers, **kwargs):
        return FakeVirtualbricks(
            self, None, *answers, protocol=wire.JSON, **kwargs
        )

    def unanswered(self, target, *words):
        status = self.main(*(words or ["status"]), target=target)
        self.assertEqual(status, client.UNANSWERED)
        self.assertEqual(self.stdout.getvalue(), "")
        return self.stderr.getvalue()

    def test_the_proof(self):
        server = self.fake(wire.answer(["sw1 runs"]), token=TOKEN)
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
        server = self.fake(wire.answer([]), token="fedcba9876543210")
        target = server.target._replace(token_file=path)
        self.assertOutput(self.main("status", target=target), "")

    def test_no_token_asked(self):
        # a socket that doesn't ask for it, as ssl with certificates
        server = self.fake(wire.answer(["Nothing runs"]))
        status = self.main("status", target=server.target)
        self.assertOutput(status, "Nothing runs\n")

    def test_another_token(self):
        server = self.fake(wire.answer([]), token="fedcba9876543210")
        self.assertEqual(
            self.unanswered(server.target),
            f"The Virtualbricks on 127.0.0.1 port {server.port} has another"
            " token\n",
        )

    def test_an_end_without_the_token(self):
        server = self.fake(wire.answer([]), token=TOKEN, lie=True)
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
        server = self.fake(wire.answer([]), token=TOKEN)
        self.assertEqual(
            self.unanswered(server.target),
            f"No token: {self.token_file} doesn't exist. Copy the one of the"
            " machine where Virtualbricks runs, or name another with"
            " tokenFile=\n",
        )

    def test_a_token_that_others_can_read(self):
        os.chmod(self.token_file, 0o644)
        server = self.fake(wire.answer([]), token=TOKEN)
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
            f" with --listen tcp:{port}\n",
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
        server.listen(2)
        port = server.getsockname()[1]
        target = wire.parse_socket(f"tcp:{port}", client=True)
        self.assertEqual(
            self.unanswered(target),
            f"127.0.0.1 port {port} didn't answer in 0.1 seconds\n",
        )
        # an AMP socket waits for the first box
        self.stderr = io.StringIO()
        target = target._replace(protocol=wire.JSON)
        self.assertEqual(
            self.unanswered(target),
            f"127.0.0.1 port {port} didn't greet in 0.1 seconds: if it speaks"
            " AMP, leave out protocol=json\n",
        )

    def test_the_folder_stays_here(self):
        # another machine reads the paths from its own folder
        server = self.fake(wire.answer([]), token=TOKEN)
        self.patch(client.Connection, "local", lambda self: False)
        self.assertOutput(self.main("status", target=server.target), "")
        self.assertEqual(server.requests[1], wire.request("status"))


class TestSslFiles(ClientTestCase):
    """The files of --command over ssl, read before it connects."""

    def unanswered(self, **fields):
        target = wire.parse_socket("ssl:127.0.0.1:1", client=True)
        status = self.main("status", target=target._replace(**fields))
        self.assertEqual(status, client.UNANSWERED)
        return self.stderr.getvalue()

    def test_the_folder_it_trusts(self):
        missing = os.path.join(short_folder(self), "nope")
        self.assertEqual(
            self.unanswered(ca_dir=missing),
            f"{missing} doesn't exist: no command sent\n",
        )

    def test_no_certificate_there(self):
        folder = short_folder(self)
        self.assertEqual(
            self.unanswered(ca_dir=folder),
            f"{folder} has no .pem certificate: no command sent\n",
        )

    def test_not_a_certificate(self):
        folder = short_folder(self)
        path = os.path.join(folder, "lab.pem")
        with open(path, "w") as file:
            file.write("notes\n")
        self.assertEqual(
            self.unanswered(ca_dir=folder),
            f"{path} isn't a certificate in PEM: no command sent\n",
        )

    def test_its_own_certificate(self):
        key = os.path.join(DATA, "tls", "alice.key")
        cert = os.path.join(DATA, "tls", "bob.pem")
        self.assertEqual(
            self.unanswered(private_key=key, cert=cert),
            f"The key {key} isn't that of the certificate {cert}, or isn't"
            " in PEM: no command sent\n",
        )

    def test_a_key_that_isnt_there(self):
        missing = os.path.join(short_folder(self), "nope.key")
        self.assertEqual(
            self.unanswered(private_key=missing),
            f"{missing}: No such file or directory\n",
        )


class TestTheProcess(unittest.TestCase):

    def test_no_reactor_and_no_gtk(self):
        # virtualbricks --command, up to the answer: here there is none
        path = os.path.join(short_folder(self), "lab.sock")
        code = (
            "import sys\n"
            "from virtualbricks import cli\n"
            f"sys.argv = ['virtualbricks', '--connect', 'unix:{path}',"
            " '--command',"
            " 'status']\n"
            "try:\n"
            "    cli.main()\n"
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

    def test_a_script(self):
        # virtualbricks --connect --run: the client sends the file
        folder = short_folder(self)
        path = os.path.join(folder, "lab.sock")
        script = os.path.join(folder, "lab.vb")
        with open(script, "w", encoding="utf-8") as fp:
            fp.write("status\n")
        code = (
            "import sys\n"
            "from virtualbricks import cli\n"
            f"sys.argv = ['virtualbricks', '--connect', 'unix:{path}',"
            f" '--run', '{script}']\n"
            "try:\n"
            "    cli.main()\n"
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
