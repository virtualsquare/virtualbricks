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

from twisted.internet import defer, task

from virtualbricks import bricks, errors
from virtualbricks.bricks import BaseConfig
from virtualbricks.bricks import BrickConfig
from virtualbricks.bricks.eventaction import StartAction
from virtualbricks.config.report import Report
from virtualbricks.config.schema import field_names, info_of, kind_of
from virtualbricks.tests import (
    BrickTestCase,
)


class TestBase(BrickTestCase):

    def test_update_config(self):
        switch = self.factory.new_brick("switch", "sw")
        calls = []
        switch.cbset_ports = calls.append
        switch.update_config({"ports": 16, "hub_mode": False})
        self.assertEqual(switch.config.ports, 16)
        self.assertEqual(calls, [16])
        self.assertRaises(KeyError, switch.update_config, {"nope": 1})
        self.assertRaises(ValueError, switch.update_config, {"ports": 500})

    def test_muted(self):
        switch = self.factory.new_brick("switch", "sw")
        changed = []
        switch.changed.connect(changed.append)
        with switch.muted():
            switch.update_config({"ports": 16})
        self.assertEqual(changed, [])
        switch.update_config({"ports": 8})
        self.assertEqual(changed, [switch])

    def test_config_table(self):
        tap = self.factory.new_brick("tap", "tap0")
        tap.update_config({"address_mode": "manual"})
        table = tap.config_table()
        self.assertEqual(table["address_mode"], "manual")
        report = Report()
        tap.load_config_table(
            {**table, "ip_address": "10.1.1.1", "type": "tap"},
            report,
            "t",
            {"type"},
        )
        self.assertEqual(tap.config.ip_address, "10.1.1.1")
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
        self.factory.rename_item(switch, "sw2")
        self.assertEqual(switch.socks[0].nickname, "sw2_port")
        self.assertEqual(
            switch.socks[0].path,
            os.path.join(self.factory.runtime_dir, "sw2.ctl"),
        )


# The types of bricks.
KINDS = (
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
)


class TestSchemas(BrickTestCase):

    def test_every_brick_has_the_events(self):
        for kind in KINDS:
            brick = self.factory.new_brick(kind, kind + "1")
            self.assertIsInstance(brick.config, BrickConfig)
            self.assertEqual(brick.config.on_start, "")
            self.assertEqual(brick.config.on_stop, "")

    def test_every_brick_and_event_has_an_icon(self):
        event = self.factory.new_event("ev")
        vm = self.factory.new_brick("qemu", "vm")
        for item in (self.factory.new_brick("switch", "sw"), vm, event):
            self.assertIsInstance(item.config, BaseConfig)
            self.assertEqual(field_names(item.config)[0], "icon")
            self.assertEqual(item.config.icon, "")
        vm.update_config({"icon": "/usr/share/pixmaps/router.png"})
        self.assertEqual(vm.config.icon, "/usr/share/pixmaps/router.png")

    def test_what_goes_with_what(self):
        # a setting goes with another setting of its schema, and a value that
        # one takes
        declared = {}
        items = [self.factory.new_brick(kind, kind + "1") for kind in KINDS]
        for item in items + [self.factory.new_event("ev")]:
            names = field_names(item.config)
            for name in names:
                when = info_of(item.config, name).when
                if when is None:
                    continue
                other, value = when
                self.assertIn(other, names, (item.name, name))
                self.assertNotEqual(other, name)
                kind_of(item.config, other).check(value)
                declared[item.name] = declared.get(item.name, 0) + 1
        self.assertEqual(declared, {"tap1": 3, "netemu1": 4, "qemu1": 13})

    def test_limits(self):
        tap = self.factory.new_brick("tap", "tap0")
        self.assertRaises(
            ValueError, tap.update_config, {"address_mode": "static"}
        )
        self.assertRaises(
            ValueError, tap.update_config, {"ip_address": "10.0.0"}
        )
        tap.update_config({"gateway": ""})
        listen = self.factory.new_brick("tunnellisten", "tl")
        self.assertRaises(ValueError, listen.update_config, {"listen_port": 0})
        vm = self.factory.new_brick("qemu", "vm")
        self.assertRaises(ValueError, vm.update_config, {"memory": 0})

    def test_tunnel_configured(self):
        listen = self.factory.new_brick("tunnellisten", "tl")
        sw = self.factory.new_brick("switch", "sw")
        self.assertFalse(listen.configured())
        listen.connect(sw.socks[0])
        self.assertTrue(listen.configured())

    def test_switch_wrapper(self):
        wrapper = self.factory.new_brick("switchwrapper", "wr")
        wrapper.update_config({"socket_path": "/nonexistent"})
        failure = self.failureResultOf(wrapper.start())
        failure.trap(errors.BadConfigError)
        path = self.mktemp()
        os.makedirs(path)
        wrapper.update_config({"socket_path": path})
        self.assertIs(self.successResultOf(wrapper.start()), wrapper)

    def test_router_has_no_name_field(self):
        router = self.factory.new_brick("router", "r")
        self.assertNotIn("name", field_names(router.config))


class TestRelatedEvents(BrickTestCase):

    def test_related_events(self):
        switch = self.factory.new_brick("switch", "sw")
        event = self.factory.new_event("boot")
        event.update_config({"actions": [StartAction("sw")]})
        started = []
        event.start = lambda: started.append("boot")
        switch._start_related_events(on=True)
        self.assertEqual(started, [])
        switch.update_config({"on_start": "boot", "on_stop": "gone"})
        switch._start_related_events(on=True)
        self.assertEqual(started, ["boot"])
        switch._start_related_events(on=False, off=True)
        self.assertEqual(started, ["boot"])


class TestRestart(BrickTestCase):

    def setUp(self):
        super().setUp()
        self.clock = task.Clock()
        self.done = []
        self.stopped = defer.Deferred()
        self.vm = self.factory.new_brick("qemu", "vm")

        def poweroff(**kwargs):
            self.done.append(("off", kwargs))
            return self.stopped

        self.vm.poweroff = poweroff
        self.vm.start = lambda: self.done.append("on") or self.vm

    def test_stops_then_starts(self):
        # a virtual machine too: not an ACPI reset
        restarted = bricks.restart(self.vm, self.clock)
        self.assertEqual(self.done, [("off", {})])
        self.stopped.callback(None)
        self.assertEqual(self.done, [("off", {}), "on"])
        self.assertIs(self.successResultOf(restarted), self.vm)
        self.clock.advance(10)
        self.assertEqual(self.done, [("off", {}), "on"])

    def test_what_doesnt_stop_doesnt_start(self):
        restarted = bricks.restart(self.vm, self.clock)
        self.stopped.errback(RuntimeError("still running"))
        self.failureResultOf(restarted, RuntimeError)
        self.assertEqual(self.done, [("off", {})])

    def test_kills_what_doesnt_stop(self):
        # after two seconds, as the Running tab did
        bricks.restart(self.vm, self.clock)
        self.clock.advance(1.9)
        self.assertEqual(self.done, [("off", {})])
        self.clock.advance(0.1)
        self.assertEqual(self.done, [("off", {}), ("off", {"kill": True})])
        self.stopped.callback(None)
        self.assertEqual(self.done[-1], "on")
