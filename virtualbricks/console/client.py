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
Virtualbricks that runs through its control socket, and its answer. It
speaks the text protocol, or AMP to a socket with ``protocol=amp``, through
:mod:`virtualbricks.console.ampbox`. Over tcp, it proves first that it knows
the token, and checks that the other end knows it too. Over ssl, it checks
the certificate of Virtualbricks, shows its own if it has one, and proves
the token when asked.

The words after ``--command`` are the command, quoted again for the
console; without words, the lines of the standard input are, each sent
after the answer to the one before, up to the first error. The answer goes
to the standard output, an error to the standard error. It loads neither
Twisted's reactor nor GTK, takes no lock and opens no project.
"""

from __future__ import annotations

import ipaddress
import os
import pwd
import shlex
import socket
import ssl
import sys

from virtualbricks import locations, locks
from virtualbricks.console import ampbox, wire
from virtualbricks.i18n import _, ngettext

# The exit statuses: the command was done, it failed, nothing answered it.
DONE = 0
FAILED = 1
UNANSWERED = 2
# as a shell reports SIGINT
INTERRUPTED = 130
# How long a socket has to answer and to prove, in seconds.
CONNECT_TIMEOUT = wire.PROOF_TIMEOUT
# The version of the AMP commands that --command knows, as ampwire.PROTOCOL
AMP_PROTOCOL = 1


class Unanswered(Exception):
    """No Virtualbricks answered; str() says why, to the user."""


def _closed() -> str:
    return _(
        "Virtualbricks closed the connection before it answered: it may have"
        " ended"
    )


def _another_protocol(version: object) -> str:
    return _(
        "The Virtualbricks that runs, version {version}, speaks another"
        " protocol: restart it"
    ).format(version=version)


class Connection:
    """
    A connection to a text socket, a wire.Socket: requests and their
    answers. A socket that asks for the proof of the token gets it first.
    """

    def __init__(self, sock: socket.socket, target: wire.Socket | None = None):
        self.sock = sock
        self.target = target
        self.reader = sock.makefile("rb")
        try:
            self.greeting = self.open()
        except BaseException:
            self.reader.close()
            raise

    def open(self) -> dict:
        """The greeting of Virtualbricks, once the token is proved."""

        first = self.receive()
        if first.get("protocol") != wire.PROTOCOL:
            raise Unanswered(_another_protocol(first.get("version")))
        if first.get("auth") == wire.AUTH_TOKEN:
            first = self.prove(first.get("nonce"))
        return first

    def close(self):
        self.reader.close()
        self.sock.close()

    def where(self) -> str:
        return self.target.where() if self.target else _("the socket")

    def local(self) -> bool:
        """Whether the Virtualbricks at the other end runs on this machine."""

        if self.target is None or self.target.kind == "unix":
            return True
        host = self.sock.getpeername()[0]
        return ipaddress.ip_address(host.partition("%")[0]).is_loopback

    def prove(self, nonce: object) -> dict:
        """Prove that this end knows the token; the greeting that follows."""

        if not isinstance(nonce, str):
            raise Unanswered(_not_the_protocol())
        token = self.read_token()
        mine = wire.new_nonce()
        proof = wire.proof(token, "client", nonce, mine)
        self.send(wire.token_proof(mine, proof))
        greeting = self.receive()
        if greeting.get("ok") is False:
            raise Unanswered(
                _("The Virtualbricks on {where} has another token").format(
                    where=self.where()
                )
            )
        expected = wire.proof(token, "server", nonce, mine)
        if not wire.same_proof(greeting.get("proof"), expected):
            raise Unanswered(
                _(
                    "What answers on {where} doesn't know your token: it"
                    " isn't your Virtualbricks"
                ).format(where=self.where())
            )
        return greeting

    def read_token(self) -> str:
        path = None
        if self.target is not None:
            path = self.target.token_file
        if path is None:
            path = locations.token_file()
        try:
            return wire.read_token(path)
        except wire.NoToken:
            raise Unanswered(
                _(
                    "No token: {path} doesn't exist. Copy the one of the"
                    " machine where Virtualbricks runs, or name another with"
                    " tokenFile="
                ).format(path=path)
            ) from None
        except wire.Unusable as exc:
            raise Unanswered(
                _("{reason}: no command sent").format(reason=exc)
            ) from None

    def send(self, message: dict):
        self.send_bytes(wire.encode(message))

    def send_bytes(self, data: bytes):
        try:
            self.sock.sendall(data)
        except (BrokenPipeError, ConnectionResetError):
            raise Unanswered(_closed()) from None

    def reading(self, read):
        """What read() reads; b"" at the end of the connection."""

        try:
            return read()
        except TimeoutError:
            raise Unanswered(self.silent()) from None
        except ssl.SSLError as exc:
            # over TLS 1.3, a refused certificate is known at the first read
            raise Unanswered(_refused_by(self.target, exc)) from None
        except ConnectionResetError:
            return b""

    def silent(self) -> str:
        """Why nothing came before the time was up, to the user."""

        # an AMP socket waits for the first box
        return _(
            "{where} didn't greet in {seconds} seconds: if it speaks AMP, add"
            " protocol=amp"
        ).format(where=self.where(), seconds=CONNECT_TIMEOUT)

    def receive(self) -> dict:
        line = self.reading(self.reader.readline)
        if not line.endswith(b"\n"):
            raise Unanswered(_closed())
        try:
            return wire.decode(line)
        except ValueError:
            raise Unanswered(_not_the_protocol()) from None

    def ask(self, line: str, cwd: str | None = None) -> dict:
        """The answer to the command of line, whose paths are read in cwd."""

        self.send(wire.request(line, cwd))
        return self.receive()


class AMPError(Exception):
    """The error of an AMP command: its code and its description."""

    def __init__(self, code: bytes, description: str):
        super().__init__(code, description)
        self.code = code
        self.description = description


class AMPConnection(Connection):
    """
    A connection to an AMP socket: the commands of ampwire, as boxes. A
    socket that asks for the proof of the token gets it first.
    """

    tag = 0

    def open(self) -> dict:
        try:
            hello = self.call(b"Hello")
        except AMPError as exc:
            if exc.code != b"TOKEN_NEEDED":
                raise self.unexpected(exc) from None
            self.authenticate()
            hello = self.call(b"Hello")
        greeting = {
            "protocol": ampbox.integer(hello.get(b"protocol", b"")),
            "version": ampbox.text(hello.get(b"version", b"")),
        }
        if greeting["protocol"] != AMP_PROTOCOL:
            raise Unanswered(_another_protocol(greeting["version"]))
        return greeting

    def authenticate(self):
        """Prove that this end knows the token: Challenge, Authenticate."""

        token = self.read_token()
        try:
            nonce = ampbox.text(self.call(b"Challenge").get(b"nonce", b""))
            mine = wire.new_nonce()
            proof = wire.proof(token, "client", nonce, mine)
            answer = self.call(
                b"Authenticate", nonce=mine.encode(), proof=proof.encode()
            )
        except AMPError as exc:
            if exc.code == b"WRONG_TOKEN":
                raise Unanswered(
                    _("The Virtualbricks on {where} has another token").format(
                        where=self.where()
                    )
                ) from None
            raise self.unexpected(exc) from None
        expected = wire.proof(token, "server", nonce, mine)
        given = ampbox.text(answer.get(b"proof", b""))
        if not wire.same_proof(given, expected):
            raise Unanswered(
                _(
                    "What answers on {where} doesn't know your token: it"
                    " isn't your Virtualbricks"
                ).format(where=self.where())
            )

    def call(self, command: bytes, **arguments: bytes) -> dict:
        """The answer of command; AMPError if it fails."""

        self.tag += 1
        tag = b"%x" % self.tag
        box = {ampbox.ASK: tag, ampbox.COMMAND: command}
        box.update((key.encode(), value) for key, value in arguments.items())
        self.send_bytes(ampbox.encode(box))
        while True:
            answer = self.receive_box()
            if answer.get(ampbox.ANSWER) == tag:
                return answer
            if answer.get(ampbox.ERROR) == tag:
                raise AMPError(
                    answer.get(ampbox.ERROR_CODE, b""),
                    ampbox.text(answer.get(ampbox.ERROR_DESCRIPTION, b"")),
                )
            # a box that isn't the answer isn't for --command

    def receive_box(self) -> dict:
        try:
            return ampbox.read(
                lambda size: self.reading(lambda: self.reader.read(size))
            )
        except ampbox.Closed:
            raise Unanswered(_closed()) from None
        except ampbox.BadBox:
            raise Unanswered(_not_the_protocol()) from None

    def unexpected(self, exc: AMPError) -> Unanswered:
        """An error that --command doesn't expect, to the user."""

        return Unanswered(f"{self.where()}: {exc.description}")

    def silent(self) -> str:
        return _timed_out(self.where())

    def ask(self, line: str, cwd: str | None = None) -> dict:
        """
        The answer to the command of line, as the text protocol gives it:
        what a command did before it failed doesn't come over AMP.
        """

        arguments = {"line": line.encode("utf-8")}
        if cwd is not None:
            arguments["cwd"] = cwd.encode("utf-8")
        try:
            answer = self.call(b"Run", **arguments)
        except ampbox.TooLong:
            return wire.refusal(
                _(
                    "The command is longer than the {most} bytes that AMP"
                    " carries"
                ).format(most=ampbox.MAX_VALUE)
            )
        except AMPError as exc:
            if exc.code in (b"COMMAND_FAILED", b"ANSWER_TOO_LONG"):
                return wire.refusal(exc.description)
            raise self.unexpected(exc) from None
        try:
            return wire.answer(ampbox.texts(answer.get(b"lines", b"")))
        except ampbox.BadBox:
            raise Unanswered(_not_the_protocol()) from None


def _not_the_protocol() -> str:
    return _("What answers on the socket doesn't speak its protocol")


def _timed_out(where: str) -> str:
    return _("{where} didn't answer in {seconds} seconds").format(
        where=where, seconds=CONNECT_TIMEOUT
    )


def _processes(holders) -> str:
    names = [f"{pid} of {user}" for pid, user in holders]
    if len(names) > 1:
        names[-2:] = [
            _("{one} and {other}").format(one=names[-2], other=names[-1])
        ]
    return ", ".join(names)


def _nobody(path: str) -> str:
    """Why nothing answers on path: the Virtualbricks that runs, if any."""

    if not wire.in_runtime_dir(path):
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
            " was started without --socket or with another one, or its log"
            " says why"
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
        "No Virtualbricks of yours runs. Start one with a socket, as"
        " virtualbricks --no-gui --socket"
    )


def connect(target: wire.Socket | None = None) -> Connection:
    """
    Connect to the Virtualbricks that listens on target, a wire.Socket, the
    socket in the runtime folder if None; raise Unanswered if none can be
    reached.
    """

    if target is None:
        target = wire.Socket(locations.control_socket())
    if target.kind != "unix":
        return _connect_network(target)
    path = target.path
    try:
        wire.check_length(path)
        there = wire.check_socket(path)
        if there:
            wire.check_path(path, wire.in_runtime_dir(path))
    except wire.Unusable as exc:
        raise Unanswered(
            _("{reason}: no command sent").format(reason=exc)
        ) from None
    if not there:
        raise Unanswered(_nobody(path))
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.connect(path)
        # the socket greets at once, or it isn't one of the text protocol
        sock.settimeout(CONNECT_TIMEOUT)
        return _open(sock, target)
    except (ConnectionRefusedError, FileNotFoundError):
        # a socket left by a crash
        sock.close()
        raise Unanswered(_nobody(path)) from None
    except OSError as exc:
        sock.close()
        raise Unanswered(f"{path}: {exc.strerror}") from None
    except BaseException:
        sock.close()
        raise


def _loopback(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host == "localhost"


def _pem_files(folder: str) -> list[str]:
    """The .pem files of folder, as Twisted reads its caCertsDir."""

    try:
        names = sorted(os.listdir(folder))
    except FileNotFoundError:
        raise Unanswered(
            _("{path} doesn't exist: no command sent").format(path=folder)
        ) from None
    except OSError as exc:
        raise Unanswered(f"{folder}: {exc.strerror}") from None
    paths = [os.path.join(folder, name) for name in names]
    paths = [
        path
        for path in paths
        if path.lower().endswith(".pem") and os.path.isfile(path)
    ]
    if not paths:
        raise Unanswered(
            _("{path} has no .pem certificate: no command sent").format(
                path=folder
            )
        )
    return paths


def _tls(target: wire.Socket) -> ssl.SSLContext:
    """
    The TLS of --command: the certificates it trusts for Virtualbricks,
    those of ca_dir or of the system, and its own certificate, if any.
    """

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    if target.ca_dir is None:
        context.load_default_certs()
    else:
        for path in _pem_files(target.ca_dir):
            try:
                context.load_verify_locations(cafile=path)
            except ssl.SSLError:
                raise Unanswered(
                    _(
                        "{path} isn't a certificate in PEM: no command sent"
                    ).format(path=path)
                ) from None
    if target.private_key or target.cert:
        cert = target.cert or target.private_key
        key = target.private_key or target.cert
        try:
            context.load_cert_chain(cert, key)
        except ssl.SSLError:
            raise Unanswered(
                _(
                    "The key {key} isn't that of the certificate {cert}, or"
                    " isn't in PEM: no command sent"
                ).format(key=key, cert=cert)
            ) from None
        except OSError as exc:
            raise Unanswered(
                f"{exc.filename or cert}: {exc.strerror}"
            ) from None
    return context


def _refused_by(target: wire.Socket | None, exc: ssl.SSLError) -> str:
    """Why the TLS of target refused this end, from the error."""

    host = target.host if target is not None else _("the socket")
    reason = exc.reason or str(exc)
    mine = target is not None and bool(target.private_key or target.cert)
    if "CERTIFICATE_REQUIRED" in reason or (
        "HANDSHAKE_FAILURE" in reason and not mine
    ):
        return _(
            "{host} asks for your certificate: privateKey= and certKey="
        ).format(host=host)
    if "ALERT" in reason and mine:
        return _("{host} refused your certificate").format(host=host)
    return f"{host}: {reason}"


def _connect_network(target: wire.Socket) -> Connection:
    where = target.where()
    context = _tls(target) if target.kind == "ssl" else None
    try:
        sock = socket.create_connection(
            (target.host, target.port), timeout=CONNECT_TIMEOUT
        )
    except socket.gaierror as exc:
        raise Unanswered(
            _("Can't find {host}: {reason}").format(
                host=target.host, reason=exc.strerror
            )
        ) from None
    except ConnectionRefusedError:
        message = _("Nothing listens on {where}").format(where=where)
        if _loopback(target.host):
            message = _(
                "Nothing listens on {where}. Start Virtualbricks with"
                " --socket {kind}:{port}"
            ).format(where=where, kind=target.kind, port=target.port)
        raise Unanswered(message) from None
    except TimeoutError:
        raise Unanswered(_timed_out(where)) from None
    except OSError as exc:
        raise Unanswered(f"{where}: {exc.strerror}") from None
    if context is not None:
        sock = _handshake(context, sock, target)
    try:
        return _open(sock, target)
    except BaseException:
        sock.close()
        raise


def _open(sock: socket.socket, target: wire.Socket) -> Connection:
    """The connection on sock, in the protocol of target, once it's open."""

    if target.protocol == wire.AMP:
        connection: Connection = AMPConnection(sock, target)
    else:
        connection = Connection(sock, target)
    # the command takes as long as it takes
    sock.settimeout(None)
    return connection


def _handshake(context, sock, target):
    """The TLS of sock, once the certificate of target is checked."""

    try:
        return context.wrap_socket(sock, server_hostname=target.host)
    except ssl.SSLCertVerificationError as exc:
        sock.close()
        raise Unanswered(
            _(
                "The certificate of {host} isn't one you trust: {reason}."
                " Name the folder of its certificate with caCertsDir="
            ).format(host=target.host, reason=exc.verify_message)
        ) from None
    except ssl.SSLError as exc:
        sock.close()
        raise Unanswered(_refused_by(target, exc)) from None
    except TimeoutError:
        sock.close()
        raise Unanswered(_timed_out(target.where())) from None
    except OSError as exc:
        sock.close()
        raise Unanswered(f"{target.where()}: {exc.strerror}") from None


def _commands(words, stdin):
    """The commands to send, with the number of their line of input."""

    if words:
        yield None, shlex.join(words)
        return
    for number, line in enumerate(stdin, start=1):
        line = line.rstrip("\n")
        if line.strip():
            yield number, line


def main(words, target=None, stdin=None, stdout=None, stderr=None) -> int:
    """
    Send the command of words, or the lines of stdin without words, to the
    Virtualbricks that listens on target, a wire.Socket, the default socket
    if None; write the answers and return the exit status.
    """

    stdin = sys.stdin if stdin is None else stdin
    stdout = sys.stdout if stdout is None else stdout
    stderr = sys.stderr if stderr is None else stderr
    connection = None
    try:
        connection = connect(target)
        # the folders of another machine aren't those of this one
        cwd = os.getcwd() if connection.local() else None
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
