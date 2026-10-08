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

import os

from twisted.trial import unittest

from virtualbricks import locations
from virtualbricks.bricks.eventaction import (
    ConsoleAction,
    EventAction,
    ShellAction,
)
from virtualbricks.config.projectfile import DEFAULT_MODEL
from virtualbricks.config.projectfile import FORMAT as PROJECT_FORMAT
from virtualbricks.config.projectfile import describe_action
from virtualbricks.config.settings import (
    ProjectSettings,
)
from virtualbricks.config.schema import Bool, Float, Int, Mac, Str, dump_record
from virtualbricks.config.report import Report
from virtualbricks.migrate import convert
from virtualbricks.migrate.convert import (
    MigrationError,
    convert_command,
    convert_project,
    convert_settings,
    convert_value,
)
from virtualbricks.migrate.legacy import parse_project
from virtualbricks.tests import isolate, reset_settings
from virtualbricks.tests.migrate.fixtures import (
    CONFIG1,
    HOSTONLY_CONFIG,
    OLD_FORMAT,
    PROJECT,
    WAN,
)
from virtualbricks.bricks.virtualmachine import UsbDevice, UsbDeviceKind


def messages(report, level=None):
    return [str(m) for m in report if level is None or m.level == level]


class TestConvertSettings(unittest.TestCase):

    def setUp(self):
        self.root = isolate(self)
        self.bin = os.path.join(self.root, "bin")
        os.makedirs(self.bin)
        self.program = os.path.join(self.bin, "program")
        with open(self.program, "w"):
            pass

    def convert(self, **options):
        """Convert options that point at programs of this machine."""

        values = {
            "term": self.program,
            "qemupath": self.bin,
            "vdepath": self.bin,
        }
        values.update(options)
        lines = {
            key: (value, lineno)
            for lineno, (key, value) in enumerate(values.items(), 1)
        }
        report = Report()
        app, project, current = convert_settings(lines, "vb.conf", report)
        return app, project, current, report

    def test_values(self):
        app, project, current, report = self.convert(
            femaleplugs="True",
            cowfmt="qcow2",
            workspace="/srv/vb",
            current_project="lab",
        )
        # the format of private copies, the one they always have now
        self.assertEqual(len(report), 0)
        self.assertEqual(current, "lab")
        # the settings of the application, and of the migrated projects
        self.assertEqual(app.workspace, "/srv/vb")
        self.assertEqual(app.terminal, self.program)
        self.assertIs(project.allow_female_plugs, True)
        self.assertEqual(project.qemu_path, self.bin)

    def test_private_copies_are_qcow2(self):
        _, _, _, report = self.convert(cowfmt="qcow")
        self.assertEqual(
            messages(report),
            [
                "vb.conf:4: cowfmt: private copies are always qcow2 now, dropped"
            ],
        )
        self.assertEqual(report.warnings, 0)

    def test_defaults(self):
        _, _, current, report = self.convert(current_project="")
        self.assertEqual(current, locations.DEFAULT_PROJECT)

    def test_dropped_and_unknown(self):
        dropped = ("alt-term", "cdroms", "kvm", "python", "sudo")
        options = {key: "x" for key in dropped}
        options["color"] = "red"
        _, _, _, report = self.convert(**options)
        self.assertEqual(
            messages(report),
            [
                "vb.conf:4: alt-term: not used any more, dropped",
                "vb.conf:5: cdroms: not used any more, dropped",
                "vb.conf:6: kvm: not used any more, dropped",
                "vb.conf:7: python: not used any more, dropped",
                "vb.conf:8: sudo: not used any more, dropped",
                "vb.conf:9: color: unknown setting, dropped",
            ],
        )
        self.assertEqual(report.warnings, 1)

    def test_invalid_values(self):
        app, project, _, report = self.convert(ksm="maybe")
        self.assertEqual(
            messages(report),
            [
                'vb.conf:4: ksm: "maybe" is not true or false, using the '
                "default false",
            ],
        )
        self.assertIs(app.kernel_samepage_merging, False)

    def test_programs_not_on_this_machine(self):
        missing = os.path.join(self.root, "missing")
        _, _, _, report = self.convert(
            term=missing, qemupath=missing, vdepath="bin"
        )
        self.assertEqual(
            messages(report),
            [
                f"vb.conf:1: term: {missing} doesn't exist on this machine, kept",
                f"vb.conf:2: qemupath: {missing} doesn't exist on this machine, "
                "kept",
            ],
        )

    def test_a_default_is_checked_too(self):
        lines = {"qemupath": (self.bin, 1)}
        report = Report()
        app, project, _ = convert_settings(lines, "vb.conf", report)
        app.terminal = os.path.join(self.root, "missing")
        report = Report()
        convert._check_programs(app, project, lines, "vb.conf", report)
        self.assertEqual(
            [m.where for m in report if "term:" in m.text], ["vb.conf"]
        )


class TestConvertValue(unittest.TestCase):

    def test_bool(self):
        self.assertIs(convert_value(Bool(), "*"), True)
        self.assertIs(convert_value(Bool(), ""), False)

    def test_numbers(self):
        self.assertEqual(convert_value(Int(), " 3 "), 3)
        self.assertEqual(convert_value(Float(), "0.5"), 0.5)
        self.assertIsInstance(convert_value(Float(), "2"), float)
        error = self.assertRaises(ValueError, convert_value, Int(), "x")
        self.assertEqual(str(error), '"x" is not an integer')
        error = self.assertRaises(ValueError, convert_value, Float(), "")
        self.assertEqual(str(error), '"" is not a number')

    def test_text(self):
        self.assertEqual(convert_value(Str(), " a "), " a ")

    def test_event_actions(self):
        kind = EventAction()
        # a command of the old console, which commands() reads later
        self.assertEqual(
            convert._convert_item(kind, "add sw1 on"),
            ConsoleAction("sw1 on"),
        )
        self.assertEqual(
            convert._convert_item(kind, "addsh logger hi"),
            ShellAction("logger hi"),
        )
        error = self.assertRaises(
            ValueError, convert._convert_item, kind, "rm -rf"
        )
        self.assertEqual(str(error), '"rm -rf" is not an event action')

    def test_usb_devices(self):
        kind = UsbDeviceKind()
        self.assertEqual(
            convert._convert_item(kind, "1d6b:0002"),
            UsbDevice("1d6b:0002", ""),
        )
        error = self.assertRaises(
            ValueError, convert._convert_item, kind, "hub"
        )
        self.assertEqual(str(error), '"hub" is not a USB id')

    def test_other_items(self):
        self.assertEqual(convert._convert_item(Str(), "a"), "a")


class ConvertTestCase(unittest.TestCase):

    def setUp(self):
        self.root = isolate(self)
        reset_settings(self)
        self.directory = os.path.join(self.root, "project")
        os.makedirs(self.directory)

    def convert(self, text):
        report = Report()
        project = parse_project(text, ".project", report)
        data, count = convert_project(
            project, ProjectSettings(), report, self.directory
        )
        return data, count, report

    def image_file(self, name):
        path = os.path.join(self.directory, name)
        with open(path, "w"):
            pass
        return path


class TestFixtures(ConvertTestCase):

    def test_config1(self):
        data, count, report = self.convert(CONFIG1)
        self.assertEqual(count, 3)
        self.assertEqual(data["format"], PROJECT_FORMAT)
        self.assertEqual(data["settings"], dump_record(ProjectSettings()))
        self.assertEqual(
            data["images"],
            {
                "martin": {
                    "path": "/vimages/vtatpa.martin.qcow2",
                    "description": "",
                }
            },
        )
        sender = data["bricks"]["sender"]
        self.assertEqual(sender["type"], "qemu")
        self.assertEqual(
            sender["disks"]["hda"], {"image": "martin", "private": True}
        )
        self.assertIs(sender["use_kvm"], True)
        self.assertIs(sender["clock_drift_fix"], True)
        self.assertEqual(
            sender["nics"],
            [
                {
                    "kind": "plug",
                    "connect": "sw1",
                    "model": "rtl8139",
                    "mac": "00:aa:79:71:be:61",
                }
            ],
        )
        self.assertEqual(data["bricks"]["wf"]["type"], "netemu")
        self.assertEqual(data["bricks"]["wf"]["endpoints"], ["", ""])
        self.assertEqual(data["bricks"]["sw1"]["type"], "switch")
        self.assertEqual(
            messages(report),
            [
                ".project:2: [Image:martin] /vimages/vtatpa.martin.qcow2 not "
                "found, kept in the library",
                ".project:8: [Qemu:sender] name: it repeats the brick name, "
                "dropped",
                ".project:12: [Wirefilter:wf] became netemu",
            ],
        )

    def test_old_format(self):
        data, count, report = self.convert(OLD_FORMAT)
        self.assertEqual(count, 2)
        self.assertEqual(list(data["images"]), ["vtatpa.qcow2"])
        vm = data["bricks"]["test1"]
        self.assertEqual(
            vm["disks"]["hda"], {"image": "vtatpa.qcow2", "private": True}
        )
        self.assertEqual(vm["disks"]["hdb"], {"image": "", "private": False})
        self.assertEqual(
            (
                vm["memory"],
                vm["cpus"],
                vm["gdb_port"],
                vm["vnc_display"],
                vm["kvm_shadow_memory"],
            ),
            (64, 1, 1234, 1, 1),
        )
        self.assertEqual(
            (vm["qemu_program"], vm["keyboard_layout"]),
            ("qemu-system-i386", "it"),
        )
        self.assertIs(vm["forget_disk_changes"], True)
        self.assertIs(vm["headless"], False)
        self.assertEqual(vm["usb_devices"], [])
        self.assertEqual(vm["nics"], [])
        wrapper = data["bricks"]["sw1"]
        self.assertEqual(wrapper["type"], "switchwrapper")
        self.assertEqual(wrapper["socket_path"], "/var/run/switch/sck")
        self.assertEqual(
            messages(report, "info"),
            [
                ".project:2: [Project:/home/user/.virtualbricks.vbl] older "
                "project metadata, dropped",
                ".project:4: [DiskImage:vtatpa.qcow2] became an image",
                ".project:8: [Qemu:test1] loadvm: a machine resumes when it's "
                "started so, not by a key, dropped",
                ".project:18: [Qemu:test1] portrait: QEMU 9 and later have no "
                "such option, dropped",
                ".project:55: [Qemu:test1] name: it repeats the brick name, "
                "dropped",
                ".project:62: [SwitchWrapper:sw1] numports: a switch wrapper "
                "has no ports of its own, dropped",
            ],
        )
        self.assertEqual(report.warnings, 1)

    def test_project(self):
        data, count, report = self.convert(PROJECT)
        self.assertEqual(count, 1)
        self.assertEqual(
            data["images"]["test_qcow2.qcow2"]["path"],
            "/images/test qcow2.qcow2",
        )
        vm = data["bricks"]["test"]
        self.assertEqual(vm["disks"]["hda"]["image"], "vtatpa.martin.qcow2")
        self.assertIs(vm["virtio_disks"], True)
        self.assertIn(
            '.project:14: link of "sender", which does not exist, dropped',
            messages(report),
        )

    def test_hostonly(self):
        data, _, report = self.convert(HOSTONLY_CONFIG)
        self.assertEqual(
            data["bricks"]["vm"]["nics"],
            [
                {
                    "kind": "hostonly",
                    "model": "rtl8139",
                    "mac": "00:11:22:33:44:55",
                }
            ],
        )
        self.assertEqual(report.warnings, 0)

    def test_netemu_with_states(self):
        data, count, report = self.convert(WAN)
        self.assertEqual(count, 3)
        wan = data["bricks"]["wan"]
        self.assertEqual(wan["transition_period"], 250)
        self.assertEqual(wan["transitions"], [[0.0, 0.2], [0.5, 0.0]])
        self.assertEqual(wan["endpoints"], ["", "sw2"])
        first, second = wan["states"]
        self.assertEqual((first["name"], first["delay"]), ("default name", 10))
        self.assertIs(first["bandwidth_symmetric"], False)
        self.assertEqual(
            (second["name"], second["delay"], second["loss"]),
            ("congested", 200, 2.5),
        )
        self.assertIs(second["bandwidth_symmetric"], True)
        self.assertEqual(data["bricks"]["sw2"]["ports"], 32)
        self.assertEqual(
            data["events"]["boot"],
            {
                "icon": "",
                "delay": 3,
                "actions": [
                    {"kind": "start", "target": "sw1"},
                    {"kind": "shell", "command": "logger hi"},
                ],
            },
        )
        self.assertEqual(
            messages(report),
            [
                ".project:20: [Switch:sw2] numports: 500 is outside 1–128, "
                "using the default 32",
                ".project:23: [Event:boot] actions: \"__import__('os')."
                "system('id')\" is not an event action, dropped",
                ".project:22: [Event:boot] 'sw1 on' is now start sw1",
            ],
        )


class TestSections(ConvertTestCase):

    def test_defined_twice(self):
        for text in (
            "[Switch:sw]\n[Tap:sw]\n",
            "[Image:a]\npath=/a\n[DiskImage:a]\npath=/b\n",
            "[Event:e]\n[Event:e]\n",
        ):
            error = self.assertRaises(MigrationError, self.convert, text)
            self.assertIn("defined twice (first at line 1)", str(error))

    def test_same_name_of_different_kinds(self):
        data, _, _ = self.convert(
            "[Image:x]\npath=/x\n[Event:x]\n[Switch:x]\n"
        )
        self.assertEqual(
            (list(data["images"]), list(data["events"]), list(data["bricks"])),
            (["x"], ["x"], ["x"]),
        )

    def test_unknown_type(self):
        data, _, report = self.convert("[Hub:h]\n")
        self.assertEqual(
            messages(report), [".project:1: [Hub:h] unknown type, dropped"]
        )
        # empty tables are left out
        self.assertEqual(list(data), ["format", "settings"])

    def test_invalid_names(self):
        data, count, report = self.convert("[Switch:1sw]\n[Event:2ev]\n")
        self.assertEqual(count, 0)
        self.assertEqual(
            messages(report),
            [
                ".project:1: [Switch:1sw] A name starts with a letter, dropped",
                ".project:2: [Event:2ev] A name starts with a letter, dropped",
            ],
        )

    def test_keys(self):
        text = (
            "[Switch:sw]\ncolor=red\nnumports=x\nhub=*\n[Router:r]\nname=r\n"
        )
        data, _, report = self.convert(text)
        self.assertIs(data["bricks"]["sw"]["hub_mode"], True)
        self.assertEqual(data["bricks"]["sw"]["ports"], 32)
        self.assertEqual(
            messages(report),
            [
                ".project:2: [Switch:sw] color: unknown, dropped",
                '.project:3: [Switch:sw] numports: "x" is not an integer, using '
                "the default 32",
                ".project:6: [Router:r] name: it repeats the brick name, dropped",
            ],
        )

    def test_lists(self):
        text = (
            "[Qemu:vm]\nusbdevlist=['1d6b:0002', 'hub']\n"
            "[Qemu:vm2]\nusbdevlist=junk\n"
        )
        data, _, report = self.convert(text)
        self.assertEqual(
            data["bricks"]["vm"]["usb_devices"],
            [{"id": "1d6b:0002", "description": ""}],
        )
        self.assertEqual(data["bricks"]["vm2"]["usb_devices"], [])
        self.assertEqual(
            messages(report),
            [
                '.project:2: [Qemu:vm] usbdevlist: "hub" is not a USB id, dropped',
                ".project:4: [Qemu:vm2] usbdevlist: 'junk' is not a list, using "
                "the default []",
            ],
        )


class TestImages(ConvertTestCase):

    def test_relative_path_and_description(self):
        path = self.image_file("disk.qcow2")
        text = "[Image:disk]\npath=disk.qcow2\ndescription=a<nl>b\nsize=1\n"
        data, _, report = self.convert(text)
        self.assertEqual(
            data["images"]["disk"], {"path": path, "description": "a\nb"}
        )
        self.assertEqual(
            messages(report),
            [".project:4: [Image:disk] size: unknown, dropped"],
        )

    def test_no_path(self):
        data, _, report = self.convert("[Image:disk]\ndescription=x\n")
        self.assertNotIn("images", data)
        self.assertEqual(
            messages(report), [".project:1: [Image:disk] has no path, dropped"]
        )

    def test_invalid_name(self):
        path = self.image_file("disk.qcow2")
        data, _, report = self.convert(f"[Image:1disk]\npath={path}\n")
        self.assertNotIn("images", data)
        self.assertEqual(report.warnings, 1)

    def test_same_file_twice(self):
        path = self.image_file("disk.qcow2")
        text = (
            f"[Image:a]\npath={path}\n[Image:b]\npath={path}\n"
            "[Qemu:vm]\nhda=b\nhdb=a\n"
        )
        data, _, report = self.convert(text)
        self.assertEqual(list(data["images"]), ["a"])
        disks = data["bricks"]["vm"]["disks"]
        self.assertEqual(
            (disks["hda"]["image"], disks["hdb"]["image"]), ("a", "a")
        )
        self.assertEqual(
            messages(report),
            [
                ".project:3: [Image:b] is the same file as a; its disks now use a"
            ],
        )


class TestNetemu(ConvertTestCase):

    def test_errors(self):
        text = (
            "[Netemu:wan]\n"
            "states=0\n"
            "transperiod=x\n"
            "states=2\n"
            "state5.delay=1\n"
            "state0.probability[0]=0.1\n"
            "state0.probability[3]=0.1\n"
            "state0.probability[1]=x\n"
            "state1.delay=x\n"
            "state1.color=red\n"
        )
        data, _, report = self.convert(text)
        wan = data["bricks"]["wan"]
        self.assertEqual(len(wan["states"]), 2)
        self.assertEqual(wan["transition_period"], 100)
        self.assertEqual(wan["transitions"], [[0.0, 0.0], [0.0, 0.0]])
        self.assertEqual(
            messages(report),
            [
                ".project:2: [Netemu:wan] states: '0' is not a positive integer, "
                "ignored",
                ".project:3: [Netemu:wan] transperiod: 'x' is not a positive "
                "integer, ignored",
                ".project:5: [Netemu:wan] state5.delay: no such state, ignored",
                ".project:6: [Netemu:wan] state0.probability[0]: no such "
                "transition, ignored",
                ".project:7: [Netemu:wan] state0.probability[3]: no such "
                "transition, ignored",
                ".project:8: [Netemu:wan] state0.probability[1]: 'x' is not a "
                "number, ignored",
                '.project:9: [Netemu:wan] state 1 delay: "x" is not an integer, '
                "using the default 0",
                ".project:10: [Netemu:wan] state 1 color: unknown, dropped",
            ],
        )

    def test_one_state_without_a_count(self):
        # the old versions wrote one state as the keys of the brick
        data, _, report = self.convert("[Netemu:wan]\ndelay=10\n")
        self.assertEqual(len(report), 0)
        wan = data["bricks"]["wan"]
        self.assertEqual(len(wan["states"]), 1)
        self.assertEqual(wan["states"][0]["delay"], 10)
        self.assertEqual(wan["transitions"], [[0.0]])

    def test_one_is_a_positive_integer(self):
        text = "[Netemu:wan]\nstates=1\ntransperiod=1\n"
        data, _, report = self.convert(text)
        self.assertEqual(len(report), 0)
        wan = data["bricks"]["wan"]
        self.assertEqual(len(wan["states"]), 1)
        self.assertEqual(wan["transition_period"], 1)

    def test_events_of_every_state(self):
        text = "[Event:on]\n[Netemu:wan]\npon_vbevent=on\nstates=3\n"
        data, _, report = self.convert(text)
        self.assertEqual(len(report), 0)
        wan = data["bricks"]["wan"]
        self.assertEqual(wan["on_start"], "on")
        self.assertEqual(len(wan["states"]), 3)
        factory = convert._Converter(
            parse_project(text, "f", Report()),
            Report(),
            self.directory,
        )
        factory.convert(ProjectSettings())
        brick = factory.factory.get_brick("wan")
        self.assertEqual(
            [state.on_start for state in brick.markov_manager.states],
            ["on", "on", "on"],
        )


class TestConnections(ConvertTestCase):

    def test_socket_cards(self):
        text = (
            "[Qemu:vm]\n[Qemu:vm2]\n[Switch:sw]\n"
            "sock|vm|vm_sock_eth0|e1000|00:11:22:33:44:55\n"
            "sock|vm|lan||00:11:22:33:44:56\n"
            "sock|vm|vm_bad name|e1000|00:11:22:33:44:57\n"
            "sock|sw|sw_x|e1000|00:11:22:33:44:58\n"
            "sock|nobody|x|e1000|00:11:22:33:44:59\n"
            "link|vm2|vm_lan|e1000|00:11:22:33:44:60\n"
        )
        data, _, report = self.convert(text)
        self.assertEqual(
            data["bricks"]["vm"]["nics"],
            [
                {
                    "kind": "socket",
                    "name": "sock_eth0",
                    "model": "e1000",
                    "mac": "00:11:22:33:44:55",
                },
                {
                    "kind": "socket",
                    "name": "lan",
                    "model": DEFAULT_MODEL,
                    "mac": "00:11:22:33:44:56",
                },
                {
                    "kind": "socket",
                    "name": "sock_eth2",
                    "model": "e1000",
                    "mac": "00:11:22:33:44:57",
                },
            ],
        )
        self.assertEqual(data["bricks"]["vm2"]["nics"][0]["connect"], "vm:lan")
        self.assertEqual(
            messages(report),
            [
                '.project:6: "vm_bad name" is not a socket name, using a default',
                '.project:7: socket card of "sw", which is not a virtual '
                "machine, dropped",
                '.project:8: socket card of "nobody", which is not a virtual '
                "machine, dropped",
            ],
        )

    def test_the_model_of_a_plug(self):
        text = "[Qemu:vm]\nlink|vm||e1000|00:11:22:33:44:55\n"
        data, _, report = self.convert(text)
        self.assertEqual(len(report), 0)
        self.assertEqual(data["bricks"]["vm"]["nics"][0]["model"], "e1000")

    def test_macs(self):
        text = "[Qemu:vm]\nsock|vm|a||\nsock|vm|b||00:11\n"
        data, _, report = self.convert(text)
        macs = [nic["mac"] for nic in data["bricks"]["vm"]["nics"]]
        for mac in macs:
            Mac().check(mac)
        self.assertEqual(
            messages(report),
            [
                f'.project:2: "" is not a MAC address, using {macs[0]}',
                f'.project:3: "00:11" is not a MAC address, using {macs[1]}',
            ],
        )

    def test_plugs(self):
        text = (
            "[Qemu:vm]\n[Switch:sw]\n[Tap:tap]\n[Wire:w]\n"
            "link|vm|nowhere||00:11:22:33:44:55\n"
            "link|tap|sw_port||\n"
            "link|w|sw_port||\n"
            "link|w|||\n"
            "link|w|sw_port||\n"
            "link|sw|sw_port||\n"
        )
        data, _, report = self.convert(text)
        self.assertEqual(
            data["bricks"]["vm"]["nics"],
            [
                {
                    "kind": "plug",
                    "connect": "",
                    "model": DEFAULT_MODEL,
                    "mac": "00:11:22:33:44:55",
                }
            ],
        )
        self.assertEqual(data["bricks"]["tap"]["connect"], "sw")
        self.assertEqual(data["bricks"]["w"]["endpoints"], ["sw", ""])
        self.assertEqual(
            messages(report),
            [
                '.project:5: no socket "nowhere", left unconnected',
                '.project:9: "w" has no plug left, link dropped',
                '.project:10: "sw" has no plug left, link dropped',
            ],
        )


class TestNames(ConvertTestCase):
    """The keys of 2.1 get the names of today."""

    def brick(self, text, name):
        data, _, report = self.convert(text)
        return data["bricks"][name], report

    def test_every_type(self):
        text = """
[Event:boot]
delay=1
actions=["add sw1 on"]

[Switch:sw1]
numports=8
hub=*
fstp=*
pon_vbevent=boot
poff_vbevent=boot

[SwitchWrapper:wr]
path=/run/vde/lab.ctl

[Tap:tap0]
mode=manual
ip=10.0.0.2
nm=255.255.0.0
gw=10.0.0.1

[Capture:cap]
iface=eth0

[TunnelListen:tl]
port=7700
password=secret

[TunnelConnect:tc]
host=lab.example.org
port=7701
localport=10001
password=secret
"""
        data, _, report = self.convert(text)
        bricks = data["bricks"]
        sw = bricks["sw1"]
        self.assertEqual(
            (sw["ports"], sw["hub_mode"], sw["fast_spanning_tree"]),
            (8, True, True),
        )
        self.assertEqual((sw["on_start"], sw["on_stop"]), ("boot", "boot"))
        self.assertEqual(bricks["wr"]["socket_path"], "/run/vde/lab.ctl")
        tap = bricks["tap0"]
        self.assertEqual(
            [tap[key] for key in ("address_mode", "ip_address", "netmask")],
            ["manual", "10.0.0.2", "255.255.0.0"],
        )
        self.assertEqual(tap["gateway"], "10.0.0.1")
        self.assertEqual(bricks["cap"]["interface"], "eth0")
        self.assertEqual(bricks["tl"]["listen_port"], 7700)
        tc = bricks["tc"]
        self.assertEqual(
            (tc["server_host"], tc["server_port"], tc["local_port"]),
            ("lab.example.org", 7701, 10001),
        )
        self.assertEqual(tc["password"], "secret")
        self.assertEqual(report.warnings, 0)

    def test_machine(self):
        vm, report = self.brick(
            """
[Qemu:vm]
argv0=qemu-system-x86_64
machine=q35
cpu=host
kvm=*
smp=2
ram=512
kvmsm=*
kvmsmem=16
boot=d
snapshot=*
use_virtio=*
novga=*
vga=*
vnc=*
vncN=3
sdl=*
soundhw=ac97
usbmode=*
keyboard=it
rtc=*
tdf=*
serial=*
kernelenbl=*
kernel=/boot/k
initrdenbl=*
initrd=/boot/i
kopt=quiet
gdb=*
gdbport=4321
basehdb=deb
""",
            "vm",
        )
        expected = {
            "qemu_program": "qemu-system-x86_64",
            "machine_type": "q35",
            "cpu_model": "host",
            "cpus": 2,
            "memory": 512,
            "kvm_shadow_memory": 16,
            "boot_order": "d",
            "vnc_display": 3,
            "sound_card": "ac97",
            "keyboard_layout": "it",
            "kernel": "/boot/k",
            "initrd": "/boot/i",
            "kernel_command_line": "quiet",
            "gdb_port": 4321,
        }
        self.assertEqual({key: vm[key] for key in expected}, expected)
        for key in (
            "use_kvm",
            "use_kvm_shadow_memory",
            "forget_disk_changes",
            "virtio_disks",
            "headless",
            "standard_vga",
            "use_vnc",
            "sdl_window",
            "use_usb",
            "clock_local_time",
            "clock_drift_fix",
            "serial_socket",
            "use_kernel",
            "use_initrd",
            "use_gdb",
        ):
            self.assertIs(vm[key], True, key)
        self.assertEqual(vm["disks"]["hdb"]["image"], "deb")

    def test_cdrom(self):
        cases = [
            ("cdromen=*\ndeviceen=*", "image"),
            ("cdromen=\ndeviceen=*", "device"),
            ("cdromen=\ndeviceen=", "none"),
            ("", "none"),
        ]
        for switches, choice in cases:
            vm, _ = self.brick(
                f"[Qemu:vm]\n{switches}\ncdrom=/c.iso\ndevice=/dev/sr0\n", "vm"
            )
            self.assertEqual(vm["cdrom"], choice, switches)
            self.assertEqual(vm["cdrom_image"], "/c.iso")
            self.assertEqual(vm["cdrom_device"], "/dev/sr0")

    def test_acpi(self):
        vm, _ = self.brick("[Qemu:vm]\nnoacpi=*\n", "vm")
        self.assertIs(vm["acpi"], False)
        vm, _ = self.brick("[Qemu:vm]\nnoacpi=\n", "vm")
        self.assertIs(vm["acpi"], True)

    def test_empty_program(self):
        vm, report = self.brick("[Qemu:vm]\nargv0=\n", "vm")
        self.assertEqual(vm["qemu_program"], "qemu-system-x86_64")
        self.assertIn(
            ".project:2: [Qemu:vm] argv0: empty, which ran "
            "qemu-system-x86_64",
            messages(report, "info"),
        )
        vm, _ = self.brick("[Qemu:vm]\n", "vm")
        self.assertEqual(vm["qemu_program"], "qemu-system-i386")

    def test_dropped(self):
        vm, report = self.brick(
            "[Qemu:vm]\nstdout=x\nportrait=*\nloadvm=snap\n", "vm"
        )
        for key in ("stdout", "portrait", "loadvm"):
            self.assertNotIn(key, vm)
        self.assertEqual(len(messages(report, "info")), 3)
        self.assertEqual(report.warnings, 0)

    def test_netemu_states(self):
        text = """
[Netemu:wan]
states=2
transperiod=50
state0.bandwidthsymm=
state0.bandwidthr=500
state0.chanbufsize=100
state1.losssymm=
state1.lossr=2.5
state1.delaysymm=
state1.delayr=20
state1.chanbufsizesymm=
state1.chanbufsizer=200
"""
        data, _, report = self.convert(text)
        wan = data["bricks"]["wan"]
        self.assertEqual(wan["transition_period"], 50)
        first, second = wan["states"]
        self.assertIs(first["bandwidth_symmetric"], False)
        self.assertEqual(first["bandwidth_right_to_left"], 500)
        self.assertEqual(first["buffer_size"], 100)
        self.assertIs(second["loss_symmetric"], False)
        self.assertEqual(second["loss_right_to_left"], 2.5)
        self.assertIs(second["delay_symmetric"], False)
        self.assertEqual(second["delay_right_to_left"], 20)
        self.assertIs(second["buffer_size_symmetric"], False)
        self.assertEqual(second["buffer_size_right_to_left"], 200)
        self.assertEqual(report.warnings, 0)

    def test_commands_of_the_events(self):
        text = """
[Event:resize]
actions=["add vm config ram=512 kvm=* noacpi=* cdromen=* stdout=x", \
"add sw config numports=8", "add vm on", "add vm config nope=1", \
"add ghost config ram=1", "addsh vm config ram=512"]

[Qemu:vm]

[Switch:sw]
"""
        data, _, report = self.convert(text)
        self.assertEqual(
            [
                describe_action(action)
                for action in data["events"]["resize"]["actions"]
            ],
            [
                'console "brick set vm memory=512 use_kvm=true acpi=false'
                ' cdrom=image"',
                'console "brick set sw ports=8"',
                "start vm",
                'console "brick set vm nope=1"',
                'console "brick set ghost ram=1"',
                'shell "vm config ram=512"',
            ],
        )
        infos = [m for m in messages(report, "info") if "[Event:resize]" in m]
        self.assertEqual(len(infos), 5)


class TestConvertCommand(unittest.TestCase):

    def setUp(self):
        from twisted.internet import defer

        from virtualbricks.brickfactory import BrickFactory

        self.factory = BrickFactory(defer.Deferred())
        self.factory.new_brick("qemu", "vm")

    def test_values(self):
        cases = {
            "vm config deviceen=*": "vm config cdrom=device",
            "vm config cdromen=": "vm config cdrom=none",
            "vm config noacpi=": "vm config acpi=true",
            "vm config argv0=": "vm config qemu_program=qemu-system-x86_64",
            "vm config argv0=qemu-system-arm": (
                "vm config qemu_program=qemu-system-arm"
            ),
            "vm config snapshot=": "vm config forget_disk_changes=false",
            "vm config pon_vbevent=boot": "vm config on_start=boot",
            "vm  config   ram=64": "vm config memory=64",
            "vm config": "vm config",
            "vm config verbose": "vm config verbose",
        }
        for old, new in cases.items():
            self.assertEqual(convert_command(self.factory, old), new, old)
