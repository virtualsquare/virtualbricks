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
