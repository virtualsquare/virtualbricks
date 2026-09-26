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

"""The menu of a brick: its items, what they do, and the process actions."""

import os
import signal

from twisted.internet import defer, error, task

from virtualbricks import tools
from virtualbricks.tests import FakeLogger
from virtualbricks.tests.gui import GuiTestCase, has_display

if has_display:
    from gi.repository import Gdk, GLib, Gtk

    from virtualbricks.gui.mainwindow import brickmenu
    from virtualbricks.gui.mainwindow.brickmenu import (
        BrickActions,
        menu,
        popup,
        restart,
        resume,
        suspend,
    )


class FakeProcess:
    pid = 41301


class FakeGui:
    def __init__(self, factory):
        self.brickfactory = factory
        self.window = object()
        self.calls = []

    def startstop_brick(self, brick):
        self.calls.append(("startstop", brick))

    def curtain_up(self, brick):
        self.calls.append(("configure", brick))

    def ask_remove_brick(self, brick):
        self.calls.append(("delete", brick))

    def user_wait_action(self, action):
        self.calls.append(("wait", action))


class FakeDialog:
    def __init__(self, shown, *args):
        self.shown = shown
        self.args = args

    def show(self, parent):
        self.shown.append((self.args, parent))


class FakeImage:
    def __init__(self, path):
        self.path = path


class FakeDisk:
    def __init__(self, cow=False, image=None):
        self.cow = cow
        self.image = image

    def is_cow(self):
        return self.cow

    def get_cow_path(self):
        return "/lab/vm_hda.cow"


def content(model):
    """The items of a menu: its sections, or its entries if it has none."""

    if model.get_n_items() and model.get_item_link(0, "section"):
        return [
            content(model.get_item_link(i, "section"))
            for i in range(model.get_n_items())
        ]
    entries = []
    for i in range(model.get_n_items()):
        label = model.get_item_attribute_value(i, "label").get_string()
        submenu = model.get_item_link(i, "submenu")
        entries.append(label if submenu is None else (label, content(submenu)))
    return entries


def attribute(model, path, name):
    """An attribute of the item at path, a list of indices through links."""

    *links, last = path
    for index in links:
        link = model.get_item_link(index, "section") or model.get_item_link(
            index, "submenu"
        )
        model = link
    value = model.get_item_attribute_value(last, name)
    return None if value is None else value.unpack()


class BrickMenuTestCase(GuiTestCase):

    def setUp(self):
        super().setUp()
        os.makedirs(self.factory.runtime_dir)
        self.gui = FakeGui(self.factory)
        self.logger = FakeLogger()
        self.patch(brickmenu, "logger", self.logger)

    def brick(self, kind, name, *socks):
        brick = self.factory.new_brick(kind, name)
        for sock in socks:
            brick.connect(sock)
        return brick

    def running(self, brick):
        brick.proc = FakeProcess()
        return brick

    def menu(self, brick, keys=False):
        return content(menu(brick, self.factory.bricks, keys))


class TestTheMenu(BrickMenuTestCase):

    def test_a_brick(self):
        sw = self.brick("switch", "sw")
        self.assertEqual(
            self.menu(sw),
            [
                ["Start", "Configure…"],
                ["Rename…", "Duplicate", "Attach Event…"],
                ["Delete…"],
            ],
        )

    def test_connect_to(self):
        sw = self.brick("switch", "sw")
        self.brick("tap", "tap")
        self.brick("switch", "sw2")
        vm = self.brick("qemu", "vm")
        self.assertEqual(
            self.menu(sw)[1],
            [
                "Rename…",
                "Duplicate",
                ("Connect To", ["tap", "vm"]),
                "Attach Event…",
            ],
        )
        model = menu(sw, self.factory.bricks)
        submenu = model.get_item_link(1, "section").get_item_link(2, "submenu")
        self.assertEqual(
            [
                (
                    submenu.get_item_attribute_value(i, "action").unpack(),
                    submenu.get_item_attribute_value(i, "target").unpack(),
                )
                for i in range(submenu.get_n_items())
            ],
            [("brick.connect", "tap"), ("brick.connect", vm.name)],
        )

    def test_a_running_brick(self):
        sw = self.running(self.brick("switch", "sw"))
        self.assertEqual(
            self.menu(sw),
            [
                ["Stop", "Configure…"],
                ["Rename…", "Duplicate", "Attach Event…"],
                [
                    (
                        "Process 41301",
                        [
                            ["Open Control Monitor"],
                            ["Pause", "Continue"],
                            ["Restart"],
                            ["Kill"],
                        ],
                    )
                ],
                ["Delete…"],
            ],
        )

    def test_a_virtual_machine(self):
        vm = self.brick("qemu", "vm")
        self.assertEqual(self.menu(vm)[2], ["Resume"])
        self.running(vm)
        self.assertEqual(
            self.menu(vm)[2],
            [
                "Resume",
                (
                    "Process 41301",
                    [
                        ["Open Control Monitor"],
                        ["Pause", "Continue"],
                        ["Suspend", "Reset", "Restart"],
                        ["Terminate", "Kill"],
                    ],
                ),
            ],
        )

    def test_no_control_monitor(self):
        for kind in ("tap", "capture"):
            brick = self.running(self.brick(kind, kind))
            process = self.menu(brick)[2][0][1]
            self.assertEqual(process[0], ["Pause", "Continue"], kind)

    def test_the_keys(self):
        sw = self.brick("switch", "sw")
        model = menu(sw, self.factory.bricks, keys=True)
        self.assertEqual(attribute(model, [0, 1], "accel"), "Return")
        self.assertEqual(attribute(model, [1, 0], "accel"), "F2")
        self.assertEqual(attribute(model, [2, 0], "accel"), "Delete")
        self.assertIsNone(attribute(model, [0, 0], "accel"))
        model = menu(sw, self.factory.bricks)
        self.assertIsNone(attribute(model, [0, 1], "accel"))

    def test_every_item_has_its_action(self):
        vm = self.running(
            self.brick("qemu", "vm", self.brick("switch", "sw").socks[0])
        )
        vm.add_sock()
        actions = set(BrickActions(self.gui, vm).list_actions())

        def walk(model):
            for i in range(model.get_n_items()):
                for link in ("section", "submenu"):
                    linked = model.get_item_link(i, link)
                    if linked is not None:
                        yield from walk(linked)
                action = model.get_item_attribute_value(i, "action")
                if action is not None:
                    yield action.unpack()

        self.brick("tap", "tap")
        used = set(walk(menu(vm, self.factory.bricks)))
        self.assertEqual({name.partition(".")[2] for name in used}, actions)
        self.assertEqual({name.partition(".")[0] for name in used}, {"brick"})


class TestWhatIsEnabled(BrickMenuTestCase):

    def enabled(self, brick):
        actions = BrickActions(self.gui, brick)
        return sorted(
            name
            for name in actions.list_actions()
            if actions.get_action_enabled(name)
        )

    STOPPED = [
        "attach-event",
        "configure",
        "connect",
        "delete",
        "duplicate",
        "rename",
        "startstop",
    ]

    def test_a_stopped_brick(self):
        self.assertEqual(
            self.enabled(self.brick("switch", "sw")), self.STOPPED
        )

    def test_a_brick_that_cant_start(self):
        tap = self.brick("tap", "tap")
        self.assertNotIn("startstop", self.enabled(tap))
        capture = self.brick(
            "capture", "cap", self.brick("switch", "sw").socks[0]
        )
        self.assertNotIn("startstop", self.enabled(capture))

    def test_a_router_has_no_panel(self):
        self.assertNotIn("configure", self.enabled(self.brick("router", "r")))

    def test_a_running_brick(self):
        sw = self.running(self.brick("switch", "sw"))
        self.assertEqual(
            self.enabled(sw),
            [
                "attach-event",
                "configure",
                "connect",
                "console",
                "continue",
                "delete",
                "duplicate",
                "kill",
                "pause",
                "restart",
                "startstop",
            ],
        )

    def test_a_virtual_machine(self):
        vm = self.brick("qemu", "vm")
        self.assertEqual(self.enabled(vm), sorted(self.STOPPED + ["resume"]))
        self.running(vm)
        for name in ("suspend", "reset", "terminate", "resume", "console"):
            self.assertIn(name, self.enabled(vm))
        self.assertNotIn("rename", self.enabled(vm))

    def test_no_control_monitor(self):
        tap = self.running(self.brick("tap", "tap"))
        self.assertNotIn("console", self.enabled(tap))


class TestWhatTheItemsDo(BrickMenuTestCase):

    def setUp(self):
        super().setUp()
        self.sw = self.brick("switch", "sw")
        self.actions = BrickActions(self.gui, self.sw)

    def activate(self, name, target=None):
        self.actions.activate_action(name, target)

    def test_the_gui(self):
        for name in ("startstop", "configure", "delete"):
            self.activate(name)
        self.assertEqual(
            self.gui.calls,
            [
                ("startstop", self.sw),
                ("configure", self.sw),
                ("delete", self.sw),
            ],
        )

    def test_the_dialogs(self):
        shown = []
        self.patch(brickmenu, "RenameDialog", lambda *a: FakeDialog(shown, *a))
        self.patch(
            brickmenu, "AttachEventDialog", lambda *a: FakeDialog(shown, *a)
        )
        self.activate("rename")
        self.activate("attach-event")
        self.assertEqual(
            shown,
            [
                ((self.factory, self.sw), self.gui.window),
                ((self.sw, self.factory), self.gui.window),
            ],
        )

    def test_duplicate(self):
        self.activate("duplicate")
        self.assertIsNotNone(self.factory.get_brick_by_name("copy_of_sw"))

    def test_connect(self):
        tap = self.brick("tap", "tap")
        self.activate("connect", GLib.Variant.new_string("nobody"))
        self.assertIsNone(tap.plugs[0].sock)
        self.activate("connect", GLib.Variant.new_string("tap"))
        self.assertIs(tap.plugs[0].sock, self.sw.socks[0])

    def test_suspend_and_resume_wait(self):
        vm = self.running(self.brick("qemu", "vm"))
        actions = BrickActions(self.gui, vm)
        self.patch(brickmenu, "suspend", lambda brick: ("suspend", brick))
        self.patch(brickmenu, "resume", lambda brick: ("resume", brick))
        actions.activate_action("suspend", None)
        actions.activate_action("resume", None)
        self.assertEqual(
            self.gui.calls,
            [("wait", ("suspend", vm)), ("wait", ("resume", vm))],
        )

    def test_the_process(self):
        vm = self.running(self.brick("qemu", "vm"))
        done = []
        vm.open_console = lambda: done.append("console")
        vm.send_signal = lambda number: done.append(number)
        vm.send = lambda data: done.append(data)
        vm.poweroff = lambda **kwargs: done.append(kwargs)
        actions = BrickActions(self.gui, vm)
        for name in (
            "console",
            "pause",
            "continue",
            "reset",
            "terminate",
            "kill",
        ):
            actions.activate_action(name, None)
        self.assertEqual(
            done,
            [
                "console",
                signal.SIGSTOP,
                signal.SIGCONT,
                b"system_reset\n",
                {"term": True},
                {"kill": True},
            ],
        )
        self.assertEqual(self.logger.formatted(), ["send ACPI reset"])

    def test_a_process_already_gone(self):
        self.running(self.sw)

        def gone(number):
            raise error.ProcessExitedAlready()

        self.sw.send_signal = gone
        self.activate("pause")
        self.activate("continue")

    def test_restart(self):
        clock = task.Clock()
        actions = BrickActions(self.gui, self.running(self.sw), clock)
        restarts = []
        self.patch(
            brickmenu, "restart", lambda brick, c: restarts.append((brick, c))
        )
        actions.activate_action("restart", None)
        self.assertEqual(restarts, [(self.sw, clock)])


class TestRestart(BrickMenuTestCase):

    def setUp(self):
        super().setUp()
        self.clock = task.Clock()
        self.done = []
        self.stopped = defer.Deferred()
        self.vm = self.brick("qemu", "vm")

        def poweroff(**kwargs):
            self.done.append(("off", kwargs))
            return self.stopped

        self.vm.poweroff = poweroff
        self.vm.poweron = lambda: self.done.append("on") or self.vm

    def test_stops_then_starts(self):
        # a virtual machine too: not an ACPI reset
        restarted = restart(self.vm, self.clock)
        self.assertEqual(self.done, [("off", {})])
        self.stopped.callback(None)
        self.assertEqual(self.done, [("off", {}), "on"])
        self.assertIs(self.successResultOf(restarted), self.vm)
        self.clock.advance(10)
        self.assertEqual(self.done, [("off", {}), "on"])

    def test_what_doesnt_stop_doesnt_start(self):
        restarted = restart(self.vm, self.clock)
        self.stopped.errback(RuntimeError("still running"))
        self.failureResultOf(restarted, RuntimeError)
        self.assertEqual(self.done, [("off", {})])

    def test_kills_what_doesnt_stop(self):
        # after two seconds, as the Running tab did
        restart(self.vm, self.clock)
        self.clock.advance(1.9)
        self.assertEqual(self.done, [("off", {})])
        self.clock.advance(0.1)
        self.assertEqual(self.done, [("off", {}), ("off", {"kill": True})])
        self.stopped.callback(None)
        self.assertEqual(self.done[-1], "on")


class TestSuspendAndResume(BrickMenuTestCase):

    def setUp(self):
        super().setUp()
        self.vm = self.brick("qemu", "vm")
        self.done = []
        self.vm.send = lambda data: self.done.append(data)
        self.vm.poweroff = lambda: defer.succeed(self.done.append("off"))
        self.vm.poweron = lambda snapshot: defer.succeed(
            self.done.append(("on", snapshot))
        )
        self.disk = FakeDisk(image=FakeImage("/lab/vm.qcow2"))
        self.vm.disk = lambda name: self.disk if name == "hda" else None
        self.formats = []

        def image_type(path):
            self.formats.append(path)
            return tools.ImageFormat.QCOW2

        self.patch(tools, "image_type_from_file", image_type)

    def not_supported(self, deferred):
        self.failureResultOf(deferred, RuntimeError)
        self.assertEqual(
            self.logger.formatted(),
            ["Suspend/Resume not supported on this disk."],
        )

    def test_suspend(self):
        self.successResultOf(suspend(self.vm))
        self.assertEqual(self.done, [b"savevm virtualbricks\n", "off"])
        self.assertEqual(self.formats, ["/lab/vm.qcow2"])

    def test_suspend_a_private_disk(self):
        self.disk.cow = True
        self.successResultOf(suspend(self.vm))
        self.assertEqual(self.formats, ["/lab/vm_hda.cow"])

    def test_suspend_needs_qcow2(self):
        self.patch(
            tools, "image_type_from_file", lambda path: tools.ImageFormat.RAW
        )
        self.not_supported(suspend(self.vm))
        self.assertEqual(self.done, [])

    def test_no_disk(self):
        self.disk.image = None
        self.not_supported(suspend(self.vm))
        self.logger = FakeLogger()
        self.patch(brickmenu, "logger", self.logger)
        self.not_supported(resume(self.vm))

    def snapshots(self, output):
        listed = []

        def qemu_img(args):
            listed.append(args)
            return defer.succeed(output)

        self.patch(brickmenu, "qemu_img", qemu_img)
        return listed

    def test_resume_a_stopped_machine(self):
        listed = self.snapshots("1  virtualbricks  1.2 GiB")
        self.successResultOf(resume(self.vm))
        self.assertEqual(listed, [["snapshot", "-l", "/lab/vm.qcow2"]])
        self.assertEqual(self.done, [("on", "virtualbricks")])

    def test_resume_a_running_machine(self):
        self.snapshots("1  virtualbricks  1.2 GiB")
        self.running(self.vm)
        self.successResultOf(resume(self.vm))
        self.assertEqual(self.done, [b"loadvm virtualbricks\n"])

    def test_nothing_to_resume(self):
        self.snapshots("")
        self.failureResultOf(resume(self.vm), RuntimeError)
        self.assertEqual(self.done, [])
        self.assertEqual(self.logger.formatted(), ["Error on snapshot"])


class TestPopup(BrickMenuTestCase):

    def test_at_the_pointer(self):
        shown = []
        self.patch(
            Gtk.Menu,
            "popup_at_pointer",
            lambda menu, event: shown.append(event),
        )
        sw = self.brick("switch", "sw")
        widget = Gtk.Button()
        self.addCleanup(widget.destroy)
        event = Gdk.Event.new(Gdk.EventType.BUTTON_PRESS)
        result = popup(widget, event, self.gui, sw)
        self.addCleanup(result.destroy)
        self.assertEqual(shown, [event])
        self.assertIs(result.get_attach_widget(), widget)
        actions = result.get_action_group("brick")
        self.assertIsInstance(actions, BrickActions)
        self.assertIs(actions.brick, sw)
        labels = [
            child.get_label()
            for child in result.get_children()
            if not isinstance(child, Gtk.SeparatorMenuItem)
        ]
        self.assertEqual(labels[:2], ["Start", "Configure…"])
        # no keys, unless asked
        configure = result.get_children()[1]
        self.assertEqual(configure.get_property("accel"), "")
        with_keys = popup(widget, event, self.gui, sw, keys=True)
        self.addCleanup(with_keys.destroy)
        configure = with_keys.get_children()[1]
        self.assertEqual(configure.get_property("accel"), "Return")
