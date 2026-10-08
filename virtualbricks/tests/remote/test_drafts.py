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
The OK of a panel over a connection: the draft on the copy, as data, given
to a draft of the object of the Virtualbricks of the bricks.
"""

import json

from virtualbricks.bricks.eventaction import ShellAction
from virtualbricks.bricks.virtualmachine import (
    Card,
    UsbDevice,
    hostonly_sock,
)
from virtualbricks.remote.drafts import apply_changes, draft_of, what_changed
from virtualbricks.tests.remote.test_mirror import MirrorTestCase


class DraftTestCase(MirrorTestCase):
    """A lab followed by its copy; OK on a draft of the copy goes there."""

    def setUp(self):
        super().setUp()
        self.lab()
        self.netemu = self.factory.new_brick("netemu", "ne1")
        self.follow()

    def draft(self, kind, name):
        """A draft on the copy, as a panel of the windows has it."""

        item = {
            "brick": self.copy.get_brick,
            "event": self.copy.get_event,
            "image": self.copy.get_image,
        }[kind](name)
        return draft_of(self.copy, item)

    def ok(self, kind, name, draft):
        """OK: the data, through JSON, applied there; the copy follows."""

        data = json.loads(json.dumps(what_changed(draft)))
        apply_changes(self.factory, kind, name, data)
        self.turn()
        self.assertSame()
        return data


class TestWhatChanged(DraftTestCase):

    def test_nothing(self):
        data = what_changed(self.draft("brick", "vm1"))
        self.assertEqual(data, {"changes": {}, "links": [], "extras": {}})

    def test_only_what_the_panel_changed(self):
        draft = self.draft("brick", "sw1")
        draft.set("ports", 8)
        # meanwhile, another window
        self.sw1.update_config({"hub_mode": True})
        data = self.ok("brick", "sw1", draft)
        self.assertEqual(data["changes"], {"ports": 8})
        self.assertEqual(self.sw1.config.ports, 8)
        # the last OK wins for the keys it changed only
        self.assertTrue(self.sw1.config.hub_mode)

    def test_a_plug_moved(self):
        draft = self.draft("brick", "w1")
        draft.link(1, None)
        draft.link(0, self.copy.get_brick("sw2").socks[0])
        data = self.ok("brick", "w1", draft)
        self.assertEqual(data["links"], [[0, "sw2"], [1, ""]])
        wire = self.factory.get_brick("w1")
        self.assertIs(wire.plugs[0].sock, self.sw2.socks[0])
        self.assertIsNone(wire.plugs[1].sock)

    def test_a_machine(self):
        self.factory.new_image("pc", "/lab/pc.qcow2")
        self.turn()
        draft = self.draft("brick", "vm1")
        draft.set("memory", 2048)
        draft.set("hda_image", "pc")
        draft.set("usb_devices", [UsbDevice("1d6b:0002", "hub")])
        draft.set_card(
            0, model="e1000", sock=self.copy.get_brick("sw2").socks[0]
        )
        draft.remove_card(1)
        index = draft.add_card()
        draft.set_card(index, sock=hostonly_sock)
        draft.cards.append(Card("socket", "e1000", "52:54:00:00:00:01"))
        data = self.ok("brick", "vm1", draft)
        self.assertIn("cards", data["extras"])
        self.assertEqual(self.vm1.config.memory, 2048)
        self.assertEqual(self.vm1.config.hda_image, "pc")
        self.assertEqual(len(self.vm1.socks), 2)
        # the socket card that vm2 plugs into stays
        self.assertIs(
            self.factory.get_brick("vm2").plugs[0].sock.brick, self.vm1
        )

    def test_a_netemu(self):
        draft = self.draft("brick", "ne1")
        draft.add()
        draft.set("bandwidth", 1000)
        draft.set_weight(0, 1, 30.0)
        draft.period = 500
        data = self.ok("brick", "ne1", draft)
        self.assertEqual(data["changes"], {})
        self.assertEqual(len(data["extras"]["states"]), 2)
        self.assertEqual(self.netemu.transPeriod, 500)
        self.assertEqual(self.netemu.markov_manager.weights[0][1], 30.0)

    def test_an_event(self):
        draft = self.draft("event", "boot")
        draft.set("delay", 30)
        draft.set("actions", [ShellAction("date")])
        self.ok("event", "boot", draft)
        self.assertEqual(self.boot.config.delay, 30)
        self.assertEqual(self.boot.config.actions, [ShellAction("date")])

    def test_an_image(self):
        draft = self.draft("image", "frr")
        draft.set("name", "debian")
        draft.set("description", "Bookworm")
        self.ok("image", "frr", draft)
        self.assertEqual(self.image.name, "debian")
        self.assertEqual(self.image.description, "Bookworm")
        # the disks follow the name
        self.assertEqual(self.vm1.config.hda_image, "debian")


class TestRefused(DraftTestCase):
    """Nothing changes when the data doesn't fit."""

    def test_no_such_object(self):
        with self.assertRaises(LookupError) as cm:
            apply_changes(self.factory, "brick", "sw9", {})
        self.assertEqual(cm.exception.args[0], "No brick named sw9")

    def test_no_such_setting(self):
        with self.assertRaises(ValueError) as cm:
            apply_changes(
                self.factory, "brick", "sw1", {"changes": {"warp": 9}}
            )
        self.assertEqual(str(cm.exception), "sw1 has no setting warp")

    def test_a_value_it_refuses(self):
        with self.assertRaises(ValueError):
            apply_changes(
                self.factory,
                "brick",
                "sw1",
                {"changes": {"ports": "many", "hub_mode": True}},
            )
        self.assertFalse(self.sw1.config.hub_mode)

    def test_no_such_socket(self):
        with self.assertRaises(ValueError) as cm:
            apply_changes(
                self.factory, "brick", "tap1", {"links": [[0, "sw9"]]}
            )
        self.assertEqual(str(cm.exception), "plug 0: no socket sw9")
        with self.assertRaises(ValueError):
            apply_changes(
                self.factory, "brick", "tap1", {"links": [[3, "sw1"]]}
            )

    def test_what_a_kind_reports(self):
        with self.assertRaises(ValueError) as cm:
            apply_changes(
                self.factory,
                "event",
                "boot",
                {"changes": {"delay": 9, "actions": [{"type": "fly"}]}},
            )
        self.assertTrue(str(cm.exception).startswith("actions"))
        self.assertEqual(self.boot.config.delay, 5)

    def test_errors_of_the_draft(self):
        # a switch with fewer ports than the plugs in it
        with self.assertRaises(ValueError) as cm:
            apply_changes(
                self.factory,
                "brick",
                "sw1",
                {"changes": {"ports": 1, "hub_mode": True}},
            )
        self.assertTrue(str(cm.exception).startswith("ports: "))
        self.assertEqual(self.sw1.config.ports, 32)
        self.assertFalse(self.sw1.config.hub_mode)
