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

"""The Network section: a row for each card of the draft."""

from virtualbricks.bricks.virtualmachine import hostonly_sock
from virtualbricks.config import settings
from virtualbricks.gui.mainwindow.bricks.config.vm.network import model_options
from virtualbricks.tests.gui.mainwindow.bricks.config.vm.test_panel import (
    MachinePanelTestCase,
)
from virtualbricks.tests.test_programs import recorded_info


class TestTheCards(MachinePanelTestCase):

    def prepare(self):
        self.vm.add_plug(self.switch.socks[0], "52:54:00:00:00:01", "e1000")
        self.vm.add_plug(hostonly_sock, "52:54:00:00:00:02", "virtio-net")

    def rows(self):
        return self.panel.cards.rows()

    def test_the_rows(self):
        rows = self.rows()
        self.assertEqual([row.index for row in rows], [0, 1])
        self.assertEqual(rows[0].model.name.get_text(), "e1000")
        # an alias of QEMU, by its name
        self.assertEqual(rows[1].model.name.get_text(), "virtio-net-pci")
        self.assertEqual(rows[1].model.value, "virtio-net")
        self.assertEqual(rows[0].mac.get_text(), "52:54:00:00:00:01")
        self.assertEqual(
            [row.plugged.get_active_id() for row in rows], ["0", "host"]
        )
        self.assertEqual(
            [item[0] for item in rows[0].plugged.get_model()],
            ["Nothing", "The host only, on QEMU's user network", "sw1"],
        )
        self.assertFalse(self.panel.cards.lack.get_visible())

    def test_the_models(self):
        options = model_options(recorded_info("ubuntu-22.04"), "e1000")
        self.assertEqual(len(options), 30)
        self.assertNotIn("igb", [option.value for option in options])
        self.assertEqual(model_options(None, "e1000"), [])

    def test_a_change(self):
        rows = self.rows()
        rows[0].model.choose("igb")
        rows[0].mac.set_text("52:54:00")
        self.assertEqual(
            rows[0].problem.get_text(), "52:54:00 isn't a MAC address"
        )
        rows[0].mac.set_text("52:54:00:00:00:09")
        rows[1].plugged.set_active_id("")
        self.assertEqual(
            rows[1].problem.get_text(), "In nothing: vm1 can't start"
        )
        card = self.panel.draft.cards[0]
        self.assertEqual((card.model, card.mac), ("igb", "52:54:00:00:00:09"))
        self.assertIsNone(self.panel.draft.cards[1].sock)
        self.assertEqual(self.vm.plugs[0].model, "e1000")

    def test_a_new_address(self):
        row = self.rows()[0]
        row.get_child().get_child_at(1, 2).get_children()[1].clicked()
        self.assertNotEqual(row.mac.get_text(), "52:54:00:00:00:01")
        self.assertEqual(self.panel.draft.cards[0].mac, row.mac.get_text())

    def test_add_and_remove(self):
        self.panel.cards.add_button.clicked()
        rows = self.rows()
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[2].plugged.get_active_id(), "")
        rows[0].remove_button.clicked()
        self.assertEqual(
            [card.mac for card in self.panel.draft.cards][0],
            "52:54:00:00:00:02",
        )
        self.assertEqual(len(self.rows()), 2)

    def test_a_socket(self):
        # offered with female plugs
        self.assertEqual(self.rows()[0].plugged.get_model()[-1][1], "0")
        # patched back by the test's settings
        settings.use_project(settings.ProjectSettings(allow_female_plugs=True))
        self.panel.cards.rebuild()
        row = self.rows()[0]
        row.plugged.set_active_id("socket")
        self.assertEqual(
            [card.kind for card in self.panel.draft.cards], ["plug", "socket"]
        )
        self.assertEqual(self.rows()[1].plugged.get_active_id(), "socket")
