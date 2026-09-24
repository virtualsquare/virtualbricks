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

from virtualbricks.config import Report, schema
from virtualbricks.tests import (
    BrickTestCase,
    CommandTestCase,
    pairs,
)
from virtualbricks.bricks.netemu import (
    BRICK_KEYS,
    STATE_KEYS,
    NetemuConfig,
    NetemuTable,
)


class TestNetemu(BrickTestCase):

    def test_states_share_the_events(self):
        netemu = self.factory.new_brick("netemu", "wan")
        netemu.markov_manager.add(1)
        self.factory.new_event("up")
        netemu.set({"pon_vbevent": "up"})
        self.assertEqual(
            [s.pon_vbevent for s in netemu.markov_manager.states], ["up", "up"]
        )
        netemu.markov_manager.add(2)
        self.assertEqual(netemu.markov_manager.states[2].pon_vbevent, "up")

    def test_event_rename_updates_every_state(self):
        netemu = self.factory.new_brick("netemu", "wan")
        netemu.markov_manager.add(1)
        event = self.factory.new_event("up")
        netemu.set({"pon_vbevent": "up"})
        self.factory.rename(event, "start")
        self.assertEqual(
            [s.pon_vbevent for s in netemu.markov_manager.states],
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
        self.assertEqual(table["transperiod"], 250)
        self.assertEqual(table["transitions"], [[0.0, 0.3], [0.0, 0.0]])
        self.assertEqual(len(table["states"]), 2)
        self.assertNotIn("pon_vbevent", table["states"][0])
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
            STATE_KEYS | BRICK_KEYS, frozenset(schema.names(NetemuConfig))
        )
        self.assertEqual(STATE_KEYS & BRICK_KEYS, frozenset())
        self.assertEqual(len(STATE_KEYS), 13)
        [state] = schema.dump(NetemuTable())["states"]
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


class TestNetemuCommandLine(CommandTestCase):

    def netemu(self):
        netemu = self.factory.new_brick("netemu", "wan")
        left = self.factory.new_brick("switch", "left")
        right = self.factory.new_brick("switch", "right")
        netemu.plugs[0].connect(left.socks[0])
        netemu.plugs[1].connect(right.socks[0])
        return netemu, left, right

    def test_symmetric(self):
        netemu, left, right = self.netemu()
        args = netemu.args()
        self.assertEqual(args[0], "vde-netemu")
        self.assertEqual(
            args[1:3],
            [
                "-v",
                left.socks[0].path.rstrip("[]")
                + ":"
                + right.socks[0].path.rstrip("[]"),
            ],
        )
        self.assertEqual(
            pairs(args[3:11]),
            [("-b", "125000"), ("-d", "0"), ("-c", "75000"), ("-l", "0.0")],
        )
        self.assertIn("--nofifo", args)
        self.assertIn("-M", args)

    def test_asymmetric(self):
        netemu, _, _ = self.netemu()
        netemu.set(
            {
                "bandwidthsymm": False,
                "bandwidth": 1,
                "bandwidthr": 2,
                "delaysymm": False,
                "delay": 3,
                "delayr": 4,
                "chanbufsizesymm": False,
                "chanbufsize": 5,
                "chanbufsizer": 6,
                "losssymm": False,
                "loss": 7.0,
                "lossr": 8.0,
            }
        )
        self.assertEqual(
            pairs(netemu.args()[3:19]),
            [
                ("-b", "LR 1"),
                ("-b", "RL 2"),
                ("-d", "LR 3"),
                ("-d", "RL 4"),
                ("-c", "LR 5"),
                ("-c", "RL 6"),
                ("-l", "LR 7.0"),
                ("-l", "RL 8.0"),
            ],
        )

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
