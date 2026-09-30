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
The windows' end of a connection: agreeing, following, and RemoteEngine,
whose calls change the factory there, which its copy follows.
"""

import os

from twisted.internet import address, defer, endpoints, reactor
from twisted.protocols import amp
from twisted.test import iosim

from virtualbricks import __version__, locations
from virtualbricks.bricks import FakeProcess
from virtualbricks.bricks.brickinfo import NEW_KINDS
from virtualbricks.bricks.eventaction import ShellAction
from virtualbricks.config import settings
from virtualbricks.console import ampcommands, ampwire, control, wire
from virtualbricks.bricks.virtualmachine import UsbDevice
from virtualbricks.config import images
from virtualbricks.errors import CommandError
from virtualbricks.qemu import run
from virtualbricks.programs import (
    QEMU_QUESTIONS,
    Answer,
    ProgramError,
    Programs,
    machine_question,
)
from virtualbricks.remote import (
    answers,
    client,
    commands,
    facts,
    follower,
    mirror,
)
from virtualbricks.remote.client import (
    NotYet,
    Refused,
    RemoteEngine,
    Windows,
    endpoint_of,
    start,
)
from virtualbricks.remote.drafts import draft_of
from virtualbricks.remote.follower import LogKeeper
from virtualbricks.remote.mirror import MirrorFactory
from virtualbricks.tests import FakeLogger, FakeTrash, use_workspace
from virtualbricks.tests.console import ConsoleTestCase
from virtualbricks.tests.console.test_control import TOKEN, tls_file
from virtualbricks.tests.config.test_images import (
    INFO,
    FakeQemuImg,
    FakeWorkspace,
)
from virtualbricks.tests.remote.test_mirror import Project
from virtualbricks.tests.test_programs import FakeRun, executable

TARGET = wire.Socket("/run/lab.amp", wire.AMP)


def started(brick):
    """What starting brick does there: its process runs."""

    brick.proc = FakeProcess(brick)
    brick.changed.notify(brick)
    return defer.succeed(brick)


def stopped(brick, **kwargs):
    brick.proc = None
    brick.changed.notify(brick)
    return defer.succeed(brick)


class ClientTestCase(ConsoleTestCase):
    """A Virtualbricks there, the windows here, and their connection."""

    token = None

    def setUp(self):
        super().setUp()
        self.factory.runtime_dir = "/run/vb"
        self.patch(control, "logger", FakeLogger())
        self.patch(follower, "logger", FakeLogger())
        self.patch(mirror, "logger", FakeLogger())
        self.patch(amp, "_log", FakeLogger())
        self.workspace = use_workspace(self)
        self.workspace.current = Project(os.path.abspath(self.mktemp()))
        os.makedirs(self.workspace.current.path)
        self.patch(follower, "keeper", LogKeeper())
        self.server = control.ControlFactory(
            self.factory,
            self.clock(),
            control.AMPControl,
            # a token is for a network socket
            wire.Socket(None, wire.AMP, "tcp", "127.0.0.1", 8765),
            token=self.token,
        )
        self.copy = MirrorFactory(self.clock())
        peer = address.IPv4Address("TCP", "127.0.0.1", 50412)
        self.windows, self.connection, self.pump = (
            iosim.connectedServerAndClient(
                lambda: self.server.buildProtocol(None),
                lambda: Windows(self.copy),
                serverTransportFactory=lambda protocol: iosim.FakeTransport(
                    protocol, True, peerAddress=peer
                ),
            )
        )
        self.quits = []
        self.engine = RemoteEngine(
            self.copy,
            self.windows,
            "lab",
            quit=lambda: self.quits.append(True),
        )

    def quiet(self, deferred):
        """
        deferred, once the connection is quiet. Chained first: AMP drops a
        connection whose failed call has no errback when the answer comes.
        """

        answer = defer.Deferred()
        deferred.chainDeferred(answer)
        self.pump.flush()
        self.clock().advance(0)
        self.pump.flush()
        return answer

    def done(self, deferred):
        return self.successResultOf(self.quiet(deferred))

    def refused(self, deferred, *errors):
        return self.failureResultOf(self.quiet(deferred), *errors)

    def start(self, target=TARGET):
        return defer.ensureDeferred(start(self.windows, target))


class TestStart(ClientTestCase):

    def test_start(self):
        self.factory.new_brick("switch", "sw1")
        answer = self.done(self.start())
        self.assertEqual(answer, {"project": "lab1", "version": __version__})
        self.assertTrue(self.copy.whole)
        self.assertIsNotNone(self.copy.get_brick("sw1"))

    def test_protocol_1_only(self):
        self.patch(ampwire, "PROTOCOLS", (1,))
        failure = self.refused(self.start(), Refused)
        self.assertEqual(
            failure.getErrorMessage(),
            "/run/lab.amp speaks only protocol 1 of AMP: its Virtualbricks"
            " is older than these windows",
        )

    def test_another_version(self):
        self.patch(control, "__version__", "9.9.9")
        failure = self.refused(self.start(), Refused)
        self.assertEqual(
            failure.getErrorMessage(),
            f"/run/lab.amp runs Virtualbricks 9.9.9, these windows are"
            f" {__version__}: run the same version on both",
        )

    def test_no_follow(self):
        locate = control.AMPControl.locateResponder

        def without_follow(connection, name):
            return None if name == b"Follow" else locate(connection, name)

        self.patch(control.AMPControl, "locateResponder", without_follow)
        failure = self.refused(self.start(), Refused)
        self.assertEqual(
            failure.getErrorMessage(),
            "/run/lab.amp has no commands for the windows: run the same"
            " Virtualbricks on both",
        )

    def test_where(self):
        self.assertEqual(
            client.where(wire.Socket(os.path.expanduser("~/lab.amp"))),
            "~/lab.amp",
        )
        target = wire.parse_socket("tcp:lab.example:8765", client=True)
        self.assertEqual(client.where(target), "lab.example")


class TestToken(ClientTestCase):

    token = TOKEN

    def target(self, token):
        path = os.path.abspath(self.mktemp())
        if token is not None:
            with open(path, "w") as file:
                file.write(token + "\n")
            os.chmod(path, 0o600)
        return wire.Socket(None, wire.AMP, "tcp", "lab", 8765, token_file=path)

    def test_the_token(self):
        self.done(self.start(self.target(TOKEN)))
        self.assertTrue(self.copy.whole)

    def test_a_wrong_token(self):
        failure = self.refused(self.start(self.target("x" * 64)), Refused)
        self.assertEqual(
            failure.getErrorMessage(), "lab doesn't take your token"
        )

    def test_no_token(self):
        target = self.target(None)
        failure = self.refused(self.start(target), Refused)
        self.assertEqual(
            failure.getErrorMessage(),
            f"lab asks for the token, and {target.token_file} has none:"
            " copy the token of that Virtualbricks there",
        )


class TestEngine(ClientTestCase):

    def setUp(self):
        super().setUp()
        self.sw1 = self.factory.new_brick("switch", "sw1")
        self.tap = self.factory.new_brick("tap", "tap1")
        self.boot = self.factory.new_event("boot")
        self.done(self.start())

    def test_what_the_windows_read(self):
        self.assertIs(self.engine.factory, self.copy)
        self.assertFalse(self.engine.local)

    def test_start_and_stop(self):
        self.sw1.poweron = lambda: started(self.sw1)
        self.sw1.poweroff = lambda **kwargs: stopped(self.sw1)
        copy = self.copy.get_brick("sw1")
        self.done(self.engine.start(copy))
        self.assertIsNotNone(copy.proc)
        self.done(self.engine.stop(copy))
        self.assertIsNone(copy.proc)

    def test_a_refusal(self):
        self.factory.remove_brick(self.tap)
        failure = self.refused(
            self.engine.start(self.copy.get_brick("tap1")),
            ampcommands.NotFound,
        )
        self.assertEqual(failure.getErrorMessage(), "No brick named tap1")

    def test_new_brick(self):
        kind = next(kind for kind in NEW_KINDS if kind.type == "Switch")
        brick = self.done(self.engine.new_brick(kind.type, "sw 2"))
        self.assertIs(brick, self.copy.get_brick("sw_2"))
        self.assertIsNotNone(self.factory.get_brick("sw_2"))

    def test_connect(self):
        connected = self.done(
            self.engine.connect(
                self.copy.get_brick("tap1"), self.copy.get_brick("sw1")
            )
        )
        self.assertTrue(connected)
        self.assertIs(self.tap.plugs[0].sock, self.sw1.socks[0])
        self.assertIsNotNone(self.copy.get_brick("tap1").plugs[0].sock)

    def test_rename(self):
        copy = self.copy.get_brick("sw1")
        self.assertEqual(self.done(self.engine.rename(copy, "core")), "sw1")
        self.assertEqual(copy.name, "core")
        self.assertEqual(self.sw1.name, "core")
        image = self.factory.new_image("frr", "/lab/frr.qcow2")
        self.done(self.engine.rename(self.copy.get_event("boot"), "up"))
        self.clock().advance(0)
        self.pump.flush()
        self.done(self.engine.rename(self.copy.get_image("frr"), "deb"))
        self.assertEqual((self.boot.name, image.name), ("up", "deb"))

    def test_duplicate(self):
        copy = self.done(self.engine.duplicate(self.copy.get_brick("sw1")))
        self.assertIs(copy, self.copy.get_brick("copy_of_sw1"))
        event = self.done(self.engine.duplicate(self.copy.get_event("boot")))
        self.assertIs(event, self.copy.get_event("copy_of_boot"))

    def test_remove(self):
        self.factory.new_image("frr", "/lab/frr.qcow2")
        self.clock().advance(0)
        self.pump.flush()
        for item in (
            self.copy.get_brick("tap1"),
            self.copy.get_event("boot"),
            self.copy.get_image("frr"),
        ):
            self.done(self.engine.remove(item))
        self.assertEqual([b.name for b in self.copy.bricks], ["sw1"])
        self.assertEqual(list(self.factory.events), [])
        self.assertEqual(list(self.factory.images), [])

    def test_update_config(self):
        self.done(
            self.engine.update_config(
                self.copy.get_brick("sw1"), {"on_start": "boot"}
            )
        )
        self.assertEqual(self.sw1.config.on_start, "boot")
        self.assertEqual(self.copy.get_brick("sw1").config.on_start, "boot")

    def test_apply(self):
        draft = draft_of(self.copy, "brick", self.copy.get_brick("sw1"))
        draft.set("ports", 8)
        self.done(self.engine.apply(draft))
        self.assertEqual(self.sw1.config.ports, 8)
        self.assertEqual(self.copy.get_brick("sw1").config.ports, 8)

    def test_apply_to_an_image_renamed(self):
        self.factory.new_image("frr", "/lab/frr.qcow2")
        self.clock().advance(0)
        self.pump.flush()
        draft = draft_of(self.copy, "image", self.copy.get_image("frr"))
        draft.set("name", "debian")
        self.done(self.engine.apply(draft))
        self.assertIsNotNone(self.factory.get_image("debian"))

    def test_events(self):
        event = self.done(self.engine.new_event("down", 7))
        self.assertIs(event, self.copy.get_event("down"))
        self.assertEqual(self.factory.get_event("down").config.delay, 7)
        ran = []
        self.boot.update_config({"actions": [ShellAction("true")]})
        self.boot.run_actions = lambda: ran.append(True)
        self.done(self.engine.run_event(self.copy.get_event("boot")))
        self.assertEqual(ran, [True])

    def test_new_image(self):
        path = os.path.abspath(self.mktemp())
        with open(path, "w"):
            pass
        image = self.done(self.engine.new_image("frr", path, "Debian"))
        self.assertIs(image, self.copy.get_image("frr"))
        self.assertEqual(self.factory.get_image("frr").description, "Debian")

    def test_settings(self):
        self.done(self.engine.set_settings({"audio_driver": "pa"}))
        self.assertEqual(settings.get_setting("audio_driver"), "pa")
        self.assertEqual(self.copy.settings["audio_driver"], "pa")

    def test_lacks(self):
        kind = next(kind for kind in NEW_KINDS if kind.type == "Router")
        self.copy.machine["lacks"]["Router"] = {"line": "none", "text": "x"}
        issue = self.done(self.engine.lacks(kind))
        self.assertEqual((issue.line, issue.text), ("none", "x"))
        self.copy.machine["lacks"]["Router"] = None
        self.assertIsNone(self.done(self.engine.lacks(kind)))

    def test_not_yet(self):
        copy = self.copy.get_brick("sw1")
        for deferred in (
            self.engine.terminate(copy),
            self.engine.open_console(copy),
            self.engine.set_readme("# lab"),
        ):
            failure = self.failureResultOf(deferred, NotYet)
            self.assertEqual(
                failure.getErrorMessage(), "Not over a connection, for now"
            )

    def test_quit(self):
        self.done(self.engine.quit())
        self.assertEqual(self.quits, [True])
        # the Virtualbricks there goes on
        self.assertFalse(self.factory.quit_d.called)

    def test_lost(self):
        lost = []
        self.windows.lost.addCallback(lost.append)
        self.windows.transport.loseConnection()
        self.pump.flush()
        self.assertEqual(len(lost), 1)
        self.assertIsInstance(lost[0], Exception)
        failure = self.failureResultOf(
            self.engine.start(self.copy.get_brick("sw1")), Refused
        )
        self.assertEqual(
            failure.getErrorMessage(), "The connection to lab is lost"
        )

    def test_the_log(self):
        messages = []
        self.windows.logged = messages.append
        from twisted.logger import LogLevel

        follower.keeper({"log_format": "hi", "log_level": LogLevel.info})
        self.clock().advance(0)
        self.pump.flush()
        self.assertEqual([message["text"] for message in messages], ["hi"])


class TestFacts(ClientTestCase):
    """What the windows ask of the machine there: its QEMU, its USB."""

    def setUp(self):
        super().setUp()
        # the QEMU program of the setting there, which answers as Debian 13's
        folder = os.path.abspath(self.mktemp())
        self.qemu = executable(folder, "qemu-system-x86_64")
        settings.set_setting("qemu_path", folder)
        os.environ["PATH"] = ""
        self.run = FakeRun()
        self.patch(facts, "programs", Programs(self.run))
        self.logger = FakeLogger()
        self.patch(facts, "logger", self.logger)
        self.found = [UsbDevice("1d6b:0002", "Linux Foundation 2.0 root hub")]
        self.patch(facts, "get_usb_devices", lambda: defer.succeed(self.found))
        self.done(self.start())

    def read_there(self):
        """What the program says of itself, read there."""

        return self.successResultOf(Programs(FakeRun()).qemu(self.qemu))

    def test_qemu(self):
        info = self.done(self.engine.qemu("qemu-system-x86_64"))
        self.assertEqual(info, self.read_there())
        self.assertEqual(info.path, self.qemu)
        self.assertEqual(
            sorted(args for _, args in self.run.calls),
            sorted(QEMU_QUESTIONS.values()),
        )

    def test_no_such_program(self):
        failure = self.refused(
            self.engine.qemu("qemu-system-riscv64"), FileNotFoundError
        )
        self.assertEqual(failure.value.args, ("qemu-system-riscv64",))

    def test_a_program_that_fails(self):
        self.run.fail = ProgramError("qemu-system-x86_64: killed by signal 9")
        failure = self.refused(
            self.engine.qemu("qemu-system-x86_64"), ampwire.CommandFailed
        )
        self.assertEqual(
            failure.getErrorMessage(), "qemu-system-x86_64: killed by signal 9"
        )
        self.assertEqual(self.logger.events, [])

    def test_an_answer_too_long(self):
        self.run.answers[QEMU_QUESTIONS["devices"]] = Answer("é" * 40000)
        failure = self.refused(
            self.engine.qemu("qemu-system-x86_64"), ampwire.AnswerTooLong
        )
        # ["é…", "", 0], in UTF-8
        self.assertIn("80011 bytes", failure.getErrorMessage())

    def test_machine_properties(self):
        info = self.done(self.engine.qemu("qemu-system-x86_64"))
        there = Programs(FakeRun())
        self.assertEqual(
            self.done(self.engine.machine_properties(info, "q35")),
            self.successResultOf(there.machine_properties(info, "q35")),
        )
        # the default machine type, as the Virtualbricks there has it
        self.done(self.engine.machine_properties(info, ""))
        self.assertEqual(
            self.run.calls[-1],
            (self.qemu, machine_question(info.default_machine)),
        )

    def test_the_default_machine_there(self):
        answer = self.done(
            self.windows.callRemote(
                commands.MachineProperties,
                program="qemu-system-x86_64",
                machine="",
            )
        )
        default = machine_question(self.read_there().default_machine)
        self.assertEqual(self.run.calls[-1], (self.qemu, default))
        self.assertEqual(answer["text"], self.run.answers[default].out)

    def test_usb(self):
        self.assertEqual(self.done(self.engine.usb()), self.found)

    def test_a_failure_on_the_way(self):
        def broken():
            raise RuntimeError("lsusb crashed")

        self.patch(facts, "get_usb_devices", broken)
        failure = self.refused(self.engine.usb(), ampwire.CommandFailed)
        self.assertEqual(failure.getErrorMessage(), "lsusb crashed")
        self.assertEqual(
            self.logger.formatted(),
            ["UsbDevices for the windows of another machine failed"],
        )

    def test_the_pushes_first(self):
        self.factory.new_brick("switch", "sw2")
        asking = self.engine.usb()
        asking.addCallback(lambda _: self.copy.get_brick("sw2"))
        self.assertIsNotNone(self.done(asking))

    def test_beside_the_queue(self):
        # a command there that takes long: the facts don't wait for it
        held = defer.Deferred()
        self.connection.requests.add(lambda: held)
        self.assertEqual(self.done(self.engine.usb()), self.found)
        held.callback(None)

    def test_before_the_agreement(self):
        # Hello again, without protocol 2
        self.done(self.windows.callRemote(ampwire.Hello))
        self.refused(self.engine.usb(), ampcommands.ProtocolNeeded)

    def test_what_the_windows_read(self):
        machine = self.engine.machine
        self.assertEqual(machine.qemu_programs(), ["qemu-system-x86_64"])
        settings.set_setting("audio_driver", "pa")
        self.pump.flush()
        self.clock().advance(0)
        self.pump.flush()
        self.assertEqual(machine.setting("audio_driver"), "pa")


class TestFileFacts(ClientTestCase):
    """The files of the machine there: those of the project, then others."""

    def setUp(self):
        super().setUp()
        folder = self.workspace.current.path
        self.path = os.path.join(folder, "frr.qcow2")
        with open(self.path, "wb") as fp:
            fp.write(b"x" * 5000)
        self.qemu_img = FakeQemuImg()
        self.qemu_img.infos[self.path] = INFO
        self.patch(run, "qemu_img", self.qemu_img)
        # another project of the workspace there has the file
        self.patch(
            facts, "projects", FakeWorkspace("lab1", lab2=[("deb", self.path)])
        )
        self.logger = FakeLogger()
        self.patch(facts, "logger", self.logger)
        self.image = self.factory.new_image("frr", self.path)
        self.vm = self.factory.new_brick("qemu", "vm1")
        self.vm.update_config({"hda_image": "frr", "hda_private": True})
        self.cow = self.vm.disk("hda").get_cow_path()
        with open(self.cow, "wb") as fp:
            fp.write(b"x" * 100)
        self.done(self.start())
        self.machine = self.engine.machine

    def test_the_files_of_the_project(self):
        machine = self.machine
        stat = os.stat(self.path)
        self.assertTrue(machine.exists(self.path))
        self.assertEqual(machine.taken(self.path), stat.st_blocks * 512)
        self.assertEqual(machine.changed(self.path), stat.st_mtime_ns / 1e9)
        # the private copy of the machine there, where it is there
        copy = self.copy.get_brick("vm1").disk("hda").get_cow_path()
        self.assertEqual(copy, self.cow)
        self.assertEqual(
            machine.taken(copy), os.stat(self.cow).st_blocks * 512
        )
        self.assertFalse(machine.exists("/nowhere/frr.qcow2"))
        # what the Virtualbricks there said, not what this machine has
        os.remove(self.path)
        self.assertTrue(machine.exists(self.path))

    def test_what_a_file_is(self):
        info = self.done(self.engine.image_info(self.path))
        self.assertEqual(info, images.parse_info(INFO))
        self.assertEqual(
            self.qemu_img.calls, [["info", "--output=json", "-U", self.path]]
        )
        self.assertEqual(
            self.machine.other_projects(self.path), [("lab2", "deb")]
        )

    def test_another_file(self):
        other = os.path.join(self.workspace.current.path, "debian.qcow2")
        with open(other, "wb") as fp:
            fp.write(b"x" * 10)
        self.qemu_img.infos[other] = INFO
        self.assertFalse(self.machine.exists(other))
        self.done(self.engine.image_info(other))
        self.assertTrue(self.machine.exists(other))
        self.assertEqual(
            self.machine.taken(other), os.stat(other).st_blocks * 512
        )

    def test_no_such_file(self):
        failure = self.refused(
            self.engine.image_info("/nowhere/frr.qcow2"), ampcommands.NotFound
        )
        self.assertEqual(
            failure.getErrorMessage(), "No file /nowhere/frr.qcow2"
        )
        self.assertEqual(self.qemu_img.calls, [])

    def test_a_file_qemu_img_cant_read(self):
        def qemu_img(args):
            return defer.fail(CommandError(1, "qemu-img: Could not open it"))

        self.patch(run, "qemu_img", qemu_img)
        failure = self.refused(
            self.engine.image_info(self.path), ampwire.CommandFailed
        )
        self.assertEqual(
            failure.getErrorMessage(), "qemu-img: Could not open it"
        )
        self.assertEqual(self.logger.events, [])

    def test_no_qemu_img(self):
        def qemu_img(args):
            return defer.fail(FileNotFoundError("qemu-img"))

        self.patch(run, "qemu_img", qemu_img)
        failure = self.refused(
            self.engine.image_info(self.path), ampwire.CommandFailed
        )
        self.assertEqual(failure.getErrorMessage(), "No program qemu-img")

    def test_read_once_while_the_file_is_the_same(self):
        infos = self.machine.infos
        self.assertIsNone(infos.get(self.path))
        first = infos.read(self.path)
        second = infos.read(self.path)
        self.assertEqual(self.done(first), images.parse_info(INFO))
        self.assertEqual(self.done(second), images.parse_info(INFO))
        self.assertEqual(len(self.qemu_img.calls), 1)
        self.assertEqual(infos.get(self.path), images.parse_info(INFO))
        self.done(infos.read(self.path))
        self.assertEqual(len(self.qemu_img.calls), 1)
        # the machine ran, and wrote into the file
        with open(self.path, "ab") as fp:
            fp.write(b"y" * 5000)
        self.vm.changed.notify(self.vm)
        self.quiet(defer.succeed(None))
        self.assertIsNone(infos.get(self.path))
        self.done(infos.read(self.path))
        self.assertEqual(len(self.qemu_img.calls), 2)

    def test_a_read_that_fails(self):
        infos = self.machine.infos
        first = infos.read("/nowhere/frr.qcow2")
        second = infos.read("/nowhere/frr.qcow2")
        self.refused(first, ampcommands.NotFound)
        self.refused(second, ampcommands.NotFound)
        # asked again
        self.refused(infos.read("/nowhere/frr.qcow2"), ampcommands.NotFound)


class TakingTrash(FakeTrash):
    """A trash that takes the file away."""

    def trash(self, path):
        super().trash(path)
        os.remove(path)


class TestFileCommands(ClientTestCase):
    """The windows change the files there: new disks, copies, the trash."""

    def setUp(self):
        super().setUp()
        root = os.path.abspath(self.mktemp())
        self.workspace = use_workspace(self, root)
        self.workspace.current = Project(os.path.join(root, "lab1"))
        os.makedirs(self.workspace.current.path)
        self.trash = TakingTrash()
        self.workspace.trasher = self.trash
        self.qemu_img = FakeQemuImg()
        self.patch(answers.qemu_run, "qemu_img", self.qemu_img)
        self.logger = FakeLogger()
        self.patch(answers, "logger", self.logger)
        self.patch(control, "logger", self.control_log)
        self.frr = self.file(os.path.join(root, "vimages"), "frr.qcow2")
        self.qemu_img.infos[self.frr] = INFO
        self.image = self.factory.new_image("frr", self.frr)
        self.vm = self.factory.new_brick("qemu", "vm1")
        self.vm.update_config({"hda_image": "frr", "hda_private": True})
        self.cow = self.file(
            self.workspace.current.path,
            os.path.basename(self.vm.disk("hda").get_cow_path()),
        )
        self.done(self.start())

    @property
    def control_log(self):
        if not hasattr(self, "_control_log"):
            self._control_log = FakeLogger()
        return self._control_log

    def file(self, folder, name):
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, name)
        with open(path, "wb") as fp:
            fp.write(b"x" * 100)
        return path

    def test_the_trash_there(self):
        self.assertTrue(self.engine.machine.can_trash("/anything"))
        self.workspace.trasher = None
        self.workspace.opened.notify(self.workspace)
        self.quiet(defer.succeed(None))
        self.assertFalse(self.engine.machine.can_trash("/anything"))
        self.assertEqual(
            self.engine.machine.image_folder(),
            os.path.join(self.workspace.path, "vimages"),
        )

    def test_a_new_disk(self):
        path = os.path.join(self.workspace.path, "vimages", "pc.qcow2")
        self.done(self.engine.make_image(path, "qcow2", 1024))
        self.assertEqual(
            self.qemu_img.calls,
            [["create", "-q", "-f", "qcow2", path, "1024"]],
        )
        self.assertIn(
            f"make image {path}", " ".join(self.control_log.formatted())
        )

    def test_the_folder_of_the_images(self):
        # made when first needed
        folder = os.path.join(self.workspace.path, "vimages")
        os.remove(self.frr)
        os.rmdir(folder)
        path = os.path.join(folder, "pc.qcow2")
        self.done(self.engine.make_image(path, "raw", 1024))
        self.assertTrue(os.path.isdir(folder))

    def test_a_new_disk_refused(self):
        failure = self.refused(
            self.engine.make_image(self.frr, "qcow2", 1024),
            ampcommands.BadArgument,
        )
        self.assertEqual(
            failure.getErrorMessage(), f"{self.frr} is there already"
        )
        failure = self.refused(
            self.engine.make_image("/lab/pc.vdi", "vdi", 1024),
            ampcommands.BadArgument,
        )
        self.assertEqual(
            failure.getErrorMessage(), "The format is qcow2 or raw"
        )
        self.assertEqual(self.qemu_img.calls, [])

    def test_qemu_img_fails(self):
        def qemu_img(args):
            return defer.fail(CommandError(1, "qemu-img: No space left"))

        self.patch(answers.qemu_run, "qemu_img", qemu_img)
        path = os.path.join(self.workspace.path, "vimages", "pc.qcow2")
        failure = self.refused(
            self.engine.make_image(path, "qcow2", 1024), ampwire.CommandFailed
        )
        self.assertEqual(failure.getErrorMessage(), "qemu-img: No space left")
        # a refusal, not a bug
        self.assertEqual(self.logger.events, [])

    def test_a_bug_on_the_way(self):
        def qemu_img(args):
            return defer.fail(RuntimeError("broken"))

        self.patch(answers.qemu_run, "qemu_img", qemu_img)
        path = os.path.join(self.workspace.path, "vimages", "pc.qcow2")
        self.refused(
            self.engine.make_image(path, "qcow2", 1024), ampwire.CommandFailed
        )
        self.assertEqual(self.logger.formatted(), [f"make of {path} failed"])

    def test_start_over(self):
        copy = self.copy.get_brick("vm1")
        self.assertTrue(self.engine.machine.exists(self.cow))
        self.assertTrue(self.done(self.engine.start_over(copy, "hda")))
        self.assertEqual(self.trash.trashed, [self.cow])
        # the copy is gone there, and the windows know
        self.assertFalse(self.engine.machine.exists(self.cow))

    def test_start_over_without_a_trash(self):
        self.workspace.trasher = None
        copy = self.copy.get_brick("vm1")
        self.assertFalse(self.done(self.engine.start_over(copy, "hda")))
        self.assertFalse(os.path.exists(self.cow))

    def test_start_over_refused(self):
        copy = self.copy.get_brick("vm1")
        self.vm.__isrunning__ = lambda: True
        failure = self.refused(
            self.engine.start_over(copy, "hda"), ampcommands.BadArgument
        )
        self.assertIn("vm1", failure.getErrorMessage())
        self.vm.__isrunning__ = lambda: False
        self.refused(
            self.windows.callRemote(
                commands.StartOver, vm="vm1", device="hdz"
            ),
            ampcommands.BadArgument,
        )
        self.factory.new_brick("switch", "sw1")
        for name in ("vm9", "sw1"):
            self.refused(
                self.windows.callRemote(
                    commands.StartOver, vm=name, device="hda"
                ),
                ampcommands.NotFound,
            )
        self.workspace.current = None
        failure = self.refused(
            self.engine.start_over(copy, "hda"), ampcommands.BadArgument
        )
        self.assertEqual(failure.getErrorMessage(), "No project is open")
        self.assertEqual(self.trash.trashed, [])

    def test_trash_a_file(self):
        self.done(self.engine.image_info(self.frr))
        self.done(self.engine.remove(self.copy.get_image("frr")))
        self.assertTrue(self.done(self.engine.discard_file(self.frr)))
        self.assertEqual(self.trash.trashed, [self.frr])
        # what was asked of it is no more
        self.assertFalse(self.engine.machine.exists(self.frr))

    def test_no_trash_there(self):
        self.workspace.trasher = None
        self.factory.remove_image(self.image)
        self.assertFalse(self.done(self.engine.discard_file(self.frr)))
        self.assertFalse(os.path.exists(self.frr))

    def test_trash_refused(self):
        # an image has it
        failure = self.refused(
            self.engine.discard_file(self.frr), ampcommands.BadArgument
        )
        self.assertEqual(
            failure.getErrorMessage(), "The image frr has the file"
        )
        # outside the workspace
        outside = self.file(os.path.abspath(self.mktemp()), "debian.qcow2")
        failure = self.refused(
            self.engine.discard_file(outside), ampcommands.BadArgument
        )
        self.assertIn("isn't in the workspace", failure.getErrorMessage())
        # another project has it
        self.factory.remove_image(self.image)
        self.patch(
            answers,
            "projects",
            FakeWorkspace("lab1", ospf=[("debian", self.frr)]),
        )
        answers.projects.path = self.workspace.path
        answers.projects.trasher = self.trash
        failure = self.refused(
            self.engine.discard_file(self.frr), ampcommands.BadArgument
        )
        self.assertEqual(
            failure.getErrorMessage(), "The project ospf uses the file"
        )
        self.assertEqual(self.trash.trashed, [])
        self.assertTrue(os.path.exists(self.frr))

    def test_relink(self):
        path = self.file(
            os.path.join(self.workspace.path, "vimages"), "new.qcow2"
        )
        self.qemu_img.infos[path] = INFO
        self.done(self.engine.relink(self.copy.get_image("frr"), path))
        self.assertEqual(self.image.path, path)
        self.assertEqual(self.copy.get_image("frr").path, path)
        # the private copy follows
        self.assertEqual(
            self.qemu_img.rebases(),
            [["rebase", "-u", "-b", path, "-F", "qcow2", self.cow]],
        )

    def test_relink_refused(self):
        path = self.file(
            os.path.join(self.workspace.path, "vimages"), "new.qcow2"
        )
        self.qemu_img.infos[path] = INFO
        self.vm.__isrunning__ = lambda: True
        self.refused(
            self.engine.relink(self.copy.get_image("frr"), path),
            ampcommands.BadArgument,
        )
        self.refused(
            self.windows.callRemote(commands.Relink, name="deb", path=path),
            ampcommands.NotFound,
        )
        self.assertEqual(self.image.path, self.frr)


class TestEndpoints(ConsoleTestCase):

    def test_unix(self):
        endpoint = endpoint_of(TARGET, reactor)
        self.assertIsInstance(endpoint, endpoints.UNIXClientEndpoint)

    def test_tcp(self):
        target = wire.parse_socket("tcp:lab:8765", client=True)
        endpoint = endpoint_of(target, reactor)
        self.assertIsInstance(endpoint, endpoints.HostnameEndpoint)

    def test_ssl_with_a_folder_it_cant_read(self):
        target = wire.parse_socket(
            "ssl:lab:8765:caCertsDir=/nowhere", client=True
        )
        with self.assertRaises(Refused) as cm:
            endpoint_of(target, reactor)
        self.assertEqual(str(cm.exception), "/nowhere doesn't exist")


class TestConnect(ConsoleTestCase):
    """The windows reach a Virtualbricks that listens, for real."""

    def setUp(self):
        super().setUp()
        self.factory.runtime_dir = "/run/vb"
        self.patch(control, "logger", FakeLogger())
        use_workspace(self).current = Project("/lab")
        self.patch(follower, "keeper", LogKeeper())
        self.factory.new_brick("switch", "sw1")

    def listen(self, socket):
        found = control.listen(self.factory, socket, reactor)
        self.addCleanup(found.close)
        return found

    def folder(self, name):
        """A folder with the certificate of name, as caCertsDir."""

        folder = os.path.abspath(self.mktemp())
        os.makedirs(folder)
        with open(tls_file(f"{name}.pem"), "rb") as source:
            with open(os.path.join(folder, f"{name}.pem"), "wb") as copy:
                copy.write(source.read())
        return folder

    @defer.inlineCallbacks
    def test_a_certificate_of_the_windows(self):
        # the Virtualbricks there asks for alice's, and no token
        found = self.listen(
            wire.Socket(
                None,
                wire.AMP,
                "ssl",
                "127.0.0.1",
                0,
                private_key=tls_file("server.key"),
                cert=tls_file("server.pem"),
                ca_dir=self.folder("alice"),
            )
        )
        target = wire.parse_socket(
            f"ssl:127.0.0.1:{found.socket.port}"
            f":caCertsDir={self.folder('server')}"
            f":privateKey={tls_file('alice.key')}"
            f":certKey={tls_file('alice.pem')}:protocol=amp",
            client=True,
        )
        copy = MirrorFactory()
        windows = yield defer.ensureDeferred(
            client.connect(target, copy, reactor)
        )
        self.addCleanup(windows.transport.loseConnection)
        self.assertIsNotNone(copy.get_brick("sw1"))

    @defer.inlineCallbacks
    def test_ssl(self):
        folder = self.folder("server")
        token_file = locations.token_file()
        os.makedirs(os.path.dirname(token_file), exist_ok=True)
        with open(token_file, "w") as file:
            file.write(TOKEN + "\n")
        os.chmod(token_file, 0o600)
        found = self.listen(
            wire.Socket(
                None,
                wire.AMP,
                "ssl",
                "127.0.0.1",
                0,
                private_key=tls_file("server.key"),
                cert=tls_file("server.pem"),
            )
        )
        target = wire.parse_socket(
            f"ssl:127.0.0.1:{found.socket.port}:caCertsDir={folder}"
            ":protocol=amp",
            client=True,
        )
        copy = MirrorFactory()
        windows = yield defer.ensureDeferred(
            client.connect(target, copy, reactor)
        )
        self.addCleanup(windows.transport.loseConnection)
        self.assertIsNotNone(copy.get_brick("sw1"))

    @defer.inlineCallbacks
    def test_nothing_there(self):
        target = wire.parse_socket("tcp:127.0.0.1:1:protocol=amp", client=True)
        with self.assertRaises(Refused) as cm:
            yield defer.ensureDeferred(
                client.connect(target, MirrorFactory(), reactor)
            )
        self.assertIn("Can't reach 127.0.0.1 port 1", str(cm.exception))
