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


"""The network emulator."""

from virtualbricks.config.report import Report
from virtualbricks.config.schema import dump_record, field_names
from virtualbricks.tests import (
    BrickTestCase,
    CommandTestCase,
)
from virtualbricks.bricks.draft import Problem, apply
from virtualbricks.bricks.netemu import (
    BRICK_KEYS,
    STATE_KEYS,
    NetemuConfig,
    NetemuDraft,
    NetemuTable,
)


class TestNetemu(BrickTestCase):

    def test_states_share_the_events(self):
        netemu = self.factory.new_brick("netemu", "wan")
        netemu.markov_manager.add(1)
        self.factory.new_event("up")
        netemu.update_config({"on_start": "up"})
        self.assertEqual(
            [s.on_start for s in netemu.markov_manager.states], ["up", "up"]
        )
        netemu.markov_manager.add(2)
        self.assertEqual(netemu.markov_manager.states[2].on_start, "up")

    def test_event_rename_updates_every_state(self):
        netemu = self.factory.new_brick("netemu", "wan")
        netemu.markov_manager.add(1)
        event = self.factory.new_event("up")
        netemu.update_config({"on_start": "up"})
        self.factory.rename(event, "start")
        self.assertEqual(
            [s.on_start for s in netemu.markov_manager.states],
            ["start", "start"],
        )
        self.assertFalse(netemu.rename_references("event", "none", "x"))

    def test_config_table_round_trip(self):
        netemu = self.factory.new_brick("netemu", "wan")
        netemu.markov_manager.add(1)
        netemu.markov_manager.states[1].delay = 200
        netemu.markov_manager.weights[0][1] = 0.3
        netemu.transPeriod = 250
        table = netemu.config_table()
        self.assertEqual(table["transition_period"], 250)
        self.assertEqual(table["transitions"], [[0.0, 0.3], [0.0, 0.0]])
        self.assertEqual(len(table["states"]), 2)
        self.assertNotIn("on_start", table["states"][0])
        other = self.factory.new_brick("netemu", "wan2")
        report = Report()
        other.load_config_table(table, report, "w", set())
        self.assertEqual(len(report), 0)
        self.assertEqual(other.config_table(), table)
        self.assertIs(other.config, other.markov_manager.states[0])
        self.assertIsInstance(other.config, NetemuConfig)

    def test_bad_matrix(self):
        netemu = self.factory.new_brick("netemu", "wan")
        table = netemu.config_table()
        table["states"].append(dict(table["states"][0]))
        report = Report()
        netemu.load_config_table(table, report, "w", set())
        self.assertEqual(
            [str(m) for m in report],
            ["w.transitions: is not a 2×2 matrix, using zeros"],
        )
        self.assertEqual(
            netemu.markov_manager.weights, [[0.0, 0.0], [0.0, 0.0]]
        )

    def test_state_schema(self):
        # a state is the config without the events of the brick
        self.assertEqual(
            STATE_KEYS | BRICK_KEYS, frozenset(field_names(NetemuConfig))
        )
        self.assertEqual(STATE_KEYS & BRICK_KEYS, frozenset())
        self.assertEqual(len(STATE_KEYS), 13)
        [state] = dump_record(NetemuTable())["states"]
        self.assertEqual(frozenset(state), STATE_KEYS)

    def test_update_sends_every_state(self):
        netemu = self.factory.new_brick("netemu", "wan")
        netemu.markov_manager.add(1)
        sent = []
        netemu.send = sent.append

        class FakeProcess:
            pid = 1

        netemu.proc = FakeProcess()
        netemu.update()
        self.assertIn(b"markov-numnodes 2\n", sent)
        self.assertIn(b"markov-time 100\n", sent)


class TestStates(CommandTestCase):

    def netemu(self):
        netemu = self.factory.new_brick("netemu", "wan")
        left = self.factory.new_brick("switch", "left")
        right = self.factory.new_brick("switch", "right")
        netemu.plugs[0].connect(left.socks[0])
        netemu.plugs[1].connect(right.socks[0])
        return netemu, left, right

    def test_new_state_names(self):
        netemu, _, _ = self.netemu()
        markov = netemu.markov_manager
        markov.add(1)
        markov.add(2)
        self.assertEqual(
            [state.name for state in markov.states],
            ["default name", "default name 0", "default name 1"],
        )
        markov.states[1].name = "busy"
        markov.add(3)
        self.assertEqual(markov.states[3].name, "default name 0")
        markov.states[3].name = "default name 5"
        markov.add(4)
        self.assertEqual(markov.states[4].name, "default name 0")
        markov.states[0].name = "idle"
        markov.add(5)
        self.assertEqual(markov.states[5].name, "default name")


class FakeProcess:
    def __init__(self):
        self.written = []

    def write(self, data):
        self.written.append(data)


class TestTheDraft(BrickTestCase):

    def setUp(self):
        super().setUp()
        self.netemu = self.factory.new_brick("netemu", "ne1")
        self.switch = self.factory.new_brick("switch", "sw1")
        for plug in self.netemu.plugs:
            plug.connect(self.switch.socks[0])
        self.changed = []
        self.netemu.changed.connect(self.changed.append)

    def two_states(self):
        self.netemu.markov_manager.add(1)
        self.netemu.markov_manager.states[1].name = "congested"
        self.netemu.markov_manager.weights[0][1] = 2.0
        return NetemuDraft(self.netemu)

    def test_a_netemu_has_one(self):
        self.assertIsInstance(
            self.netemu.draft_factory(self.netemu), NetemuDraft
        )

    def test_a_copy(self):
        draft = self.two_states()
        manager = self.netemu.markov_manager
        self.assertEqual(draft.states, manager.states)
        self.assertIsNot(draft.states[0], manager.states[0])
        self.assertEqual(draft.weights, [[0.0, 2.0], [0.0, 0.0]])
        self.assertIsNot(draft.weights[0], manager.weights[0])
        self.assertEqual(draft.period, 100)
        self.assertEqual(draft.selected, 0)
        self.assertIs(draft.settings, draft.states[0])
        draft.set("delay", 20)
        self.assertEqual(manager.states[0].delay, 0)
        self.assertEqual(draft.changes(), {})

    def test_select(self):
        draft = self.two_states()
        draft.set("loss", 200)
        draft.select(1)
        self.assertIs(draft.settings, draft.states[1])
        self.assertEqual(draft.get("name"), "congested")
        # what the other state refused goes with it
        self.assertEqual(draft.refused, {})

    def test_the_directions(self):
        draft = NetemuDraft(self.netemu)
        self.assertFalse(draft.uses("delay_right_to_left"))
        draft.set("delay_symmetric", False)
        self.assertTrue(draft.uses("delay_right_to_left"))
        self.assertTrue(draft.uses("delay"))

    def test_add(self):
        draft = self.two_states()
        self.factory.new_event("up")
        draft.states[0].on_start = "up"
        draft.select(0)
        self.assertEqual(draft.add(), 1)
        self.assertEqual(
            [state.name for state in draft.states],
            ["default name", "state 3", "congested"],
        )
        self.assertEqual(draft.selected, 1)
        self.assertIs(draft.settings, draft.states[1])
        # the events are the brick's
        self.assertEqual(draft.states[1].on_start, "up")
        self.assertEqual(
            draft.weights,
            [[0.0, 0.0, 2.0], [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]],
        )
        draft.add()
        self.assertEqual(draft.states[2].name, "state 4")
        self.assertEqual(self.netemu.markov_manager.weights[0], [0.0, 2.0])

    def test_remove(self):
        draft = self.two_states()
        draft.select(0)
        draft.remove()
        self.assertEqual([state.name for state in draft.states], ["congested"])
        self.assertEqual(draft.weights, [[0.0]])
        self.assertEqual(draft.selected, 0)
        # one is left
        draft.remove()
        self.assertEqual(len(draft.states), 1)
        # the last one: the one before it shows
        draft = NetemuDraft(self.netemu)
        draft.select(1)
        draft.remove()
        self.assertEqual(draft.selected, 0)

    def test_the_chances(self):
        draft = self.two_states()
        self.assertEqual(draft.stays(0), 98.0)
        self.assertEqual(draft.stays(1), 100.0)
        draft.set_weight(1, 0, 60.0)
        self.assertEqual(draft.stays(1), 40.0)
        self.assertEqual(draft.errors(), [])
        draft.set_weight(1, 0, 110.0)
        self.assertEqual(
            draft.errors(),
            [
                Problem(
                    "transitions",
                    "From congested the chances add up to more than 100 %",
                )
            ],
        )
        # what a state keeps doesn't count
        draft.set_weight(1, 0, 60.0)
        draft.set_weight(1, 1, 50.0)
        self.assertEqual(draft.stays(1), 40.0)
        self.assertEqual(draft.errors(), [])

    def test_two_states_with_one_name(self):
        draft = self.two_states()
        draft.set("name", "congested")
        self.assertEqual(
            draft.errors(),
            [Problem("name", "Two states are called congested")],
        )

    def test_a_socket_card_on_the_left(self):
        vm = self.factory.new_brick("qemu", "vm1")
        sock = vm.add_sock()
        draft = NetemuDraft(self.netemu)
        draft.link(1, sock)
        self.assertEqual(draft.errors(), [])
        draft.link(0, sock)
        self.assertEqual(
            draft.errors(),
            [
                Problem(
                    "plug0",
                    "A machine's socket card can only be the right end",
                )
            ],
        )

    def test_apply(self):
        draft = self.two_states()
        draft.select(1)
        draft.set("delay", 80)
        draft.set_weight(1, 0, 10.0)
        draft.period = 250
        apply(draft)
        manager = self.netemu.markov_manager
        self.assertEqual(manager.states[1].delay, 80)
        self.assertEqual(manager.weights, [[0.0, 2.0], [10.0, 0.0]])
        self.assertEqual(self.netemu.transPeriod, 250)
        self.assertIs(self.netemu.config, manager.states[0])
        self.assertEqual(self.changed, [self.netemu])
        table = self.netemu.config_table()
        self.assertEqual(table["transition_period"], 250)
        self.assertEqual(table["states"][1]["delay"], 80)

    def test_apply_nothing(self):
        apply(self.two_states())
        self.assertEqual(self.changed, [])

    def test_the_current_state_removed(self):
        draft = self.two_states()
        self.netemu.currentState = 1
        self.netemu.config = self.netemu.markov_manager.states[1]
        draft.select(1)
        draft.remove()
        apply(draft)
        self.assertEqual(self.netemu.currentState, 0)
        self.assertIs(self.netemu.config, draft.states[0])

    def test_a_running_emulator(self):
        self.netemu.proc = FakeProcess()
        draft = NetemuDraft(self.netemu)
        draft.period = 300
        apply(draft)
        self.assertIn(b"markov-time 300\n", self.netemu.proc.written)
        self.assertIn(b"markov-numnodes 1\n", self.netemu.proc.written)
