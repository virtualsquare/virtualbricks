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

"""What the Bricks tab says about a brick, and how two bricks connect."""

import os
import subprocess
import sys
from unittest import mock

from twisted.trial import unittest

from virtualbricks.brickfactory import BRICK_CLASSES
from virtualbricks.bricks.netemu import Netemu
from virtualbricks.bricks.router import Router
from virtualbricks.bricks.switch import Switch
from virtualbricks.bricks.switchwrapper import SwitchWrapper
from virtualbricks.bricks.tunnelconnect import TunnelConnect
from virtualbricks.bricks.tunnellisten import TunnelListen
from virtualbricks.bricks.virtualmachine import VirtualMachine, hostonly_sock
from virtualbricks.bricks.wire import Wire
from virtualbricks.programs import VDE_PROGRAMS
from virtualbricks.tests import BrickTestCase

from virtualbricks.bricks import brickinfo
from virtualbricks.bricks.brickinfo import (
    HOST,
    LINKS,
    MACHINES,
    NEW_KINDS,
    Issue,
    State,
    connect,
    connectable,
    connection,
    issue,
    kind,
    new_name,
    process,
    state,
    summary,
)


def new_kind(brick_class):
    """The kind of New Brick whose bricks are of brick_class."""

    return next(kind for kind in NEW_KINDS if kind.brick is brick_class)


class FakeProcess:
    pid = 41301


class OtherBrick:
    """A brick of a type the tab doesn't know."""

    plugs = []
    socks = []

    def get_type(self):
        return "Other"


class BrickInfoTestCase(BrickTestCase):

    def setUp(self):
        super().setUp()
        # a switch can start once the folder of its socket is there
        os.makedirs(self.factory.runtime_dir)

    def brick(self, kind, name, *socks):
        brick = self.factory.new_brick(kind, name)
        for sock in socks:
            brick.connect(sock)
        return brick

    def switch(self, name="sw"):
        return self.brick("switch", name)


class TestKind(BrickInfoTestCase):

    def test_in_words(self):
        kinds = {
            "switch": "Switch",
            "switchwrapper": "Switch wrapper",
            "tap": "Tap",
            "wire": "Wire",
            "netemu": "Netemu",
            "capture": "Capture interface",
            "tunnellisten": "Tunnel server",
            "tunnelconnect": "Tunnel client",
            "router": "Router",
            "qemu": "Virtual machine",
        }
        for type, words in kinds.items():
            self.assertEqual(kind(self.brick(type, type)), words)
        self.assertEqual(sorted(brickinfo.KINDS), sorted(brickinfo._SUMMARIES))

    def test_unknown(self):
        self.assertEqual(kind(OtherBrick()), "Other")
        self.assertEqual(summary(OtherBrick()), "")


class TestState(BrickInfoTestCase):

    def test_stopped(self):
        self.assertIs(state(self.switch()), State.STOPPED)
        self.assertIsNone(process(self.switch("sw2")))

    def test_running(self):
        sw = self.switch()
        sw.proc = FakeProcess()
        self.assertIs(state(sw), State.RUNNING)
        self.assertEqual(process(sw), 41301)

    def test_not_connected(self):
        tap = self.brick("tap", "tap")
        self.assertIs(state(tap), State.NOT_CONNECTED)
        tap.connect(self.switch().socks[0])
        self.assertIs(state(tap), State.STOPPED)

    def test_not_configured(self):
        capture = self.brick("capture", "cap", self.switch().socks[0])
        self.assertIs(state(capture), State.NOT_CONFIGURED)
        capture.config.interface = "eth0"
        self.assertIs(state(capture), State.STOPPED)

    def test_a_free_plug_comes_first(self):
        # a wire with a free end is not configured either
        wire = self.brick("wire", "w", self.switch().socks[0])
        self.assertFalse(wire.configured())
        self.assertIs(state(wire), State.NOT_CONNECTED)

    def test_each_has_a_label(self):
        self.assertEqual(
            [brickinfo.LABELS[s] for s in State],
            ["Running", "Stopped", "Not connected", "Not configured"],
        )


class TestSummary(BrickInfoTestCase):

    def test_a_switch(self):
        sw = self.switch()
        self.assertEqual(summary(sw), "32 ports")
        sw.config.ports = 1
        self.assertEqual(summary(sw), "1 port")
        sw.config.fast_spanning_tree = True
        sw.config.hub_mode = True
        self.assertEqual(summary(sw), "1 port · FSTP · hub")

    def test_a_switch_wrapper(self):
        wrapper = self.brick("switchwrapper", "wrapper")
        self.assertEqual(summary(wrapper), "no socket")
        wrapper.config.socket_path = "/run/vde/lab.ctl"
        self.assertEqual(summary(wrapper), "/run/vde/lab.ctl")

    def test_a_tap(self):
        tap = self.brick("tap", "tap")
        self.assertEqual(summary(tap), "no address")
        tap.connect(self.switch().socks[0])
        self.assertEqual(summary(tap), "on sw · no address")
        tap.config.address_mode = "dhcp"
        self.assertEqual(summary(tap), "on sw · DHCP")
        tap.config.address_mode = "manual"
        self.assertEqual(summary(tap), "on sw · 10.0.0.1/24")
        tap.config.netmask = "255.255.240.0"
        self.assertEqual(summary(tap), "on sw · 10.0.0.1/20")

    def test_a_tap_with_a_mask_that_is_not_one(self):
        tap = self.brick("tap", "tap")
        tap.config.address_mode = "manual"
        tap.config.netmask = "255.0.255.0"
        self.assertEqual(summary(tap), "10.0.0.1/255.0.255.0")

    def test_a_wire(self):
        wire = self.brick("wire", "w")
        self.assertEqual(summary(wire), "nothing ↔ nothing")
        wire.connect(self.switch("sw1").socks[0])
        self.assertEqual(summary(wire), "sw1 ↔ nothing")
        wire.connect(self.switch("sw2").socks[0])
        self.assertEqual(summary(wire), "sw1 ↔ sw2")

    def test_a_netemu(self):
        sw1, sw2 = self.switch("sw1"), self.switch("sw2")
        netemu = self.brick("netemu", "ne", sw1.socks[0], sw2.socks[0])
        self.assertEqual(summary(netemu), "sw1 ↔ sw2")
        netemu.config.delay = 20
        netemu.config.loss = 1.0
        self.assertEqual(summary(netemu), "sw1 ↔ sw2 · 20 ms · 1% loss")

    def test_a_netemu_one_way(self):
        netemu = self.brick("netemu", "ne")
        netemu.config.delay_symmetric = False
        netemu.config.delay_right_to_left = 30
        netemu.config.loss_symmetric = False
        netemu.config.loss = 0.5
        self.assertEqual(
            summary(netemu), "nothing ↔ nothing · 0/30 ms · 0.5/0% loss"
        )

    def test_a_capture_interface(self):
        capture = self.brick("capture", "cap")
        self.assertEqual(summary(capture), "no interface")
        capture.config.interface = "eth0"
        self.assertEqual(summary(capture), "eth0")
        capture.connect(self.switch().socks[0])
        self.assertEqual(summary(capture), "eth0 on sw")

    def test_a_tunnel_server(self):
        server = self.brick("tunnellisten", "server")
        self.assertEqual(summary(server), "UDP port 7667")
        server.connect(self.switch().socks[0])
        self.assertEqual(summary(server), "on sw · UDP port 7667")

    def test_a_tunnel_client(self):
        client = self.brick("tunnelconnect", "client")
        self.assertEqual(summary(client), "no host")
        client.config.server_host = "lab.example.org"
        client.connect(self.switch().socks[0])
        self.assertEqual(summary(client), "on sw · to lab.example.org")

    def test_a_router(self):
        self.assertEqual(summary(self.brick("router", "r")), "")

    def test_a_virtual_machine(self):
        vm = self.brick("qemu", "vm")
        self.assertEqual(summary(vm), "i386 · 64 MiB · no network card")
        vm.config.qemu_program = "/usr/bin/qemu-kvm"
        vm.config.use_kvm = True
        vm.config.memory = 512
        self.assertEqual(
            summary(vm), "qemu-kvm · KVM · 512 MiB · no network card"
        )

    def test_the_cards_of_a_virtual_machine(self):
        vm = self.brick("qemu", "vm", self.switch().socks[0])
        vm.add_plug(None)
        vm.add_plug(hostonly_sock)
        vm.add_sock()
        self.assertEqual(
            summary(vm),
            "i386 · 64 MiB · eth0 on sw · eth1 not connected · "
            "eth2 host only · eth3 as a socket",
        )


class TestConnection(BrickInfoTestCase):

    def test_a_plug_and_a_sock(self):
        sw, tap = self.switch(), self.brick("tap", "tap")
        self.assertEqual(connection(tap, sw), (tap, sw.socks[0]))
        self.assertEqual(connection(sw, tap), (tap, sw.socks[0]))

    def test_a_plug_already_taken(self):
        sw = self.switch()
        tap = self.brick("tap", "tap", self.switch("sw2").socks[0])
        self.assertIsNone(connection(tap, sw))
        self.assertIsNone(connection(sw, tap))

    def test_a_virtual_machine_adds_a_card(self):
        sw = self.switch()
        vm = self.brick("qemu", "vm", sw.socks[0])
        self.assertEqual(connection(vm, sw), (vm, sw.socks[0]))
        self.assertEqual(connection(sw, vm), (vm, sw.socks[0]))

    def test_the_socket_of_a_virtual_machine(self):
        vm1, vm2 = self.brick("qemu", "vm1"), self.brick("qemu", "vm2")
        sock = vm2.add_sock()
        self.assertEqual(connection(vm1, vm2), (vm1, sock))
        self.assertEqual(connection(vm2, vm1), (vm1, sock))
        # a switch takes no plug, but the machine plugs into its socket
        sw = self.switch()
        self.assertEqual(connection(vm2, sw), (vm2, sw.socks[0]))

    def test_nothing_to_connect(self):
        sw1, sw2 = self.switch("sw1"), self.switch("sw2")
        tap, vm = self.brick("tap", "tap"), self.brick("qemu", "vm")
        self.assertIsNone(connection(sw1, sw2))
        self.assertIsNone(connection(tap, vm))
        self.assertIsNone(connection(vm, tap))
        self.assertIsNone(connection(tap, tap))

    def test_connect(self):
        sw, tap = self.switch(), self.brick("tap", "tap")
        self.assertIs(connect(sw, tap), True)
        self.assertIs(tap.plugs[0].sock, sw.socks[0])
        self.assertIs(connect(sw, tap), False)
        self.assertIs(connect(sw, self.switch("sw2")), False)

    def test_connectable(self):
        sw1, sw2 = self.switch("sw1"), self.switch("sw2")
        tap = self.brick("tap", "tap")
        tap2 = self.brick("tap", "tap2")
        vm = self.brick("qemu", "vm")
        bricks = [sw1, tap, sw2, tap2, vm]
        self.assertEqual(connectable(tap, bricks), [sw1, sw2])
        self.assertEqual(connectable(sw1, bricks), [tap, tap2, vm])
        self.assertEqual(connectable(vm, bricks), [sw1, sw2])


class TestNewKinds(BrickInfoTestCase):

    def test_every_kind_of_brick_once(self):
        classes = [kind.brick for kind in NEW_KINDS]
        self.assertEqual(len(set(classes)), len(classes))
        self.assertEqual(
            set(classes),
            set(BRICK_CLASSES.values()),
        )

    def test_in_three_groups(self):
        self.assertEqual(
            [kind.group for kind in NEW_KINDS],
            [MACHINES] * 4 + [LINKS] * 4 + [HOST] * 2,
        )

    def test_words(self):
        for new in NEW_KINDS:
            self.assertEqual(new.words, brickinfo.KINDS[new.type])
            self.assertTrue(new.line, new.type)
            self.assertTrue(new.about, new.type)

    def test_the_factory_makes_each(self):
        self.factory.runtime_dir = "/run/vb"
        for new in NEW_KINDS:
            name = new_name(self.factory, new)
            self.assertEqual(name, new.prefix + "1")
            # a name that passes the checks of any name
            self.assertEqual(
                self.factory.check_brick_name(new.type, name), name
            )
            brick = self.factory.new_brick(new.type, name)
            self.assertIsInstance(brick, new.brick)


class TestNewName(BrickInfoTestCase):

    def test_the_first_number_free(self):
        self.assertEqual(new_name(self.factory, new_kind(Switch)), "sw1")
        self.switch("sw1")
        self.switch("sw3")
        self.assertEqual(new_name(self.factory, new_kind(Switch)), "sw2")

    def test_free_in_the_whole_project(self):
        self.factory.new_event("vm1")
        self.factory.new_image("vm2", "/images/vm2.qcow2")
        self.brick("qemu", "vm3")
        self.assertEqual(
            new_name(self.factory, new_kind(VirtualMachine)), "vm4"
        )


class TestIssue(BrickInfoTestCase):

    def setUp(self):
        super().setUp()
        self.vde = self.folder()
        self.qemu = self.folder()
        for name in VDE_PROGRAMS:
            self.install(self.vde, name)
        self.install(self.qemu, "qemu-system-i386")
        # only the folders: this computer's PATH has programs of its own
        patcher = mock.patch.dict(os.environ, {"PATH": ""})
        patcher.start()
        self.addCleanup(patcher.stop)

    def folder(self):
        path = os.path.abspath(self.mktemp())
        os.makedirs(path)
        return path

    def install(self, folder, name):
        path = os.path.join(folder, name)
        with open(path, "w") as fp:
            fp.write("#!/bin/sh\n")
        os.chmod(path, 0o755)

    def uninstall(self, *names):
        for name in names:
            os.remove(os.path.join(self.vde, name))

    def issue(self, brick_class):
        return issue(new_kind(brick_class), self.vde, self.qemu)

    def test_everything_installed(self):
        for new in NEW_KINDS:
            self.assertIsNone(issue(new, self.vde, self.qemu), new.type)

    def test_a_program_missing(self):
        self.uninstall("vde_cryptcab")
        expected = Issue(
            "vde_cryptcab isn't installed",
            "vde_cryptcab isn't installed: the package vde2-cryptcab has it."
            " The brick can be made now, and starts once it is installed.",
        )
        self.assertEqual(self.issue(TunnelListen), expected)
        self.assertEqual(self.issue(TunnelConnect), expected)
        self.assertIsNone(self.issue(Switch))

    def test_a_program_that_no_distribution_ships(self):
        self.uninstall("vde_router")
        self.assertEqual(
            self.issue(Router),
            Issue(
                "vde_router isn't installed",
                "vde_router isn't installed, and no distribution ships it."
                " The brick can be made now, and starts once it is"
                " installed.",
            ),
        )

    def test_either_program(self):
        self.uninstall("vde-netemu")
        self.assertIsNone(self.issue(Netemu))
        self.uninstall("wirefilter")
        self.assertEqual(
            self.issue(Netemu),
            Issue(
                "vde-netemu isn't installed",
                "Neither vde-netemu (vde-netemu) nor wirefilter (vde2) is"
                " installed. The brick can be made now, and starts once it is"
                " installed.",
            ),
        )

    def test_several_programs(self):
        self.uninstall("dpipe", "vde_plug")
        self.assertEqual(
            self.issue(Wire),
            Issue(
                "dpipe isn't installed",
                "dpipe isn't installed: the package vde2 has it. vde_plug"
                " isn't installed: the package vde2 has it. The brick can be"
                " made now, and starts once they are installed.",
            ),
        )

    def test_qemu_in_its_own_folder(self):
        # the folder of QEMU, not VDE's
        self.install(self.vde, "qemu-system-i386")
        os.remove(os.path.join(self.qemu, "qemu-system-i386"))
        self.assertEqual(
            self.issue(VirtualMachine),
            Issue(
                "qemu-system-i386 isn't installed",
                "qemu-system-i386 isn't installed: the package"
                " qemu-system-x86 has it. The brick can be made now, and"
                " starts once it is installed.",
            ),
        )

    def test_in_path_too(self):
        self.uninstall("vde_switch")
        self.install(self.qemu, "vde_switch")
        os.environ["PATH"] = self.qemu
        self.assertIsNone(self.issue(Switch))

    def test_a_switch_wrapper_runs_nothing(self):
        self.uninstall(*VDE_PROGRAMS)
        self.assertIsNone(self.issue(SwitchWrapper))


class TestWithoutTheDesktop(unittest.TestCase):

    def test_no_graphics_library(self):
        # in a process of its own: the tests of the windows load GTK; the
        # console reads these modules
        code = (
            "import sys; import virtualbricks.bricks.brickinfo, "
            "virtualbricks.bricks.eventinfo; "
            "print([m for m in sys.modules if m == 'gi'"
            " or m.startswith(('gi.', 'gtk', 'gobject'))])"
        )
        result = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "[]")
