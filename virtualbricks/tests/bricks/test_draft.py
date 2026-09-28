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

"""
The draft of a brick's settings: a copy, checked as it is set, applied at
once. The drafts here are those of a switch, without its own checks.
"""

from virtualbricks.bricks.draft import Draft, Problem, apply
from virtualbricks.config.settings import set_setting
from virtualbricks.tests import BrickTestCase


class FakeProcess:
    """What a running brick writes to its process."""

    def __init__(self):
        self.written = []

    def write(self, data):
        self.written.append(data)


class HubDraft(Draft):
    """A draft whose settings go with others, and a check of its own."""

    WITH = {
        "ports": ("hub_mode", True),
        "hub_mode": ("fast_spanning_tree", False),
    }

    def check(self):
        if self.settings.ports == 13:
            return [Problem("ports", "unlucky"), Problem("icon", "odd", False)]
        return []


class LoopDraft(Draft):
    """Two settings that go with each other."""

    WITH = {"ports": ("hub_mode", True), "hub_mode": ("ports", 32)}


class DraftTestCase(BrickTestCase):

    def setUp(self):
        super().setUp()
        self.switch = self.factory.new_brick("switch", "sw1")
        self.changed = []
        self.switch.changed.connect(self.changed.append)


class TestADraft(DraftTestCase):

    def test_a_copy(self):
        draft = Draft(self.switch)
        self.assertIs(draft.brick, self.switch)
        self.assertEqual(draft.settings, self.switch.config)
        self.assertIsNot(draft.settings, self.switch.config)
        draft.set("ports", 16)
        draft.set("hub_mode", True)
        self.assertEqual(draft.get("ports"), 16)
        self.assertEqual(draft.get("hub_mode"), True)
        self.assertEqual(self.switch.config.ports, 32)
        self.assertFalse(self.switch.config.hub_mode)
        self.assertEqual(self.changed, [])

    def test_a_value_refused(self):
        draft = Draft(self.switch)
        draft.set("ports", 200)
        # as typed, the copy keeps its last good value
        self.assertEqual(draft.get("ports"), 200)
        self.assertEqual(draft.settings.ports, 32)
        self.assertEqual(
            draft.problems(), [Problem("ports", "200 is outside 1–128")]
        )
        self.assertEqual(draft.errors(), draft.problems())
        self.assertEqual(draft.changes(), {})
        draft.set("ports", 64)
        self.assertEqual(draft.problems(), [])
        self.assertEqual(draft.get("ports"), 64)

    def test_not_a_setting(self):
        draft = Draft(self.switch)
        self.assertRaises(KeyError, draft.set, "nope", 1)
        self.assertRaises(AttributeError, draft.get, "nope")

    def test_what_is_used(self):
        draft = HubDraft(self.switch)
        # a setting that goes with nothing is always used
        self.assertTrue(draft.uses("icon"))
        # hub_mode goes with fast_spanning_tree off, which it is
        self.assertTrue(draft.uses("hub_mode"))
        self.assertFalse(draft.uses("ports"))
        draft.set("hub_mode", True)
        self.assertTrue(draft.uses("ports"))
        # and along: ports goes with hub_mode, which goes with no FSTP
        draft.set("fast_spanning_tree", True)
        self.assertFalse(draft.uses("hub_mode"))
        self.assertFalse(draft.uses("ports"))

    def test_a_loop(self):
        draft = LoopDraft(self.switch)
        self.assertFalse(draft.uses("ports"))
        draft.set("hub_mode", True)
        self.assertTrue(draft.uses("ports"))
        self.assertTrue(draft.uses("hub_mode"))

    def test_what_is_used_as_typed(self):
        draft = LoopDraft(self.switch)
        draft.set("ports", 200)
        # hub_mode goes with ports 32, and 200 isn't
        self.assertFalse(draft.uses("hub_mode"))

    def test_the_limits(self):
        draft = Draft(self.switch)
        self.assertEqual(draft.limits("ports"), (1, 128))
        self.assertEqual(draft.note("ports"), "")

    def test_its_own_check(self):
        draft = HubDraft(self.switch)
        draft.set("icon", 1)
        draft.set("ports", 13)
        self.assertEqual(
            draft.problems(),
            [
                Problem("icon", "1 is not a string"),
                Problem("ports", "unlucky"),
                Problem("icon", "odd", error=False),
            ],
        )
        self.assertEqual(
            draft.errors(),
            [
                Problem("icon", "1 is not a string"),
                Problem("ports", "unlucky"),
            ],
        )

    def test_the_changes(self):
        draft = Draft(self.switch)
        self.assertEqual(draft.changes(), {})
        draft.set("fast_spanning_tree", True)
        draft.set("ports", 16)
        # in the order of the settings
        self.assertEqual(
            list(draft.changes().items()),
            [("ports", 16), ("fast_spanning_tree", True)],
        )
        draft.set("ports", 32)
        self.assertEqual(draft.changes(), {"fast_spanning_tree": True})

    def test_changes_made_elsewhere_stay(self):
        # the console changes the brick while its settings show
        draft = Draft(self.switch)
        self.switch.set({"hub_mode": True})
        draft.set("ports", 16)
        self.assertEqual(draft.changes(), {"ports": 16})
        apply(draft)
        self.assertTrue(self.switch.config.hub_mode)

    def test_what_a_running_brick_takes(self):
        draft = Draft(self.switch)
        self.assertEqual(
            draft.live(), ["ports", "hub_mode", "fast_spanning_tree"]
        )
        router = self.factory.new_brick("router", "r1")
        self.assertEqual(Draft(router).live(), [])


class TestApply(DraftTestCase):

    def test_once(self):
        draft = Draft(self.switch)
        draft.set("ports", 16)
        draft.set("hub_mode", True)
        apply(draft)
        self.assertEqual(self.switch.config.ports, 16)
        self.assertTrue(self.switch.config.hub_mode)
        self.assertEqual(self.changed, [self.switch])

    def test_nothing_changed(self):
        apply(Draft(self.switch))
        self.assertEqual(self.changed, [])

    def test_a_running_brick(self):
        self.switch.proc = FakeProcess()
        draft = Draft(self.switch)
        draft.set("ports", 16)
        draft.set("fast_spanning_tree", True)
        apply(draft)
        self.assertEqual(
            self.switch.proc.written,
            [b"port/setnumports 16\n", b"fstp/setfstp 1\n"],
        )

    def test_errors(self):
        draft = HubDraft(self.switch)
        draft.set("hub_mode", True)
        draft.set("ports", 13)
        error = self.assertRaises(ValueError, apply, draft)
        self.assertEqual(str(error), "ports: unlucky")
        self.assertEqual(self.switch.config.ports, 32)
        self.assertFalse(self.switch.config.hub_mode)
        self.assertEqual(self.changed, [])


class TestAnEvent(DraftTestCase):
    """A draft of what has no plugs: an event."""

    def test_an_event(self):
        event = self.factory.new_event("boot")
        changed = []
        event.changed.connect(changed.append)
        draft = Draft(event)
        self.assertEqual(draft.links, [])
        draft.set("delay", 7)
        self.assertEqual(draft.problems(), [])
        self.assertEqual(event.config.delay, 0)
        apply(draft)
        self.assertEqual(event.config.delay, 7)
        self.assertEqual(changed, [event])


class TestLinks(DraftTestCase):

    def setUp(self):
        super().setUp()
        self.sw2 = self.factory.new_brick("switch", "sw2")
        self.tap = self.factory.new_brick("tap", "tap0")
        self.tap.plugs[0].connect(self.switch.socks[0])
        self.tap_changed = []
        self.tap.changed.connect(self.tap_changed.append)

    def test_the_sockets(self):
        vm = self.factory.new_brick("qemu", "vm1")
        vm.add_sock()
        wrapper = self.factory.new_brick("switchwrapper", "sww")
        draft = Draft(self.tap)
        # the switches, in their order, not the socket of a machine
        self.assertEqual(
            draft.sockets(),
            [self.switch.socks[0], self.sw2.socks[0], wrapper.socks[0]],
        )
        # nor, for a machine, its own
        set_setting("allow_female_plugs", True)
        self.assertEqual(
            [sock.nickname for sock in Draft(vm).sockets()],
            ["sw1_port", "sw2_port", "sww_port"],
        )
        self.assertEqual(
            [sock.nickname for sock in Draft(self.tap).sockets()],
            ["sw1_port", "sw2_port", "vm1_sock_eth0", "sww_port"],
        )

    def test_a_copy(self):
        draft = Draft(self.tap)
        self.assertEqual(draft.links, [self.switch.socks[0]])
        draft.link(0, self.sw2.socks[0])
        self.assertEqual(draft.links, [self.sw2.socks[0]])
        self.assertIs(self.tap.plugs[0].sock, self.switch.socks[0])
        self.assertEqual(draft.moved(), {0: self.sw2.socks[0]})
        draft.link(0, self.switch.socks[0])
        self.assertEqual(draft.moved(), {})

    def test_in_nothing(self):
        draft = Draft(self.tap)
        self.assertEqual(draft.check(), [])
        draft.link(0, None)
        self.assertEqual(
            draft.check(),
            [Problem("plug0", "In nothing: tap0 can't start", error=False)],
        )
        self.assertEqual(draft.errors(), [])

    def test_apply(self):
        draft = Draft(self.tap)
        draft.link(0, self.sw2.socks[0])
        apply(draft)
        self.assertIs(self.tap.plugs[0].sock, self.sw2.socks[0])
        self.assertEqual(self.switch.socks[0].plugs, [])
        self.assertEqual(self.sw2.socks[0].plugs, [self.tap.plugs[0]])
        # it said it changed, with no setting changed
        self.assertEqual(self.tap_changed, [self.tap])

    def test_apply_with_settings(self):
        draft = Draft(self.tap)
        draft.link(0, None)
        draft.set("address_mode", "dhcp")
        apply(draft)
        self.assertIsNone(self.tap.plugs[0].sock)
        self.assertEqual(self.switch.socks[0].plugs, [])
        self.assertEqual(self.tap.config.address_mode, "dhcp")
        self.assertEqual(self.tap_changed, [self.tap])

    def test_into_a_socket_from_nothing(self):
        wire = self.factory.new_brick("wire", "w1")
        draft = Draft(wire)
        self.assertEqual(draft.links, [None, None])
        draft.link(1, self.sw2.socks[0])
        apply(draft)
        self.assertIsNone(wire.plugs[0].sock)
        self.assertIs(wire.plugs[1].sock, self.sw2.socks[0])
