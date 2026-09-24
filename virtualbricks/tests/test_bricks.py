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


"""The bricks: their configuration, events and command line."""

import os


from virtualbricks import errors
from virtualbricks.bricks import BrickConfig
from virtualbricks.config import schema
from virtualbricks.config.report import Report
from virtualbricks.tests import (
    BrickTestCase,
)


class TestBase(BrickTestCase):

    def test_get_and_set(self):
        switch = self.factory.new_brick("switch", "sw")
        calls = []
        switch.cbset_numports = calls.append
        switch.set({"numports": 16, "hub": False})
        self.assertEqual(switch.get("numports"), 16)
        self.assertEqual(calls, [16])
        self.assertRaises(KeyError, switch.get, "nope")
        self.assertRaises(KeyError, switch.set, {"nope": 1})
        self.assertRaises(ValueError, switch.set, {"numports": 500})

    def test_configure_from_the_console(self):
        switch = self.factory.new_brick("switch", "sw")
        switch.configure(["numports=8", "fstp=yes"])
        self.assertEqual(switch.config.numports, 8)
        self.assertIs(switch.config.fstp, True)
        self.assertRaises(KeyError, switch.configure, ["nope=1"])
        self.assertRaises(ValueError, switch.configure, ["numports=x"])

    def test_config_table(self):
        tap = self.factory.new_brick("tap", "tap0")
        tap.set({"mode": "manual"})
        table = tap.config_table()
        self.assertEqual(table["mode"], "manual")
        report = Report()
        tap.load_config_table(
            {**table, "ip": "10.1.1.1", "type": "tap"}, report, "t", {"type"}
        )
        self.assertEqual(tap.config.ip, "10.1.1.1")
        self.assertEqual(len(report), 0)

    def test_runtime_paths(self):
        switch = self.factory.new_brick("switch", "sw")
        self.assertEqual(
            switch.path(), os.path.join(self.factory.runtime_dir, "sw.ctl")
        )
        self.assertEqual(
            switch.console(), os.path.join(self.factory.runtime_dir, "sw.mgmt")
        )
        self.assertEqual(switch.socks[0].path, switch.path())
        self.factory.rename(switch, "sw2")
        self.assertEqual(switch.socks[0].nickname, "sw2_port")
        self.assertEqual(
            switch.socks[0].path,
            os.path.join(self.factory.runtime_dir, "sw2.ctl"),
        )


class TestCommandLine(BrickTestCase):

    def test_typed_values(self):
        switch = self.factory.new_brick("switch", "sw")
        switch.command_builder = {
            "-x": "hub",
            "-n": "numports",
            "-F": "fstp",
            "-m": "mode",
            "#skipped": "numports",
            "-s": lambda: "/tmp/sw",
            "-e": lambda: "",
            "-M": lambda: "*",
            "*plain": lambda: "value",
            "-z": None,
        }
        self.assertEqual(
            switch.build_cmd_line(),
            ["-n", "32", "-s", "/tmp/sw", "-M", "value"],
        )
        switch.set({"hub": True, "fstp": True})
        self.assertEqual(
            switch.build_cmd_line(),
            ["-x", "-n", "32", "-F", "-s", "/tmp/sw", "-M", "value"],
        )

    def test_switch(self):
        switch = self.factory.new_brick("switch", "sw")
        switch.set({"numports": 8, "hub": True})
        line = switch.build_cmd_line()
        self.assertEqual(line[:3], ["-x", "-n", "8"])
        self.assertIn("-s", line)

    def test_capture_and_tunnels(self):
        capture = self.factory.new_brick("capture", "cap")
        capture.set({"iface": "eth0"})
        self.assertEqual(capture.build_cmd_line(), ["eth0"])
        connect = self.factory.new_brick("tunnelconnect", "tc")
        connect.set({"host": "example.org"})
        self.assertEqual(
            connect.build_cmd_line(), ["-p", "10771", "-c", "example.org:7667"]
        )
        self.assertEqual(connect.get_host(), "example.org:7667")


class TestSchemas(BrickTestCase):

    def test_every_brick_has_the_events(self):
        for kind in (
            "switch",
            "switchwrapper",
            "tap",
            "capture",
            "wire",
            "netemu",
            "tunnellisten",
            "tunnelconnect",
            "router",
            "qemu",
        ):
            brick = self.factory.new_brick(kind, kind + "1")
            self.assertIsInstance(brick.config, BrickConfig)
            self.assertEqual(brick.config.pon_vbevent, "")

    def test_limits(self):
        tap = self.factory.new_brick("tap", "tap0")
        self.assertRaises(ValueError, tap.set, {"mode": "static"})
        self.assertRaises(ValueError, tap.set, {"ip": "10.0.0"})
        tap.set({"gw": ""})
        listen = self.factory.new_brick("tunnellisten", "tl")
        self.assertRaises(ValueError, listen.set, {"port": 0})
        vm = self.factory.new_brick("qemu", "vm")
        self.assertRaises(ValueError, vm.set, {"ram": 0})

    def test_tunnel_parameters(self):
        listen = self.factory.new_brick("tunnellisten", "tl")
        sw = self.factory.new_brick("switch", "sw")
        self.assertEqual(listen.get_parameters(), "disconnected")
        listen.connect(sw.socks[0])
        self.assertIn("7667", listen.get_parameters())

    def test_switch_wrapper(self):
        wrapper = self.factory.new_brick("switchwrapper", "wr")
        wrapper.set({"path": "/nonexistent"})
        self.assertEqual(wrapper.get_parameters(), "/nonexistent")
        failure = self.failureResultOf(wrapper.poweron())
        failure.trap(errors.BadConfigError)
        path = self.mktemp()
        os.makedirs(path)
        wrapper.set({"path": path})
        self.assertIs(self.successResultOf(wrapper.poweron()), wrapper)

    def test_router_has_no_name_field(self):
        router = self.factory.new_brick("router", "r")
        self.assertNotIn("name", schema.names(router.config))
        self.assertEqual(router.build_cmd_line()[0], "-M")


class TestRelatedEvents(BrickTestCase):

    def test_related_events(self):
        switch = self.factory.new_brick("switch", "sw")
        event = self.factory.new_event("boot")
        started = []
        event.poweron = lambda: started.append("boot")
        switch._start_related_events(on=True)
        self.assertEqual(started, [])
        switch.set({"pon_vbevent": "boot", "poff_vbevent": "gone"})
        switch._start_related_events(on=True)
        self.assertEqual(started, ["boot"])
        switch._start_related_events(on=False, off=True)
        self.assertEqual(started, ["boot"])
