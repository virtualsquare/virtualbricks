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

"""What the Bricks tab says about a brick, and how two bricks connect."""

import os

from virtualbricks.bricks.virtualmachine import hostonly_sock
from virtualbricks.tests.gui import GuiTestCase, has_display

if has_display:
    from virtualbricks.gui.mainwindow import brickinfo
    from virtualbricks.gui.mainwindow.brickinfo import (
        State,
        connect,
        connectable,
        connection,
        kind,
        process,
        state,
        summary,
    )


class FakeProcess:
    pid = 41301


class OtherBrick:
    """A brick of a type the tab doesn't know."""

    plugs = []
    socks = []

    def get_type(self):
        return "Other"


class BrickInfoTestCase(GuiTestCase):

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
        capture.config.iface = "eth0"
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
        sw.config.numports = 1
        self.assertEqual(summary(sw), "1 port")
        sw.config.fstp = True
        sw.config.hub = True
        self.assertEqual(summary(sw), "1 port · FSTP · hub")

    def test_a_switch_wrapper(self):
        wrapper = self.brick("switchwrapper", "wrapper")
        self.assertEqual(summary(wrapper), "no socket")
        wrapper.config.path = "/run/vde/lab.ctl"
        self.assertEqual(summary(wrapper), "/run/vde/lab.ctl")

    def test_a_tap(self):
        tap = self.brick("tap", "tap")
        self.assertEqual(summary(tap), "no address")
        tap.connect(self.switch().socks[0])
        self.assertEqual(summary(tap), "on sw · no address")
        tap.config.mode = "dhcp"
        self.assertEqual(summary(tap), "on sw · DHCP")
        tap.config.mode = "manual"
        self.assertEqual(summary(tap), "on sw · 10.0.0.1/24")
        tap.config.nm = "255.255.240.0"
        self.assertEqual(summary(tap), "on sw · 10.0.0.1/20")

    def test_a_tap_with_a_mask_that_is_not_one(self):
        tap = self.brick("tap", "tap")
        tap.config.mode = "manual"
        tap.config.nm = "255.0.255.0"
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
        netemu.config.delaysymm = False
        netemu.config.delayr = 30
        netemu.config.losssymm = False
        netemu.config.loss = 0.5
        self.assertEqual(
            summary(netemu), "nothing ↔ nothing · 0/30 ms · 0.5/0% loss"
        )

    def test_a_capture_interface(self):
        capture = self.brick("capture", "cap")
        self.assertEqual(summary(capture), "no interface")
        capture.config.iface = "eth0"
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
        client.config.host = "lab.example.org"
        client.connect(self.switch().socks[0])
        self.assertEqual(summary(client), "on sw · to lab.example.org")

    def test_a_router(self):
        self.assertEqual(summary(self.brick("router", "r")), "")

    def test_a_virtual_machine(self):
        vm = self.brick("qemu", "vm")
        self.assertEqual(summary(vm), "i386 · 64 MiB · no network card")
        vm.config.argv0 = "/usr/bin/qemu-kvm"
        vm.config.kvm = True
        vm.config.ram = 512
        self.assertEqual(
            summary(vm), "qemu-kvm · KVM · 512 MiB · no network card"
        )
        vm.config.argv0 = ""
        self.assertTrue(summary(vm).startswith("x86_64 · KVM"))

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
