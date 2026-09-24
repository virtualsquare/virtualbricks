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

import copy
import os

from twisted.trial import unittest

from virtualbricks import console
from virtualbricks.config import (
    ProjectFormatError,
    Report,
    projectfile,
    schema,
    settings,
    tomlfile,
)
from virtualbricks.tests import isolate, make_factory, reset_settings
from virtualbricks.bricks.virtualmachine import UsbDevice


def build_lab(factory, image_path="/images/deb.qcow2"):
    """A project with a brick of each kind and each kind of connection."""

    image = factory.new_disk_image("deb", image_path, "Debian\nbase")
    event = factory.new_event("boot")
    event.set(
        {
            "delay": 5,
            "actions": [
                console.VbShellCommand("vm on"),
                console.ShellCommand("logger hi"),
            ],
        }
    )
    sw1 = factory.new_brick("switch", "sw1")
    sw1.set({"numports": 16, "pon_vbevent": "boot"})
    sw2 = factory.new_brick("switch", "sw2")
    vm = factory.new_brick("qemu", "vm")
    vm.set(
        {
            "kvm": True,
            "privatehda": True,
            "usbdevlist": [UsbDevice("1d6b:0002", "hub")],
        }
    )
    vm.set_image("hda", image)
    vm.add_plug(sw1.socks[0], "00:aa:00:00:00:01", "e1000")
    vm.add_plug(factory.get_sock_by_name("_hostonly"), "00:aa:00:00:00:02")
    vm.add_plug(None, "00:aa:00:00:00:03", "rtl8139")
    vm.add_sock("00:aa:00:00:00:04", "virtio")
    tap = factory.new_brick("tap", "tap0")
    tap.set({"mode": "manual", "ip": "10.0.0.2"})
    tap.connect(sw2.socks[0])
    wan = factory.new_brick("netemu", "wan")
    wan.plugs[0].connect(sw1.socks[0])
    wan.plugs[1].connect(sw2.socks[0])
    wan.markov_manager.add(1)
    wan.markov_manager.states[1].delay = 200
    wan.markov_manager.weights[0][1] = 0.2
    wire = factory.new_brick("wire", "w")
    wire.plugs[1].connect(factory.get_sock_by_name("vm_sock_eth3"))
    factory.new_brick("capture", "cap")
    factory.new_brick("tunnellisten", "tl").connect(sw1.socks[0])
    factory.new_brick("switchwrapper", "wr")
    factory.new_brick("router", "r")
    return factory


class ProjectFileTestCase(unittest.TestCase):

    def setUp(self):
        isolate(self)
        reset_settings(self)
        self.factory = make_factory(self)
        self.report = Report()

    def messages(self):
        return [str(m) for m in self.report]

    def restore(self, data, directory="/"):
        factory = make_factory(self)
        project_settings = projectfile.restore(
            factory, data, self.report, directory
        )
        return factory, project_settings


class TestDocument(ProjectFileTestCase):

    def test_empty_project(self):
        data = projectfile.document(self.factory, settings.ProjectSettings())
        self.assertEqual(
            data,
            {"format": 1, "settings": schema.dump(settings.ProjectSettings())},
        )

    def test_lab(self):
        data = projectfile.document(
            build_lab(self.factory), settings.ProjectSettings(femaleplugs=True)
        )
        self.assertEqual(data["settings"]["femaleplugs"], True)
        self.assertEqual(
            data["images"],
            {
                "deb": {
                    "path": "/images/deb.qcow2",
                    "description": "Debian\nbase",
                }
            },
        )
        self.assertEqual(data["events"]["boot"]["delay"], 5)
        bricks = data["bricks"]
        self.assertEqual(bricks["sw1"]["type"], "switch")
        self.assertEqual(bricks["sw1"]["pon_vbevent"], "boot")
        self.assertEqual(
            bricks["vm"]["disks"]["hda"], {"image": "deb", "private": True}
        )
        self.assertEqual(
            bricks["vm"]["nics"],
            [
                {
                    "kind": "plug",
                    "connect": "sw1",
                    "model": "e1000",
                    "mac": "00:aa:00:00:00:01",
                },
                {
                    "kind": "hostonly",
                    "model": "rtl8139",
                    "mac": "00:aa:00:00:00:02",
                },
                {
                    "kind": "plug",
                    "connect": "",
                    "model": "rtl8139",
                    "mac": "00:aa:00:00:00:03",
                },
                {
                    "kind": "socket",
                    "name": "sock_eth3",
                    "model": "virtio",
                    "mac": "00:aa:00:00:00:04",
                },
            ],
        )
        self.assertEqual(bricks["tap0"]["connect"], "sw2")
        self.assertEqual(bricks["wan"]["endpoints"], ["sw1", "sw2"])
        self.assertEqual(bricks["w"]["endpoints"], ["", "vm:sock_eth3"])
        self.assertEqual(bricks["cap"]["connect"], "")
        self.assertNotIn("connect", bricks["wr"])
        self.assertEqual(
            set(bricks["r"]), {"type", "pon_vbevent", "poff_vbevent"}
        )

    def test_socket_target(self):
        vm = self.factory.new_brick("qemu", "vm_1")
        sock = vm.add_sock()
        self.assertEqual(projectfile.socket_target(sock), "vm_1:sock_eth0")

    def test_save_and_create(self):
        path = self.mktemp()
        projectfile.create(path, settings.ProjectSettings())
        self.assertEqual(tomlfile.load(path)["format"], 1)
        projectfile.save(
            build_lab(self.factory), settings.ProjectSettings(), path
        )
        self.assertIn("bricks", tomlfile.load(path))


class TestRoundTrip(ProjectFileTestCase):

    def test_lab(self):
        data = projectfile.document(
            build_lab(self.factory), settings.ProjectSettings(vdepath="/opt")
        )
        text = tomlfile.dumps(data)
        factory, project_settings = self.restore(tomlfile.loads(text))
        self.assertEqual(
            self.messages(),
            ["images.deb: /images/deb.qcow2 not found, kept in the library"],
        )
        self.assertEqual(project_settings.vdepath, "/opt")
        self.assertEqual(projectfile.document(factory, project_settings), data)
        vm = factory.get_brick_by_name("vm")
        self.assertIs(vm.disk("hda").image, factory.get_image_by_name("deb"))
        self.assertEqual(len(vm.plugs), 3)
        self.assertEqual(vm.plugs[1].sock.nickname, "_hostonly")
        self.assertIsNone(vm.plugs[2].sock)
        wire = factory.get_brick_by_name("w")
        self.assertIsNone(wire.plugs[0].sock)
        self.assertEqual(wire.plugs[1].sock.nickname, "vm_sock_eth3")

    def test_load_from_a_file(self):
        directory = os.path.abspath(self.mktemp())
        os.makedirs(directory)
        with open(os.path.join(directory, "deb.qcow2"), "w"):
            pass
        build_lab(self.factory, "deb.qcow2")
        data = projectfile.document(self.factory, settings.ProjectSettings())
        data["images"]["deb"]["path"] = "deb.qcow2"
        path = os.path.join(directory, "project.toml")
        tomlfile.dump(data, path)
        factory = make_factory(self)
        projectfile.load(factory, path, self.report)
        self.assertEqual(self.messages(), [])
        image = factory.get_image_by_name("deb")
        self.assertEqual(
            image.get_path(), os.path.join(directory, "deb.qcow2")
        )


class TestUpgrade(ProjectFileTestCase):

    def test_current(self):
        data = {"format": 1}
        self.assertIs(projectfile.upgrade(data, self.report), data)
        self.assertEqual(self.messages(), [])

    def test_unknown(self):
        for value in (None, "1", True, 0):
            report = Report()
            data = {} if value is None else {"format": value}
            projectfile.upgrade(data, report)
            self.assertEqual(report.warnings, 1)

    def test_newer(self):
        self.assertRaises(
            ProjectFormatError,
            projectfile.upgrade,
            {"format": 2},
            self.report,
        )

    def test_steps(self):
        self.patch(projectfile, "FORMAT", 3)
        steps = {
            1: lambda data, report: {**data, "one": True},
            2: lambda data, report: {**data, "two": True},
        }
        self.patch(projectfile, "UPGRADES", steps)
        self.assertEqual(
            projectfile.upgrade({"format": 1}, self.report),
            {"format": 1, "one": True, "two": True},
        )


class TestLenientReading(ProjectFileTestCase):

    def lab(self):
        return projectfile.document(
            build_lab(self.factory), settings.ProjectSettings()
        )

    def test_unknown_top_level_keys(self):
        self.restore({"format": 1, "settings": {}, "colors": 1})
        self.assertIn("colors: unknown field, dropped", self.messages())

    def test_settings_from_the_app(self):
        settings.set_app("qemupath", "/opt/qemu")
        _, project_settings = self.restore({"format": 1})
        self.assertEqual(project_settings.qemupath, "/opt/qemu")
        self.assertEqual(
            self.messages(), ["settings: missing, using the app settings"]
        )

    def test_settings_not_a_table(self):
        self.restore({"format": 1, "settings": 1})
        self.assertEqual(
            self.messages(),
            ["settings: is not a table, using the app settings"],
        )

    def test_partial_settings(self):
        settings.set_app("cowfmt", "qcow")
        _, project_settings = self.restore(
            {"format": 1, "settings": {"femaleplugs": True, "color": 1}}
        )
        self.assertTrue(project_settings.femaleplugs)
        self.assertEqual(project_settings.cowfmt, "qcow")
        self.assertIn(
            'settings.cowfmt: missing, using the app setting "qcow"',
            self.messages(),
        )
        self.assertIn(
            "settings.color: unknown field, dropped", self.messages()
        )

    def test_empty_settings_table(self):
        self.restore({"format": 1, "settings": {}})
        self.assertEqual(self.messages(), [])

    def test_tables(self):
        data = {"format": 1, "settings": {}, "images": 1, "bricks": {"sw": 1}}
        self.restore(data)
        self.assertEqual(
            self.messages(),
            [
                "images: is not a table, ignored",
                "bricks.sw: is not a table, ignored",
            ],
        )

    def test_images(self):
        path = os.path.abspath(self.mktemp())
        with open(path, "w"):
            pass
        data = {
            "format": 1,
            "settings": {},
            "images": {
                "empty": {"path": "", "description": ""},
                "one": {"path": path, "description": "x"},
                "same": {"path": path, "description": ""},
                "1bad": {"path": path + "2", "description": ""},
            },
        }
        factory, _ = self.restore(data)
        self.assertEqual(
            [i.get_name() for i in factory.iter_disk_images()], ["one"]
        )
        self.assertEqual(
            self.messages(),
            [
                "images.empty: has no path, image dropped",
                "images.same: uses the file of another image, image dropped",
                f"images.1bad: {path}2 not found, kept in the library",
                "images.1bad: Name must start with a letter, image dropped",
            ],
        )

    def test_events(self):
        data = {
            "format": 1,
            "settings": {},
            "events": {"1bad": {}, "ok": {"delay": 1, "actions": []}},
        }
        factory, _ = self.restore(data)
        self.assertEqual([e.get_name() for e in factory.iter_events()], ["ok"])
        self.assertEqual(len(self.messages()), 1)

    def test_bricks(self):
        data = self.lab()
        data["bricks"]["x"] = {"type": 3}
        data["bricks"]["y"] = {"type": "spaceship"}
        data["bricks"]["1bad"] = {"type": "switch"}
        data["bricks"]["sw1"]["numports"] = 500
        data["bricks"]["sw1"]["color"] = "red"
        factory, _ = self.restore(data)
        self.assertIsNone(factory.get_brick_by_name("x"))
        self.assertIsNone(factory.get_brick_by_name("y"))
        self.assertEqual(factory.get_brick_by_name("sw1").config.numports, 32)
        messages = self.messages()
        self.assertIn(
            "bricks.sw1.numports: 500 is outside 1–128, using the default 32",
            messages,
        )
        self.assertIn("bricks.sw1.color: unknown field, dropped", messages)
        self.assertEqual(
            sum(1 for m in messages if m.endswith("brick dropped")), 3
        )
        for brick in factory.bricks:
            self.assertFalse(brick._restore)

    def test_connections(self):
        data = self.lab()
        bricks = data["bricks"]
        bricks["tap0"]["connect"] = 3
        bricks["cap"]["connect"] = "nowhere"
        bricks["wan"]["endpoints"] = ["sw1"]
        bricks["w"]["endpoints"] = ["vm", "vm:sock_eth9"]
        bricks["tl"]["connect"] = "wr:nope"
        factory, _ = self.restore(data)
        self.assertIsNone(factory.get_brick_by_name("tap0").plugs[0].sock)
        self.assertEqual(
            [p.sock for p in factory.get_brick_by_name("wan").plugs],
            [None, None],
        )
        messages = self.messages()
        self.assertIn(
            "bricks.tap0.connect: 3 is not a connection, left unconnected",
            messages,
        )
        self.assertIn(
            'bricks.cap: no socket "nowhere", left unconnected', messages
        )
        self.assertIn(
            "bricks.wan: is not a list of two ends, left unconnected", messages
        )
        self.assertIn('bricks.w: no socket "vm", left unconnected', messages)
        self.assertIn(
            'bricks.w: no socket "vm:sock_eth9", left unconnected', messages
        )
        self.assertIn(
            'bricks.tl: no socket "wr:nope", left unconnected', messages
        )

    def test_resolve_checks_the_owner(self):
        build_lab(self.factory)
        other = self.factory.new_brick("qemu", "vm_sock")
        other.add_sock(name="eth3")
        # "vm_sock_eth3" is the nickname of both; the owner decides.
        self.assertIs(
            projectfile.resolve(self.factory, "vm:sock_eth3").brick,
            self.factory.get_brick_by_name("vm"),
        )
        self.assertIsNone(projectfile.resolve(self.factory, "sw1:sock_eth3"))

    def test_nics(self):
        data = self.lab()
        data["bricks"]["vm"]["nics"] = [
            1,
            {"kind": "bridge"},
            {"kind": "plug", "connect": "sw1", "model": 3, "mac": "zz"},
            {"kind": "plug", "connect": "sw1", "mac": ""},
            {"kind": "socket", "name": "bad name", "mac": "00:aa:00:00:00:09"},
            {"kind": "hostonly", "mac": "00:aa:00:00:00:08", "vlan": 1},
        ]
        factory, _ = self.restore(data)
        vm = factory.get_brick_by_name("vm")
        self.assertEqual(len(vm.plugs), 3)
        self.assertEqual(vm.plugs[0].model, "rtl8139")
        self.assertEqual([s.nickname for s in vm.socks], ["vm_sock_eth4"])
        messages = self.messages()
        self.assertIn(
            "bricks.vm.nics[0]: is not a table, card dropped", messages
        )
        self.assertIn(
            'bricks.vm.nics[1]: kind: "bridge" is not one of plug, socket, '
            "hostonly, card dropped",
            messages,
        )
        self.assertIn("bricks.vm.nics[2]: model: 3, using rtl8139", messages)
        self.assertIn(
            "bricks.vm.nics[4]: name: missing or invalid, using sock_eth4",
            messages,
        )
        self.assertIn(
            "bricks.vm.nics[5].vlan: unknown field, dropped", messages
        )
        self.assertEqual(sum(1 for m in messages if "mac: " in m), 2)

    def test_nics_not_a_list(self):
        data = self.lab()
        data["bricks"]["vm"]["nics"] = "none"
        factory, _ = self.restore(data)
        self.assertEqual(factory.get_brick_by_name("vm").plugs, [])
        self.assertIn(
            "bricks.vm: nics: is not a list, cards dropped", self.messages()
        )

    def test_missing_connections(self):
        data = self.lab()
        del data["bricks"]["wan"]["endpoints"]
        del data["bricks"]["tap0"]["connect"]
        del data["bricks"]["vm"]["nics"]
        factory, _ = self.restore(data)
        self.assertEqual(factory.get_brick_by_name("vm").plugs, [])
        self.assertIsNone(factory.get_brick_by_name("tap0").plugs[0].sock)

    def test_dangling_references(self):
        data = self.lab()
        del data["images"]
        del data["events"]
        data["bricks"]["sw1"]["poff_vbevent"] = "down"
        self.restore(data)
        messages = self.messages()
        self.assertIn(
            'bricks.sw1.pon_vbevent: no event named "boot"', messages
        )
        self.assertIn(
            'bricks.sw1.poff_vbevent: no event named "down"', messages
        )
        self.assertIn('bricks.vm.hda: no image named "deb"', messages)

    def test_event_references(self):
        data = self.lab()
        data["events"]["boot"]["actions"] = []
        self.restore(data)
        self.assertNotIn("events", " ".join(self.messages()))


class TestRead(ProjectFileTestCase):

    def test_not_toml(self):
        path = self.mktemp()
        with open(path, "w") as fp:
            fp.write("[bricks\n")
        self.assertRaises(ProjectFormatError, projectfile.read, path)

    def test_missing(self):
        self.assertRaises(FileNotFoundError, projectfile.read, self.mktemp())


class TestEditing(unittest.TestCase):

    DATA = {
        "images": {"deb": {"path": "/a"}, "bad": 1, "nopath": {}},
        "bricks": {
            "vm": {
                "type": "qemu",
                "disks": {"hda": {"image": "deb"}, "hdb": "x"},
            },
            "vm2": {"type": "qemu"},
            "sw": {"type": "switch", "disks": {"hda": {"image": "deb"}}},
            "odd": 1,
        },
    }

    def test_image_paths(self):
        self.assertEqual(
            projectfile.image_paths(self.DATA), {"deb": "/a", "nopath": ""}
        )
        self.assertEqual(projectfile.image_paths({}), {})

    def test_remap_image(self):
        data = copy.deepcopy(self.DATA)
        projectfile.remap_image(data, "deb", "/b")
        projectfile.remap_image(data, "missing", "/c")
        projectfile.remap_image(data, "bad", "/c")
        self.assertEqual(data["images"]["deb"]["path"], "/b")
        self.assertEqual(data["images"]["bad"], 1)

    def test_devices_for_image(self):
        self.assertEqual(
            list(projectfile.devices_for_image(self.DATA, "deb")),
            [("vm", "hda")],
        )
        self.assertEqual(list(projectfile.devices_for_image({}, "deb")), [])
