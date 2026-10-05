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

from twisted.internet import error

from virtualbricks.engine import LocalEngine
from virtualbricks.tests import FakeLogger
from virtualbricks.tests.gui import GuiTestCase, RecordingEngine, has_display

if has_display:
    from gi.repository import Gdk, GLib, Gtk

    from virtualbricks.gui.mainwindow.bricks import brickmenu
    from virtualbricks.gui.mainwindow.bricks.brickmenu import (
        BrickActions,
        menu,
        popup,
    )


class FakeProcess:
    pid = 41301


class FakeGui:
    def __init__(self, factory):
        self.brickfactory = factory
        self.engine = LocalEngine(factory)
        self.window = object()
        self.calls = []

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

    def events(self):
        return list(self.factory.events)

    def menu(self, brick, keys=False):
        return content(menu(brick, self.factory.bricks, self.events(), keys))


class TestTheMenu(BrickMenuTestCase):

    def test_a_brick(self):
        sw = self.brick("switch", "sw")
        self.assertEqual(
            self.menu(sw),
            [
                ["Start", "Configure…"],
                [
                    "Rename…",
                    "Duplicate",
                    ("When It Starts", [["No Event"]]),
                    ("When It Stops", [["No Event"]]),
                ],
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
                ("When It Starts", [["No Event"]]),
                ("When It Stops", [["No Event"]]),
            ],
        )
        model = menu(sw, self.factory.bricks, self.events())
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
                [
                    "Rename…",
                    "Duplicate",
                    ("When It Starts", [["No Event"]]),
                    ("When It Stops", [["No Event"]]),
                ],
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
        model = menu(sw, self.factory.bricks, self.events(), keys=True)
        self.assertEqual(attribute(model, [0, 1], "accel"), "Return")
        self.assertEqual(attribute(model, [1, 0], "accel"), "F2")
        self.assertEqual(attribute(model, [2, 0], "accel"), "Delete")
        self.assertIsNone(attribute(model, [0, 0], "accel"))
        model = menu(sw, self.factory.bricks, self.events())
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
        used = set(walk(menu(vm, self.factory.bricks, self.events())))
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
        "configure",
        "connect",
        "delete",
        "duplicate",
        "rename",
        "startstop",
        "when-starts",
        "when-stops",
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
                "configure",
                "connect",
                "console",
                "continue",
                "duplicate",
                "kill",
                "pause",
                "restart",
                "startstop",
                "when-starts",
                "when-stops",
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

    def recording(self, brick):
        """The actions of brick, with an engine that only remembers."""

        self.gui.engine = RecordingEngine(self.factory)
        return BrickActions(self.gui, brick)

    def test_the_gui(self):
        for name in ("configure", "delete"):
            self.activate(name)
        self.assertEqual(
            self.gui.calls, [("configure", self.sw), ("delete", self.sw)]
        )

    def test_start_and_stop(self):
        actions = self.recording(self.sw)
        actions.activate_action("startstop", None)
        self.running(self.sw)
        actions.activate_action("startstop", None)
        self.assertEqual(
            self.gui.engine.calls, [("start", self.sw), ("stop", self.sw)]
        )

    def test_rename(self):
        shown = []
        self.patch(brickmenu, "RenameDialog", lambda *a: FakeDialog(shown, *a))
        self.activate("rename")
        self.assertEqual(
            shown, [((self.gui.engine, self.sw), self.gui.window)]
        )

    def test_duplicate(self):
        self.activate("duplicate")
        self.assertIsNotNone(self.factory.get_brick("sw2"))

    def test_connect(self):
        tap = self.brick("tap", "tap")
        self.activate("connect", GLib.Variant.new_string("nobody"))
        self.assertIsNone(tap.plugs[0].sock)
        self.activate("connect", GLib.Variant.new_string("tap"))
        self.assertIs(tap.plugs[0].sock, self.sw.socks[0])

    def test_suspend_and_resume_wait(self):
        vm = self.running(self.brick("qemu", "vm"))
        actions = self.recording(vm)
        actions.activate_action("suspend", None)
        actions.activate_action("resume", None)
        self.assertEqual(
            self.gui.engine.calls, [("suspend", vm), ("resume", vm)]
        )
        self.assertEqual([call[0] for call in self.gui.calls], ["wait"] * 2)

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
        actions = self.recording(self.running(self.sw))
        actions.activate_action("restart", None)
        self.assertEqual(self.gui.engine.calls, [("restart", self.sw)])


class TestTheEventsOfABrick(BrickMenuTestCase):

    def setUp(self):
        super().setUp()
        self.sw = self.brick("switch", "sw")
        self.factory.new_event("boot")
        # without actions: it can be chosen too
        self.factory.new_event("draft")

    def submenu(self, label, model=None):
        if model is None:
            model = menu(self.sw, self.factory.bricks, self.events())
        section = model.get_item_link(1, "section")
        for i in range(section.get_n_items()):
            if section.get_item_attribute_value(i, "label").unpack() == label:
                return section.get_item_link(i, "submenu")
        raise AssertionError(label)

    def targets(self, submenu):
        return [
            [
                (
                    section.get_item_attribute_value(i, "action").unpack(),
                    section.get_item_attribute_value(i, "target").unpack(),
                )
                for i in range(section.get_n_items())
            ]
            for section in (
                submenu.get_item_link(j, "section")
                for j in range(submenu.get_n_items())
            )
        ]

    def test_the_submenus(self):
        for label, action in (
            ("When It Starts", "brick.when-starts"),
            ("When It Stops", "brick.when-stops"),
        ):
            submenu = self.submenu(label)
            self.assertEqual(
                content(submenu), [["No Event"], ["boot", "draft"]]
            )
            self.assertEqual(
                self.targets(submenu),
                [[(action, "")], [(action, "boot"), (action, "draft")]],
            )

    def test_no_events(self):
        for event in self.events():
            self.factory.remove_event(event)
        self.assertEqual(
            content(self.submenu("When It Starts")), [["No Event"]]
        )

    def test_a_missing_event(self):
        # deleted, the brick still names it
        self.sw.update_config({"on_stop": "gone"})
        submenu = self.submenu("When It Stops")
        self.assertEqual(
            content(submenu),
            [["No Event"], ["boot", "draft", "gone (missing)"]],
        )
        self.assertEqual(
            self.targets(submenu)[1][2], ("brick.when-stops", "gone")
        )
        self.assertEqual(
            content(self.submenu("When It Starts")),
            [["No Event"], ["boot", "draft"]],
        )

    def test_choosing(self):
        actions = BrickActions(self.gui, self.sw)
        for name in ("when-starts", "when-stops"):
            self.assertEqual(actions.get_action_state(name).unpack(), "")
        actions.activate_action("when-starts", GLib.Variant.new_string("boot"))
        actions.activate_action("when-stops", GLib.Variant.new_string("draft"))
        self.assertEqual(self.sw.config.on_start, "boot")
        self.assertEqual(self.sw.config.on_stop, "draft")
        self.assertEqual(
            actions.get_action_state("when-starts").unpack(), "boot"
        )
        # No Event
        actions.activate_action("when-starts", GLib.Variant.new_string(""))
        self.assertEqual(self.sw.config.on_start, "")
        self.assertEqual(self.sw.config.on_stop, "draft")

    def test_the_choice_follows_the_brick(self):
        actions = BrickActions(self.gui, self.sw)
        self.sw.update_config({"on_start": "boot"})
        actions.update()
        self.assertEqual(
            actions.get_action_state("when-starts").unpack(), "boot"
        )

    def test_a_radio_item_each(self):
        # as GTK shows them: the one chosen, checked
        self.sw.update_config({"on_start": "boot"})
        result = Gtk.Menu.new_from_model(
            menu(self.sw, self.factory.bricks, self.events())
        )
        self.addCleanup(result.destroy)
        result.insert_action_group("brick", BrickActions(self.gui, self.sw))
        [item] = [
            child
            for child in result.get_children()
            if child.get_label() == "When It Starts"
        ]
        items = [
            child
            for child in item.get_submenu().get_children()
            if not isinstance(child, Gtk.SeparatorMenuItem)
        ]
        self.assertEqual(
            [
                (i.get_label(), i.get_draw_as_radio(), i.get_active())
                for i in items
            ],
            [
                ("No Event", True, False),
                ("boot", True, True),
                ("draft", True, False),
            ],
        )


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

    def test_under_a_widget(self):
        # for the Menu key: no event
        shown = []
        self.patch(
            Gtk.Menu,
            "popup_at_widget",
            lambda menu, widget, anchor, gravity, event: shown.append(
                (widget, anchor, gravity, event)
            ),
        )
        widget = Gtk.Button()
        self.addCleanup(widget.destroy)
        result = popup(widget, None, self.gui, self.brick("switch", "sw"))
        self.addCleanup(result.destroy)
        self.assertEqual(
            shown,
            [(widget, Gdk.Gravity.SOUTH_EAST, Gdk.Gravity.NORTH_EAST, None)],
        )
