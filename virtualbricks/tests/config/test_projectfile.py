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

import copy
import os

from twisted.trial import unittest

from virtualbricks.brickfactory import BRICK_CLASSES
from virtualbricks.bricks.eventaction import (
    ShellAction,
    StartAction,
)
from virtualbricks.bricks.virtualmachine import UsbDevice
from virtualbricks.config import projectfile, tomlfile
from virtualbricks.config.projectfile import (
    FORMAT,
    HEADER,
    ProjectFormatError,
    create_project_file,
    devices_for_image,
    free_sock_name,
    image_paths,
    project_document,
    project_notes,
    read_project_file,
    remap_image,
    restore_project,
    save_project,
    socket_target,
    unique_sock_names,
    upgrade_project,
    upgrade_readme,
)
from virtualbricks.config.projectfile import (
    resolve as resolve_socket,
)
from virtualbricks.config.report import Report
from virtualbricks.config.schema import dump_record
from virtualbricks.config.settings import ProjectSettings, use_project
from virtualbricks.config.tomlfile import (
    FORMAT_NOTE,
    Note,
    comment_lines,
    dump_toml,
    dumps_toml,
    load_toml,
    loads_toml,
)
from virtualbricks.tests import isolate, make_factory, reset_settings


def build_lab(factory, image_path="/images/deb.qcow2"):
    """A project with a brick of each kind and each kind of connection."""

    image = factory.new_image("deb", image_path, "Debian\nbase")
    event = factory.new_event("boot")
    event.update_config(
        {
            "delay": 5,
            "actions": [
                StartAction("vm"),
                ShellAction("logger hi"),
            ],
        }
    )
    sw1 = factory.new_brick("switch", "sw1")
    sw1.update_config({"ports": 16, "on_start": "boot"})
    sw2 = factory.new_brick("switch", "sw2")
    vm = factory.new_brick("qemu", "vm")
    vm.update_config(
        {
            "use_kvm": True,
            "hda_private": True,
            "usb_devices": [UsbDevice("1d6b:0002", "hub")],
        }
    )
    vm.set_image("hda", image)
    vm.add_plug(sw1.socks[0], "00:aa:00:00:00:01", "e1000")
    vm.add_plug(factory.get_sock("_hostonly"), "00:aa:00:00:00:02")
    vm.add_plug(None, "00:aa:00:00:00:03", "rtl8139")
    vm.add_sock("00:aa:00:00:00:04", "virtio", "sock_eth3")
    tap = factory.new_brick("tap", "tap0")
    tap.update_config({"address_mode": "manual", "ip_address": "10.0.0.2"})
    tap.connect(sw2.socks[0])
    wan = factory.new_brick("netemu", "wan")
    wan.plugs[0].connect(sw1.socks[0])
    wan.plugs[1].connect(sw2.socks[0])
    wan.markov_manager.add(1)
    wan.markov_manager.states[1].delay = 200
    wan.markov_manager.weights[0][1] = 0.2
    wire = factory.new_brick("wire", "w")
    wire.plugs[1].connect(factory.get_sock("vm_sock_eth3"))
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
        project_settings = restore_project(
            factory, data, self.report, directory
        )
        return factory, project_settings


class TestDocument(ProjectFileTestCase):

    def test_empty_project(self):
        data = project_document(self.factory, ProjectSettings())
        self.assertEqual(
            data,
            {
                "format": FORMAT,
                "settings": dump_record(ProjectSettings()),
            },
        )

    def test_lab(self):
        data = project_document(
            build_lab(self.factory), ProjectSettings(allow_female_plugs=True)
        )
        self.assertEqual(data["settings"]["allow_female_plugs"], True)
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
        self.assertEqual(bricks["sw1"]["on_start"], "boot")
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
            set(bricks["r"]), {"type", "icon", "on_start", "on_stop"}
        )

    def test_socket_target(self):
        vm = self.factory.new_brick("qemu", "vm_1")
        sock = vm.add_sock()
        self.assertEqual(socket_target(sock), "vm_1:sock_eth0")

    def test_save_and_create(self):
        path = self.mktemp()
        create_project_file(path, ProjectSettings())
        self.assertEqual(load_toml(path)["format"], FORMAT)
        save_project(build_lab(self.factory), ProjectSettings(), path)
        self.assertIn("bricks", load_toml(path))


class TestRoundTrip(ProjectFileTestCase):

    def test_lab(self):
        data = project_document(
            build_lab(self.factory), ProjectSettings(vde_path="/opt")
        )
        text = dumps_toml(data)
        factory, project_settings = self.restore(loads_toml(text))
        self.assertEqual(
            self.messages(),
            ["images.deb: /images/deb.qcow2 not found, kept in the library"],
        )
        self.assertEqual(project_settings.vde_path, "/opt")
        self.assertEqual(project_document(factory, project_settings), data)
        vm = factory.get_brick("vm")
        self.assertIs(vm.disk("hda").image, factory.get_image("deb"))
        self.assertEqual(len(vm.plugs), 3)
        self.assertEqual(vm.plugs[1].sock.nickname, "_hostonly")
        self.assertIsNone(vm.plugs[2].sock)
        wire = factory.get_brick("w")
        self.assertIsNone(wire.plugs[0].sock)
        self.assertEqual(wire.plugs[1].sock.nickname, "vm_sock_eth3")

    def test_the_cards_in_their_order(self):
        data = project_document(build_lab(self.factory), ProjectSettings())
        data["bricks"]["vm"]["nics"] = [
            {"kind": "socket", "name": "lan", "mac": "00:aa:00:00:00:01"},
            {"kind": "plug", "connect": "vm2:dmz", "mac": "00:aa:00:00:00:02"},
            {"kind": "hostonly", "mac": "00:aa:00:00:00:03"},
            {"kind": "socket", "name": "dmz", "mac": "00:aa:00:00:00:04"},
            {"kind": "plug", "connect": "sw1", "mac": "00:aa:00:00:00:05"},
        ]
        data["bricks"]["w"]["endpoints"] = ["vm:lan", "vm:dmz"]
        # read after vm
        data["bricks"]["vm2"] = {
            "type": "qemu",
            "nics": [
                {"kind": "socket", "name": "dmz", "mac": "00:aa:00:00:00:06"}
            ],
        }
        factory, project_settings = self.restore(data)
        vm, vm2 = factory.get_brick("vm"), factory.get_brick("vm2")
        self.assertEqual(
            [card.mac for card in vm.links],
            [f"00:aa:00:00:00:0{n}" for n in range(1, 6)],
        )
        self.assertEqual(
            [plug.sock for plug in vm.plugs],
            [
                vm2.socks[0],
                factory.get_sock("_hostonly"),
                factory.get_brick("sw1").socks[0],
            ],
        )
        self.assertEqual(
            [sock.nickname for sock in vm.socks], ["vm_lan", "vm_dmz"]
        )
        self.assertEqual(
            [plug.sock for plug in factory.get_brick("w").plugs], vm.socks
        )
        saved = project_document(factory, project_settings)
        self.assertEqual(
            [
                (nic["kind"], nic["mac"])
                for nic in saved["bricks"]["vm"]["nics"]
            ],
            [
                (nic["kind"], nic["mac"])
                for nic in data["bricks"]["vm"]["nics"]
            ],
        )

    def test_announced_once_restored(self):
        data = project_document(build_lab(self.factory), ProjectSettings())
        factory = make_factory(self)
        bricks, events = {}, {}

        def brick_changed(brick):
            bricks[brick.name] = (dump_record(brick.config), len(brick.plugs))

        def event_changed(event):
            events[event.name] = dump_record(event.config)

        factory.brick_changed.connect(brick_changed)
        factory.event_changed.connect(event_changed)
        restore_project(factory, data, self.report, "/")
        # what shows them, as the lists of the window, learns their
        # configuration and their links, not the defaults they were made with
        self.assertEqual(bricks["sw1"][0]["ports"], 16)
        self.assertEqual(bricks["vm"][1], 3)
        self.assertTrue(bricks["vm"][0]["use_kvm"])
        self.assertEqual(events["boot"]["delay"], 5)
        self.assertEqual(sorted(bricks), sorted(data["bricks"]))

    def test_load_from_a_file(self):
        directory = os.path.abspath(self.mktemp())
        os.makedirs(directory)
        with open(os.path.join(directory, "deb.qcow2"), "w"):
            pass
        build_lab(self.factory, "deb.qcow2")
        data = project_document(self.factory, ProjectSettings())
        data["images"]["deb"]["path"] = "deb.qcow2"
        path = os.path.join(directory, "project.toml")
        dump_toml(data, path)
        factory = make_factory(self)
        data = upgrade_project(read_project_file(path), self.report)
        restore_project(factory, data, self.report, directory)
        self.assertEqual(self.messages(), [])
        image = factory.get_image("deb")
        self.assertEqual(image.path, os.path.join(directory, "deb.qcow2"))


def _lines(data, path=()):
    """The path of each key that is written on a line of its own."""

    for key, value in data.items():
        if not tomlfile._is_block(value):
            yield path + (key,)
        elif isinstance(value, dict):
            yield from _lines(value, path + (key,))
        else:
            for index, item in enumerate(value):
                yield from _lines(item, path + (key, index))


class TestNotes(ProjectFileTestCase):
    """The comments of a project file."""

    def lab(self):
        build_lab(self.factory)
        self.factory.new_brick("tunnelconnect", "tc")
        return project_document(self.factory, ProjectSettings())

    def test_every_key_has_a_comment(self):
        data = self.lab()
        notes = project_notes(data)
        lines = set(_lines(data))
        for path in lines:
            self.assertTrue(comment_lines(notes[path]), path)
        # the other notes are of tables, which have no comment
        self.assertEqual(set(notes) - lines, {("bricks", "wan", "states")})

    def test_fixed_notes(self):
        notes = project_notes(self.lab())
        self.assertEqual(notes[("format",)], FORMAT_NOTE)
        self.assertEqual(
            notes[("bricks", "sw1", "type")], Note("A VDE switch")
        )
        self.assertEqual(
            notes[("bricks", "tap0", "connect")],
            Note("The socket it's plugged into"),
        )
        self.assertEqual(
            notes[("bricks", "w", "endpoints")].text,
            "The sockets of its two ends, left and right",
        )
        self.assertEqual(
            notes[("bricks", "vm", "nics", 3, "name")].text,
            "The name of the socket card, which other bricks plug into",
        )
        self.assertNotIn(("bricks", "vm", "nics", 3, "connect"), notes)
        self.assertNotIn(("bricks", "vm", "nics"), notes)

    def test_every_type_says_what_it_is(self):
        for name, cls in BRICK_CLASSES.items():
            self.assertTrue(cls.summary, name)
        self.assertIsNone(projectfile._brick_class("event"))

    def test_defaults(self):
        notes = project_notes(self.lab())
        self.assertFalse(notes[("bricks", "sw1", "ports")].default)
        self.assertTrue(notes[("bricks", "sw2", "ports")].default)
        self.assertTrue(notes[("settings", "vde_path")].default)
        # the states of a netemu, by their index
        self.assertTrue(notes[("bricks", "wan", "states", 0, "delay")].default)
        self.assertFalse(
            notes[("bricks", "wan", "states", 1, "delay")].default
        )

    def test_whatever_the_data(self):
        data = {
            "format": 1,
            "settings": "x",
            "images": {"a": "x"},
            "events": [],
            "bricks": {
                "a": {"type": "nope"},
                "b": {"type": 1},
                "c": "x",
                "d": {"type": "event", "delay": 1},
                "e": {"type": "qemu", "nics": "x"},
                "f": {"type": "qemu", "nics": ["x", {"kind": "plug"}]},
                "g": {"type": "Switch", "ports": 3},
            },
        }
        notes = project_notes(data)
        self.assertEqual(
            sorted(path for path in notes if path[0] == "bricks"),
            [
                ("bricks", "e", "type"),
                ("bricks", "f", "nics", 1, "kind"),
                ("bricks", "f", "type"),
                ("bricks", "g", "ports"),
                ("bricks", "g", "type"),
            ],
        )

    def test_files(self):
        path = self.mktemp()
        create_project_file(path, ProjectSettings())
        with open(path, encoding="utf-8") as fp:
            text = fp.read()
        self.assertTrue(
            text.startswith(tomlfile.dumps_toml({}, header=HEADER))
        )
        self.assertIn(
            f"\n# The version of the layout of this file\nformat = {FORMAT}\n",
            text,
        )
        data = self.lab()
        save_project(self.factory, ProjectSettings(), path)
        with open(path, encoding="utf-8") as fp:
            text = fp.read()
        self.assertEqual(loads_toml(text), data)
        self.assertIn("\nports = 16\n", text)
        self.assertIn("\nhub_mode = false  # default\n", text)
        self.assertTrue(all(len(line) <= 79 for line in text.splitlines()))


class TestUpgrade(ProjectFileTestCase):

    def test_current(self):
        data = {"format": FORMAT}
        self.assertIs(upgrade_project(data, self.report), data)
        self.assertEqual(self.messages(), [])

    def test_unknown(self):
        for value in (None, "1", True, 0):
            report = Report()
            data = {} if value is None else {"format": value}
            upgrade_project(data, report)
            self.assertEqual(report.warnings, 1)

    def test_newer(self):
        self.assertRaises(
            ProjectFormatError,
            upgrade_project,
            {"format": FORMAT + 1},
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
            upgrade_project({"format": 1}, self.report),
            {"format": 1, "one": True, "two": True},
        )


class TestUpgradeReadme(unittest.TestCase):

    def setUp(self):
        self.folder = self.mktemp()
        os.makedirs(self.folder)

    def write(self, name, text):
        with open(os.path.join(self.folder, name), "w") as fp:
            fp.write(text)

    def files(self):
        result = {}
        for name in sorted(os.listdir(self.folder)):
            with open(os.path.join(self.folder, name)) as fp:
                result[name] = fp.read()
        return result

    def test_renamed(self):
        self.write("README", "A lab")
        upgrade_readme(self.folder)
        self.assertEqual(self.files(), {"README.md": "A lab"})

    def test_a_readme_md_stays(self):
        self.write("README", "A lab")
        self.write("README.md", "The lab")
        upgrade_readme(self.folder)
        self.assertEqual(
            self.files(), {"README": "A lab", "README.md": "The lab"}
        )

    def test_without_a_readme(self):
        upgrade_readme(self.folder)
        self.assertEqual(self.files(), {})

    def test_a_folder_named_readme_stays(self):
        os.mkdir(os.path.join(self.folder, "README"))
        upgrade_readme(self.folder)
        self.assertEqual(os.listdir(self.folder), ["README"])


class TestLenientReading(ProjectFileTestCase):

    def lab(self):
        return project_document(build_lab(self.factory), ProjectSettings())

    def test_unknown_top_level_keys(self):
        self.restore({"format": 1, "settings": {}, "colors": 1})
        self.assertIn("colors: unknown field, dropped", self.messages())

    def test_missing_settings(self):
        # not those of the project that is open
        use_project(ProjectSettings(qemu_path="/opt/qemu"))
        _, project_settings = self.restore({"format": 1})
        self.assertEqual(project_settings, ProjectSettings())
        self.assertEqual(
            self.messages(), ["settings: missing, using the defaults"]
        )

    def test_settings_not_a_table(self):
        self.restore({"format": 1, "settings": 1})
        self.assertEqual(
            self.messages(),
            ["settings: is not a table, using the defaults"],
        )

    def test_partial_settings(self):
        _, project_settings = self.restore(
            {"format": 1, "settings": {"allow_female_plugs": True, "color": 1}}
        )
        self.assertTrue(project_settings.allow_female_plugs)
        self.assertEqual(project_settings.qemu_path, "/usr/bin")
        self.assertIn(
            'settings.qemu_path: missing, using the default "/usr/bin"',
            self.messages(),
        )
        self.assertIn(
            "settings.color: unknown field, dropped", self.messages()
        )

    def test_retired_settings(self):
        # every project written before private copies were always qcow2,
        # and before a loop of links always stopped a start
        settings = {"cow_format": "qcow", "log_link_loops": True}
        _, project_settings = self.restore(
            {"format": 1, "settings": {**settings, "vde_path": "/v"}}
        )
        self.assertEqual(project_settings.vde_path, "/v")
        # read without a word; the other missing settings are reported
        for key in settings:
            self.assertFalse([m for m in self.messages() if key in m])

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
        self.assertEqual([i.name for i in factory.images], ["one"])
        self.assertEqual(
            self.messages(),
            [
                "images.empty: has no path, image dropped",
                "images.same: uses the file of another image, image dropped",
                f"images.1bad: {path}2 not found, kept in the library",
                "images.1bad: A name starts with a letter, image dropped",
            ],
        )

    def test_events(self):
        data = {
            "format": 1,
            "settings": {},
            "events": {
                "1bad": {},
                "ok": {"icon": "", "delay": 1, "actions": []},
            },
        }
        factory, _ = self.restore(data)
        self.assertEqual([e.name for e in factory.events], ["ok"])
        self.assertEqual(len(self.messages()), 1)

    def test_bricks(self):
        data = self.lab()
        data["bricks"]["x"] = {"type": 3}
        data["bricks"]["y"] = {"type": "spaceship"}
        data["bricks"]["1bad"] = {"type": "switch"}
        data["bricks"]["sw1"]["ports"] = 500
        data["bricks"]["sw1"]["color"] = "red"
        factory, _ = self.restore(data)
        self.assertIsNone(factory.get_brick("x"))
        self.assertIsNone(factory.get_brick("y"))
        self.assertEqual(factory.get_brick("sw1").config.ports, 32)
        messages = self.messages()
        self.assertIn(
            "bricks.sw1.ports: 500 is outside 1–128, using the default 32",
            messages,
        )
        self.assertIn("bricks.sw1.color: unknown field, dropped", messages)
        self.assertEqual(
            sum(1 for m in messages if m.endswith("brick dropped")), 3
        )
        # read, they are heard again
        changed = []
        factory.brick_changed.connect(changed.append)
        sw1 = factory.get_brick("sw1")
        sw1.changed.notify(sw1)
        self.assertEqual(changed, [sw1])

    def test_bricks_heard_after_a_failure(self):
        data = self.lab()
        factory = make_factory(self)

        def fail(*args):
            raise RuntimeError("a bug")

        self.patch(projectfile, "_connect", fail)
        self.assertRaises(
            RuntimeError, restore_project, factory, data, self.report, "/"
        )
        bricks = list(factory.bricks)
        self.assertTrue(bricks)
        changed = []
        factory.brick_changed.connect(changed.append)
        for brick in bricks:
            brick.changed.notify(brick)
        self.assertEqual(changed, bricks)

    def test_connections(self):
        data = self.lab()
        bricks = data["bricks"]
        bricks["tap0"]["connect"] = 3
        bricks["cap"]["connect"] = "nowhere"
        bricks["wan"]["endpoints"] = ["sw1"]
        bricks["w"]["endpoints"] = ["vm", "vm:sock_eth9"]
        bricks["tl"]["connect"] = "wr:nope"
        factory, _ = self.restore(data)
        self.assertIsNone(factory.get_brick("tap0").plugs[0].sock)
        self.assertEqual(
            [p.sock for p in factory.get_brick("wan").plugs],
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
            resolve_socket(self.factory, "vm:sock_eth3").brick,
            self.factory.get_brick("vm"),
        )
        self.assertIsNone(resolve_socket(self.factory, "sw1:sock_eth3"))

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
        vm = factory.get_brick("vm")
        self.assertEqual(len(vm.plugs), 3)
        self.assertEqual(vm.plugs[0].model, "rtl8139")
        self.assertEqual([s.nickname for s in vm.socks], ["vm_sock_eth0"])
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
            "bricks.vm.nics[4]: name: missing or invalid, using sock_eth0",
            messages,
        )
        self.assertIn(
            "bricks.vm.nics[5].vlan: unknown field, dropped", messages
        )
        self.assertEqual(sum(1 for m in messages if "mac: " in m), 2)

    def test_socket_cards_of_one_name(self):
        data = self.lab()
        data["bricks"]["vm"]["nics"] = [
            {
                "kind": "socket",
                "name": "sock_eth1",
                "mac": "00:aa:00:00:00:01",
            },
            {
                "kind": "socket",
                "name": "sock_eth1",
                "mac": "00:aa:00:00:00:02",
            },
            {"kind": "socket", "mac": "00:aa:00:00:00:03"},
            {
                "kind": "socket",
                "name": "sock_eth0",
                "mac": "00:aa:00:00:00:04",
            },
        ]
        data["bricks"]["w"]["endpoints"] = ["vm:sock_eth1", "vm:sock_eth0"]
        factory, _ = self.restore(data)
        vm = factory.get_brick("vm")
        self.assertEqual(
            [(sock.nickname, sock.mac) for sock in vm.socks],
            [
                ("vm_sock_eth1", "00:aa:00:00:00:01"),
                ("vm_sock_eth2", "00:aa:00:00:00:02"),
                ("vm_sock_eth3", "00:aa:00:00:00:03"),
                ("vm_sock_eth0", "00:aa:00:00:00:04"),
            ],
        )
        # the first card of a name keeps what plugs into it
        self.assertEqual(
            [plug.sock.mac for plug in factory.get_brick("w").plugs],
            ["00:aa:00:00:00:01", "00:aa:00:00:00:04"],
        )
        messages = self.messages()
        self.assertIn(
            "bricks.vm.nics[1]: name: sock_eth1 is another card's, using "
            "sock_eth2",
            messages,
        )
        self.assertIn(
            "bricks.vm.nics[2]: name: missing or invalid, using sock_eth3",
            messages,
        )
        saved = project_document(factory, ProjectSettings())
        self.assertEqual(
            [nic["name"] for nic in saved["bricks"]["vm"]["nics"]],
            ["sock_eth1", "sock_eth2", "sock_eth3", "sock_eth0"],
        )

    def test_nics_not_a_list(self):
        data = self.lab()
        data["bricks"]["vm"]["nics"] = "none"
        factory, _ = self.restore(data)
        self.assertEqual(factory.get_brick("vm").plugs, [])
        self.assertIn(
            "bricks.vm: nics: is not a list, cards dropped", self.messages()
        )

    def test_missing_connections(self):
        data = self.lab()
        del data["bricks"]["wan"]["endpoints"]
        del data["bricks"]["tap0"]["connect"]
        del data["bricks"]["vm"]["nics"]
        factory, _ = self.restore(data)
        self.assertEqual(factory.get_brick("vm").plugs, [])
        self.assertIsNone(factory.get_brick("tap0").plugs[0].sock)

    def test_dangling_references(self):
        data = self.lab()
        del data["images"]
        del data["events"]
        data["bricks"]["sw1"]["on_stop"] = "down"
        self.restore(data)
        messages = self.messages()
        self.assertIn('bricks.sw1.on_start: no event named "boot"', messages)
        self.assertIn('bricks.sw1.on_stop: no event named "down"', messages)
        self.assertIn(
            'bricks.vm.disks.hda.image: no image named "deb"', messages
        )

    def test_event_references(self):
        data = self.lab()
        data["events"]["boot"]["actions"] = []
        self.restore(data)
        self.assertNotIn("events", " ".join(self.messages()))


class TestSockNames(unittest.TestCase):

    def test_free(self):
        self.assertEqual(free_sock_name(set()), "sock_eth0")
        self.assertEqual(
            free_sock_name({"sock_eth0", "sock_eth2", "sock_eth1x"}),
            "sock_eth1",
        )

    def test_unique(self):
        self.assertEqual(unique_sock_names([]), [])
        self.assertEqual(
            unique_sock_names(["lan", "sock_eth0", "lan", None, "sock_eth0"]),
            ["lan", "sock_eth0", "sock_eth1", "sock_eth2", "sock_eth3"],
        )

    def test_a_card_after_keeps_its_name(self):
        self.assertEqual(
            unique_sock_names([None, "sock_eth0"]), ["sock_eth1", "sock_eth0"]
        )


class TestRead(ProjectFileTestCase):

    def test_not_toml(self):
        path = self.mktemp()
        with open(path, "w") as fp:
            fp.write("[bricks\n")
        self.assertRaises(ProjectFormatError, read_project_file, path)

    def test_missing(self):
        self.assertRaises(FileNotFoundError, read_project_file, self.mktemp())


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
        self.assertEqual(image_paths(self.DATA), {"deb": "/a", "nopath": ""})
        self.assertEqual(image_paths({}), {})

    def test_remap_image(self):
        data = copy.deepcopy(self.DATA)
        remap_image(data, "deb", "/b")
        remap_image(data, "missing", "/c")
        remap_image(data, "bad", "/c")
        self.assertEqual(data["images"]["deb"]["path"], "/b")
        self.assertEqual(data["images"]["bad"], 1)

    def test_devices_for_image(self):
        self.assertEqual(
            list(devices_for_image(self.DATA, "deb")),
            [("vm", "hda")],
        )
        self.assertEqual(list(devices_for_image({}, "deb")), [])


class TestTheOldCommands(ProjectFileTestCase):
    """The commands of the old console in the events of 2.1."""

    def test_each_form(self):
        bricks, events = {"sw1", "vm1"}, {"boot"}
        for text, action in (
            ("sw1 on", {"kind": "start", "target": "sw1"}),
            ("boot off", {"kind": "stop", "target": "boot"}),
            # a brick that is gone
            ("sw9 on", {"kind": "start", "target": "sw9"}),
            ("brick sw1 on", {"kind": "start", "target": "sw1"}),
            (
                "vm1 config memory=512 cpus=2",
                {
                    "kind": "console",
                    "command": "brick set vm1 memory=512 cpus=2",
                },
            ),
            (
                "boot config delay=5",
                {"kind": "console", "command": "event set boot delay=5"},
            ),
            ("sw1 remove", {"kind": "console", "command": "brick delete sw1"}),
            ("boot show", {"kind": "console", "command": "event show boot"}),
            (
                "vm1 connect sw1_port",
                {"kind": "console", "command": "brick connect vm1 sw1"},
            ),
            (
                "vm1 disconnect",
                {"kind": "console", "command": "brick disconnect vm1"},
            ),
            (
                "new switch sw3",
                {"kind": "console", "command": "brick new switch sw3"},
            ),
            (
                "n event later",
                {"kind": "console", "command": "event new later"},
            ),
            (
                "config set terminal /usr/bin/xterm",
                {
                    "kind": "console",
                    "command": "setting set terminal=/usr/bin/xterm",
                },
            ),
            ("ps", {"kind": "console", "command": "status"}),
            ("quit", {"kind": "console", "command": "quit"}),
            ("images list", {"kind": "console", "command": "image list"}),
        ):
            self.assertEqual(
                projectfile.old_action(text, bricks, events),
                (action, True),
                text,
            )

    def test_what_the_console_doesnt_read(self):
        for text in ("reset", "socks", "sw1 on now", "python"):
            self.assertEqual(
                projectfile.old_action(text, {"sw1"}, set()),
                ({"kind": "console", "command": text}, False),
            )
