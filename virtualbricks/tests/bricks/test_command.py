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
The command lines of the bricks, on the programs of every target.

The lines expected are those that the code before command() gave, where the
program of the target still takes them; the differences are the fixes and the
options that each QEMU spells its own way.
"""

import os

import attr

from virtualbricks import bricks, errors
from virtualbricks.brickfactory import install_brick_types
from virtualbricks.bricks import virtualmachine
from virtualbricks.bricks.command import (
    Command,
    Prepared,
    joined,
    socket_path,
    vde_program,
)
from virtualbricks.bricks.virtualmachine import UsbDevice, hostonly_sock
from virtualbricks.config.settings import set_setting
from virtualbricks.programs import (
    VDE_PROGRAMS,
    ProgramError,
    Programs,
    parse_machine_properties,
)
from virtualbricks.tests import BrickTestCase, CommandTestCase, FakeLogger
from virtualbricks.tests.test_programs import (
    TARGETS,
    FakeRun,
    answers,
    load,
    recorded_info,
)
from virtualbricks.programs import vde_info as make_vde_info

RUN = "/run/vb"


def vde_info(target="debian-13"):
    data = load(target)
    found = {
        name: path for name, path in data["vde"]["programs"].items() if path
    }
    return make_vde_info("/usr/bin", found, answers(data["vde"]["answers"]))


def prepared_vde(target="debian-13", **programs):
    info = vde_info(target)
    return Prepared(
        vde=attr.evolve(info, programs={**info.programs, **programs})
    )


def prepared_qemu(
    target="debian-13", disks=(), driver="alsa", resume="", **changes
):
    qemu = attr.evolve(recorded_info(target), **changes)
    pc = load(target)["qemu"]["machines"]["pc"]["out"]
    return Prepared(
        qemu=qemu,
        machine_properties=parse_machine_properties(pc),
        disks=disks,
        audio_driver=driver,
        resume=resume,
    )


class TestCommand(BrickTestCase):

    def test_arguments(self):
        cmd = Command("/usr/bin/vde_switch")
        cmd.flag("-x", False)
        cmd.flag("-F", True)
        cmd.option("-n", 0)
        cmd.option("-g", "")
        cmd.option("-m", None)
        cmd.arg("=", 3)
        self.assertEqual(
            cmd.argv, ["/usr/bin/vde_switch", "-F", "-n", "0", "=", "3"]
        )
        self.assertEqual(cmd.warnings, [])
        cmd.warn("left out")
        self.assertEqual(cmd.warnings, ["left out"])

    def test_joined(self):
        self.assertEqual(joined("type=pc", "", "acpi=off"), "type=pc,acpi=off")
        self.assertEqual(joined("", ""), "")

    def test_socket_path(self):
        sw = self.factory.new_brick("switch", "sw")
        vm = self.factory.new_brick("qemu", "vm")
        tap = self.factory.new_brick("tap", "tap")
        tap.connect(sw.socks[0])
        self.assertEqual(socket_path(tap.plugs[0]), sw.path())
        card = vm.add_sock()
        tap.disconnect()
        tap.connect(card)
        self.assertTrue(card.path.endswith("[]"))
        # a socket card joins its plug without a switch
        self.assertEqual(socket_path(tap.plugs[0]), f"ptp://{card.path[:-2]}")

    def test_vde_program(self):
        vde = vde_info()
        self.assertEqual(vde_program(vde, "vde_switch"), "/usr/bin/vde_switch")
        with self.assertRaises(ProgramError) as caught:
            vde_program(attr.evolve(vde, programs={}), "vde_cryptcab")
        self.assertEqual(
            str(caught.exception),
            "vde_cryptcab (vde2-cryptcab) isn't installed",
        )
        with self.assertRaises(ProgramError) as caught:
            vde_program(vde, "vde_router")
        self.assertEqual(str(caught.exception), "vde_router isn't installed")


class LinesTestCase(BrickTestCase):

    def setUp(self):
        super().setUp()
        self.factory.runtime_dir = RUN
        self.sw1 = self.brick("switch", "sw1")
        self.sw2 = self.brick("switch", "sw2")

    def brick(self, kind, name, *socks, **values):
        brick = self.factory.new_brick(kind, name)
        if values:
            brick.update_config(values)
        for plug, sock in zip(brick.plugs, socks):
            plug.connect(sock.socks[0])
        return brick

    def line(self, brick, prepared):
        cmd = brick.command(prepared)
        return cmd.argv, cmd.warnings

    def assertLine(self, brick, expected, warnings=(), targets=TARGETS):
        for target in targets:
            self.assertEqual(
                self.line(brick, prepared_vde(target)),
                (expected, list(warnings)),
                target,
            )


class TestVdeBricks(LinesTestCase):
    """The same programs of VDE on every target."""

    def test_switch(self):
        self.assertLine(
            self.sw1,
            [
                "/usr/bin/vde_switch",
                "-n",
                "32",
                "-s",
                f"{RUN}/sw1.ctl",
                "-M",
                f"{RUN}/sw1.mgmt",
            ],
        )
        sw3 = self.brick(
            "switch", "sw3", hub_mode=True, fast_spanning_tree=True, ports=8
        )
        self.assertLine(
            sw3,
            ["/usr/bin/vde_switch", "-x", "-n", "8", "-F"]
            + ["-s", f"{RUN}/sw3.ctl", "-M", f"{RUN}/sw3.mgmt"],
        )

    def test_each_tap_its_own(self):
        tap1 = self.brick("tap", "tap1", self.sw1)
        tap2 = self.brick("tap", "tap2", self.sw2)
        self.assertLine(
            tap1, ["/usr/bin/vde_plug2tap", "-s", f"{RUN}/sw1.ctl", "tap1"]
        )
        self.assertLine(
            tap2, ["/usr/bin/vde_plug2tap", "-s", f"{RUN}/sw2.ctl", "tap2"]
        )

    def test_capture(self):
        capture = self.brick("capture", "cap1", self.sw1, interface="eth0")
        self.assertLine(
            capture, ["/usr/bin/vde_pcapplug", "-s", f"{RUN}/sw1.ctl", "eth0"]
        )

    def test_wire(self):
        wire = self.brick("wire", "w1", self.sw1, self.sw2)
        self.assertLine(
            wire,
            ["/usr/bin/dpipe", "/usr/bin/vde_plug", f"{RUN}/sw1.ctl", "="]
            + ["/usr/bin/vde_plug", f"{RUN}/sw2.ctl"],
        )

    def test_each_tunnel_its_own(self):
        tl1 = self.brick("tunnellisten", "tl1", self.sw1)
        tl2 = self.brick("tunnellisten", "tl2", self.sw2, listen_port=7700)
        self.assertLine(
            tl1,
            ["/usr/bin/vde_cryptcab", "-P", f"{RUN}/tl1.key"]
            + ["-s", f"{RUN}/sw1.ctl", "-p", "7667"],
        )
        self.assertLine(
            tl2,
            ["/usr/bin/vde_cryptcab", "-P", f"{RUN}/tl2.key"]
            + ["-s", f"{RUN}/sw2.ctl", "-p", "7700"],
        )
        tc1 = self.brick(
            "tunnelconnect", "tc1", self.sw2, server_host="example.org"
        )
        self.assertLine(
            tc1,
            ["/usr/bin/vde_cryptcab", "-P", f"{RUN}/tc1.key"]
            + [
                "-s",
                f"{RUN}/sw2.ctl",
                "-p",
                "10771",
                "-c",
                "example.org:7667",
            ],
        )

    def test_router(self):
        router = self.brick("router", "r1")
        for target in TARGETS:
            with self.assertRaises(ProgramError, msg=target):
                router.command(prepared_vde(target))
        prepared = prepared_vde(vde_router="/usr/local/bin/vde_router")
        self.assertEqual(
            self.line(router, prepared),
            (["/usr/local/bin/vde_router", "-M", f"{RUN}/r1.mgmt"], []),
        )


class TestPrograms(LinesTestCase):
    """The programs a brick declares are those its command line runs."""

    def runs(self, brick, vde):
        argv = brick.command(Prepared(vde=vde)).argv
        return {os.path.basename(arg) for arg in argv if arg.startswith("/v/")}

    def assertRuns(self, brick, vde):
        names = self.runs(brick, vde)
        # one program of each choice, and nothing else
        for choice in brick.programs:
            self.assertEqual(len(names & set(choice)), 1, (brick.name, choice))
        declared = {name for choice in brick.programs for name in choice}
        self.assertLessEqual(names, declared, brick.name)

    def test_the_vde_bricks(self):
        everything = {name: f"/v/{name}" for name in VDE_PROGRAMS}
        vde = attr.evolve(vde_info(), programs=everything)
        netemu = self.brick("netemu", "ne1", self.sw1, self.sw2)
        server = self.brick("tunnellisten", "tl1", self.sw1)
        client = self.brick(
            "tunnelconnect", "tc1", self.sw2, server_host="example.org"
        )
        tried = [
            self.sw1,
            self.brick("tap", "tap1", self.sw1),
            self.brick("capture", "cap1", self.sw1, interface="eth0"),
            self.brick("wire", "w1", self.sw1, self.sw2),
            netemu,
            server,
            client,
            self.brick("router", "r1"),
        ]
        for brick in tried:
            self.assertRuns(brick, vde)
        # the other program of Netemu's choice
        del everything["vde-netemu"]
        wirefilter = attr.evolve(vde, programs=everything)
        self.assertRuns(netemu, wirefilter)
        self.assertEqual(self.runs(netemu, wirefilter), {"wirefilter"})
        # every kind that runs a program of VDE
        kinds = {
            kind
            for kind in install_brick_types().values()
            if issubclass(kind, bricks.Brick)
            and kind.programs
            and kind is not virtualmachine.VirtualMachine
        }
        self.assertEqual({type(brick) for brick in tried}, kinds)

    def test_a_new_machine(self):
        vm = self.factory.new_brick("qemu", "vm1")
        self.assertEqual(vm.programs, ((vm.config.qemu_program,),))

    def test_a_switch_wrapper_runs_nothing(self):
        wrapper = self.factory.new_brick("switchwrapper", "wr1")
        self.assertEqual(wrapper.programs, ())


class TestNetemu(LinesTestCase):

    def setUp(self):
        super().setUp()
        self.netemu = self.brick("netemu", "ne1", self.sw1, self.sw2)

    def test_wirefilter_in_its_place(self):
        # no target ships vde-netemu
        self.assertLine(
            self.netemu,
            ["/usr/bin/wirefilter", "-v", f"{RUN}/sw1.ctl:{RUN}/sw2.ctl"]
            + ["-b", "125000", "-d", "0", "-c", "75000", "-l", "0.0"]
            + ["--nofifo", "-M", f"{RUN}/ne1.mgmt"],
            [
                "ne1: vde-netemu (vde-netemu) isn't installed: wirefilter runs"
                " in its place"
            ],
        )

    def test_vde_netemu(self):
        self.netemu.update_config(
            {
                "bandwidth_symmetric": False,
                "bandwidth_right_to_left": 1000,
                "delay_symmetric": False,
                "delay": 10,
                "delay_right_to_left": 20,
                "buffer_size_symmetric": False,
                "buffer_size_right_to_left": 500,
                "loss_symmetric": False,
                "loss": 1.5,
                "loss_right_to_left": 2.5,
            }
        )
        prepared = prepared_vde(**{"vde-netemu": "/usr/bin/vde-netemu"})
        self.assertEqual(
            self.line(self.netemu, prepared),
            (
                ["/usr/bin/vde-netemu", "-v", f"{RUN}/sw1.ctl:{RUN}/sw2.ctl"]
                + ["-b", "LR 125000", "-b", "RL 1000"]
                + ["-d", "LR 10", "-d", "RL 20"]
                + ["-c", "LR 75000", "-c", "RL 500"]
                + ["-l", "LR 1.5", "-l", "RL 2.5"]
                + ["--nofifo", "-M", f"{RUN}/ne1.mgmt"],
                [],
            ),
        )

    def test_a_socket_card(self):
        vm = self.factory.new_brick("qemu", "vm")
        card = vm.add_sock()
        self.netemu.plugs[1].disconnect()
        self.netemu.plugs[1].connect(card)
        argv, _ = self.line(self.netemu, prepared_vde())
        self.assertIn(f"{RUN}/sw1.ctl:ptp://{RUN}/vm_sock_eth0", argv)
        # -v can't take it on the left
        self.netemu.plugs[0].disconnect()
        self.netemu.plugs[0].connect(card)
        with self.assertRaises(errors.BadConfigError) as caught:
            self.netemu.command(prepared_vde())
        self.assertEqual(
            str(caught.exception),
            "ne1: the socket card of a machine can only be the right end of a"
            " Netemu (endpoints)",
        )

    def test_neither(self):
        vde = vde_info()
        programs = dict(vde.programs)
        del programs["wirefilter"]
        prepared = Prepared(vde=attr.evolve(vde, programs=programs))
        with self.assertRaises(ProgramError) as caught:
            self.netemu.command(prepared)
        self.assertEqual(
            str(caught.exception),
            "vde-netemu (vde-netemu) isn't installed, nor wirefilter (vde2)",
        )

    def test_wirefilter_without_the_options(self):
        vde = vde_info()
        options = {"wirefilter": vde.options["wirefilter"] - {"-M", "-l"}}
        prepared = Prepared(vde=attr.evolve(vde, options=options))
        with self.assertRaises(ProgramError) as caught:
            self.netemu.command(prepared)
        self.assertEqual(
            str(caught.exception),
            "vde-netemu (vde-netemu) isn't installed, and wirefilter has no"
            " -l, -M",
        )


def machine_line(path, name):
    return [
        path,
        "-smp",
        "1",
        "-m",
        "64",
        "-name",
        name,
        "-net",
        "none",
        "-mon",
        "chardev=mon",
        "-chardev",
        f"socket,id=mon,path={RUN}/{name}.mgmt,server=on,wait=off",
        "-mon",
        "chardev=mon_cons",
        "-chardev",
        "stdio,id=mon_cons,signal=off",
    ]


class TestMachine(LinesTestCase):

    def machine(self, name="vm2"):
        vm = self.brick("qemu", name)
        vm.update_config(
            {
                "qemu_program": "qemu-system-x86_64",
                "use_kvm": True,
                "machine_type": "pc",
                "use_kvm_shadow_memory": True,
                "kvm_shadow_memory": 2,
                "cpu_model": "host",
                "cpus": 2,
                "memory": 512,
                "boot_order": "d",
                "sound_card": "ac97",
                "forget_disk_changes": True,
                "sdl_window": True,
                "acpi": False,
                "use_kernel": True,
                "kernel": "/boot/k",
                "use_initrd": True,
                "initrd": "/boot/i",
                "kernel_command_line": 'console=ttyS0 init="/bin/sh"',
                "use_gdb": True,
                "gdb_port": 1234,
                "use_vnc": True,
                "vnc_display": 2,
                "standard_vga": True,
                "use_usb": True,
                "usb_devices": [UsbDevice("1d6b:0002", "hub")],
                "cdrom": "image",
                "cdrom_image": "/c.iso",
                "clock_local_time": True,
                "clock_drift_fix": True,
                "keyboard_layout": "it",
                "serial_socket": True,
            }
        )
        vm.add_plug(self.sw1.socks[0], "00:aa:00:00:00:01", "e1000")
        vm.add_plug(hostonly_sock, "00:aa:00:00:00:02", "rtl8139")
        vm.add_sock("00:aa:00:00:00:03", "virtio-net-pci")
        return vm

    def test_default(self):
        vm = self.brick("qemu", "vm1")
        for target in TARGETS:
            prepared = prepared_qemu(target)
            self.assertEqual(
                self.line(vm, prepared),
                (machine_line(prepared.qemu.path, "vm1"), []),
                target,
            )

    def test_every_option(self):
        vm = self.machine()
        for target, facts in TARGETS.items():
            prepared = prepared_qemu(target, resume="snap1")
            argv, warnings = self.line(vm, prepared)
            expected_warnings = []
            sock = f"vde,id=vx2,sock=ptp://{RUN}/vm2_sock_eth2"
            if facts.vde:
                cards = [
                    "-device",
                    "e1000,mac=00:aa:00:00:00:01,id=vx0,netdev=vx0",
                    "-netdev",
                    f"vde,id=vx0,sock={RUN}/sw1.ctl",
                    "-device",
                    "rtl8139,mac=00:aa:00:00:00:02,id=vx1,netdev=vx1",
                    "-netdev",
                    "user,id=vx1",
                    "-device",
                    "virtio-net-pci,mac=00:aa:00:00:00:03,id=vx2,netdev=vx2",
                    "-netdev",
                    sock,
                ]
            else:
                cards = [
                    "-device",
                    "e1000,mac=00:aa:00:00:00:01,id=vx0",
                    "-device",
                    "rtl8139,mac=00:aa:00:00:00:02,id=vx1,netdev=vx1",
                    "-netdev",
                    "user,id=vx1",
                    "-device",
                    "virtio-net-pci,mac=00:aa:00:00:00:03,id=vx2",
                ]
                expected_warnings.append(
                    f"vm2: QEMU {prepared.qemu.version} can't join a VDE"
                    " switch: card 0, 2 unplugged; install a QEMU built with"
                    " VDE"
                )
            expected = (
                [prepared.qemu.path, "-machine", "type=pc,acpi=off"]
                + ["-accel", "kvm,kvm-shadow-mem=2097152", "-accel", "tcg"]
                + ["-cpu", "host", "-smp", "2", "-m", "512", "-boot", "d"]
                + ["-audiodev", "alsa,id=snd0"]
                + ["-device", "AC97,audiodev=snd0"]
                + ["-usb", "-snapshot", "-display", "sdl"]
                + ["-loadvm", "snap1"]
                + ["-kernel", "/boot/k", "-initrd", "/boot/i"]
                + ["-append", 'console=ttyS0 init="/bin/sh"']
                + ["-gdb", "tcp::1234", "-vnc", ":2", "-vga", "std"]
                + ["-device", "usb-host,vendorid=0x1d6b,productid=0x0002"]
                + ["-name", "vm2"]
                + cards
                + ["-cdrom", "/c.iso", "-rtc", "base=localtime,driftfix=slew"]
                + ["-k", "it"]
                + ["-serial", f"unix:{RUN}/vm2_serial,server=on,wait=off"]
                + machine_line("", "vm2")[9:]
            )
            self.assertEqual(argv, expected, target)
            self.assertEqual(warnings, expected_warnings, target)

    def test_few_options(self):
        vm = self.brick(
            "qemu",
            "vm",
            kernel="/boot/k",
            kernel_command_line="quiet",
            cdrom="device",
            cdrom_device="/dev/cdrom",
            clock_drift_fix=True,
            keyboard_layout="ita",
            headless=True,
            use_vnc=True,
            sdl_window=True,
            use_initrd=True,
            initrd="/boot/i",
        )
        argv, warnings = self.line(vm, prepared_qemu())
        self.assertEqual(argv[1:3], ["-smp", "1"])
        self.assertIn("-cdrom", argv)
        self.assertEqual(argv[argv.index("-cdrom") + 1], "/dev/cdrom")
        self.assertEqual(argv[argv.index("-rtc") + 1], "driftfix=slew")
        # no display at all, and no ramdisk without a kernel
        self.assertEqual(argv[argv.index("-display") + 1], "none")
        self.assertNotIn("sdl", argv)
        for option in ("-machine", "-accel", "-append", "-kernel", "-k"):
            self.assertNotIn(option, argv)
        for option in ("-vnc", "-initrd"):
            self.assertNotIn(option, argv)
        self.assertEqual(warnings, [])

    def test_disks(self):
        vm = self.brick("qemu", "vm")
        disks = (("hda", "/lab/vm_hda.cow"), ("hdc", "/images/c.qcow2"))
        argv, _ = self.line(vm, prepared_qemu(disks=disks))
        self.assertEqual(
            argv[5:9], ["-hda", "/lab/vm_hda.cow", "-hdc", "/images/c.qcow2"]
        )
        vm.update_config({"virtio_disks": True})
        argv, _ = self.line(vm, prepared_qemu(disks=disks))
        self.assertEqual(
            argv[5:9],
            ["-drive", "file=/lab/vm_hda.cow,if=virtio"]
            + ["-drive", "file=/images/c.qcow2,if=virtio"],
        )

    def test_unknown_machine_and_cpu(self):
        vm = self.brick(
            "qemu", "vm", machine_type="pc-q35-11.1", cpu_model="Zen9"
        )
        argv, warnings = self.line(vm, prepared_qemu("ubuntu-24.04"))
        self.assertNotIn("-machine", argv)
        self.assertNotIn("-cpu", argv)
        self.assertEqual(
            warnings,
            [
                "vm: QEMU 8.2.2 has no machine type pc-q35-11.1 (machine_type): the"
                " machine starts with the default one",
                "vm: QEMU 8.2.2 has no CPU model Zen9 (cpu_model): the machine"
                " starts with the default one",
            ],
        )

    def test_without_kvm(self):
        vm = self.brick("qemu", "vm", use_kvm=True)
        prepared = prepared_qemu(accelerators=frozenset(["tcg"]))
        argv, warnings = self.line(vm, prepared)
        self.assertNotIn("-accel", argv)
        self.assertEqual(
            warnings,
            ["vm: QEMU 10.0.13 has no KVM (use_kvm): the machine is emulated"],
        )
        vm.update_config({"use_kvm_shadow_memory": False})
        argv, _ = self.line(vm, prepared_qemu())
        self.assertEqual(argv[1:5], ["-accel", "kvm", "-accel", "tcg"])

    def test_without_sdl(self):
        vm = self.brick("qemu", "vm", sdl_window=True)
        prepared = prepared_qemu(displays=frozenset(["none", "curses"]))
        argv, warnings = self.line(vm, prepared)
        self.assertNotIn("sdl", argv)
        self.assertEqual(
            warnings,
            [
                "vm: QEMU 10.0.13 has no SDL window (sdl_window): install the"
                " qemu-system-gui package"
            ],
        )

    def test_acpi_off(self):
        vm = self.brick("qemu", "vm", acpi=False)
        argv, _ = self.line(vm, prepared_qemu())
        self.assertEqual(argv[1:3], ["-machine", "acpi=off"])
        # a machine without the property, on a QEMU with the old option
        prepared = attr.evolve(
            prepared_qemu("ubuntu-22.04"), machine_properties=frozenset()
        )
        argv, warnings = self.line(vm, prepared)
        self.assertEqual(argv[1], "-no-acpi")
        self.assertEqual(warnings, [])
        prepared = attr.evolve(prepared_qemu(), machine_properties=frozenset())
        argv, warnings = self.line(vm, prepared)
        self.assertNotIn("-no-acpi", argv)
        self.assertEqual(
            warnings, ["vm: QEMU 10.0.13 can't turn ACPI off here (acpi)"]
        )

    def test_sound(self):
        vm = self.brick("qemu", "vm", sound_card="sb16")
        argv, _ = self.line(vm, prepared_qemu(driver="pa"))
        self.assertEqual(
            argv[5:9],
            ["-audiodev", "pa,id=snd0", "-device", "sb16,audiodev=snd0"],
        )
        # QEMU 6.2 can't list its drivers: the one of the settings is taken
        argv, warnings = self.line(
            vm, prepared_qemu("ubuntu-22.04", driver="x")
        )
        self.assertEqual(argv[5:7], ["-audiodev", "x,id=snd0"])
        self.assertEqual(warnings, [])

    def test_pc_speaker(self):
        vm = self.brick("qemu", "vm", sound_card="pcspk", machine_type="q35")
        argv, _ = self.line(vm, prepared_qemu())
        self.assertEqual(
            argv[1:5],
            ["-machine", "type=q35,pcspk-audiodev=snd0", "-smp", "1"],
        )
        self.assertEqual(argv[7:9], ["-audiodev", "alsa,id=snd0"])

    def test_sound_left_out(self):
        vm = self.brick("qemu", "vm", sound_card="gus2")
        argv, warnings = self.line(vm, prepared_qemu())
        self.assertNotIn("-audiodev", argv)
        self.assertEqual(
            warnings,
            [
                "vm: QEMU 10.0.13 has no sound card gus2 (sound_card): the"
                " machine has none"
            ],
        )
        vm.update_config({"sound_card": "ac97"})
        argv, warnings = self.line(vm, prepared_qemu(driver="coreaudio"))
        self.assertNotIn("-audiodev", argv)
        self.assertEqual(
            warnings,
            [
                "vm: QEMU 10.0.13 has no audio driver coreaudio (audio_driver"
                " of the settings): the machine has no sound card"
            ],
        )

    def test_card_model(self):
        vm = self.brick("qemu", "vm")
        vm.add_plug(hostonly_sock, "00:aa:00:00:00:01", "ne3000")
        argv, warnings = self.line(vm, prepared_qemu())
        self.assertIn("rtl8139,mac=00:aa:00:00:00:01,id=vx0,netdev=vx0", argv)
        self.assertEqual(
            warnings,
            [
                "vm: QEMU 10.0.13 has no network card ne3000: card 0 is a rtl8139"
            ],
        )

    def test_card_on_the_user_network(self):
        vm = self.brick("qemu", "vm")
        plug = vm.add_plug(None, "00:aa:00:00:00:01", "e1000")
        plug.mode = "user"
        argv, _ = self.line(vm, prepared_qemu())
        index = argv.index("-netdev")
        self.assertEqual(argv[index + 1], "user,id=vx0")


class TestPrepare(CommandTestCase):

    def setUp(self):
        super().setUp()
        self.run = FakeRun()
        fake = Programs(self.run)
        self.patch(bricks, "programs", fake)
        self.patch(virtualmachine, "programs", fake)

    def test_vde(self):
        sw = self.factory.new_brick("switch", "sw")
        prepared = self.successResultOf(sw.prepare())
        self.assertEqual(
            prepared.vde.programs["vde_switch"],
            os.path.join(self.bin, "vde_switch"),
        )
        self.assertIsNone(prepared.qemu)

    def test_tunnel_key(self):
        listen = self.factory.new_brick("tunnellisten", "tl")
        listen.update_config({"password": "secret"})
        self.successResultOf(listen.prepare())
        path = os.path.join(self.factory.runtime_dir, "tl.key")
        self.assertEqual(listen.key_path(), path)
        with open(path, "rb") as fp:
            self.assertEqual(
                fp.read(), b"fc683cd9ed1990ca2ea10b84e5e6fba048c24929  -\n"
            )

    def test_resume(self):
        vm = self.factory.new_brick("qemu", "vm")
        self.assertEqual(self.successResultOf(vm.prepare()).resume, "")
        prepared = self.successResultOf(vm.prepare("virtualbricks"))
        self.assertEqual(prepared.resume, "virtualbricks")

    def test_machine(self):
        set_setting("audio_driver", "pipewire")
        self.factory.new_disk_image("debian", "/images/debian.qcow2")
        vm = self.factory.new_brick("qemu", "vm")
        vm.update_config({"hdb_image": "debian", "machine_type": "q35"})
        prepared = self.successResultOf(vm.prepare())
        self.assertEqual(
            prepared.qemu.path, os.path.join(self.bin, "qemu-system-i386")
        )
        self.assertIn("acpi", prepared.machine_properties)
        self.assertEqual(prepared.disks, (("hdb", "/images/debian.qcow2"),))
        self.assertEqual(prepared.audio_driver, "pipewire")
        asked = [args for _, args in self.run.calls]
        self.assertIn(("-machine", "q35,help"), asked)

    def test_unknown_machine(self):
        vm = self.factory.new_brick("qemu", "vm")
        vm.update_config({"machine_type": "pc-q35-11.1"})
        info = recorded_info("debian-13")
        self.run.answers[("-machine", f"{info.default_machine},help")] = (
            self.run.answers[("-machine", "pc,help")]
        )
        self.successResultOf(vm.prepare())
        asked = [args for _, args in self.run.calls]
        self.assertIn(("-machine", f"{info.default_machine},help"), asked)

    def test_missing_program(self):
        vm = self.factory.new_brick("qemu", "vm")
        vm.update_config({"qemu_program": "qemu-system-arm"})
        failure = self.failureResultOf(vm.prepare())
        failure.trap(ProgramError)
        self.assertEqual(str(failure.value), "qemu-system-arm isn't installed")
        os.remove(os.path.join(self.bin, "qemu-system-i386"))
        self.patch(os, "environ", dict(os.environ, PATH=self.bin))
        vm.update_config({"qemu_program": "qemu-system-i386"})
        failure = self.failureResultOf(vm.prepare())
        self.assertEqual(
            str(failure.value),
            "qemu-system-i386 (qemu-system-x86) isn't installed",
        )


class FakeReactor:

    def __init__(self):
        self.spawned = []

    def spawnProcess(self, protocol, executable, args, env):
        self.spawned.append((executable, args))


class TestStart(CommandTestCase):

    def setUp(self):
        super().setUp()
        self.patch(bricks, "programs", Programs(FakeRun()))
        self.reactor = FakeReactor()
        self.patch(bricks, "reactor", self.reactor)

    def netemu(self):
        sw1 = self.factory.new_brick("switch", "sw1")
        sw2 = self.factory.new_brick("switch", "sw2")
        netemu = self.factory.new_brick("netemu", "ne")
        netemu.connect(sw1.socks[0])
        netemu.connect(sw2.socks[0])
        # the switches run, and the emulator gets no commands
        sw1.proc = sw2.proc = object()
        netemu.update = lambda: None
        netemu.logger = FakeLogger()
        return netemu

    def test_spawn(self):
        netemu = self.netemu()
        netemu.poweron()
        [(executable, args)] = self.reactor.spawned
        self.assertEqual(executable, os.path.join(self.bin, "vde-netemu"))
        self.assertEqual(args[:2], [executable, "-v"])
        self.assertEqual(netemu.logger.levels(), ["info"])

    def test_warnings(self):
        os.remove(os.path.join(self.bin, "vde-netemu"))
        wirefilter = os.path.join(self.bin, "wirefilter")
        with open(wirefilter, "w") as fp:
            fp.write("#!/bin/sh\n")
        os.chmod(wirefilter, 0o755)
        self.patch(os, "environ", dict(os.environ, PATH=self.bin))
        netemu = self.netemu()
        netemu.poweron()
        [(executable, _)] = self.reactor.spawned
        self.assertEqual(executable, wirefilter)
        self.assertEqual(netemu.logger.levels(), ["warn", "info"])
        self.assertEqual(
            netemu.logger.formatted()[0],
            "ne: vde-netemu (vde-netemu) isn't installed: wirefilter runs in"
            " its place",
        )

    def test_sudo(self):
        self.patch(os, "geteuid", lambda: 1000)
        self.patch(bricks, "sudo_command", lambda args: ["sudo", "--"] + args)
        sw = self.factory.new_brick("switch", "sw")
        tap = self.factory.new_brick("tap", "tap0")
        tap.connect(sw.socks[0])
        sw.proc = object()
        tap.poweron()
        [(executable, args)] = self.reactor.spawned
        self.assertEqual(executable, "sudo")
        self.assertEqual(
            args,
            ["sudo", "--", os.path.join(self.bin, "vde_plug2tap")]
            + ["-s", sw.path(), "tap0"],
        )

    def test_missing_program(self):
        router = self.factory.new_brick("router", "r")
        failure = self.failureResultOf(router.poweron())
        failure.trap(ProgramError)
        self.assertEqual(self.reactor.spawned, [])

    def test_resume(self):
        self.patch(virtualmachine, "programs", bricks.programs)
        vm = self.factory.new_brick("qemu", "vm")
        locks = []
        vm.acquire = lambda: locks.append("acquire")
        started = vm.poweron(resume="virtualbricks")
        [(_, args)] = self.reactor.spawned
        self.assertEqual(args[args.index("-loadvm") + 1], "virtualbricks")
        # running already: nothing more starts, and nothing is locked again
        self.assertIs(self.successResultOf(vm.poweron()), vm)
        self.assertNoResult(started)
        self.assertEqual(len(self.reactor.spawned), 1)
        self.assertEqual(locks, [])

    def test_machine_not_configured(self):
        vm = self.factory.new_brick("qemu", "vm")
        vm.add_plug(None, "52:54:00:00:00:01", "e1000")
        failure = self.failureResultOf(vm.poweron())
        failure.trap(errors.BadConfigError)
        self.assertEqual(self.reactor.spawned, [])

    def test_spawn_a_command(self):
        sw = self.factory.new_brick("switch", "sw")
        sw.logger = FakeLogger()
        command = Command("/usr/bin/vde_switch")
        command.option("-n", 8)
        command.warn("sw: left out")
        sw.spawn(command)
        self.assertEqual(
            self.reactor.spawned,
            [("/usr/bin/vde_switch", ["/usr/bin/vde_switch", "-n", "8"])],
        )
        self.assertEqual(
            sw.logger.formatted(),
            ["sw: left out", "Starting: /usr/bin/vde_switch -n 8"],
        )
        self.assertIsNotNone(sw.proc)
