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

"""
A program that follows the Virtualbricks of the bricks: the project, then
what changes, once a turn, before the answers.
"""

import json
import os

from twisted.internet import defer
from twisted.logger import LogLevel, LogPublisher
from twisted.protocols import amp
from twisted.python.failure import Failure
from twisted.test import iosim

from virtualbricks import __version__, locations
from virtualbricks.bricks import FakeProcess
from virtualbricks.bricks.eventaction import ShellAction
from virtualbricks.config import settings
from virtualbricks.console import ampcommands, ampwire, control, wire
from virtualbricks.programs import qemu_programs
from virtualbricks.remote import commands, follower
from virtualbricks.remote.follower import (
    LogKeeper,
    in_order,
    message_of,
    state_of,
    table_of,
)
from virtualbricks.tests import FakeLogger, use_workspace
from virtualbricks.tests.console import ConsoleTestCase


class Project:
    name = "lab1"
    path = "/lab/lab1"


class Program(amp.AMP):
    """A program that follows: what it gets, in the order it gets it."""

    def __init__(self):
        super().__init__()
        self.got = []

    @commands.Opened.responder
    def opened(self, project, settings, machine):
        self.got.append(
            ("Opened", project, json.loads(settings), json.loads(machine))
        )
        return {}

    @commands.Changed.responder
    def changed(self, kind, name, table, state):
        self.got.append(
            ("Changed", kind, name, json.loads(table), json.loads(state))
        )
        return {}

    @commands.Renamed.responder
    def renamed(self, kind, old, new):
        self.got.append(("Renamed", kind, old, new))
        return {}

    @commands.Removed.responder
    def removed(self, kind, name):
        self.got.append(("Removed", kind, name))
        return {}

    @commands.Synced.responder
    def synced(self):
        self.got.append(("Synced",))
        return {}

    @commands.SettingsChanged.responder
    def settings_changed(self, settings):
        self.got.append(("SettingsChanged", json.loads(settings)))
        return {}

    @commands.Logged.responder
    def logged(self, message):
        self.got.append(("Logged", json.loads(message)))
        return {}

    @commands.Quitting.responder
    def quitting(self):
        self.got.append(("Quitting",))
        return {}


def event(text, **fields):
    return dict(
        {
            "log_format": text,
            "log_level": LogLevel.info,
            "log_time": 1790000000.5,
            "log_namespace": "virtualbricks.bricks",
        },
        **fields,
    )


class FollowTestCase(ConsoleTestCase):
    """A program that agreed on protocol 2, and the connection it follows."""

    def setUp(self):
        super().setUp()
        self.factory.runtime_dir = "/run/vb"
        self.logger = FakeLogger()
        self.patch(control, "logger", self.logger)
        self.patch(follower, "logger", self.logger)
        self.patch(amp, "_log", FakeLogger())
        self.workspace = use_workspace(self)
        self.workspace.current = Project()
        self.keeper = LogKeeper()
        self.patch(follower, "keeper", self.keeper)
        self.server = control.ControlFactory(
            self.factory, self.clock(), control.AMPControl
        )
        self.program, self.connection, self.pump = (
            iosim.connectedServerAndClient(
                lambda: self.server.buildProtocol(None), Program
            )
        )

    def call(self, command, **arguments):
        """The answer to command, once the pump is done; the program notes it."""

        answer = defer.Deferred()
        called = self.program.callRemote(command, **arguments)

        def noted(result):
            self.program.got.append(("answer", command.commandName.decode()))
            return result

        called.addCallback(noted)
        called.chainDeferred(answer)
        self.pump.flush()
        return answer

    def follow(self):
        answer = self.call(ampwire.Hello, protocols=[2])
        self.assertEqual(self.successResultOf(answer)["protocol"], 2)
        self.got()
        return self.successResultOf(self.call(commands.Follow))

    def turn(self):
        """The end of the reactor's turn, and what it sends."""

        self.clock().advance(0)
        self.pump.flush()

    def got(self):
        """What the program got since the last time, by name."""

        got, self.program.got = self.program.got, []
        return got

    def names(self):
        return [item[0] for item in self.got()]


class TestFollow(FollowTestCase):

    def test_protocol_2_first(self):
        failure = self.failureResultOf(
            self.call(commands.Follow), ampcommands.ProtocolNeeded
        )
        self.assertIn("protocol 2", failure.getErrorMessage())
        self.assertEqual(self.got(), [])

    def test_the_project_then_the_answer(self):
        self.factory.new_image("frr", "/lab/frr.qcow2")
        self.factory.new_event("boot")
        switch = self.factory.new_brick("switch", "sw1")
        tap = self.factory.new_brick("tap", "tap1")
        tap.connect(switch.socks[0])
        self.got()
        answer = self.follow()
        self.assertEqual(answer, {"project": "lab1", "version": __version__})
        got = self.got()
        self.assertEqual(
            [item[:3] for item in got],
            [
                ("Opened", "lab1", got[0][2]),
                ("Changed", "image", "frr"),
                ("Changed", "brick", "sw1"),
                ("Changed", "brick", "tap1"),
                ("Changed", "event", "boot"),
                ("Synced",),
                ("answer", "Follow"),
            ],
        )
        _, _, table, machine = got[0]
        self.assertEqual(table["qemu_path"], settings.get_setting("qemu_path"))
        self.assertEqual(table["terminal"], settings.get_setting("terminal"))
        self.assertEqual(machine["version"], __version__)
        self.assertEqual(machine["runtime_dir"], "/run/vb")
        self.assertIn("Switch", machine["lacks"])
        self.assertEqual(machine["project_folder"], "/lab/lab1")
        # no windows there, no trash
        self.assertFalse(machine["trash"])
        self.assertEqual(
            machine["workspace_runtime_dir"],
            locations.workspace_runtime_dir(self.workspace.path),
        )
        self.assertEqual(
            machine["qemu_programs"],
            qemu_programs(settings.get_setting("qemu_path")),
        )
        self.assertEqual(
            got[1][3:],
            ({"path": "/lab/frr.qcow2", "description": ""}, {"file": None}),
        )
        self.assertEqual(got[3][3], table_of(tap))
        self.assertEqual(got[3][3]["connect"], "sw1")
        self.assertEqual(got[3][4], {"pid": None})
        self.assertEqual(got[4][4], {"left": None})

    def test_no_project_open(self):
        self.workspace.current = None
        answer = self.follow()
        self.assertEqual(answer["project"], None)
        self.assertEqual(self.got()[0][1], None)

    def test_a_brick_after_those_it_plugs_into(self):
        tap = self.factory.new_brick("tap", "tap1")
        wire = self.factory.new_brick("wire", "w1")
        switch = self.factory.new_brick("switch", "sw1")
        other = self.factory.new_brick("switch", "sw2")
        tap.connect(switch.socks[0])
        wire.connect(switch.socks[0])
        wire.connect(other.socks[0])
        self.follow()
        self.assertEqual(
            [item[2] for item in self.got() if item[0] == "Changed"],
            ["sw1", "tap1", "sw2", "w1"],
        )

    def test_again(self):
        self.follow()
        self.got()
        self.successResultOf(self.call(commands.Follow))
        self.assertEqual(self.names(), ["Opened", "Synced", "answer"])

    def test_the_checks_of_the_typed_commands(self):
        class FollowAll(amp.Command):
            commandName = b"Follow"
            arguments = [(b"all", amp.Unicode())]
            response = commands.Follow.response
            errors = ampcommands.ERRORS

        self.follow()
        failure = self.failureResultOf(
            self.call(FollowAll, all="yes"), ampcommands.BadArgument
        )
        self.assertEqual(
            failure.getErrorMessage(), "Follow has no argument all"
        )


class TestChanges(FollowTestCase):

    def setUp(self):
        super().setUp()
        self.switch = self.factory.new_brick("switch", "sw1")
        self.follow()
        self.got()

    def test_once_a_turn(self):
        self.switch.update_config({"ports": 8})
        self.switch.update_config({"hub_mode": True})
        self.factory.new_event("boot")
        self.switch.update_config({"ports": 16})
        self.pump.flush()
        self.assertEqual(self.got(), [])
        self.turn()
        got = self.got()
        self.assertEqual(
            [item[:3] for item in got],
            [("Changed", "brick", "sw1"), ("Changed", "event", "boot")],
        )
        self.assertEqual(got[0][3]["ports"], 16)
        self.assertTrue(got[0][3]["hub_mode"])
        self.turn()
        self.assertEqual(self.got(), [])

    def test_before_the_answer(self):
        self.call(ampwire.Hello, protocols=[2])
        self.got()
        self.call(ampcommands.BrickNew, kind="switch", name="sw2")
        self.assertEqual(
            [item[:3] for item in self.got()],
            [("Changed", "brick", "sw2"), ("answer", "BrickNew")],
        )

    def test_before_a_refusal(self):
        # what the command did, before it failed
        self.switch.update_config({"ports": 8})
        failure = self.failureResultOf(
            self.call(ampcommands.BrickStart, name=["nowhere"]),
            ampcommands.NotFound,
        )
        self.assertIn("nowhere", failure.getErrorMessage())
        self.assertEqual(self.names(), ["Changed"])

    def test_before_the_answer_of_run(self):
        self.call(ampwire.Run, line="brick new switch sw2")
        self.assertEqual(self.names(), ["Changed", "answer"])

    def test_a_rename(self):
        image = self.factory.new_image("frr", "/lab/frr.qcow2")
        vm = self.factory.new_brick("qemu", "vm1")
        vm.update_config({"hda_image": "frr"})
        self.turn()
        self.got()
        self.factory.rename_item(image, "debian")
        self.factory.rename_item(self.switch, "sw9")
        self.turn()
        got = self.got()
        self.assertEqual(
            [item[:4] for item in got],
            [
                ("Renamed", "image", "frr", "debian"),
                ("Renamed", "brick", "sw1", "sw9"),
                ("Changed", "image", "debian", got[2][3]),
                ("Changed", "brick", "vm1", got[3][3]),
                ("Changed", "brick", "sw9", got[4][3]),
            ],
        )
        self.assertEqual(got[3][3]["disks"]["hda"]["image"], "debian")

    def test_a_new_one_renamed(self):
        event = self.factory.new_event("boot")
        self.factory.rename_item(event, "up")
        self.turn()
        self.assertEqual(
            [item[:3] for item in self.got()], [("Changed", "event", "up")]
        )

    def test_a_delete(self):
        tap = self.factory.new_brick("tap", "tap1")
        tap.connect(self.switch.socks[0])
        self.turn()
        self.got()
        self.switch.update_config({"ports": 8})
        self.factory.remove_brick(self.switch)
        self.turn()
        # the tap is unplugged as the copy removes the switch too
        self.assertEqual(
            [item[:3] for item in self.got()], [("Removed", "brick", "sw1")]
        )

    def test_new_and_gone_in_a_turn(self):
        event = self.factory.new_event("boot")
        self.factory.remove_event(event)
        self.turn()
        self.assertEqual(self.got(), [])

    def test_gone_then_new_again(self):
        self.factory.remove_brick(self.switch)
        self.factory.new_brick("tap", "sw1")
        self.turn()
        got = self.got()
        self.assertEqual(
            [item[:3] for item in got],
            [("Removed", "brick", "sw1"), ("Changed", "brick", "sw1")],
        )
        self.assertEqual(got[1][3]["type"], "tap")

    def test_a_brick_that_runs(self):
        self.switch.proc = FakeProcess(self.switch)
        self.switch.changed.notify(self.switch)
        self.turn()
        self.assertEqual(self.got()[0][4], {"pid": -1})

    def test_a_machine_that_runs(self):
        # the files of its private copies, and its images again: it writes
        # them
        folder = os.path.abspath(self.mktemp())
        os.makedirs(folder)
        self.workspace.current.path = folder
        image = self.factory.new_image("frr", os.path.join(folder, "frr"))
        vm = self.factory.new_brick("qemu", "vm1")
        vm.update_config(
            {
                "hda_image": "frr",
                "hda_private": True,
                "hdb_image": "frr",
                "hdb_private": False,
            }
        )
        copy = vm.disk("hda").get_cow_path()
        with open(copy, "wb") as fp:
            fp.write(b"x" * 100)
        self.turn()
        self.got()
        vm.proc = FakeProcess(vm)
        vm.changed.notify(vm)
        self.turn()
        got = self.got()
        self.assertEqual(
            [item[:3] for item in got],
            [("Changed", "image", "frr"), ("Changed", "brick", "vm1")],
        )
        self.assertEqual(got[0][4], state_of(image))
        stat = os.stat(copy)
        self.assertEqual(
            got[1][4]["copies"],
            {
                "hda": {
                    "size": 100,
                    "mtime": stat.st_mtime_ns,
                    "taken": stat.st_blocks * 512,
                }
            },
        )

    def test_an_event_that_waits(self):
        event = self.factory.new_event("boot")
        event.update_config({"delay": 30, "actions": [ShellAction("true")]})
        event.start()
        self.addCleanup(event.stop)
        self.turn()
        [(_, _, _, _, state)] = self.got()
        self.assertGreater(state["left"], 29)
        self.assertLessEqual(state["left"], 30)

    def test_a_project_opened(self):
        # what waits goes: the whole project comes again
        self.switch.update_config({"ports": 8})
        self.workspace.opened.notify(self.workspace)
        self.factory.new_event("boot")
        self.turn()
        self.assertEqual(
            [
                item[:3] if item[0] == "Changed" else item[:2]
                for item in self.got()
            ],
            [
                ("Opened", "lab1"),
                ("Changed", "brick", "sw1"),
                ("Changed", "event", "boot"),
                ("Synced",),
            ],
        )

    def test_the_settings(self):
        settings.set_setting("audio_driver", "pa")
        settings.set_setting("terminal", "xterm")
        self.turn()
        got = self.got()
        self.assertEqual([item[0] for item in got], ["SettingsChanged"])
        self.assertEqual(got[0][1]["audio_driver"], "pa")
        self.assertEqual(got[0][1]["terminal"], "xterm")

    def test_quitting(self):
        self.factory.quit()
        self.pump.flush()
        self.assertEqual(self.names(), ["Quitting"])

    def test_the_connection_lost(self):
        self.program.transport.loseConnection()
        self.pump.flush()
        self.switch.update_config({"ports": 8})
        settings.set_setting("terminal", "xterm")
        self.keeper(event("after"))
        self.assertEqual(self.clock().getDelayedCalls(), [])
        self.assertEqual(self.keeper.listeners, [])

    def test_too_long(self):
        vm = self.factory.new_brick("qemu", "vm1")
        # not by update_config(), which logs it: trial -j carries the log
        # over AMP too
        vm.config.kernel = "/" + "k" * 70000
        vm.changed.notify(vm)
        self.factory.new_event("boot")
        self.turn()
        self.assertEqual(
            [item[:3] for item in self.got()], [("Changed", "event", "boot")]
        )
        self.assertEqual(
            self.logger.formatted(),
            [
                "Not sent to a program: Changed of vm1 is too long for AMP",
            ],
        )


class TestLog(FollowTestCase):

    def test_the_last_ones_first(self):
        for text in ("one", "two"):
            self.keeper(event(text))
        self.keeper(event("hidden", log_level=LogLevel.debug))
        self.follow()
        got = self.got()
        self.assertEqual(
            [item[0] for item in got][-4:],
            ["Synced", "Logged", "Logged", "answer"],
        )
        self.assertEqual(
            [item[1]["text"] for item in got if item[0] == "Logged"],
            ["one", "two"],
        )

    def test_the_next_ones(self):
        self.follow()
        self.got()
        self.keeper(event("three", log_level=LogLevel.warn))
        self.turn()
        [(name, message)] = self.got()
        self.assertEqual(message["text"], "three")
        self.assertEqual(message["level"], "warn")

    def test_as_many_as_it_keeps(self):
        keeper = LogKeeper(size=2)
        for text in ("one", "two", "three"):
            keeper(event(text))
        self.assertEqual(
            [message["text"] for message in keeper.messages], ["two", "three"]
        )

    def test_start_and_stop(self):
        publisher = LogPublisher()
        keeper = LogKeeper()
        # two sockets listen
        keeper.start(publisher)
        keeper.start(publisher)
        publisher(event("one"))
        keeper.stop()
        publisher(event("two"))
        keeper.stop()
        publisher(event("three"))
        keeper.stop()
        self.assertEqual(
            [message["text"] for message in keeper.messages], ["one", "two"]
        )
        self.assertEqual(publisher._observers, [])

    def test_from_a_thread(self):
        class Reactor:
            def callFromThread(self, call, *args):
                calls.append((call, args))

        calls = []
        keeper = LogKeeper(reactor=Reactor())
        keeper.thread = None
        keeper(event("far"))
        self.assertEqual(list(keeper.messages), [])
        [(call, args)] = calls
        call(*args)
        self.assertEqual(keeper.messages[0]["text"], "far")


class TestListening(ConsoleTestCase):
    """The log is kept while an AMP socket listens."""

    def setUp(self):
        super().setUp()
        self.keeper = LogKeeper()
        self.patch(follower, "keeper", self.keeper)
        self.patch(self.keeper, "start", lambda: self.started.append(True))
        self.patch(self.keeper, "stop", lambda: self.started.pop())
        self.started = []

    def control(self, protocol):
        class Port:
            def stopListening(self):
                pass

        server = control.ControlFactory(self.factory, self.clock())
        return control.Control(
            wire.Socket("/run/vb.amp", protocol), Port(), None, server
        )

    def test_amp(self):
        found = self.control(wire.AMP)
        self.assertEqual(self.started, [True])
        self.successResultOf(found.close())
        self.successResultOf(found.close())
        self.assertEqual(self.started, [])

    def test_text(self):
        found = self.control(wire.JSON)
        self.assertEqual(self.started, [])
        self.successResultOf(found.close())


class TestMessage(ConsoleTestCase):

    def test_a_message(self):
        self.assertEqual(
            message_of(event("sw1 {what}", what="started", pid=4242)),
            {
                "time": 1790000000.5,
                "level": "info",
                "stream": None,
                "namespace": "virtualbricks.bricks",
                "pid": 4242,
                "source": None,
                "source_type": None,
                "text": "sw1 started",
                "traceback": None,
            },
        )

    def test_the_output_of_a_brick(self):
        switch = self.factory.new_brick("switch", "sw1")
        message = message_of(
            event("vde$ ", stream="stdout", log_source=switch)
        )
        self.assertEqual(message["stream"], "stdout")
        self.assertEqual(
            (message["source"], message["source_type"]), ("sw1", "switch")
        )
        message = message_of(event("x", stream="other"))
        self.assertIsNone(message["stream"])

    def test_the_process_of_a_brick(self):
        switch = self.factory.new_brick("switch", "sw1")
        message = message_of(event("x", log_source=FakeProcess(switch)))
        self.assertEqual(message["source"], "sw1")

    def test_a_failure(self):
        try:
            1 / 0
        except ZeroDivisionError:
            failure = Failure()
        message = message_of(
            event("oops", log_level=LogLevel.critical, log_failure=failure)
        )
        self.assertEqual(message["level"], "critical")
        self.assertIn("ZeroDivisionError", message["traceback"])


class TestOrder(ConsoleTestCase):

    def test_images_bricks_events(self):
        boot = self.factory.new_event("boot")
        switch = self.factory.new_brick("switch", "sw1")
        image = self.factory.new_image("frr", "/lab/frr.qcow2")
        self.assertEqual(
            in_order([boot, switch, image]), [image, switch, boot]
        )

    def test_a_loop(self):
        # two machines, each plugged into a socket card of the other
        vm1 = self.factory.new_brick("qemu", "vm1")
        vm2 = self.factory.new_brick("qemu", "vm2")
        sock1 = vm1.add_sock()
        sock2 = vm2.add_sock()
        vm1.add_plug(sock2)
        vm2.add_plug(sock1)
        self.assertEqual(in_order([vm2, vm1]), [vm2, vm1])
        switch = self.factory.new_brick("switch", "sw1")
        vm1.add_plug(switch.socks[0])
        self.assertEqual(in_order([vm2, vm1, switch]), [switch, vm2, vm1])

    def test_the_state_of_an_image(self):
        image = self.factory.new_image("frr", "/lab/frr.qcow2")
        self.assertEqual(state_of(image), {"file": None})
        path = os.path.abspath(self.mktemp())
        with open(path, "wb") as fp:
            fp.write(b"x" * 5000)
        stat = os.stat(path)
        self.assertEqual(
            state_of(self.factory.new_image("pc", path)),
            {
                "file": {
                    "size": 5000,
                    "mtime": stat.st_mtime_ns,
                    "taken": stat.st_blocks * 512,
                }
            },
        )

    def test_a_machine_without_a_project(self):
        # its private copies aren't known
        vm = self.factory.new_brick("qemu", "vm1")
        vm.update_config({"hda_private": True})
        self.assertEqual(state_of(vm), {"pid": None})
