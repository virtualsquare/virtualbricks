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

import os

from twisted.trial import unittest

from virtualbricks import console, locations
from virtualbricks.config import Report, projectfile, schema, settings
from virtualbricks.events import EventAction
from virtualbricks.migrate import convert, legacy
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
            "sudo": self.program,
            "qemupath": self.bin,
            "vdepath": self.bin,
        }
        values.update(options)
        lines = {
            key: (value, lineno)
            for lineno, (key, value) in enumerate(values.items(), 1)
        }
        report = Report()
        app, current = convert.convert_settings(lines, "vb.conf", report)
        return app, current, report

    def test_values(self):
        app, current, report = self.convert(
            femaleplugs="True",
            cowfmt="qcow",
            workspace="/srv/vb",
            current_project="lab",
        )
        self.assertEqual(len(report), 0)
        self.assertEqual(current, "lab")
        self.assertIs(app.femaleplugs, True)
        self.assertEqual(app.cowfmt, "qcow")
        self.assertEqual(app.workspace, "/srv/vb")
        self.assertEqual(app.term, self.program)

    def test_defaults(self):
        app, current, report = self.convert(current_project="")
        self.assertEqual(current, locations.DEFAULT_PROJECT)
        self.assertEqual(app.cowfmt, "qcow2")

    def test_dropped_and_unknown(self):
        options = {key: "x" for key in ("alt-term", "cdroms", "kvm", "python")}
        options["color"] = "red"
        _, _, report = self.convert(**options)
        self.assertEqual(
            messages(report),
            [
                "vb.conf:5: alt-term: not used any more, dropped",
                "vb.conf:6: cdroms: not used any more, dropped",
                "vb.conf:7: kvm: not used any more, dropped",
                "vb.conf:8: python: not used any more, dropped",
                "vb.conf:9: color: unknown setting, dropped",
            ],
        )
        self.assertEqual(report.warnings, 1)

    def test_invalid_values(self):
        app, _, report = self.convert(cowfmt="qed", ksm="maybe")
        self.assertEqual(
            messages(report),
            [
                'vb.conf:5: cowfmt: "qed" is not one of cow, qcow, qcow2, '
                'using the default "qcow2"',
                'vb.conf:6: ksm: "maybe" is not true or false, using the '
                "default false",
            ],
        )
        self.assertEqual(app.cowfmt, "qcow2")

    def test_programs_not_on_this_machine(self):
        missing = os.path.join(self.root, "missing")
        _, _, report = self.convert(
            term=missing, sudo="", qemupath=missing, vdepath="bin"
        )
        self.assertEqual(
            messages(report),
            [
                f"vb.conf:1: term: {missing} doesn't exist on this machine, kept",
                f"vb.conf:3: qemupath: {missing} doesn't exist on this machine, "
                "kept",
            ],
        )

    def test_a_default_is_checked_too(self):
        lines = {"sudo": (self.program, 1)}
        report = Report()
        app, _ = convert.convert_settings(lines, "vb.conf", report)
        app.term = os.path.join(self.root, "missing")
        report = Report()
        convert._check_programs(app, lines, "vb.conf", report)
        self.assertEqual(
            [m.where for m in report if "term:" in m.text], ["vb.conf"]
        )


class TestConvertValue(unittest.TestCase):

    def test_bool(self):
        self.assertIs(convert.convert_value(schema.Bool(), "*"), True)
        self.assertIs(convert.convert_value(schema.Bool(), ""), False)

    def test_numbers(self):
        self.assertEqual(convert.convert_value(schema.Int(), " 3 "), 3)
        self.assertEqual(convert.convert_value(schema.Float(), "0.5"), 0.5)
        self.assertIsInstance(
            convert.convert_value(schema.Float(), "2"), float
        )
        error = self.assertRaises(
            ValueError, convert.convert_value, schema.Int(), "x"
        )
        self.assertEqual(str(error), '"x" is not an integer')
        error = self.assertRaises(
            ValueError, convert.convert_value, schema.Float(), ""
        )
        self.assertEqual(str(error), '"" is not a number')

    def test_text(self):
        self.assertEqual(convert.convert_value(schema.Str(), " a "), " a ")

    def test_event_actions(self):
        kind = EventAction()
        self.assertEqual(
            convert._convert_item(kind, "add sw1 on"),
            console.VbShellCommand("sw1 on"),
        )
        self.assertEqual(
            convert._convert_item(kind, "addsh logger hi"),
            console.ShellCommand("logger hi"),
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
        self.assertEqual(convert._convert_item(schema.Str(), "a"), "a")


class ConvertTestCase(unittest.TestCase):

    def setUp(self):
        self.root = isolate(self)
        reset_settings(self)
        self.directory = os.path.join(self.root, "project")
        os.makedirs(self.directory)

    def convert(self, text):
        report = Report()
        project = legacy.parse_project(text, ".project", report)
        data, count = convert.convert_project(
            project, settings.ProjectSettings(), report, self.directory
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
        self.assertEqual(data["format"], projectfile.FORMAT)
        self.assertEqual(
            data["settings"], schema.dump(settings.ProjectSettings())
        )
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
        self.assertIs(sender["kvm"], True)
        self.assertIs(sender["tdf"], True)
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
            (vm["ram"], vm["smp"], vm["gdbport"], vm["vncN"], vm["kvmsmem"]),
            (64, 1, 1234, 1, 1),
        )
        self.assertEqual(
            (vm["argv0"], vm["keyboard"]), ("qemu-system-i386", "it")
        )
        self.assertIs(vm["snapshot"], True)
        self.assertIs(vm["novga"], False)
        self.assertEqual(vm["usbdevlist"], [])
        self.assertEqual(vm["nics"], [])
        wrapper = data["bricks"]["sw1"]
        self.assertEqual(wrapper["type"], "switchwrapper")
        self.assertEqual(wrapper["path"], "/var/run/switch/sck")
        self.assertEqual(
            messages(report, "info"),
            [
                ".project:2: [Project:/home/user/.virtualbricks.vbl] older "
                "project metadata, dropped",
                ".project:4: [DiskImage:vtatpa.qcow2] became an image",
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
        self.assertIs(vm["use_virtio"], True)
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
        self.assertEqual(wan["transperiod"], 250)
        self.assertEqual(wan["transitions"], [[0.0, 0.2], [0.5, 0.0]])
        self.assertEqual(wan["endpoints"], ["", "sw2"])
        first, second = wan["states"]
        self.assertEqual((first["name"], first["delay"]), ("default name", 10))
        self.assertIs(first["bandwidthsymm"], False)
        self.assertEqual(
            (second["name"], second["delay"], second["loss"]),
            ("congested", 200, 2.5),
        )
        self.assertIs(second["bandwidthsymm"], True)
        self.assertEqual(data["bricks"]["sw2"]["numports"], 32)
        self.assertEqual(
            data["events"]["boot"],
            {
                "actions": [
                    {"kind": "vb", "command": "sw1 on"},
                    {"kind": "shell", "command": "logger hi"},
                ],
                "delay": 3,
            },
        )
        self.assertEqual(
            messages(report),
            [
                ".project:20: [Switch:sw2] numports: 500 is outside 1–128, "
                "using the default 32",
                ".project:23: [Event:boot] actions: \"__import__('os')."
                "system('id')\" is not an event action, dropped",
            ],
        )


class TestSections(ConvertTestCase):

    def test_defined_twice(self):
        for text in (
            "[Switch:sw]\n[Tap:sw]\n",
            "[Image:a]\npath=/a\n[DiskImage:a]\npath=/b\n",
            "[Event:e]\n[Event:e]\n",
        ):
            error = self.assertRaises(
                convert.MigrationError, self.convert, text
            )
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
                ".project:1: [Switch:1sw] Name must start with a letter, dropped",
                ".project:2: [Event:2ev] Name must start with a letter, dropped",
            ],
        )

    def test_keys(self):
        text = (
            "[Switch:sw]\ncolor=red\nnumports=x\nhub=*\n[Router:r]\nname=r\n"
        )
        data, _, report = self.convert(text)
        self.assertIs(data["bricks"]["sw"]["hub"], True)
        self.assertEqual(data["bricks"]["sw"]["numports"], 32)
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
            data["bricks"]["vm"]["usbdevlist"],
            [{"id": "1d6b:0002", "description": ""}],
        )
        self.assertEqual(data["bricks"]["vm2"]["usbdevlist"], [])
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
        self.assertEqual(wan["transperiod"], 100)
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

    def test_events_of_every_state(self):
        text = "[Event:on]\n[Netemu:wan]\npon_vbevent=on\nstates=3\n"
        data, _, report = self.convert(text)
        self.assertEqual(len(report), 0)
        wan = data["bricks"]["wan"]
        self.assertEqual(wan["pon_vbevent"], "on")
        self.assertEqual(len(wan["states"]), 3)
        factory = convert._Converter(
            legacy.parse_project(text, "f", Report()), Report(), self.directory
        )
        factory.convert(settings.ProjectSettings())
        brick = factory.factory.get_brick_by_name("wan")
        self.assertEqual(
            [state.pon_vbevent for state in brick.markov_manager.states],
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
                    "model": projectfile.DEFAULT_MODEL,
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

    def test_macs(self):
        text = "[Qemu:vm]\nsock|vm|a||\nsock|vm|b||00:11\n"
        data, _, report = self.convert(text)
        macs = [nic["mac"] for nic in data["bricks"]["vm"]["nics"]]
        for mac in macs:
            schema.Mac().check(mac)
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
                    "model": projectfile.DEFAULT_MODEL,
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
