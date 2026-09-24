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


"""The virtual machines: disks, network cards, command line."""

import os

from twisted.internet import defer

from virtualbricks import bricks, project
from virtualbricks.config import settings
from virtualbricks.config.report import Report
from virtualbricks.tests import (
    BrickTestCase,
    CommandTestCase,
    adjacent,
)
from virtualbricks.bricks.virtualmachine import (
    UsbDevice,
    UsbDeviceKind,
    hostonly_sock,
)


class TestVirtualMachine(BrickTestCase):

    def test_disks_refer_to_images_by_name(self):
        vm = self.factory.new_brick("qemu", "vm")
        disk = vm.disk("hda")
        self.assertIsNone(disk.image)
        image = self.factory.new_disk_image("deb", "/i/deb.qcow2")
        changes = []
        vm.image_changed.connect(lambda payload: changes.append(payload))
        vm.set_image("hda", image)
        self.assertEqual(vm.config.hda, "deb")
        self.assertIs(disk.image, image)
        self.assertEqual(changes, [(vm, image)])
        vm.set({"privatehda": True})
        self.assertTrue(disk.is_cow())
        self.assertFalse(disk.readonly())
        vm.set_image("hda", None)
        self.assertEqual(vm.config.hda, "")
        vm.config.hdb = "missing"
        self.assertIsNone(vm.disk("hdb").image)
        self.assertEqual([d.device for d in vm.disks()][0], "hda")

    def test_image_rename_updates_the_disks(self):
        vm = self.factory.new_brick("qemu", "vm")
        image = self.factory.new_disk_image("deb", "/i/deb.qcow2")
        vm.set_image("hda", image)
        self.factory.rename(image, "debian")
        self.assertEqual(vm.config.hda, "debian")
        self.assertIs(vm.disk("hda").image, image)

    def test_sockets(self):
        vm = self.factory.new_brick("qemu", "vm")
        sw = self.factory.new_brick("switch", "sw")
        vm.add_plug(sw.socks[0], "00:aa:00:00:00:01", "e1000")
        default = vm.add_sock("00:aa:00:00:00:02", "e1000")
        named = vm.add_sock(name="sock_x")
        self.assertEqual(default.nickname, "vm_sock_eth1")
        self.assertEqual(named.nickname, "vm_sock_x")
        self.assertEqual(
            named.path, os.path.join(self.factory.runtime_dir, "vm_sock_x[]")
        )
        manager = project.ProjectManager(self.mktemp())
        self.patch(project, "manager", manager)
        manager.current = project.Project(self.mktemp(), manager)
        os.makedirs(manager.current.path)
        vm.rename("vm2")
        self.assertEqual(default.nickname, "vm2_sock_eth1")
        self.assertEqual(
            default.path,
            os.path.join(self.factory.runtime_dir, "vm2_sock_eth1[]"),
        )

    def test_rename_keeps_other_sockets(self):
        vm = self.factory.new_brick("qemu", "vm")
        sock = vm.add_sock()
        sock.nickname = "other"
        vm.set_name("vm3")
        self.assertEqual(sock.nickname, "other")

    def test_usb_kind(self):
        kind = UsbDeviceKind()
        report = Report()
        device = UsbDevice("1d6b:0002", "hub")
        kind.check(device)
        self.assertRaises(ValueError, kind.check, "1d6b:0002")
        self.assertEqual(
            kind.to_data(device), {"id": "1d6b:0002", "description": "hub"}
        )
        self.assertEqual(
            kind.from_data({"id": "1d6b:0002", "x": 1}, report, "u"),
            UsbDevice("1d6b:0002", ""),
        )
        self.assertEqual(len(report), 1)
        for bad in (
            "1d6b:0002",
            {"id": "usb"},
            {"id": "1d6b:0002", "description": 1},
        ):
            self.assertRaises(ValueError, kind.from_data, bad, report, "u")
        self.assertEqual(kind.format(device), "1d6b:0002")

    def test_usb_devices_are_hashable(self):
        devices = {
            UsbDevice("1d6b:0002", "hub"),
            UsbDevice("1d6b:0002", "hub"),
        }
        self.assertEqual(len(devices), 1)


class TestCommandLine(CommandTestCase):

    def test_every_option(self):
        vm = self.factory.new_brick("qemu", "vm")
        vm.set(
            {
                "argv0": "",
                "kvm": True,
                "machine": "pc",
                "kvmsm": True,
                "kvmsmem": 2,
                "cpu": "host",
                "novga": True,
                "kernelenbl": True,
                "kernel": "/boot/k",
                "initrdenbl": True,
                "initrd": "/boot/i",
                "kopt": 'console="ttyS0"',
                "gdb": True,
                "gdbport": 1234,
                "vnc": True,
                "vncN": 2,
                "vga": True,
                "usbmode": True,
                "usbdevlist": [UsbDevice("1d6b:0002", "hub")],
                "cdromen": True,
                "cdrom": "/c.iso",
                "rtc": True,
                "tdf": True,
                "keyboard": "it",
                "serial": True,
            }
        )
        sw = self.factory.new_brick("switch", "sw")
        vm.add_plug(sw.socks[0], "00:aa:00:00:00:01", "e1000")
        vm.add_plug(hostonly_sock, "00:aa:00:00:00:02", "rtl8139")
        sock = vm.add_sock("00:aa:00:00:00:03", "virtio-net-pci")
        args = self.successResultOf(vm.args())
        self.assertEqual(args[0], os.path.join(self.bin, "qemu-system-x86_64"))
        options = adjacent(args)
        for pair in [
            ("-machine", "type=pc,accel=kvm:tcg,kvm_shadow_mem=2"),
            ("-cpu", "host"),
            ("-display", "none"),
            ("-kernel", "/boot/k"),
            ("-initrd", "/boot/i"),
            ("-append", "'console=ttyS0'"),
            ("-gdb", "tcp::1234"),
            ("-vnc", ":2"),
            ("-vga", "std"),
            ("-usbdevice", "host:1d6b:0002"),
            ("-name", "vm"),
            ("-device", "e1000,mac=00:aa:00:00:00:01,id=vx0,netdev=vx0"),
            ("-netdev", f"vde,id=vx0,sock={sw.socks[0].path.rstrip('[]')}"),
            ("-netdev", "user,id=vx1"),
            ("-netdev", f"vde,id=vx2,sock={sock.path}"),
            ("-cdrom", "/c.iso"),
            ("-rtc", "base=localtime,driftfix=slew"),
            ("-k", "it"),
            (
                "-serial",
                f"unix:{self.factory.runtime_dir}/vm_serial,server,nowait",
            ),
        ]:
            self.assertIn(pair, options)

    def test_few_options(self):
        vm = self.factory.new_brick("qemu", "vm")
        vm.set(
            {
                "argv0": "qemu-system-i386",
                "kernel": "/boot/k",
                "kopt": "quiet",
                "deviceen": True,
                "device": "/dev/cdrom",
                "tdf": True,
                "keyboard": "",
            }
        )
        args = self.successResultOf(vm.args())
        self.assertEqual(args[0], os.path.join(self.bin, "qemu-system-i386"))
        options = adjacent(args)
        self.assertIn(("-net", "none"), options)
        self.assertIn(("-cdrom", "/dev/cdrom"), options)
        self.assertIn(("-rtc", "driftfix=slew"), options)
        for option in ("-machine", "-append", "-kernel", "-k", "-usbdevice"):
            self.assertNotIn(option, args)

    def test_a_plug_without_vde(self):
        vm = self.factory.new_brick("qemu", "vm")
        plug = vm.add_plug(None, "00:aa:00:00:00:01", "e1000")
        plug.mode = "user"
        args = self.successResultOf(vm.args())
        self.assertIn(("-netdev", "user"), adjacent(args))
        self.assertTrue(vm.configured())
        plug.mode = "vde"
        self.assertFalse(vm.configured())

    def test_parameters(self):
        vm = self.factory.new_brick("qemu", "vm")
        sw = self.factory.new_brick("switch", "sw")
        vm.add_plug(sw.socks[0], "00:aa:00:00:00:01", "e1000")
        prog = os.path.join(self.bin, "qemu-system-i386")
        self.assertEqual(
            vm.get_parameters(), f"command: {prog}, ram: 64, eth0: sw_port"
        )
        # the program isn't on this machine
        settings.set("qemupath", os.path.join(self.bin, "missing"))
        self.patch(os, "environ", dict(os.environ, PATH=self.bin + "/missing"))
        self.assertTrue(
            vm.get_parameters().startswith("command: qemu-system-i386,")
        )
        vm.set({"argv0": ""})
        self.assertTrue(
            vm.get_parameters().startswith("command: qemu-system-x86_64,")
        )

    def test_update_usb_devices(self):
        vm = self.factory.new_brick("qemu", "vm")
        vm.set({"usbdevlist": [UsbDevice("1d6b:0002", "hub")]})
        sent = []
        vm.send = sent.append
        vm.update_usbdevlist(
            [UsbDevice("1d6b:0002", "hub"), UsbDevice("046d:c52b", "mouse")]
        )
        self.assertEqual(sent, [b"usb_add host:046d:c52b\n"])

    def test_power_on_a_snapshot(self):
        vm = self.factory.new_brick("qemu", "vm")
        started = defer.Deferred()
        seen = []

        def poweron(brick):
            seen.append(brick.config.loadvm)
            brick._exited_d = defer.Deferred()
            return started

        self.patch(bricks.Brick, "poweron", poweron)
        vm.acquire = vm.release = lambda: None
        d = vm.poweron("snap1")
        self.assertEqual(seen, ["snap1"])
        started.callback(vm)
        self.successResultOf(d)
        self.assertEqual(vm.config.loadvm, "")
