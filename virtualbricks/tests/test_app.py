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


"""The launcher: the lock, the logging, the options."""

import functools
import os
import pwd
import sys

from twisted.internet import defer
from twisted.python import usage
from twisted.trial import unittest

from virtualbricks import app, locations, locks
from virtualbricks.console import wire
from virtualbricks.tests import (
    hold_lock,
    isolate,
    lock_is_free,
    short_folder,
)


class FakeReactor:

    def __init__(self):
        self.triggers = []

    def addSystemEventTrigger(self, phase, event, callable):
        self.triggers.append((phase, event, callable))

    def shutdown(self):
        for phase, event, callable in self.triggers:
            callable()


class FakeApplication:

    def __init__(self, started, config):
        self.started = started
        self.config = config

    def run(self, reactor):
        self.started.append(self.config["lock"])
        return defer.succeed(None)


class TestLock(unittest.TestCase):

    def setUp(self):
        isolate(self)
        self.reactor = FakeReactor()
        self.started = []

    def parse(self, *args):
        options = app.Options()
        options.parseOptions(list(args))
        return options

    def run_app(self, *args):
        factory = functools.partial(FakeApplication, self.started)
        application = app.LockedApplication(factory)(self.parse(*args))
        return application.run(self.reactor)

    def test_the_policy(self):
        self.assertEqual(self.parse()["lock"], locks.SYSTEM)
        for policy in locks.POLICIES:
            self.assertEqual(self.parse("--lock", policy)["lock"], policy)
        self.assertEqual(self.parse("--lock=user")["lock"], locks.USER)
        error = self.assertRaises(
            usage.UsageError, self.parse, "--lock", "workspace"
        )
        self.assertEqual(
            str(error), "--lock: 'workspace' is not one of system, user, none"
        )

    def test_held_until_shutdown(self):
        self.successResultOf(self.run_app("--lock", "user"))
        self.assertEqual(self.started, [locks.USER])
        self.assertFalse(lock_is_free())
        self.reactor.shutdown()
        self.assertTrue(lock_is_free())

    def test_refused(self):
        hold_lock(self, locks.USER, "bob")
        failure = self.failureResultOf(self.run_app(), SystemExit)
        user = pwd.getpwuid(os.getuid()).pw_name
        self.assertEqual(
            str(failure.value),
            "Virtualbricks is running on this machine with --lock user, one "
            "for each user: start this one with --lock user as well. Held by "
            f"process {os.getpid()} of {user}.",
        )
        self.assertEqual(self.started, [])
        self.successResultOf(self.run_app("--lock", "user"))
        self.assertEqual(self.started, [locks.USER])
        self.reactor.shutdown()

    def test_none_starts_anyway(self):
        hold_lock(self)
        self.successResultOf(self.run_app("--lock", "none"))
        self.assertEqual(self.started, [locks.NONE])

    def test_a_lock_that_cannot_be_opened(self):
        os.symlink("elsewhere", locations.SYSTEM_LOCK_FILE)
        self.addCleanup(os.remove, locations.SYSTEM_LOCK_FILE)
        failure = self.failureResultOf(self.run_app(), SystemExit)
        self.assertEqual(
            str(failure.value),
            f"Cannot take the lock {locations.SYSTEM_LOCK_FILE}: Too many "
            "levels of symbolic links. With --lock none, Virtualbricks runs "
            "without locks.",
        )
        self.assertEqual(self.started, [])


class TestWorkspace(unittest.TestCase):

    def setUp(self):
        self.root = isolate(self)

    def parse(self, *args):
        options = app.Options()
        options.parseOptions(list(args))
        return options["workspace"]

    def test_the_setting_without_it(self):
        self.assertIsNone(self.parse())

    def test_an_absolute_path(self):
        self.assertEqual(self.parse("--workspace", "/srv/labs/"), "/srv/labs")
        self.assertEqual(self.parse("--workspace=/srv/labs"), "/srv/labs")

    def test_home_and_the_current_folder(self):
        self.assertEqual(
            self.parse("--workspace", "~/labs"),
            os.path.join(self.root, "labs"),
        )
        self.assertEqual(
            self.parse("--workspace", "labs"),
            os.path.join(os.getcwd(), "labs"),
        )

    def test_not_a_folder(self):
        path = os.path.join(self.root, "file")
        open(path, "w").close()
        error = self.assertRaises(
            usage.UsageError, self.parse, "--workspace", path
        )
        self.assertEqual(str(error), f"--workspace: {path} is not a folder")
        self.assertRaises(usage.UsageError, self.parse, "--workspace", "")


class TestSocket(unittest.TestCase):

    def setUp(self):
        self.root = isolate(self)
        # a runtime folder short enough for a socket's path, not made yet
        self.runtime = os.path.join(short_folder(self), "run")
        os.environ["XDG_RUNTIME_DIR"] = self.runtime
        self.default = locations.control_socket()

    def parse(self, *args):
        options = app.Options()
        options.parseOptions(list(args))
        return options

    def sockets(self, *args):
        return self.parse(*args)["sockets"]

    def refused(self, *args):
        return str(self.assertRaises(usage.UsageError, self.parse, *args))

    def test_none_without_it(self):
        self.assertEqual(self.sockets(), [])
        self.assertNotIn("socket", self.parse())

    def test_alone(self):
        # the runtime folder is made at start
        self.assertFalse(os.path.exists(os.path.dirname(self.default)))
        self.assertEqual(self.sockets("--socket"), [wire.Socket(self.default)])

    def test_a_description(self):
        self.assertEqual(
            self.sockets("--socket", "unix:/tmp/lab.sock"),
            [wire.Socket("/tmp/lab.sock")],
        )
        self.assertEqual(
            self.sockets("--socket=unix:/tmp/lab.sock:protocol=TEXT"),
            [wire.Socket("/tmp/lab.sock")],
        )
        self.assertEqual(
            self.sockets(
                "--socket", "--socket", "unix:/tmp/lab.amp:protocol=amp"
            ),
            [wire.Socket(self.default), wire.Socket("/tmp/lab.amp", "amp")],
        )
        # a home short enough for a socket's path
        home = short_folder(self)
        os.environ["HOME"] = home
        self.assertEqual(
            self.sockets("--socket", "unix:~/lab.sock"),
            [wire.Socket(os.path.join(home, "lab.sock"))],
        )
        self.assertEqual(
            self.sockets("--socket", "unix:address=lab.sock"),
            [wire.Socket(os.path.join(os.getcwd(), "lab.sock"))],
        )

    def test_the_next_word(self):
        # taken when it starts with a type, as unix:
        options = self.parse("--socket", "--no-gui")
        self.assertEqual(options["sockets"], [wire.Socket(self.default)])
        self.assertTrue(options["no-gui"])
        options = self.parse("--command", "--socket", "brick", "list")
        self.assertEqual(options["sockets"], [wire.Socket(self.default)])
        self.assertEqual(options["words"], ["brick", "list"])
        # the value of another option isn't one
        options = self.parse("--workspace", "--socket")
        self.assertEqual(options["sockets"], [])
        self.assertEqual(
            options["workspace"], os.path.join(os.getcwd(), "--socket")
        )
        options = self.parse("--workspace=labs", "--socket")
        self.assertEqual(options["sockets"], [wire.Socket(self.default)])
        # the options end at the first word, and at --
        self.assertEqual(
            self.parse("--command", "status", "--socket")["words"],
            ["status", "--socket"],
        )
        self.assertEqual(self.sockets("--command", "--", "--socket"), [])

    def test_a_prefix(self):
        # getopt reads a prefix of one option as the option
        self.assertEqual(
            self.sockets("--sock", "unix:/tmp/lab.sock"),
            [wire.Socket("/tmp/lab.sock")],
        )

    def test_more_than_one(self):
        self.assertEqual(
            self.sockets("--socket", "--socket", "unix:/tmp/lab.sock"),
            [wire.Socket(self.default), wire.Socket("/tmp/lab.sock")],
        )
        self.assertEqual(
            self.refused("--socket", "--socket"),
            f"--socket: {self.default} is given twice",
        )
        self.assertEqual(
            self.refused("--socket", f"unix:{self.default}", "--socket"),
            f"--socket: {self.default} is given twice",
        )

    def test_a_path(self):
        self.assertEqual(
            self.refused("--socket", "~/lab.sock"),
            "--socket: ~/lab.sock needs its type: unix:~/lab.sock",
        )
        self.assertEqual(
            self.refused("--socket=/tmp/lab.sock"),
            "--socket: /tmp/lab.sock needs its type: unix:/tmp/lab.sock",
        )

    def test_what_is_refused(self):
        self.assertEqual(
            self.refused("--socket", "ssl:443"),
            "--socket: ssl:443: the types are unix and tcp, as unix:PATH or"
            " tcp:PORT",
        )
        self.assertEqual(
            self.refused("--socket=unix:"),
            "--socket: unix: needs a path, as unix:~/labs/lab1.sock",
        )
        folder = os.path.join(self.root, "nope")
        self.assertEqual(
            self.refused("--socket", f"unix:{folder}/lab.sock"),
            f"--socket: {folder} doesn't exist",
        )
        self.assertEqual(
            self.refused("--socket", f"unix:{self.root}"),
            f"--socket: {self.root} is a folder",
        )
        path = "/tmp/" + "a" * 103
        self.assertEqual(
            self.refused("--socket", f"unix:{path}"),
            f"--socket: {path} is longer than 107 bytes, the most a"
            " socket's path can have",
        )


class TestTcpSocket(unittest.TestCase):

    def setUp(self):
        self.root = isolate(self)
        self.patch(sys, "stdin", Input(False))

    def parse(self, *args):
        options = app.Options()
        options.parseOptions(list(args))
        return options

    def sockets(self, *args):
        return self.parse(*args)["sockets"]

    def refused(self, *args):
        return str(self.assertRaises(usage.UsageError, self.parse, *args))

    def tcp(self, port, host="127.0.0.1", protocol="text", token_file=None):
        return wire.Socket(None, protocol, "tcp", host, port, token_file)

    def write_token(self, path, mode=0o600):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as file:
            file.write("0123456789abcdef\n")
        os.chmod(path, mode)

    def test_a_port(self):
        self.assertEqual(
            self.sockets("--socket", "tcp:8765"), [self.tcp(8765)]
        )
        # the token file is made when the socket opens
        self.assertFalse(os.path.exists(locations.token_file()))
        # a runtime folder short enough for the default socket
        os.environ["XDG_RUNTIME_DIR"] = os.path.join(short_folder(self), "run")
        self.assertEqual(
            self.sockets(
                "--socket",
                "--socket=tcp:8766:protocol=amp",
                r"--socket=tcp:8765:interface=\:\:1",
            ),
            [
                wire.Socket(locations.control_socket()),
                self.tcp(8766, protocol="amp"),
                self.tcp(8765, "::1"),
            ],
        )

    def test_the_same_port_twice(self):
        self.assertEqual(
            self.refused(
                "--socket",
                "tcp:8765",
                "--socket",
                "tcp:port=8765:protocol=amp",
            ),
            "--socket: 127.0.0.1 port 8765 is given twice",
        )

    def test_a_token_file(self):
        folder = os.path.join(self.root, "vb")
        self.assertEqual(
            self.refused("--socket", "tcp:8765:tokenFile=~/vb/lab1.token"),
            f"--socket: {folder} doesn't exist",
        )
        os.mkdir(folder)
        path = os.path.join(folder, "lab1.token")
        self.assertEqual(
            self.sockets("--socket", "tcp:8765:tokenFile=~/vb/lab1.token"),
            [self.tcp(8765, token_file=path)],
        )
        self.write_token(path, 0o644)
        self.assertEqual(
            self.refused("--socket", "tcp:8765:tokenFile=~/vb/lab1.token"),
            f"--socket: Others can read or change {path}: chmod 600 {path}",
        )

    def test_the_default_token(self):
        path = locations.token_file()
        self.write_token(path)
        self.assertEqual(
            self.sockets("--socket", "tcp:8765"), [self.tcp(8765)]
        )
        with open(path, "w") as file:
            file.write("1234\n")
        self.assertEqual(
            self.refused("--socket", "tcp:8765"),
            f"--socket: The token of {path} has 4 characters; a token has at"
            " least 16",
        )

    def test_with_command(self):
        # the machine to talk to; the token is --command's to read
        self.write_token(locations.token_file(), 0o644)
        for args in (
            ["--socket", "tcp:lab.example:8765", "--command", "status"],
            ["--command", "--socket", "tcp:lab.example:8765", "status"],
        ):
            self.assertEqual(
                self.sockets(*args), [self.tcp(8765, "lab.example")]
            )
        self.assertEqual(
            self.sockets("--socket", "tcp:8765", "--command", "status"),
            [self.tcp(8765)],
        )
        self.assertEqual(
            self.refused(
                "--socket",
                "tcp:8765:interface=127.0.0.1",
                "--command",
                "status",
            ),
            "--socket: tcp:8765:interface=127.0.0.1: --command reaches the"
            " machine of host=, as tcp:lab.example:8765; interface= is where"
            " Virtualbricks listens",
        )
        # listening, the same description is refused
        self.assertEqual(
            self.refused("--socket", "tcp:lab.example:8765"),
            "--socket: tcp:lab.example:8765: the address to listen on is"
            " interface=lab.example",
        )


class Input:
    def __init__(self, tty):
        self.tty = tty

    def isatty(self):
        return self.tty


class TestCommand(unittest.TestCase):

    def setUp(self):
        self.root = isolate(self)
        self.patch(sys, "stdin", Input(False))

    def parse(self, *args):
        options = app.Options()
        options.parseOptions(list(args))
        return options

    def refused(self, *args):
        return str(self.assertRaises(usage.UsageError, self.parse, *args))

    def test_the_words(self):
        options = self.parse("--command", "brick", "start", "--force", "vm1")
        self.assertTrue(options["command"])
        # the options end at the first word
        self.assertEqual(
            options["words"], ["brick", "start", "--force", "vm1"]
        )
        options = self.parse(
            "--socket", "unix:/tmp/lab.sock", "--command", "status"
        )
        self.assertEqual(options["sockets"], [wire.Socket("/tmp/lab.sock")])
        self.assertFalse(self.parse()["command"])

    def test_one_socket(self):
        self.assertEqual(
            self.refused(
                "--socket",
                "unix:/tmp/a.sock",
                "--socket",
                "unix:/tmp/b.sock",
                "--command",
                "status",
            ),
            "--command talks to one --socket",
        )
        self.assertEqual(
            self.refused(
                "--socket",
                "unix:/tmp/a.amp:protocol=amp",
                "--command",
                "status",
            ),
            "--command speaks the text protocol, not amp",
        )

    def test_words_without_it(self):
        self.assertEqual(
            self.refused("brick", "set", "vm1", "name=my vm"),
            "unexpected words: brick set vm1 name=my vm. To send them to the"
            " Virtualbricks that runs: virtualbricks --command brick set vm1"
            " 'name=my vm'",
        )

    def test_the_options_of_a_run(self):
        script = os.path.join(self.root, "lab.vb")
        open(script, "w").close()
        for args in (
            ["--no-gui"],
            ["--noterm"],
            ["--run", script],
            ["--workspace", self.root],
            ["--lock", "system"],
            ["--logfile", "-"],
            ["--logger", "virtualbricks.app.file_logger"],
        ):
            name = args[0][2:]
            self.assertEqual(
                self.refused(*args, "--command", "status"),
                f"--command takes no --{name}: it talks to a Virtualbricks"
                " that runs",
            )

    def test_the_standard_input(self):
        self.assertEqual(self.parse("--command")["words"], [])
        self.patch(sys, "stdin", Input(True))
        self.assertEqual(
            self.refused("--command"),
            "--command needs a command, as virtualbricks --command brick list,"
            " or lines on its standard input",
        )
        self.parse("--command", "status")


class TestTheConsoleOptions(unittest.TestCase):

    def setUp(self):
        self.root = isolate(self)

    def parse(self, *args):
        options = app.Options()
        options.parseOptions(list(args))
        return options

    def test_no_gui(self):
        self.assertFalse(self.parse()["no-gui"])
        self.assertTrue(self.parse("--no-gui")["no-gui"])

    def test_run(self):
        self.assertIsNone(self.parse()["run"])
        path = os.path.join(self.root, "lab.vb")
        open(path, "w").close()
        self.assertEqual(self.parse("--run", "~/lab.vb")["run"], path)
        error = self.assertRaises(
            usage.UsageError, self.parse, "--run", "/nope.vb"
        )
        self.assertEqual(str(error), "--run: /nope.vb is not a file")

    def test_no_daemon(self):
        self.assertRaises(usage.UsageError, self.parse, "--daemon")
