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


"""The draft of a tunnel client: it needs its server."""

from virtualbricks.bricks.draft import Problem
from virtualbricks.bricks.tunnelconnect import TunnelConnectDraft
from virtualbricks.tests import BrickTestCase


class TestTheDraft(BrickTestCase):

    def test_its_server(self):
        tunnel = self.factory.new_brick("tunnelconnect", "tc1")
        draft = tunnel.draft_factory(tunnel)
        self.assertIsInstance(draft, TunnelConnectDraft)
        self.assertEqual(
            draft.check(),
            [
                Problem(
                    "server_host",
                    "Without a server, tc1 can't start",
                    error=False,
                ),
                Problem("plug0", "In nothing: tc1 can't start", error=False),
            ],
        )
        draft.set("server_host", "  ")
        self.assertEqual(draft.check()[0].key, "server_host")
        draft.set("server_host", "lab.example.org")
        self.assertEqual([p.key for p in draft.check()], ["plug0"])
