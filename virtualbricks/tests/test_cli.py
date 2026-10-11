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

"""The command line read with argparse: the modes, the options, the checks."""

import io
import os
import subprocess
import sys

from twisted.trial import unittest

from virtualbricks import __version__, locations, locks, sockets
from virtualbricks.cli import (
    COMMAND,
    DEFAULT_SOCKET,
    GUI,
    NO_GUI,
    REMOTE,
    UNSET,
    CommandLineOptions,
    UsageError,
    parse,
    parse_or_exit,
    parser,
)
from virtualbricks.tests import DATA, isolate, short_folder


class Input:
    def __init__(self, tty):
        self.tty = tty

    def isatty(self):
        return self.tty


class Base(unittest.TestCase):

    def setUp(self):
        self.root = isolate(self)
        self.script = os.path.join(self.root, "lab.vb")
        with open(self.script, "w") as fp:
            fp.write("status\n")

    def parse(self, *args, tty=False):
        return parse(list(args), Input(tty))

    def refused(self, *args, tty=False):
        return str(
            self.assertRaises(UsageError, parse, list(args), Input(tty))
        )


class TestModes(Base):

    def test_the_windows(self):
        self.assertEqual(self.parse(), CommandLineOptions(GUI))

    def test_no_gui(self):
        self.assertEqual(self.parse("--no-gui"), CommandLineOptions(NO_GUI))

    def test_remote(self):
        line = self.parse("--connect")
        self.assertEqual(line.mode, REMOTE)
        self.assertEqual(line.target, DEFAULT_SOCKET)
        # their terminal reads no console
        self.assertTrue(line.no_term)

    def test_command(self):
        line = self.parse("--command", "brick", "list")
        self.assertEqual(line.mode, COMMAND)
        self.assertEqual(line.words, ("brick", "list"))
        self.assertIsNone(line.target)
        self.assertFalse(line.no_term)

    def test_connect_and_run(self):
        line = self.parse("--connect", "tcp:lab:8765", "--run", self.script)
        self.assertEqual(line.mode, COMMAND)
        self.assertEqual(
            line.target, sockets.Socket(None, "amp", "tcp", "lab", 8765)
        )
        self.assertEqual(line.run, self.script)

    def test_run_without_connect(self):
        line = self.parse("--run", self.script)
        self.assertEqual(line.mode, GUI)
        self.assertEqual(line.run, self.script)


class TestLock(Base):

    def test_the_default(self):
        self.assertEqual(self.parse().lock, locks.SYSTEM)

    def test_given(self):
        for policy in locks.POLICIES:
            self.assertEqual(self.parse("--lock", policy).lock, policy)
        self.assertEqual(self.parse("--lock=user").lock, locks.USER)

    def test_of_a_workspace(self):
        # one Virtualbricks for each workspace, unless --lock says otherwise
        self.assertEqual(
            self.parse("--workspace", "/srv/labs").lock, locks.WORKSPACE
        )
        self.assertEqual(
            self.parse("--workspace", "/srv/labs", "--lock", "user").lock,
            locks.USER,
        )

    def test_unknown(self):
        # argparse's words, which change with the version of Python
        self.assertTrue(
            self.refused("--lock", "group").startswith(
                "argument --lock: invalid choice: 'group'"
            )
        )


class TestPaths(Base):

    def test_workspace(self):
        self.assertEqual(
            self.parse("--workspace", "/srv/labs").workspace, "/srv/labs"
        )
        self.assertEqual(
            self.parse("--workspace", "labs").workspace,
            os.path.join(os.getcwd(), "labs"),
        )
        self.assertEqual(
            self.parse("--workspace", "~/labs").workspace,
            os.path.join(self.root, "labs"),
        )
        self.assertIsNone(self.parse().workspace)

    def test_workspace_refused(self):
        self.assertEqual(
            self.refused("--workspace", ""),
            "argument --workspace: needs a folder, as ~/labs",
        )
        self.assertEqual(
            self.refused("--workspace", self.script),
            f"argument --workspace: {self.script} is not a folder",
        )

    def test_run(self):
        self.assertEqual(self.parse("--run", "~/lab.vb").run, self.script)
        missing = os.path.join(self.root, "nope.vb")
        self.assertEqual(
            self.refused("--run", missing),
            f"argument --run: {missing} is not a file",
        )

    def test_nothing_opened(self):
        # the log file is the mode's to open, the logger its to import
        log = os.path.join(self.root, "vb.log")
        line = self.parse("-l", log, "--logger", "no.such.module")
        self.assertEqual(line.logfile, log)
        self.assertEqual(line.logger, "no.such.module")
        self.assertFalse(os.path.exists(log))
        self.assertEqual(self.parse("--logfile=-").logfile, "-")


class TestListen(Base):

    def test_none(self):
        self.assertEqual(self.parse().listen, ())

    def test_alone(self):
        self.assertEqual(self.parse("--listen").listen, (DEFAULT_SOCKET,))

    def test_a_description(self):
        self.assertEqual(
            self.parse("--listen", "unix:/tmp/lab.sock").listen,
            (sockets.Socket("/tmp/lab.sock"),),
        )
        self.assertEqual(
            self.parse("--listen=unix:/tmp/lab.sock:protocol=JSON").listen,
            (sockets.Socket("/tmp/lab.sock", sockets.JSON),),
        )
        self.assertEqual(
            self.parse("--listen=tcp:8765").listen,
            (sockets.Socket(None, "amp", "tcp", "127.0.0.1", 8765),),
        )

    def test_an_absolute_path(self):
        # a home short enough for a socket's path
        home = short_folder(self)
        os.environ["HOME"] = home
        self.assertEqual(
            self.parse("--listen", "unix:~/lab.sock").listen,
            (sockets.Socket(os.path.join(home, "lab.sock")),),
        )
        # a path of the current folder, which may be too deep for a socket
        self.addCleanup(os.chdir, os.getcwd())
        os.chdir(home)
        self.assertEqual(
            self.parse("--listen", "unix:address=lab.sock").listen,
            (sockets.Socket(os.path.join(home, "lab.sock")),),
        )

    def test_more_than_one(self):
        self.assertEqual(
            self.parse("--listen", "--listen", "unix:/tmp/lab.sock").listen,
            (DEFAULT_SOCKET, sockets.Socket("/tmp/lab.sock")),
        )
        self.assertEqual(
            self.refused("--listen", "--listen"),
            "--listen alone is given twice",
        )
        self.assertEqual(
            self.refused("--listen", "unix:/tmp/a", "--listen=unix:/tmp/a"),
            "--listen: /tmp/a is given twice",
        )

    def test_the_folder(self):
        folder = os.path.join(self.root, "nope")
        self.assertEqual(
            self.refused("--listen", f"unix:{folder}/lab.sock"),
            f"--listen: {folder} doesn't exist",
        )
        self.assertEqual(
            self.refused("--listen", f"unix:{self.root}"),
            f"--listen: {self.root} is a folder",
        )
        # Virtualbricks makes the runtime folder at start
        runtime = os.path.join(short_folder(self), "run")
        os.environ["XDG_RUNTIME_DIR"] = runtime
        path = os.path.join(runtime, "virtualbricks", "lab.sock")
        self.assertEqual(
            self.parse("--listen", f"unix:{path}").listen,
            (sockets.Socket(path),),
        )

    def test_too_long(self):
        path = "/tmp/" + "a" * 103
        self.assertEqual(
            self.refused("--listen", f"unix:{path}"),
            f"--listen: {path} is longer than 107 bytes, the most a"
            " socket's path can have",
        )

    def test_checked_after_the_mode(self):
        # --command takes no --listen, whatever its socket
        self.assertEqual(
            self.refused("--command", "--listen", "unix:/nope/lab.sock", "s"),
            "--command takes no --listen: --connect names the Virtualbricks"
            " to talk to",
        )

    def test_a_prefix(self):
        self.assertEqual(
            self.parse("--lis", "unix:/tmp/lab.sock").listen,
            (sockets.Socket("/tmp/lab.sock"),),
        )

    def test_the_next_option(self):
        line = self.parse("--listen", "--no-gui")
        self.assertEqual(line.listen, (DEFAULT_SOCKET,))
        self.assertEqual(line.mode, NO_GUI)

    def test_refused(self):
        # what sockets.parse_socket says
        self.assertEqual(
            self.refused("--listen", "~/lab.sock"),
            "argument --listen: ~/lab.sock needs its type: unix:~/lab.sock",
        )
        self.assertEqual(
            self.refused("--listen", "tls:443"),
            "argument --listen: tls:443: the types are unix, tcp and ssl, as"
            " unix:PATH or tcp:PORT",
        )
        self.assertEqual(
            self.refused("--listen", "ssl:8765"),
            "argument --listen: ssl:8765 needs privateKey=FILE, the key of"
            " its certificate",
        )


class TestConnect(Base):

    def test_unset(self):
        # without it, the namespace says so
        self.assertIs(parser().parse_args([]).target, UNSET)
        self.assertEqual(
            parser().parse_args(["--connect"]).target, DEFAULT_SOCKET
        )

    def test_a_description(self):
        self.assertEqual(
            self.parse("--connect", "tcp:lab.example:8765").target,
            sockets.Socket(None, "amp", "tcp", "lab.example", 8765),
        )

    def test_the_last(self):
        # a second one replaces the first
        self.assertEqual(
            self.parse("--connect", "tcp:lab:1", "--connect=tcp:lab:2").target,
            sockets.Socket(None, "amp", "tcp", "lab", 2),
        )

    def test_a_keyword_to_listen(self):
        self.assertEqual(
            self.refused("--connect", "tcp:8765:interface=::1"),
            "argument --connect: tcp:8765:interface=::1: --connect reaches"
            " the machine of host=, as tcp:lab.example:8765; interface= is"
            " where Virtualbricks listens",
        )

    def test_the_workspace(self):
        # --workspace names the Virtualbricks of --connect alone
        line = self.parse("--connect", "--workspace", "/srv/labs")
        self.assertEqual(line.target, DEFAULT_SOCKET)
        self.assertEqual(line.workspace, "/srv/labs")
        message = (
            "--connect and --workspace each name a Virtualbricks: give one"
            " of them"
        )
        self.assertEqual(
            self.refused(
                "--connect", "tcp:lab:8765", "--workspace", "/srv/labs"
            ),
            message,
        )
        self.assertEqual(
            self.refused(
                "--connect=tcp:lab:8765", "--workspace=/srv/labs", "--command"
            ),
            message,
        )

    def test_the_next_word(self):
        # argparse takes it, and says how to give --connect alone
        self.assertEqual(
            self.refused("--command", "--connect", "brick", "list"),
            "argument --connect: brick: the types are unix, tcp and ssl, as"
            " unix:PATH or tcp:PORT. For --connect alone before the words of"
            " --command, end the options with --: --connect -- brick",
        )
        line = self.parse("--command", "--connect", "--", "brick", "list")
        self.assertEqual(line.words, ("brick", "list"))
        self.assertEqual(line.target, DEFAULT_SOCKET)
        line = self.parse("--connect", "--command", "brick", "list")
        self.assertEqual(line.words, ("brick", "list"))

    def test_the_protocol(self):
        # the windows speak AMP; --command speaks either
        self.assertEqual(
            self.refused("--connect", "unix:/tmp/lab.sock:protocol=json"),
            "--connect opens the windows, which speak AMP: protocol=json is"
            " for --command",
        )
        line = self.parse(
            "--connect", "unix:/tmp/lab.sock:protocol=json", "--command", "s"
        )
        self.assertEqual(line.target.protocol, sockets.JSON)


class TestConnectPaths(Base):

    def test_an_absolute_path(self):
        home = short_folder(self)
        os.environ["HOME"] = home
        self.assertEqual(
            self.parse("--connect", "unix:~/lab.sock").target,
            sockets.Socket(os.path.join(home, "lab.sock")),
        )

    def test_the_folder(self):
        folder = os.path.join(self.root, "nope")
        self.assertEqual(
            self.refused("--connect", f"unix:{folder}/lab.sock"),
            f"--connect: {folder} doesn't exist",
        )

    def test_the_files(self):
        # its files are the client's to read
        self.assertEqual(
            self.parse(
                "--connect",
                "ssl:lab.example:8765:caCertsDir=~/vb/lab:privateKey=~/a.key",
                "--command",
                "status",
            ).target,
            sockets.Socket(
                None,
                "amp",
                "ssl",
                "lab.example",
                8765,
                private_key=os.path.join(self.root, "a.key"),
                ca_dir=os.path.join(self.root, "vb", "lab"),
            ),
        )


class TestTcpListen(Base):

    def tcp(self, port, host="127.0.0.1", protocol="amp", token_file=None):
        return sockets.Socket(None, protocol, "tcp", host, port, token_file)

    def write_token(self, path, mode=0o600):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as file:
            file.write("0123456789abcdef\n")
        os.chmod(path, mode)

    def test_a_port(self):
        self.assertEqual(
            self.parse("--listen", "tcp:8765").listen, (self.tcp(8765),)
        )
        # the token file is made when the socket opens
        self.assertFalse(os.path.exists(locations.token_file()))

    def test_the_same_port_twice(self):
        self.assertEqual(
            self.refused(
                "--listen",
                "tcp:8765",
                "--listen",
                "tcp:port=8765:protocol=json",
            ),
            "--listen: 127.0.0.1 port 8765 is given twice",
        )

    def test_a_token_file(self):
        folder = os.path.join(self.root, "vb")
        self.assertEqual(
            self.refused("--listen", "tcp:8765:tokenFile=~/vb/lab1.token"),
            f"--listen: {folder} doesn't exist",
        )
        os.mkdir(folder)
        path = os.path.join(folder, "lab1.token")
        self.assertEqual(
            self.parse(
                "--listen", "tcp:8765:tokenFile=~/vb/lab1.token"
            ).listen,
            (self.tcp(8765, token_file=path),),
        )
        self.write_token(path, 0o644)
        self.assertEqual(
            self.refused("--listen", "tcp:8765:tokenFile=~/vb/lab1.token"),
            f"--listen: Others can read or change {path}: chmod 600 {path}",
        )

    def test_the_default_token(self):
        path = locations.token_file()
        self.write_token(path)
        self.assertEqual(
            self.parse("--listen", "tcp:8765").listen, (self.tcp(8765),)
        )
        with open(path, "w") as file:
            file.write("1234\n")
        self.assertEqual(
            self.refused("--listen", "tcp:8765"),
            f"--listen: The token of {path} has 4 characters; a token has at"
            " least 16",
        )

    def test_with_connect(self):
        # the machine to talk to; the token is the client's to read
        self.write_token(locations.token_file(), 0o644)
        self.assertEqual(
            self.parse(
                "--connect", "tcp:lab.example:8765", "--command", "status"
            ).target,
            self.tcp(8765, "lab.example"),
        )


class TestSslListen(Base):

    TLS = os.path.join(DATA, "tls")

    def data(self, name):
        return os.path.join(self.TLS, name)

    def test_a_port(self):
        os.symlink(self.TLS, os.path.join(self.root, "vb"))
        [socket] = self.parse(
            "--listen",
            "ssl:8765:interface=0.0.0.0:privateKey=~/vb/server.key"
            ":certKey=~/vb/server.pem",
        ).listen
        folder = os.path.join(self.root, "vb")
        self.assertEqual(
            socket,
            sockets.Socket(
                None,
                "amp",
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
            "--listen",
            f"ssl:8765:privateKey={self.data('server.key')}"
            f":certKey={self.data('server.pem')}:caCertsDir={self.TLS}",
        )

    def test_the_files(self):
        key = self.data("server.key")
        self.assertEqual(
            self.refused(
                "--listen",
                f"ssl:8765:privateKey={key}:certKey={self.data('bob.pem')}",
            ),
            f"--listen: The key {key} isn't that of the certificate"
            f" {self.data('bob.pem')}",
        )
        missing = os.path.join(self.root, "lab.pem")
        self.assertEqual(
            self.refused("--listen", "ssl:8765:privateKey=~/lab.pem"),
            f"--listen: {missing} doesn't exist",
        )
        self.assertEqual(
            self.refused(
                "--listen",
                f"ssl:8765:privateKey={key}:certKey={self.data('server.pem')}"
                f":caCertsDir={self.root}",
            ),
            f"--listen: {self.root} has no .pem certificate",
        )


class TestWords(Base):

    def test_options_end_at_the_first_word(self):
        line = self.parse("--command", "status", "--listen")
        self.assertEqual(line.words, ("status", "--listen"))
        self.assertEqual(line.listen, ())
        line = self.parse("--command", "brick", "config", "vm1", "-m", "512")
        self.assertEqual(line.words, ("brick", "config", "vm1", "-m", "512"))

    def test_and_at_two_dashes(self):
        line = self.parse("--command", "--", "--listen")
        self.assertEqual(line.words, ("--listen",))
        self.assertEqual(line.listen, ())
        # only the first ends the options
        self.assertEqual(
            self.parse("--command", "--", "--", "x").words, ("--", "x")
        )

    def test_without_command(self):
        self.assertEqual(
            self.refused("brick", "list", "it's"),
            "unexpected words: brick list it's. To send them to the"
            " Virtualbricks that runs: virtualbricks --command brick list"
            " 'it'\"'\"'s'",
        )

    def test_the_standard_input(self):
        # without words, the lines of the standard input, not a terminal
        self.assertEqual(self.parse("--command").words, ())
        self.assertEqual(
            self.refused("--command", tty=True),
            "--command needs a command, as virtualbricks --command brick"
            " list, or lines on its standard input",
        )
        self.assertEqual(
            self.parse("--command", "status", tty=True).words, ("status",)
        )

    def test_unknown_option(self):
        self.assertEqual(
            self.refused("--nope"), "unrecognized arguments: --nope"
        )


class TestClient(Base):

    def test_the_options_of_a_run(self):
        for args, name in [
            (["--no-gui"], "no-gui"),
            (["--no-term"], "no-term"),
            (["--run", self.script], "run"),
            (["--lock", "none"], "lock"),
            (["-l", "vb.log"], "logfile"),
            (["--logger", "a.b"], "logger"),
        ]:
            self.assertEqual(
                self.refused("--command", *args, "status"),
                f"--command takes no --{name}: it talks to a Virtualbricks"
                " that runs",
            )
        # --workspace sets the lock, but isn't --lock
        self.assertEqual(
            self.parse("--workspace", "/srv/labs", "--command", "s").mode,
            COMMAND,
        )

    def test_connect_and_run(self):
        # --connect sends the commands of --run
        self.assertEqual(
            self.refused("--connect", "--run", self.script, "--no-term"),
            "--connect takes no --no-term: it talks to a Virtualbricks that"
            " runs",
        )

    def test_listen(self):
        self.assertEqual(
            self.refused("--command", "--listen", "--", "status"),
            "--command takes no --listen: --connect names the Virtualbricks"
            " to talk to",
        )


class TestWindows(Base):

    def test_what_is_for_the_bricks(self):
        for args, name in [
            (["--no-gui"], "no-gui"),
            (["--lock", "user"], "lock"),
            (["--listen"], "listen"),
        ]:
            self.assertEqual(
                self.refused("--connect", *args),
                "--connect opens the windows of another Virtualbricks:"
                f" --{name} is for the one that runs the bricks",
            )

    def test_no_term(self):
        self.assertTrue(self.parse("--connect", "--no-term").no_term)


class TestVerbosity(Base):

    def test_steps(self):
        for args, verbosity in [
            ([], 0),
            (["-v"], 1),
            (["-vv"], 2),
            (["--verbose", "--verbose", "--verbose"], 3),
            (["-q"], -1),
            (["--quiet", "-q"], -2),
            (["-v", "-q"], 0),
            (["-b"], 2),
            (["--debug", "-q"], 1),
            (["-v", "-b"], 2),
        ]:
            self.assertEqual(self.parse(*args).verbosity, verbosity, args)

    def test_with_a_short_option(self):
        line = self.parse("-vl", "vb.log")
        self.assertEqual(line.verbosity, 1)
        self.assertEqual(line.logfile, "vb.log")


class TestExit(Base):

    def test_parse_or_exit(self):
        self.patch(sys, "argv", ["virtualbricks", "--nope"])
        error = self.assertRaises(SystemExit, parse_or_exit)
        self.assertEqual(
            error.code, "virtualbricks: unrecognized arguments: --nope"
        )
        self.assertEqual(parse_or_exit(["--no-gui"]).mode, NO_GUI)

    def test_version(self):
        out = io.StringIO()
        self.patch(sys, "stdout", out)
        error = self.assertRaises(SystemExit, self.parse, "--version")
        self.assertEqual(error.code, 0)
        self.assertEqual(out.getvalue(), f"Virtualbricks {__version__}\n")


class TestOptions(unittest.TestCase):

    def test_the_options(self):
        strings = {
            string
            for action in parser()._actions
            for string in action.option_strings
        }
        self.assertEqual(
            strings,
            {
                "-h",
                "--help",
                "--no-term",
                "--no-gui",
                "--command",
                "--listen",
                "--connect",
                "-l",
                "--logfile",
                "--run",
                "--workspace",
                "--lock",
                "--logger",
                "-v",
                "--verbose",
                "-q",
                "--quiet",
                "-b",
                "--debug",
                "--version",
            },
        )

    def test_imports(self):
        # no Twisted, and of Virtualbricks only sockets, locks and
        # console.wire, for the checks of the sockets, even to parse one; a
        # unix one in a folder that is there, as a tcp one reads the token
        code = (
            "import sys\n"
            "from virtualbricks import cli\n"
            "cli.parse(['--workspace', '/srv',"
            " '--listen', 'unix:/tmp/vb-imports.sock'])\n"
            "print(sorted(name for name in sys.modules"
            " if name.startswith(('twisted', 'virtualbricks', 'gi'))))\n"
        )
        output = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        self.assertEqual(
            output,
            "['virtualbricks', 'virtualbricks.cli',"
            " 'virtualbricks.console', 'virtualbricks.console.wire',"
            " 'virtualbricks.i18n', 'virtualbricks.locations',"
            " 'virtualbricks.locks', 'virtualbricks.sockets']\n",
        )
