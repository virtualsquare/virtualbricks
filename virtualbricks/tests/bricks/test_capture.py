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


"""The capture, and the draft of its settings."""

import os

from virtualbricks.bricks import capture
from virtualbricks.bricks.capture import CaptureDraft, host_interfaces
from virtualbricks.bricks.draft import Problem
from virtualbricks.tests import (
    BrickTestCase,
    CommandTestCase,
)

NET_DEV = """\
Inter-|   Receive                                                |  Transmit
 face |bytes    packets errs drop fifo frame compressed multicast|bytes
    lo: 1204736    9530    0    0    0     0          0         0  1204736
enp3s0: 915218862  676120    0    0    0     0          0      3481 51329
 wlan0:       0       0    0    0    0     0          0         0        0
"""


class TestCapture(CommandTestCase):

    def test_capture(self):
        capture = self.factory.new_brick("capture", "cap")
        capture.set({"interface": "eth0"})
        self.assertFalse(capture.configured())
        sw = self.factory.new_brick("switch", "sw")
        capture.plugs[0].connect(sw.socks[0])
        self.assertTrue(capture.configured())


class TestTheDraft(BrickTestCase):

    def setUp(self):
        super().setUp()
        path = os.path.abspath(self.mktemp())
        with open(path, "w") as fp:
            fp.write(NET_DEV)
        self.patch(capture, "NET_DEV", path)
        self.capture = self.factory.new_brick("capture", "cap")
        sw = self.factory.new_brick("switch", "sw")
        self.capture.plugs[0].connect(sw.socks[0])

    def test_the_interfaces_of_the_host(self):
        self.assertEqual(host_interfaces(), ["enp3s0", "wlan0"])
        self.patch(capture, "NET_DEV", os.path.abspath(self.mktemp()))
        self.assertEqual(host_interfaces(), [])

    def test_a_capture_has_one(self):
        draft = self.capture.draft_factory(self.capture)
        self.assertIsInstance(draft, CaptureDraft)
        self.assertEqual(draft.interfaces, ["enp3s0", "wlan0"])

    def test_what_keeps_it_from_starting(self):
        draft = CaptureDraft(self.capture)
        self.assertEqual(
            draft.check(),
            [
                Problem(
                    "interface",
                    "Without an interface, cap can't start",
                    error=False,
                )
            ],
        )
        draft.set("interface", "eth9")
        draft.link(0, None)
        self.assertEqual(
            draft.check(),
            [
                Problem(
                    "interface",
                    "eth9 isn't an interface of this host",
                    error=False,
                ),
                Problem("plug0", "In nothing: cap can't start", error=False),
            ],
        )
        draft.set("interface", "wlan0")
        self.assertEqual([problem.key for problem in draft.check()], ["plug0"])
