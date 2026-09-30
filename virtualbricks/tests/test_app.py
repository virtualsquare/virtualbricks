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
from virtualbricks.config.settings import AppSettings, write_settings
from virtualbricks.console import wire
from virtualbricks.tests import (
    DATA,
    hold_lock,
    isolate,
    lock_is_free,
    short_folder,
)

ME = pwd.getpwuid(os.getuid()).pw_name


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
        # called by migrate, as the startup migration runs
        self.migrating = None

    def migrate(self):
        if self.migrating is not None:
            self.migrating()

    def run(self, reactor):
        d = defer.maybeDeferred(self.migrate)
        d.addCallback(lambda _: self.started.append(self.config["lock"]))
        return d


class TestLock(unittest.TestCase):

    def setUp(self):
        self.root = isolate(self)
        self.reactor = FakeReactor()
        self.started = []
        # the workspace of the settings
        self.workspace = os.path.join(self.root, ".virtualbricks")

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
            usage.UsageError, self.parse, "--lock", "group"
        )
        self.assertEqual(
            str(error),
            "--lock: 'group' is not one of system, user, workspace, none",
        )

    def test_the_policy_of_a_workspace(self):
        # one Virtualbricks for each workspace, unless --lock says otherwise
        self.assertEqual(
            self.parse("--workspace", "/srv/labs")["lock"], locks.WORKSPACE
        )
        for policy in locks.POLICIES:
            options = self.parse("--lock", policy, "--workspace", "/srv/a")
            self.assertEqual(options["lock"], policy)

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
            "Virtualbricks is running on this machine with --lock user or "
            "--lock workspace, which let others run beside it: start this "
            f"one with one of them as well. Held by process {os.getpid()} of "
            f"{user}.",
        )
        self.assertEqual(self.started, [])
        self.successResultOf(self.run_app("--lock", "user"))
        self.assertEqual(self.started, [locks.USER])
        self.reactor.shutdown()

    def test_none_starts_anyway(self):
        hold_lock(self)
        self.successResultOf(self.run_app("--lock", "none"))
        self.assertEqual(self.started, [locks.NONE])
        # no lock in the workspace, not even the folder
        self.assertFalse(os.path.exists(self.workspace))

    def test_the_workspace_of_the_settings(self):
        self.successResultOf(self.run_app())
        path = locations.workspace_lock_file(self.workspace)
        self.assertEqual(locks.holders(path), ((os.getpid(), ME),))
        self.reactor.shutdown()
        self.assertEqual(locks.holders(path), ())

    def test_the_workspace_of_the_settings_file(self):
        labs = os.path.join(self.root, "labs")
        write_settings(AppSettings(workspace=labs), locations.settings_file())
        self.successResultOf(self.run_app("--lock", "user"))
        path = locations.workspace_lock_file(labs)
        self.assertEqual(locks.holders(path), ((os.getpid(), ME),))
        self.reactor.shutdown()

    def test_side_by_side(self):
        a = os.path.join(self.root, "labs", "a")
        b = os.path.join(self.root, "labs", "b")
        self.successResultOf(self.run_app("--workspace", a))
        # the folder is made for its lock
        self.assertTrue(os.path.isfile(locations.workspace_lock_file(a)))
        self.successResultOf(self.run_app("--workspace", b))
        self.assertEqual(self.started, [locks.WORKSPACE, locks.WORKSPACE])
        failure = self.failureResultOf(
            self.run_app("--workspace", a), SystemExit
        )
        self.assertEqual(
            str(failure.value),
            "Another Virtualbricks is running in the workspace ~/labs/a: "
            "start this one in another, with --workspace. Held by process "
            f"{os.getpid()} of {ME}.",
        )
        # nor the one of the settings, in the system mode
        failure = self.failureResultOf(self.run_app(), SystemExit)
        self.assertIn("--lock user or --lock workspace", str(failure.value))
        self.successResultOf(self.run_app("--lock", "workspace"))
        self.assertEqual(len(self.started), 3)
        self.reactor.shutdown()

    def test_the_settings_of_2_1_are_converted_alone(self):
        with open(locations.legacy_settings_file(), "w"):
            pass
        refused = []

        def migrating():
            # the user lock alone: no other workspace starts meanwhile
            other = os.path.join(self.root, "other")
            refused.append(self.run_app("--workspace", other))
            write_settings(AppSettings(), locations.settings_file())

        def application(config):
            fake = FakeApplication(self.started, config)
            fake.migrating = migrating
            return fake

        config = self.parse("--workspace", os.path.join(self.root, "a"))
        running = app.LockedApplication(application)(config)
        self.successResultOf(running.run(self.reactor))
        [d] = refused
        failure = self.failureResultOf(d, SystemExit)
        self.assertIn("--lock user", str(failure.value))
        # then shared: another workspace starts
        self.successResultOf(
            self.run_app("--workspace", os.path.join(self.root, "b"))
        )
        self.assertEqual(self.started, [locks.WORKSPACE, locks.WORKSPACE])
        self.reactor.shutdown()

    def test_a_workspace_lock_that_cannot_be_opened(self):
        os.makedirs(self.workspace)
        path = locations.workspace_lock_file(self.workspace)
        os.symlink("elsewhere", path)
        failure = self.failureResultOf(self.run_app(), SystemExit)
        self.assertEqual(
            str(failure.value),
            f"Cannot take the lock {path}: Too many levels of symbolic links."
            " With --lock none, Virtualbricks runs without locks.",
        )
        self.assertEqual(self.started, [])

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
        options = self.parse("--command", "--connect", "brick", "list")
        self.assertEqual(options["target"], wire.Socket(self.default))
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
            self.refused("--socket", "tls:443"),
            "--socket: tls:443: the types are unix, tcp and ssl, as unix:PATH"
            " or tcp:PORT",
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

    def test_with_connect(self):
        # the machine to talk to; the token is the client's to read
        self.write_token(locations.token_file(), 0o644)
        for args in (
            ["--connect", "tcp:lab.example:8765", "--command", "status"],
            ["--command", "--connect", "tcp:lab.example:8765", "status"],
        ):
            options = self.parse(*args)
            self.assertEqual(options["target"], self.tcp(8765, "lab.example"))
            self.assertEqual(options["sockets"], [])
        self.assertEqual(
            self.parse("--connect", "tcp:8765", "--command", "status")[
                "target"
            ],
            self.tcp(8765),
        )
        self.assertEqual(
            self.refused(
                "--connect",
                "tcp:8765:interface=127.0.0.1",
                "--command",
                "status",
            ),
            "--connect: tcp:8765:interface=127.0.0.1: --connect reaches the"
            " machine of host=, as tcp:lab.example:8765; interface= is where"
            " Virtualbricks listens",
        )
        # listening, the same description is refused
        self.assertEqual(
            self.refused("--socket", "tcp:lab.example:8765"),
            "--socket: tcp:lab.example:8765: the address to listen on is"
            " interface=lab.example",
        )


class TestSslSocket(unittest.TestCase):

    TLS = os.path.join(DATA, "tls")

    def setUp(self):
        self.root = isolate(self)
        self.patch(sys, "stdin", Input(False))

    def parse(self, *args):
        options = app.Options()
        options.parseOptions(list(args))
        return options

    def refused(self, *args):
        return str(self.assertRaises(usage.UsageError, self.parse, *args))

    def data(self, name):
        return os.path.join(self.TLS, name)

    def test_a_port(self):
        os.symlink(self.TLS, os.path.join(self.root, "vb"))
        [socket] = self.parse(
            "--socket",
            "ssl:8765:interface=0.0.0.0:privateKey=~/vb/server.key"
            ":certKey=~/vb/server.pem",
        )["sockets"]
        folder = os.path.join(self.root, "vb")
        self.assertEqual(
            socket,
            wire.Socket(
                None,
                "text",
                "ssl",
                "0.0.0.0",
                8765,
                private_key=os.path.join(folder, "server.key"),
                cert=os.path.join(folder, "server.pem"),
            ),
        )

    def test_certificates_in_place_of_the_token(self):
        # the token isn't read: a client shows its certificate
        path = locations.token_file()
        os.makedirs(os.path.dirname(path))
        with open(path, "w") as file:
            file.write("1234\n")
        self.parse(
            "--socket",
            f"ssl:8765:privateKey={self.data('server.key')}"
            f":certKey={self.data('server.pem')}:caCertsDir={self.TLS}",
        )

    def test_the_files(self):
        key = self.data("server.key")
        self.assertEqual(
            self.refused(
                "--socket",
                f"ssl:8765:privateKey={key}:certKey={self.data('bob.pem')}",
            ),
            f"--socket: The key {key} isn't that of the certificate"
            f" {self.data('bob.pem')}",
        )
        missing = os.path.join(self.root, "lab.pem")
        self.assertEqual(
            self.refused("--socket", "ssl:8765:privateKey=~/lab.pem"),
            f"--socket: {missing} doesn't exist",
        )
        self.assertEqual(
            self.refused(
                "--socket",
                f"ssl:8765:privateKey={key}:certKey={self.data('server.pem')}"
                f":caCertsDir={self.root}",
            ),
            f"--socket: {self.root} has no .pem certificate",
        )

    def test_no_pyopenssl(self):
        name = "virtualbricks.console.tls"
        module = sys.modules.pop(name, None)
        sys.modules[name] = None

        def restore():
            del sys.modules[name]
            if module is not None:
                sys.modules[name] = module

        self.addCleanup(restore)
        self.assertEqual(
            self.refused("--socket", "ssl:8765:privateKey=/vb/lab.pem"),
            "--socket: ssl needs pyOpenSSL: the package python3-openssl",
        )

    def test_with_connect(self):
        # its files are the client's to read
        socket = self.parse(
            "--connect",
            "ssl:lab.example:8765:caCertsDir=~/vb/lab:privateKey=~/a.key",
            "--command",
            "status",
        )["target"]
        self.assertEqual(
            socket,
            wire.Socket(
                None,
                "text",
                "ssl",
                "lab.example",
                8765,
                private_key=os.path.join(self.root, "a.key"),
                ca_dir=os.path.join(self.root, "vb", "lab"),
            ),
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
            "--connect", "unix:/tmp/lab.sock", "--command", "status"
        )
        self.assertEqual(options["target"], wire.Socket("/tmp/lab.sock"))
        self.assertTrue(options["connect"])
        # without --connect, the default socket
        options = self.parse("--command", "status")
        self.assertIsNone(options["target"])
        self.assertFalse(options["connect"])
        self.assertFalse(self.parse()["command"])

    def test_one_virtualbricks(self):
        self.assertEqual(
            self.refused(
                "--connect",
                "unix:/tmp/a.sock",
                "--connect",
                "unix:/tmp/b.sock",
                "--command",
                "status",
            ),
            "--connect names one Virtualbricks",
        )
        # either protocol
        self.assertEqual(
            self.parse(
                "--connect",
                "unix:/tmp/a.amp:protocol=amp",
                "--command",
                "status",
            )["target"],
            wire.Socket("/tmp/a.amp", wire.AMP),
        )

    def test_no_socket(self):
        # --socket listens, which a client doesn't
        for args in (
            ["--socket", "--command", "status"],
            ["--socket", "unix:/tmp/a.sock", "--command", "status"],
        ):
            self.assertEqual(
                self.refused(*args),
                "--command takes no --socket, which listens: --connect names"
                " the Virtualbricks to talk to",
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


class TestConnect(unittest.TestCase):

    def setUp(self):
        self.root = isolate(self)
        # a runtime folder short enough for a socket's path
        os.environ["XDG_RUNTIME_DIR"] = os.path.join(short_folder(self), "run")
        self.patch(sys, "stdin", Input(False))
        self.script = os.path.join(self.root, "lab.vb")
        open(self.script, "w").close()

    def parse(self, *args):
        options = app.Options()
        options.parseOptions(list(args))
        return options

    def refused(self, *args):
        return str(self.assertRaises(usage.UsageError, self.parse, *args))

    def test_run(self):
        # the commands of the file go to the Virtualbricks that runs
        options = self.parse("--connect", "--run", self.script)
        self.assertTrue(options["connect"])
        self.assertFalse(options["command"])
        self.assertEqual(options["run"], self.script)
        self.assertEqual(
            options["target"], wire.Socket(locations.control_socket())
        )
        options = self.parse(
            "--connect", "unix:/tmp/lab.sock", "--run", self.script
        )
        self.assertEqual(options["target"], wire.Socket("/tmp/lab.sock"))
        # without it, those of the Virtualbricks that starts
        options = self.parse("--run", self.script)
        self.assertFalse(options["connect"])
        self.assertIsNone(options["target"])

    def test_alone(self):
        self.assertEqual(
            self.refused("--connect"),
            "--connect needs --command or --run: it talks to a Virtualbricks"
            " that runs",
        )

    def test_the_options_of_a_run(self):
        for args in (
            ["--no-gui"],
            ["--noterm"],
            ["--workspace", self.root],
            ["--lock", "system"],
            ["--logfile", "-"],
            ["--logger", "virtualbricks.app.file_logger"],
        ):
            name = args[0][2:]
            self.assertEqual(
                self.refused(*args, "--connect", "--run", self.script),
                f"--connect takes no --{name}: it talks to a Virtualbricks"
                " that runs",
            )
        self.assertEqual(
            self.refused("--socket", "--connect", "--run", self.script),
            "--connect takes no --socket, which listens: --connect names the"
            " Virtualbricks to talk to",
        )

    def test_command_or_run(self):
        self.assertEqual(
            self.refused(
                "--connect", "--run", self.script, "--command", "status"
            ),
            "--command takes no --run: it talks to a Virtualbricks that runs",
        )


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
