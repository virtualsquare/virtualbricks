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

"""Apply and Connect, the commands of the windows that the console lacks."""

import json

from virtualbricks.console import ampcommands, ampwire
from virtualbricks.remote import answers, commands
from virtualbricks.tests import FakeLogger
from virtualbricks.tests.remote.test_follower import FollowTestCase


def apply_arguments(kind, name, changes=None, links=None, extras=None):
    return {
        "kind": kind,
        "name": name,
        "changes": json.dumps(changes or {}),
        "links": json.dumps(links or []),
        "extras": json.dumps(extras or {}),
    }


class TestApply(FollowTestCase):

    def setUp(self):
        super().setUp()
        self.switch = self.factory.new_brick("switch", "sw1")
        self.answers_log = FakeLogger()
        self.patch(answers, "logger", self.answers_log)
        self.follow()
        self.got()

    def test_before_the_agreement(self):
        # a new connection, without Hello
        self.program.callRemote(ampwire.Hello)
        self.pump.flush()
        self.failureResultOf(
            self.call(commands.Apply, **apply_arguments("brick", "sw1")),
            ampcommands.ProtocolNeeded,
        )

    def test_apply(self):
        answer = self.call(
            commands.Apply,
            **apply_arguments("brick", "sw1", {"ports": 8, "hub_mode": True}),
        )
        self.assertEqual(self.successResultOf(answer), {})
        self.assertEqual(self.switch.config.ports, 8)
        self.assertTrue(self.switch.config.hub_mode)
        self.assertEqual(self.names(), ["Changed", "answer"])
        self.assertIn("apply brick sw1", " ".join(self.logger.formatted()))

    def test_no_such_brick(self):
        failure = self.failureResultOf(
            self.call(commands.Apply, **apply_arguments("brick", "sw9")),
            ampcommands.NotFound,
        )
        self.assertEqual(failure.getErrorMessage(), "No brick named sw9")

    def test_it_doesnt_fit(self):
        failure = self.failureResultOf(
            self.call(
                commands.Apply,
                **apply_arguments(
                    "brick", "sw1", {"ports": "many", "hub_mode": True}
                ),
            ),
            ampcommands.BadArgument,
        )
        self.assertIn("ports", failure.getErrorMessage())
        self.assertFalse(self.switch.config.hub_mode)
        self.turn()
        self.assertEqual(self.names(), [])

    def test_a_failure_on_the_way(self):
        def broken(*args):
            raise RuntimeError("disk full")

        self.patch(answers, "apply_changes", broken)
        failure = self.failureResultOf(
            self.call(commands.Apply, **apply_arguments("brick", "sw1")),
            ampwire.CommandFailed,
        )
        self.assertEqual(failure.getErrorMessage(), "disk full")
        self.assertEqual(self.answers_log.formatted(), ["apply of sw1 failed"])


class TestConnect(FollowTestCase):

    def setUp(self):
        super().setUp()
        self.switch = self.factory.new_brick("switch", "sw1")
        self.tap = self.factory.new_brick("tap", "tap1")
        self.follow()
        self.got()

    def test_connect(self):
        answer = self.call(commands.Connect, source="tap1", target="sw1")
        self.assertEqual(self.successResultOf(answer), {"connected": True})
        self.assertIs(self.tap.plugs[0].sock, self.switch.socks[0])
        self.assertEqual(self.names(), ["Changed", "answer"])

    def test_nothing_to_connect(self):
        other = self.factory.new_brick("switch", "sw2")
        self.turn()
        self.got()
        answer = self.call(commands.Connect, source="sw1", target="sw2")
        self.assertEqual(self.successResultOf(answer), {"connected": False})
        self.assertEqual(other.plugs, [])

    def test_no_such_brick(self):
        failure = self.failureResultOf(
            self.call(commands.Connect, source="tap1", target="sw9"),
            ampcommands.NotFound,
        )
        self.assertEqual(failure.getErrorMessage(), "No brick named sw9")
        self.assertIsNone(self.tap.plugs[0].sock)
