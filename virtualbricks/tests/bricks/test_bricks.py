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


"""The bricks: their configuration, events and command line."""

import os

from twisted.internet import defer, task
from twisted.trial import unittest

from virtualbricks import bricks, errors
from virtualbricks.bricks import (
    BaseConfig,
    BrickConfig,
    brickinfo,
    terminal_command,
)
from virtualbricks.bricks.brickinfo import State
from virtualbricks.bricks.eventaction import StartAction
from virtualbricks.config import settings
from virtualbricks.config.report import Report
from virtualbricks.config.schema import field_names, info_of, kind_of
from virtualbricks.tests import (
    BrickTestCase,
)


class TestBase(BrickTestCase):

    def test_plugs_and_socks_of_the_links(self):
        switch = self.factory.new_brick("switch", "sw")
        wire = self.factory.new_brick("wire", "w")
        self.assertEqual(len(switch.links), 1)
        self.assertEqual((switch.plugs, switch.socks), ([], switch.links))
        self.assertEqual(len(wire.links), 2)
        self.assertEqual((wire.plugs, wire.socks), (wire.links, []))
        # each time a new list: the brick keeps its links
        wire.plugs.clear()
        self.assertEqual(len(wire.plugs), 2)

    def test_update_config(self):
        switch = self.factory.new_brick("switch", "sw")
        calls = []
        switch.cbset_ports = calls.append
        switch.update_config({"ports": 16, "hub_mode": False})
        self.assertEqual(switch.config.ports, 16)
        self.assertEqual(calls, [16])
        self.assertRaises(KeyError, switch.update_config, {"nope": 1})
        self.assertRaises(ValueError, switch.update_config, {"ports": 500})

    def test_update_config_all_or_none(self):
        # a bad value, or a name the config doesn't have, after a good one:
        # nothing changes, nothing goes to the program, no one is told
        switch = self.factory.new_brick("switch", "sw")
        calls = []
        changed = []
        switch.cbset_ports = calls.append
        switch.changed.connect(changed.append)
        with self.assertRaisesRegex(ValueError, "^hub_mode: "):
            switch.update_config({"ports": 16, "hub_mode": "maybe"})
        self.assertRaises(
            KeyError, switch.update_config, {"ports": 16, "nope": 1}
        )
        self.assertEqual(switch.config.ports, 32)
        self.assertEqual((calls, changed), ([], []))

    def test_setters_see_the_new_config(self):
        # every value is set before the first setter runs
        switch = self.factory.new_brick("switch", "sw")
        seen = []
        switch.cbset_ports = lambda ports: seen.append(switch.config.hub_mode)
        switch.update_config({"ports": 16, "hub_mode": True})
        self.assertEqual(seen, [True])

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


class TestLoop(BrickTestCase):

    def ring(self, *names):
        """Machines, each plugged into a socket card of the next one."""

        vms = [self.factory.new_brick("qemu", name) for name in names]
        for vm, after in zip(vms, vms[1:] + vms[:1]):
            vm.add_plug(after.add_sock())
        return vms

    def slow_switch(self, name):
        """A switch whose start goes on until the test ends."""

        switch = self.factory.new_brick("switch", name)
        os.makedirs(os.path.dirname(switch.socks[0].path), exist_ok=True)
        switch.prepare = lambda resume="": defer.Deferred()
        return switch

    def assertLoop(self, deferred, message):
        error = self.failureResultOf(deferred, errors.LinkLoopError)
        self.assertEqual(error.getErrorMessage(), message)

    def test_a_loop_stops_the_start(self):
        # vm2 starts first, for vm1, and asks for vm1 again
        vm1, vm2 = self.ring("vm1", "vm2")
        self.assertLoop(
            vm1.start(),
            "Cannot start 'vm1': its links make a loop, vm1 → vm2 → vm1",
        )
        self.assertFalse(vm1.starting())
        self.assertFalse(vm2.starting())
        # and again, not waiting for the start that failed
        self.assertLoop(
            vm2.start(),
            "Cannot start 'vm2': its links make a loop, vm2 → vm1 → vm2",
        )

    def test_every_brick_of_the_loop(self):
        vm1, _, _ = self.ring("vm1", "vm2", "vm3")
        self.assertLoop(
            vm1.start(),
            "Cannot start 'vm1': its links make a loop, vm1 → vm2 → vm3 → vm1",
        )

    def test_only_the_bricks_of_the_loop(self):
        # a wire into the cards of the machines of a loop: not on it
        vm1, vm2 = self.ring("vm1", "vm2")
        wire = self.factory.new_brick("wire", "wire1")
        wire.connect(vm1.add_sock())
        wire.connect(vm2.add_sock())
        self.assertLoop(
            wire.start(),
            "Cannot start 'vm1': its links make a loop, vm1 → vm2 → vm1",
        )

    def test_two_links_to_one_brick_are_no_loop(self):
        sw1 = self.slow_switch("sw1")
        vm1 = self.factory.new_brick("qemu", "vm1")
        vm1.add_plug(sw1.socks[0])
        vm1.add_plug(sw1.socks[0])
        self.assertNoResult(vm1.start())
        self.assertTrue(sw1.starting())

    def test_no_loop_while_a_brick_it_plugs_into_starts(self):
        # a wire between a switch and a switch wrapper with no switch yet
        sw1 = self.slow_switch("sw1")
        sw2 = self.factory.new_brick("switchwrapper", "sw2")
        sw2.cbset_socket_path(self.mktemp())
        wire = self.factory.new_brick("wire", "wire1")
        wire.connect(sw1.socks[0])
        wire.connect(sw2.socks[0])
        self.failureResultOf(wire.start(), errors.BadConfigError)
        # started again while the switch starts: no loop, still no switch
        self.assertTrue(sw1.starting())
        self.failureResultOf(wire.start(), errors.BadConfigError)


class FakeProcess:
    pid = 41301

    def __init__(self, brick):
        self.brick = brick
        self.signals = []

    def signal_process(self, signal):
        self.signals.append(signal)


class TestCallOff(BrickTestCase):
    """A stop that comes while the brick starts."""

    def setUp(self):
        super().setUp()
        # a switch can start once the folder of its socket is there
        os.makedirs(self.factory.runtime_dir)
        self.spawned = []
        self.prepared = []

    def slow(self, kind, name):
        """A brick whose start waits for the Deferred of each prepare()."""

        brick = self.factory.new_brick(kind, name)

        def prepare(resume=""):
            self.prepared.append(name)
            deferred = defer.Deferred()
            brick.waits_for = deferred
            return deferred

        brick.prepare = prepare
        brick.command = lambda prepared: name
        brick.spawn = lambda command: self.spawn(brick)
        return brick

    def quick(self, kind, name):
        brick = self.slow(kind, name)
        brick.prepare = lambda resume="": defer.succeed(None)
        return brick

    def spawn(self, brick):
        self.spawned.append(brick.name)
        brick.proc = FakeProcess(brick)
        brick.process_started(brick.proc)

    def test_its_program_doesnt_run(self):
        sw = self.slow("switch", "sw1")
        started = sw.start()
        stopped = sw.stop()
        self.assertTrue(sw.starting())
        # the stop answers once the start ended
        self.assertNoResult(stopped)
        sw.waits_for.callback(None)
        error = self.failureResultOf(started, errors.StartCalledOffError)
        self.assertEqual(
            error.getErrorMessage(),
            "Cannot start 'sw1': stopped before it ran",
        )
        self.assertEqual(self.successResultOf(stopped), (sw, None))
        self.assertEqual(self.spawned, [])
        self.assertFalse(sw.starting())
        self.assertFalse(bricks.must_stop(sw))

    def test_kill(self):
        sw = self.slow("switch", "sw1")
        started = sw.start()
        stopped = sw.stop(kill=True)
        sw.waits_for.callback(None)
        self.failureResultOf(started, errors.StartCalledOffError)
        self.assertEqual(self.successResultOf(stopped), (sw, None))
        self.assertEqual(self.spawned, [])

    def test_the_bricks_it_plugs_into_start(self):
        # and its own prepare() is skipped
        sw1 = self.slow("switch", "sw1")
        sw2 = self.quick("switch", "sw2")
        wire = self.slow("wire", "wire1")
        wire.connect(sw1.socks[0])
        wire.connect(sw2.socks[0])
        started = wire.start()
        stopped = wire.stop()
        self.assertEqual(self.spawned, ["sw2"])
        sw1.waits_for.callback(None)
        self.failureResultOf(started, errors.StartCalledOffError)
        self.successResultOf(stopped)
        self.assertEqual(self.spawned, ["sw2", "sw1"])
        self.assertEqual(self.prepared, ["sw1"])

    def test_a_start_after_the_stop_fails_too(self):
        # the stop wins: a start then waits for the start under way
        sw = self.slow("switch", "sw1")
        first = sw.start()
        stopped = sw.stop()
        again = sw.start()
        sw.waits_for.callback(None)
        self.failureResultOf(first, errors.StartCalledOffError)
        self.failureResultOf(again, errors.StartCalledOffError)
        self.successResultOf(stopped)
        self.assertEqual(self.spawned, [])

    def test_the_next_start_runs(self):
        sw = self.slow("switch", "sw1")
        self.failureResultOf(self.called_off(sw), errors.StartCalledOffError)
        started = sw.start()
        sw.waits_for.callback(None)
        self.assertIs(self.successResultOf(started), sw)
        self.assertEqual(self.spawned, ["sw1"])

    def called_off(self, brick):
        started = brick.start()
        brick.stop()
        brick.waits_for.callback(None)
        return started

    def test_a_start_that_fails_on_its_own(self):
        # the stop answers all the same: nothing runs
        sw = self.slow("switch", "sw1")
        started = sw.start()
        stopped = sw.stop()
        sw.waits_for.errback(errors.BadConfigError("no vde_switch"))
        self.failureResultOf(started, errors.BadConfigError)
        self.assertEqual(self.successResultOf(stopped), (sw, None))

    def test_a_program_that_runs_all_the_same_stops(self):
        # a stop that comes after the last look at the flag
        sw = self.slow("switch", "sw1")

        def command(prepared):
            stopped.append(sw.stop())
            return "sw1"

        stopped = []
        sw.command = command
        started = sw.start()
        sw.waits_for.callback(None)
        self.successResultOf(started)
        self.assertEqual(sw.proc.signals, ["TERM"])
        sw.process_ended(sw.proc, "TERM")
        self.assertEqual(self.successResultOf(stopped[0]), (sw, "TERM"))

    def test_a_machine_gets_no_powerdown(self):
        vm = self.slow("qemu", "vm1")
        sent = []
        vm.send = sent.append
        started = vm.start()
        stopped = vm.stop()
        vm.waits_for.callback(None)
        self.failureResultOf(started, errors.StartCalledOffError)
        self.assertEqual(self.successResultOf(stopped), (vm, None))
        self.assertEqual((self.spawned, sent), ([], []))

    def test_changes(self):
        # the windows see the start begin, and end
        sw = self.slow("switch", "sw1")
        states = []
        sw.changed.connect(lambda brick: states.append(brickinfo.state(brick)))
        self.failureResultOf(self.called_off(sw))
        self.assertEqual(states, [State.STARTING, State.STOPPED])
        del states[:]
        sw.start()
        sw.waits_for.callback(None)
        self.assertEqual(states, [State.STARTING, State.RUNNING])
        # a start refused doesn't begin
        del states[:]
        wire = self.factory.new_brick("wire", "wire1")
        wire.changed.connect(states.append)
        self.failureResultOf(wire.start(), errors.BadConfigError)
        self.assertEqual(states, [])


class TestStarting(BrickTestCase):
    """A brick that is starting has to stop, as one that runs."""

    def setUp(self):
        super().setUp()
        os.makedirs(self.factory.runtime_dir)
        self.sw = self.factory.new_brick("switch", "sw1")
        self.sw.prepare = lambda resume="": defer.Deferred()
        self.sw.start()

    def test_must_stop(self):
        self.assertTrue(bricks.must_stop(self.sw))
        self.assertFalse(bricks.is_running(self.sw))

    def test_quit_and_close_are_refused(self):
        self.assertRaises(errors.BrickRunningError, self.factory.quit)
        self.assertRaises(errors.BrickRunningError, self.factory.reset)

    def test_delete_is_refused(self):
        self.assertRaises(
            errors.BrickRunningError, self.factory.remove_brick, self.sw
        )
        self.assertIs(self.factory.get_brick("sw1"), self.sw)


class TestRestart(BrickTestCase):

    def setUp(self):
        super().setUp()
        self.clock = task.Clock()
        self.done = []
        self.stopped = defer.Deferred()
        self.vm = self.factory.new_brick("qemu", "vm")

        def stop(**kwargs):
            self.done.append(("off", kwargs))
            return self.stopped

        self.vm.stop = stop
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


VDETERM = ["/usr/bin/vdeterm", "/run/vb/lab/sw1.mgmt"]


class TestTerminalCommand(unittest.TestCase):
    """The line of the terminal that opens a console (page 32)."""

    def line(self, setting, command=VDETERM, name="sw1"):
        return terminal_command(setting, command, name)

    def test_the_place_of_the_console(self):
        self.assertEqual(
            self.line("gnome-terminal -- {command}"),
            ["gnome-terminal", "--", *VDETERM],
        )
        # the words split as the shell splits them, without a shell
        self.assertEqual(
            self.line("xterm -fa 'DejaVu Sans Mono' -e {command}"),
            ["xterm", "-fa", "DejaVu Sans Mono", "-e", *VDETERM],
        )

    def test_without_the_place(self):
        # -e at the end, as the terminal used to be run
        self.assertEqual(self.line("xterm"), ["xterm", "-e", *VDETERM])
        self.assertEqual(
            self.line("/usr/bin/xterm -hold"),
            ["/usr/bin/xterm", "-hold", "-e", *VDETERM],
        )

    def test_inside_a_word(self):
        # the console quoted for the shell, which reads that word
        command = ["/usr/bin/vdeterm", "/run/my lab/sw1.mgmt"]
        self.assertEqual(
            self.line("foot sh -c '{command}; read'", command),
            [
                "foot",
                "sh",
                "-c",
                "/usr/bin/vdeterm '/run/my lab/sw1.mgmt'; read",
            ],
        )

    def test_in_quotes(self):
        # one word, as the shell keeps a quoted word: for a terminal that
        # takes one string
        for setting in ("xfce4-terminal -e '{command}'", 'sh -c "{command}"'):
            self.assertEqual(
                self.line(setting)[-1], "/usr/bin/vdeterm /run/vb/lab/sw1.mgmt"
            )
        # quotes around a word that is the place only in part
        self.assertEqual(
            self.line("x {command}''"),
            ["x", "/usr/bin/vdeterm /run/vb/lab/sw1.mgmt"],
        )

    def test_the_name(self):
        self.assertEqual(
            self.line("xterm -T {name} -e {command}"),
            ["xterm", "-T", "sw1", "-e", *VDETERM],
        )
        self.assertEqual(
            self.line("kgx '--title=Console of {name}' -- {command}"),
            ["kgx", "--title=Console of sw1", "--", *VDETERM],
        )
        # the name isn't the place of the console
        self.assertEqual(
            self.line("xterm -T {name}"),
            ["xterm", "-T", "sw1", "-e", *VDETERM],
        )

    def test_other_braces(self):
        self.assertEqual(
            self.line("xterm -T {title} -e {command}"),
            ["xterm", "-T", "{title}", "-e", *VDETERM],
        )
        # what replaces a place isn't read again for places
        command = ["/usr/bin/vdeterm", "/run/{name}/sw1.mgmt"]
        self.assertEqual(
            self.line("sh -c 'exec {command}'", command),
            ["sh", "-c", "exec /usr/bin/vdeterm '/run/{name}/sw1.mgmt'"],
        )

    def test_no_line(self):
        for setting in ("", "  "):
            with self.assertRaisesRegex(errors.BadConfigError, "empty"):
                self.line(setting)
        with self.assertRaisesRegex(
            errors.BadConfigError, "^The setting terminal can't be read: "
        ):
            self.line("xterm -T 'sw1")


class FakeSpawner:
    def __init__(self):
        self.spawned = []

    def spawnProcess(self, protocol, executable, args, env):
        self.spawned.append((executable, args))


class TestOpenConsole(BrickTestCase):

    def setUp(self):
        super().setUp()
        self.folder = os.path.abspath(self.mktemp())
        os.makedirs(self.folder)
        for name in ("vdeterm", "unixterm"):
            path = os.path.join(self.folder, name)
            with open(path, "w") as fp:
                fp.write("#!/bin/sh\n")
            os.chmod(path, 0o755)
        settings.set_setting("vde_path", self.folder)
        self.reactor = FakeSpawner()
        self.patch(bricks, "_reactor", lambda: self.reactor)

    def test_the_line_of_the_setting(self):
        settings.set_setting("terminal", "xterm -T {name} -e {command}")
        switch = self.factory.new_brick("switch", "sw1")
        switch.open_console()
        vdeterm = os.path.join(self.folder, "vdeterm")
        self.assertEqual(
            self.reactor.spawned,
            [
                (
                    "xterm",
                    ["xterm", "-T", "sw1", "-e", vdeterm, switch.console()],
                )
            ],
        )

    def test_a_machine(self):
        vm = self.factory.new_brick("qemu", "vm1")
        vm.open_console()
        unixterm = os.path.join(self.folder, "unixterm")
        self.assertEqual(
            self.reactor.spawned,
            [
                (
                    "x-terminal-emulator",
                    ["x-terminal-emulator", "-e", unixterm, vm.console()],
                )
            ],
        )
