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
The copy of the project of another Virtualbricks, kept equal to its factory
by the pushes of Follow.
"""

import os

from twisted.internet import defer
from twisted.protocols import amp
from twisted.test import iosim

from virtualbricks.bricks import FakeProcess, brickinfo, eventinfo
from virtualbricks.bricks.eventaction import ShellAction, StartAction
from virtualbricks.config import settings
from virtualbricks.config.projectfile import project_document
from virtualbricks.config.workspace import OpenProject
from virtualbricks.console import ampwire, control
from virtualbricks.remote import commands, follower, mirror
from virtualbricks.remote.commands import BRICK, IMAGE
from virtualbricks.remote.follower import LogKeeper, state_of
from virtualbricks.remote.mirror import (
    MirrorFactory,
    Mirroring,
    NotOnTheCopy,
    StandIn,
)
from virtualbricks.tests import FakeLogger, use_workspace
from virtualbricks.tests.console import ConsoleTestCase


class Project:
    name = "lab1"

    def __init__(self, path):
        # where the lab renames the private disks of a machine
        self.path = path


class Program(Mirroring, amp.AMP):
    """The windows: the copy, and the messages of the log."""

    def __init__(self, copy):
        super().__init__()
        self.mirror = copy
        self.logged = []

    @commands.Logged.responder
    def logged_message(self, message):
        self.logged.append(message)
        return {}


class MirrorTestCase(ConsoleTestCase):
    """A factory there, its copy here, and the connection between them."""

    def setUp(self):
        super().setUp()
        self.factory.runtime_dir = "/run/vb"
        self.patch(control, "logger", FakeLogger())
        self.patch(follower, "logger", FakeLogger())
        self.logger = FakeLogger()
        self.patch(mirror, "logger", self.logger)
        self.patch(amp, "_log", FakeLogger())
        self.workspace = use_workspace(self)
        self.workspace.current = Project(os.path.abspath(self.mktemp()))
        os.makedirs(self.workspace.current.path)
        self.patch(follower, "keeper", LogKeeper())
        self.server = control.ControlFactory(
            self.factory, self.clock(), control.AMPControl
        )
        self.copy = MirrorFactory(self.clock())
        self.told = []
        for name in ("synced", "settings_changed", "ended"):
            getattr(self.copy, name).connect(
                lambda factory, name=name: self.told.append(name)
            )
        self.program, self.connection, self.pump = (
            iosim.connectedServerAndClient(
                lambda: self.server.buildProtocol(None),
                lambda: Program(self.copy),
            )
        )
        # the copy took every push, unless a test says otherwise
        self.quiet = True
        self.addCleanup(self.took_all)

    def took_all(self):
        if self.quiet:
            self.assertEqual(self.logger.formatted(), [])

    def call(self, command, **arguments):
        answer = defer.Deferred()
        self.program.callRemote(command, **arguments).chainDeferred(answer)
        self.pump.flush()
        return self.successResultOf(answer)

    def follow(self):
        self.assertEqual(
            self.call(ampwire.Hello, protocols=[2])["protocol"], 2
        )
        return self.call(commands.Follow)

    def turn(self):
        self.clock().advance(0)
        self.pump.flush()

    def assertSame(self):
        """The copy writes the project as the factory there does."""

        project = settings.ProjectSettings()
        self.assertEqual(
            project_document(self.copy, project),
            project_document(self.factory, project),
        )
        for brick in self.factory.bricks:
            self.assertEqual(
                state_of(self.copy.get_brick(brick.name)), state_of(brick)
            )
        for event in self.factory.events:
            copy = self.copy.get_event(event.name)
            self.assertEqual(
                copy.scheduled is None, event.scheduled is None, event.name
            )

    def lab(self):
        """A lab of each kind of object, and of the links between them."""

        factory = self.factory
        self.image = factory.new_image("frr", "/lab/frr.qcow2", "Debian")
        self.sw1 = factory.new_brick("switch", "sw1")
        self.sw2 = factory.new_brick("switch", "sw2")
        tap = factory.new_brick("tap", "tap1")
        tap.connect(self.sw1.socks[0])
        wire = factory.new_brick("wire", "w1")
        wire.connect(self.sw1.socks[0])
        wire.connect(self.sw2.socks[0])
        self.vm1 = factory.new_brick("qemu", "vm1")
        self.vm1.update_config({"hda_image": "frr", "hda_private": True})
        self.vm1.add_sock(name="sock_eth1")
        self.vm1.add_plug(self.sw1.socks[0])
        self.vm1.add_plug(factory.get_sock("_hostonly"))
        self.vm2 = factory.new_brick("qemu", "vm2")
        self.vm2.add_plug(self.vm1.socks[0])
        self.boot = factory.new_event("boot")
        self.boot.update_config(
            {"delay": 5, "actions": [StartAction("vm1"), ShellAction("true")]}
        )
        self.sw1.update_config({"on_start": "boot"})


class TestTheProject(MirrorTestCase):

    def test_the_project(self):
        self.lab()
        self.follow()
        self.assertSame()
        self.assertEqual(self.told, ["synced"])
        self.assertEqual(self.copy.project, "lab1")
        self.assertEqual(self.copy.runtime_dir, "/run/vb")
        self.assertEqual(self.copy.machine["runtime_dir"], "/run/vb")
        self.assertEqual(
            self.copy.settings["qemu_path"],
            settings.get_setting("qemu_path"),
        )
        # the real classes, and the images the disks name
        vm1 = self.copy.get_brick("vm1")
        self.assertIsInstance(vm1, type(self.vm1))
        self.assertIs(vm1.disk("hda").image, self.copy.get_image("frr"))
        self.assertEqual(self.copy.get_image("frr").description, "Debian")
        self.assertEqual(
            self.copy.get_brick("vm2").plugs[0].sock.nickname,
            "vm1_sock_eth1",
        )

    def test_machines_plugged_into_each_other(self):
        # a loop: one of them comes before the socket it plugs into
        vm1 = self.factory.new_brick("qemu", "vm1")
        vm2 = self.factory.new_brick("qemu", "vm2")
        sock1 = vm1.add_sock()
        sock2 = vm2.add_sock()
        vm1.add_plug(sock2)
        vm2.add_plug(sock1)
        told = []
        self.copy.brick_changed.connect(
            lambda brick: told.append((brick.name, brick.plugs[0].sock))
        )
        self.follow()
        self.assertSame()
        # the one that came first is told when its socket comes
        self.assertEqual(told[0][0], "vm1")
        self.assertIsNone(told[0][1])
        self.assertIsNotNone(
            [sock for name, sock in told if name == "vm1"][-1]
        )

    def test_a_brick_gone_waits_for_nothing(self):
        # tables of what matters here only: the log says what they lack
        self.quiet = False
        self.follow()
        nic = {"kind": "plug", "model": "e1000", "mac": "52:54:00:12:34:56"}
        self.copy.take_changed(
            "brick",
            "vm1",
            {"type": "qemu", "nics": [dict(nic, connect="vm2:sock_eth0")]},
            {},
        )
        waiting = self.copy.get_brick("vm1").plugs[0]
        self.copy.take_removed("brick", "vm1")
        self.copy.take_changed(
            "brick",
            "vm2",
            {
                "type": "qemu",
                "nics": [dict(nic, kind="socket", name="sock_eth0")],
            },
            {},
        )
        self.assertIsNone(waiting.sock)
        self.assertEqual(self.copy.get_sock("vm2_sock_eth0").plugs, [])

    def test_a_project_opened_there(self):
        self.lab()
        self.follow()
        self.copy.get_brick("sw1").proc = StandIn(self.sw1, 7)
        self.told = []
        self.factory.reset()
        self.factory.new_brick("switch", "other")
        self.workspace.opened.notify(self.workspace)
        self.turn()
        self.assertSame()
        self.assertEqual(self.told, ["synced"])

    def test_the_settings(self):
        self.follow()
        self.told = []
        settings.set_setting("audio_driver", "pa")
        self.turn()
        self.assertEqual(self.copy.settings["audio_driver"], "pa")
        self.assertEqual(self.told, ["settings_changed"])

    def test_it_quits(self):
        self.follow()
        self.told = []
        self.factory.quit()
        self.pump.flush()
        self.assertEqual(self.told, ["ended"])


class TestTheStates(MirrorTestCase):
    """What the copy keeps of the states there: files, processes."""

    def setUp(self):
        super().setUp()
        self.lab()
        self.follow()

    def test_what_came(self):
        copy = self.copy
        self.assertEqual(copy.state(IMAGE, "frr"), state_of(self.image))
        self.assertEqual(copy.state(BRICK, "vm1"), state_of(self.vm1))
        self.assertIn("copies", copy.state(BRICK, "vm1"))
        self.assertEqual(copy.state(BRICK, "vm9"), {})

    def test_renamed_then_removed(self):
        state = self.copy.state(IMAGE, "frr")
        self.factory.rename_item(self.image, "debian")
        self.turn()
        self.assertEqual(self.copy.state(IMAGE, "debian"), state)
        self.assertEqual(self.copy.state(IMAGE, "frr"), {})
        self.factory.remove_image(self.image)
        self.turn()
        self.assertEqual(self.copy.state(IMAGE, "debian"), {})

    def test_a_project_opened(self):
        self.factory.reset()
        self.workspace.opened.notify(self.workspace)
        self.turn()
        self.assertEqual(self.copy.state(IMAGE, "frr"), {})
        self.assertEqual(self.copy.state(BRICK, "vm1"), {})

    def test_a_file_that_changed_there(self):
        path = os.path.join(self.workspace.current.path, "pc.qcow2")
        with open(path, "wb") as fp:
            fp.write(b"x" * 10)
        self.factory.new_image("pc", path)
        self.vm1.update_config({"hdb_image": "pc"})
        self.turn()
        changed = []
        self.copy.image_changed.connect(changed.append)
        # the same state again: nothing to show
        self.vm1.changed.notify(self.vm1)
        self.turn()
        self.assertEqual(changed, [])
        # vm1 wrote into it
        with open(path, "ab") as fp:
            fp.write(b"y" * 10)
        self.vm1.changed.notify(self.vm1)
        self.turn()
        pc = self.copy.get_image("pc")
        self.assertEqual(changed, [pc])
        self.assertEqual(self.copy.state(IMAGE, "pc")["file"]["size"], 20)

    def test_the_private_copies_there(self):
        vm1 = self.copy.get_brick("vm1")
        self.assertEqual(vm1.project_folder(), self.workspace.current.path)
        self.assertEqual(
            vm1.disk("hda").get_cow_path(),
            self.vm1.disk("hda").get_cow_path(),
        )
        # the folder there, whatever this process has open
        self.copy.machine["project_folder"] = "/srv/labs/ospf"
        self.assertEqual(
            vm1.disk("hda").get_cow_path(), "/srv/labs/ospf/vm1_hda.cow"
        )


class TestChanges(MirrorTestCase):

    def setUp(self):
        super().setUp()
        self.lab()
        self.follow()

    def test_settings(self):
        self.sw1.update_config({"ports": 8, "hub_mode": True})
        self.boot.update_config({"delay": 9})
        self.image.set_description("Bookworm")
        self.image.set_path("/lab/bookworm.qcow2")
        self.turn()
        self.assertSame()
        self.assertEqual(self.copy.get_brick("sw1").config.ports, 8)

    def test_in_place(self):
        copy = self.copy.get_brick("sw1")
        self.sw1.update_config({"ports": 8})
        self.turn()
        self.assertIs(self.copy.get_brick("sw1"), copy)

    def test_new_ones(self):
        self.factory.new_brick("switch", "sw3")
        tap = self.factory.new_brick("tap", "tap3")
        tap.connect(self.sw2.socks[0])
        self.factory.new_event("down")
        self.factory.new_image("pc", "/lab/pc.qcow2")
        self.turn()
        self.assertSame()

    def test_links(self):
        wire = self.factory.get_brick("w1")
        wire.plugs[1].disconnect()
        wire.plugs[1].connect(self.sw1.socks[0])
        wire.changed.notify(wire)
        tap = self.factory.get_brick("tap1")
        tap.plugs[0].disconnect()
        tap.changed.notify(tap)
        self.turn()
        self.assertSame()

    def test_the_cards_of_a_machine(self):
        vm1 = self.copy.get_brick("vm1")
        sock = vm1.socks[0]
        self.vm1.add_sock(name="sock_eth3")
        self.vm1.remove_plug(self.vm1.plugs[1])
        self.vm1.plugs[0].disconnect()
        self.vm1.plugs[0].connect(self.sw2.socks[0])
        self.vm1.socks[0].mac = "52:54:00:aa:bb:cc"
        self.vm1.changed.notify(self.vm1)
        self.turn()
        self.assertSame()
        # the same socket card, which vm2 plugs into still
        self.assertIs(vm1.socks[0], sock)
        self.assertIs(
            self.copy.get_brick("vm2").plugs[0].sock,
            self.copy.get_sock("vm1_sock_eth1"),
        )
        # a socket card removed
        self.vm1.remove_plug(self.vm1.socks[1])
        self.vm1.changed.notify(self.vm1)
        self.turn()
        self.assertSame()
        self.assertEqual(len(vm1.socks), 1)

    def test_renames(self):
        self.factory.rename_item(self.image, "debian")
        self.factory.rename_item(self.boot, "up")
        self.factory.rename_item(self.vm1, "r1")
        self.factory.rename_item(self.sw1, "core")
        self.turn()
        self.assertSame()
        self.assertEqual(
            self.copy.get_brick("vm2").plugs[0].sock.nickname, "r1_sock_eth1"
        )

    def test_deletes(self):
        self.factory.remove_brick(self.sw2)
        self.factory.remove_brick(self.vm2)
        self.factory.remove_event(self.boot)
        self.factory.remove_image(self.image)
        self.turn()
        self.assertSame()

    def test_what_named_a_deleted_one_follows(self):
        # as changes, after the delete there, as after a rename
        self.copy.take_removed("event", "boot")
        self.assertEqual(self.copy.get_brick("sw1").config.on_start, "boot")
        self.factory.remove_event(self.boot)
        self.turn()
        self.assertSame()
        self.assertEqual(self.copy.get_brick("sw1").config.on_start, "")

    def test_a_brick_that_runs(self):
        self.sw1.proc = FakeProcess(self.sw1)
        self.sw1.changed.notify(self.sw1)
        self.turn()
        self.assertSame()
        copy = self.copy.get_brick("sw1")
        self.assertEqual(brickinfo.state(copy), brickinfo.State.RUNNING)
        self.assertEqual(brickinfo.process(copy), -1)
        self.sw1.proc = None
        self.sw1.changed.notify(self.sw1)
        self.turn()
        self.assertEqual(brickinfo.state(copy), brickinfo.state(self.sw1))
        self.assertIsNone(brickinfo.process(copy))

    def test_an_event_that_waits(self):
        self.boot.start()
        self.addCleanup(self.boot.stop)
        self.turn()
        self.assertSame()
        copy = self.copy.get_event("boot")
        self.assertEqual(eventinfo.state(copy), eventinfo.State.WAITING)
        self.assertEqual(eventinfo.seconds_left(copy, self.clock()), 5)
        # the clock of the copy counts down
        self.clock().advance(3)
        self.assertEqual(eventinfo.seconds_left(copy, self.clock()), 2)
        # stopped there before its time: the timer of the copy goes
        self.boot.stop()
        self.turn()
        self.assertIsNone(copy.scheduled)
        self.assertEqual(self.clock().getDelayedCalls(), [])
        # its time come here first: the copy waits no more
        self.boot.start()
        self.turn()
        self.clock().advance(5)
        self.assertIsNone(copy.scheduled)

    def test_the_log(self):
        from twisted.logger import LogLevel

        follower.keeper(
            {"log_format": "hello", "log_level": LogLevel.info, "log_time": 1}
        )
        self.turn()
        self.assertEqual(len(self.program.logged), 1)


class TestTheCopy(MirrorTestCase):
    """What the copy refuses, and what it doesn't touch."""

    def setUp(self):
        super().setUp()
        self.lab()
        self.follow()

    def test_it_starts_nothing(self):
        vm1 = self.copy.get_brick("vm1")
        for call in ("start", "stop", "send", "send_signal"):
            self.assertRaises(NotOnTheCopy, getattr(vm1, call))
        with self.assertRaises(NotOnTheCopy) as cm:
            vm1.open_console()
        self.assertEqual(
            str(cm.exception),
            "open_console of vm1 is for the Virtualbricks of the bricks:"
            " here is its copy",
        )
        boot = self.copy.get_event("boot")
        for call in ("start", "stop", "run_actions"):
            self.assertRaises(NotOnTheCopy, getattr(boot, call))
        stand_in = StandIn(vm1, 42)
        self.assertRaises(NotOnTheCopy, stand_in.signal_process, 15)
        self.assertRaises(NotOnTheCopy, stand_in.write, b"quit\n")

    def test_the_refusal_names_the_brick_now(self):
        self.factory.rename_item(self.sw1, "core")
        self.turn()
        with self.assertRaises(NotOnTheCopy) as cm:
            self.copy.get_brick("core").start()
        self.assertIn("start of core", str(cm.exception))

    def test_a_machine_renamed_here_renames_no_file(self):
        folder = os.path.abspath(self.mktemp())
        os.makedirs(folder)
        disk = os.path.join(folder, "vm1_hda.cow")
        with open(disk, "w"):
            pass
        self.workspace.current = OpenProject(folder, None)
        self.copy.take_renamed("brick", "vm1", "r1")
        self.assertTrue(os.path.exists(disk))
        self.assertEqual(self.copy.get_brick("r1").name, "r1")

    def test_what_it_cant_take(self):
        # a push the copy can't take goes to the log; the next ones come
        self.quiet = False
        answer = self.program.take_changed(
            kind="brick", name="x1", table='{"type": "spaceship"}', state="{}"
        )
        self.assertEqual(answer, {})
        self.assertEqual(
            self.logger.formatted(), ["The copy didn't take Changed of x1"]
        )
        self.assertEqual(self.logger.levels(), ["failure"])
        self.sw1.update_config({"ports": 8})
        self.turn()
        self.assertSame()

    def test_references_follow_a_rename(self):
        # at once, before the changes that follow it there
        self.copy.take_renamed("image", "frr", "debian")
        self.copy.take_renamed("event", "boot", "up")
        self.assertEqual(self.copy.get_brick("vm1").config.hda_image, "debian")
        self.assertEqual(self.copy.get_brick("sw1").config.on_start, "up")
        self.assertIs(self.copy.get_event("up").name, "up")

    def test_names_it_doesnt_know(self):
        self.copy.take_renamed("brick", "nowhere", "somewhere")
        self.copy.take_removed("event", "nowhere")
        self.assertSame()
