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

"""The commands of the bricks."""

import os
import signal

from twisted.internet import defer, error

from virtualbricks import errors
from virtualbricks.bricks.eventaction import ConsoleAction, StartAction
from virtualbricks.bricks.virtualmachine import hostonly_sock
from virtualbricks.config import settings
from virtualbricks.console import bricks as console_bricks
from virtualbricks.console.dispatch import run
from virtualbricks.tests import FakeLogger
from virtualbricks.tests.console import ConsoleTestCase


class FakeProcess:
    def __init__(self, pid):
        self.pid = pid
        self.written = []

    def write(self, data):
        self.written.append(data)


class BricksTestCase(ConsoleTestCase):

    def setUp(self):
        super().setUp()
        # short, so that a name has room in the paths of the sockets
        self.factory.runtime_dir = "/run/vb"
        self.logger = FakeLogger()
        self.patch(console_bricks, "logger", self.logger)
        self.done = []
        self.pids = iter(range(41822, 41900))

    def brick(self, kind, name):
        return self.factory.new_brick(kind, name)

    def running(self, brick):
        brick.proc = FakeProcess(next(self.pids))
        return brick

    def startable(self, brick, result=None):
        """start() starts brick at once, or fails with result."""

        def start(resume=""):
            self.done.append(("on", brick.name))
            if result is not None:
                return defer.fail(result)
            if brick.proc is None:
                self.running(brick)
            return defer.succeed(brick)

        brick.start = start
        return brick

    def stoppable(self, brick):
        def stop(kill=False):
            self.done.append(("off", brick.name, kill))
            brick.proc = None
            return defer.succeed((brick, 0))

        brick.stop = stop
        return brick


class TestKinds(BricksTestCase):

    def test_types(self):
        lines = self.run_line("brick types")
        self.assertEqual(
            lines[0].split(), ["KIND", "NAME", "WHAT", "IT", "IS"]
        )
        words = [line.split()[0] for line in lines[1:]]
        self.assertEqual(
            words,
            [
                "vm",
                "switch",
                "switchwrapper",
                "router",
                "wire",
                "netemu",
                "tunnelserver",
                "tunnelclient",
                "tap",
                "capture",
            ],
        )

    def test_what_this_computer_lacks(self):
        # the VDE programs are in a folder that has none, and not in PATH
        settings.use_project(settings.ProjectSettings(vde_path=self.mktemp()))
        self.patch(os, "environ", dict(os.environ, PATH=""))
        lines = self.run_line("brick types")
        switch = next(line for line in lines if line.startswith("switch "))
        self.assertIn("vde_switch isn't installed", switch)


class TestNew(BricksTestCase):

    def test_named_after_the_kind(self):
        self.assertEqual(self.run_line("brick new switch"), ["sw1"])
        self.assertEqual(self.run_line("brick new switch"), ["sw2"])
        # the type of the project file is a kind too
        self.assertEqual(self.run_line("brick new qemu"), ["vm1"])
        self.assertEqual(
            [(b.name, b.get_type()) for b in self.factory.bricks],
            [("sw1", "Switch"), ("sw2", "Switch"), ("vm1", "Qemu")],
        )

    def test_a_name(self):
        self.assertEqual(self.run_line("brick new vm router"), ["router"])
        self.assertEqual(
            self.run_line("brick new switch 'core switch'"), ["core_switch"]
        )
        self.assertEqual(
            self.fails("brick new tap router"),
            "router is the name of a brick",
        )
        self.assertEqual(
            self.fails("brick new tap tap_of_the_lab_1"),
            "The interface of this computer takes a tap's name: at most 15"
            " characters, and this one has 16",
        )
        self.assertEqual(
            self.fails("brick new nope"),
            "No kind nope: brick types lists them",
        )


class TestListAndShow(BricksTestCase):

    def test_nothing(self):
        self.assertEqual(self.run_line("brick list"), ["No bricks"])

    def test_list(self):
        # a switch needs a folder for its sockets
        self.factory.runtime_dir = os.path.abspath(self.mktemp())
        os.makedirs(self.factory.runtime_dir)
        self.brick("switch", "sw1")
        self.running(self.brick("tap", "tap1"))
        self.assertEqual(
            self.run_line("brick list"),
            [
                "NAME  KIND    STATE    SUMMARY",
                "sw1   Switch  Stopped  32 ports",
                "tap1  Tap     Running  no address",
            ],
        )

    def test_show(self):
        sw1 = self.brick("switch", "sw1")
        vm = self.running(self.brick("qemu", "vm1"))
        vm.add_plug(sw1.socks[0], "52:54:00:00:00:01", "e1000")
        vm.update_config({"use_vnc": True, "headless": True})
        lines = self.run_line("brick show vm1")
        self.assertEqual(
            lines[:2],
            [
                "vm1  Virtual machine  Running  process 41822",
                "eth0: plugged into sw1, e1000, 52:54:00:00:00:01",
            ],
        )
        for line in (
            "headless = true",
            "use_vnc = true  # not used: headless is true",
            "memory = 64",
        ):
            self.assertIn(line, lines)

    def test_links_of_a_wire(self):
        self.brick("switch", "sw1")
        self.brick("wire", "w1")
        self.run_line("brick connect w1 sw1")
        self.assertEqual(
            self.run_line("brick show w1")[1:3],
            ["left: sw1", "right: nothing"],
        )


class TestKeys(BricksTestCase):

    def test_of_a_kind(self):
        self.assertEqual(
            self.run_line("brick keys switch")[3:],
            [
                "ports               Number of ports (1-128; default 32)",
                "hub_mode            Send every packet to every port, as a"
                " hub (default false)",
                "fast_spanning_tree  Run the fast spanning tree protocol"
                " (default false)",
            ],
        )

    def test_of_a_brick_and_one_key(self):
        self.brick("qemu", "router")
        self.assertEqual(
            self.run_line("brick keys router memory"),
            ["memory: Memory in MiB (1-99999; default 64)"],
        )
        self.assertEqual(
            self.fails("brick keys vm nope"),
            "No key nope: brick keys lists them",
        )


class TestSet(BricksTestCase):

    def test_set(self):
        vm = self.brick("qemu", "vm1")
        self.assertEqual(
            self.run_line(
                'brick set vm1 memory=512 kernel_command_line="console=ttyS0'
                ' root=/dev/vda"'
            ),
            [],
        )
        self.assertEqual(vm.config.memory, 512)
        self.assertEqual(
            vm.config.kernel_command_line, "console=ttyS0 root=/dev/vda"
        )

    def test_all_or_none(self):
        vm = self.brick("qemu", "vm1")
        self.assertEqual(
            self.fails("brick set vm1 cpus=2 memory=99999999"),
            "vm1 memory: 99999999 is outside 1–99999",
        )
        self.assertEqual(
            self.fails("brick set vm1 cpus=2 nope=1"),
            "vm1 has no key nope: brick keys vm1 lists them",
        )
        self.assertEqual(
            self.fails("brick set vm1 memory=abc"),
            "vm1 memory: 'abc' is not an integer",
        )
        self.assertEqual(vm.config.cpus, 1)

    def test_a_running_brick(self):
        sw = self.running(self.brick("switch", "sw1"))
        vm = self.running(self.brick("qemu", "vm1"))
        # a switch takes its ports at once
        self.assertEqual(self.run_line("brick set sw1 ports=4"), [])
        self.assertEqual(sw.config.ports, 4)
        self.assertEqual(
            self.run_line("brick set vm1 memory=512 cpus=2"),
            ["vm1 is running: memory, cpus count from its next start"],
        )
        self.assertEqual(vm.config.memory, 512)

    def test_unset(self):
        vm = self.brick("qemu", "vm1")
        vm.update_config({"memory": 512, "cpus": 4})
        self.assertEqual(self.run_line("brick unset vm1 memory cpus"), [])
        self.assertEqual((vm.config.memory, vm.config.cpus), (64, 1))
        self.assertEqual(
            self.fails("brick unset vm1 nope"),
            "vm1 has no key nope: brick keys vm1 lists them",
        )


class TestStartAndStop(BricksTestCase):

    def test_start(self):
        sw = self.startable(self.brick("switch", "sw1"))
        vm = self.startable(self.brick("qemu", "vm1"))
        self.running(self.startable(self.brick("tap", "tap1")))

        def start(resume=""):
            # the switch first, as a brick starts what it plugs into
            sw.start()
            self.running(vm)
            return defer.succeed(vm)

        vm.start = start
        self.assertEqual(
            self.run_line("brick start vm1 tap1"),
            [
                "tap1 runs already",
                "sw1 runs, process 41823",
                "vm1 runs, process 41824",
            ],
        )

    def test_a_start_that_fails(self):
        self.startable(self.brick("switch", "sw1"))
        self.startable(
            self.brick("qemu", "vm1"),
            errors.BadConfigError("Cannot start 'vm1': not configured"),
        )
        failure = self.failureResultOf(
            run(self.factory, "brick start sw1 vm1", self.clock())
        )
        self.assertEqual(
            failure.getErrorMessage(), "Cannot start 'vm1': not configured"
        )
        # what started before is said
        self.assertEqual(failure.value.lines, ["sw1 runs, process 41822"])
        self.assertEqual(self.logger.formatted(), [])

    def test_a_program_that_fails_is_logged(self):
        self.startable(self.brick("switch", "sw1"), OSError("No such file"))
        self.assertEqual(self.fails("brick start sw1"), "No such file")
        self.assertEqual(self.logger.formatted(), ["Starting sw1 failed"])

    def test_stop_and_kill(self):
        self.stoppable(self.running(self.brick("switch", "sw1")))
        self.stoppable(self.running(self.brick("tap", "tap1")))
        self.stoppable(self.brick("wire", "w1"))
        self.assertEqual(
            self.run_line("brick stop sw1 w1"),
            ["sw1 stopped", "w1 isn't running"],
        )
        self.assertEqual(self.run_line("brick kill tap1"), ["tap1 stopped"])
        self.assertEqual(
            self.done, [("off", "sw1", False), ("off", "tap1", True)]
        )

    def test_restart(self):
        sw = self.running(self.brick("switch", "sw1"))
        restarted = []

        def restart(brick, clock):
            restarted.append((brick, clock))
            return defer.succeed(brick)

        self.patch(console_bricks.bricks_module, "restart", restart)
        self.assertEqual(
            self.run_line("brick restart sw1"),
            ["sw1 runs again, process 41822"],
        )
        self.assertEqual(restarted, [(sw, self.clock())])
        self.brick("tap", "tap1")
        self.assertEqual(
            self.fails("brick restart sw1 tap1"), "tap1 isn't running"
        )
        self.assertEqual(len(restarted), 1)


class TestProcess(BricksTestCase):

    def test_pause_and_continue(self):
        sw = self.running(self.brick("switch", "sw1"))
        sent = []
        sw.send_signal = sent.append
        self.assertEqual(self.run_line("brick pause sw1"), [])
        self.assertEqual(self.run_line("brick continue sw1"), [])
        self.assertEqual(sent, [signal.SIGSTOP, signal.SIGCONT])

        def exited(number):
            raise error.ProcessExitedAlready()

        sw.send_signal = exited
        self.assertEqual(self.run_line("brick pause sw1"), [])
        self.brick("tap", "tap1")
        self.assertEqual(self.fails("brick pause tap1"), "tap1 isn't running")

    def test_suspend_and_resume(self):
        vm = self.running(self.brick("qemu", "vm1"))
        self.brick("switch", "sw1")
        self.patch(
            console_bricks,
            "suspend_vm",
            lambda brick: defer.succeed(self.done.append(("suspend", brick))),
        )
        self.patch(
            console_bricks,
            "resume_vm",
            lambda brick: defer.succeed(self.done.append(("resume", brick))),
        )
        self.assertEqual(
            self.run_line("brick suspend vm1"), ["vm1 is suspended"]
        )
        self.assertEqual(self.run_line("brick resume vm1"), ["vm1 is resumed"])
        self.assertEqual(self.done, [("suspend", vm), ("resume", vm)])
        self.assertEqual(
            self.fails("brick suspend sw1"), "sw1 is not a virtual machine"
        )
        vm.proc = None
        self.assertEqual(self.fails("brick suspend vm1"), "vm1 isn't running")

    def test_reset(self):
        vm = self.running(self.brick("qemu", "vm1"))
        sent = []
        vm.send = sent.append
        self.assertEqual(self.run_line("brick reset vm1"), [])
        self.assertEqual(sent, [b"system_reset\n"])

    def test_monitor(self):
        sw = self.running(self.brick("switch", "sw1"))
        sw.open_console = lambda: self.done.append("console")
        self.running(self.brick("tap", "tap1"))
        self.assertEqual(self.run_line("brick monitor sw1"), [])
        self.assertEqual(self.done, ["console"])
        self.assertEqual(
            self.fails("brick monitor tap1"), "tap1 has no control monitor"
        )


class TestLinks(BricksTestCase):

    def setUp(self):
        super().setUp()
        self.sw1 = self.brick("switch", "sw1")
        self.sw2 = self.brick("switch", "sw2")

    def test_a_plug(self):
        tap = self.brick("tap", "tap1")
        self.assertEqual(
            self.run_line("brick connect tap1 sw1"), ["plugged into sw1"]
        )
        self.assertIs(tap.plugs[0].sock, self.sw1.socks[0])
        # into another switch
        self.run_line("brick connect tap1 sw2")
        self.assertIs(tap.plugs[0].sock, self.sw2.socks[0])
        self.assertEqual(
            self.run_line("brick disconnect tap1"), ["plugged into nothing"]
        )
        self.assertEqual(
            self.fails("brick disconnect tap1 left"),
            "tap1 has no ends: brick disconnect tap1",
        )

    def test_the_ends_of_a_wire(self):
        wire = self.brick("wire", "w1")
        self.assertEqual(
            self.run_line("brick connect w1 sw1 sw2"),
            ["left: sw1", "right: sw2"],
        )
        self.assertEqual(
            self.run_line("brick disconnect w1 left"),
            ["left: nothing", "right: sw2"],
        )
        # one switch goes to the free end
        self.assertEqual(
            self.run_line("brick connect w1 sw1"), ["left: sw1", "right: sw2"]
        )
        self.assertEqual(
            self.fails("brick connect w1 sw1"),
            "w1 has no free plug: brick disconnect w1",
        )
        self.assertEqual(
            self.fails("brick connect w1 sw1 sw2 sw1"), "w1 has 2 plugs"
        )
        self.assertIs(wire.plugs[1].sock, self.sw2.socks[0])

    def test_what_cant_be_plugged(self):
        self.brick("tap", "tap1")
        vm = self.brick("qemu", "vm1")
        vm.add_sock()
        self.assertEqual(
            self.fails("brick connect tap1 vm1"),
            "vm1 has no socket to plug into",
        )
        self.assertEqual(
            self.fails("brick connect tap1 vm1:sock_eth0"),
            "tap1 can't plug into vm1:sock_eth0: only switches take plugs,"
            " unless allow_female_plugs is true",
        )
        settings.use_project(settings.ProjectSettings(allow_female_plugs=True))
        self.assertEqual(
            self.run_line("brick connect tap1 vm1:sock_eth0"),
            ["plugged into vm1:sock_eth0"],
        )
        self.assertEqual(
            self.fails("brick connect vm1 sw1"),
            "vm1 has network cards: brick card add vm1 plug TARGET",
        )
        self.assertEqual(
            self.fails("brick connect sw1 sw2"),
            "sw1 doesn't plug into anything",
        )

    def test_not_while_running(self):
        self.running(self.brick("tap", "tap1"))
        self.assertEqual(
            self.fails("brick connect tap1 sw1"),
            "tap1 is running: stop it first",
        )


class TestCards(BricksTestCase):

    def setUp(self):
        super().setUp()
        self.sw1 = self.brick("switch", "sw1")
        self.vm = self.brick("qemu", "vm1")

    def test_add(self):
        self.assertEqual(
            self.run_line(
                "brick card add vm1 plug sw1 model=e1000 mac=52:54:00:00:00:01"
            ),
            ["vm1 eth0: plugged into sw1, e1000, 52:54:00:00:00:01"],
        )
        self.assertEqual(
            self.run_line("brick card add vm1 socket mac=52:54:00:00:00:03"),
            [
                "vm1 eth1: socket vm1:sock_eth1, rtl8139, 52:54:00:00:00:03",
            ],
        )
        # a plug goes before the sockets
        self.assertEqual(
            self.run_line("brick card add vm1 hostonly mac=52:54:00:00:00:02"),
            ["vm1 eth1: host only, rtl8139, 52:54:00:00:00:02"],
        )
        self.assertIs(self.vm.plugs[1].sock, hostonly_sock)
        self.assertEqual(
            self.run_line("brick card add vm1 plug"),
            [f"vm1 eth2: in nothing, rtl8139, {self.vm.plugs[2].mac}"],
        )

    def test_what_is_wrong(self):
        self.assertEqual(
            self.fails("brick card add vm1 plug sw1 mac=nope"),
            "vm1 eth0: nope isn't a MAC address",
        )
        self.assertEqual(
            self.fails("brick card add vm1 socket sw1"),
            '"sw1" is not model=, mac= or a target',
        )
        self.assertEqual(
            self.fails("brick card add sw1 plug"),
            "sw1 is not a virtual machine",
        )
        self.assertEqual(self.vm.plugs + self.vm.socks, [])

    def test_set_and_remove(self):
        self.run_line("brick card add vm1 plug sw1 mac=52:54:00:00:00:01")
        self.run_line("brick card add vm1 socket mac=52:54:00:00:00:02")
        self.assertEqual(
            self.run_line(
                "brick card set vm1 eth0 model=e1000 target=hostonly"
            ),
            ["vm1 eth0: host only, e1000, 52:54:00:00:00:01"],
        )
        self.assertEqual(
            self.run_line("brick card set vm1 eth0 target="),
            ["vm1 eth0: in nothing, e1000, 52:54:00:00:00:01"],
        )
        self.assertEqual(
            self.fails("brick card set vm1 eth2 model=e1000"),
            "vm1 has no eth2",
        )
        self.assertEqual(
            self.fails("brick card set vm1 eth1 target=sw1"),
            '"target=sw1" is not model=, mac= or a target',
        )
        self.assertEqual(
            self.fails("brick card remove vm1 sock"),
            '"sock" is not a card: eth0, eth1…',
        )
        self.assertEqual(
            self.run_line("brick card remove vm1 eth0"),
            ["eth0: socket vm1:sock_eth1, rtl8139, 52:54:00:00:00:02"],
        )

    def test_remove_several(self):
        for number in range(3):
            self.run_line(
                f"brick card add vm1 plug mac=52:54:00:00:00:0{number}"
            )
        self.assertEqual(
            self.run_line("brick card remove vm1 eth0 eth1"),
            ["eth0: in nothing, rtl8139, 52:54:00:00:00:02"],
        )

    def test_not_while_running(self):
        self.running(self.vm)
        self.assertEqual(
            self.fails("brick card add vm1 plug sw1"),
            "vm1 is running: stop it first",
        )


class TestNames(BricksTestCase):

    def test_rename(self):
        sw = self.brick("switch", "sw1")
        self.assertEqual(self.run_line("brick rename sw1 core"), [])
        self.assertEqual(sw.name, "core")
        self.assertEqual(
            self.run_line("brick rename core 'core switch'"), ["core_switch"]
        )
        self.brick("tap", "tap1")
        self.assertEqual(
            self.fails("brick rename tap1 core_switch"),
            "core_switch is the name of a brick",
        )
        self.running(sw)
        self.assertEqual(
            self.fails("brick rename core_switch sw1"),
            "core_switch is running: stop it first",
        )

    def test_duplicate(self):
        sw = self.brick("switch", "sw1")
        sw.update_config({"ports": 4})
        self.assertEqual(self.run_line("brick duplicate sw1"), ["sw2"])
        self.assertEqual(self.run_line("brick duplicate sw1 core"), ["core"])
        self.assertEqual(self.factory.get_brick("core").config.ports, 4)
        self.assertEqual(
            self.fails("brick duplicate sw1 core"),
            "core is the name of a brick",
        )
        self.assertEqual(len(list(self.factory.bricks)), 3)

    def test_delete(self):
        self.brick("switch", "sw1")
        self.brick("switch", "sw2")
        self.running(self.brick("tap", "tap1"))
        self.assertEqual(
            self.fails("brick delete sw1 tap1"),
            "tap1 is running: stop it first",
        )
        self.assertEqual(len(list(self.factory.bricks)), 3)
        self.assertEqual(self.run_line("brick delete sw1 sw2"), [])
        self.assertEqual([b.name for b in self.factory.bricks], ["tap1"])

    def test_delete_drops_the_actions(self):
        self.brick("switch", "sw1")
        boot = self.factory.new_event("boot")
        command = ConsoleAction("brick set sw1 ports=4")
        boot.update_config({"actions": [StartAction("sw1"), command]})
        self.assertEqual(self.run_line("brick delete sw1"), [])
        # a command stays as it is written
        self.assertEqual(boot.config.actions, [command])
