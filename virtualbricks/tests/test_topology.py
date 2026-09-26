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

"""The layout of a lab: where Graphviz puts the bricks and their links."""

from twisted.trial import unittest

from virtualbricks.tests import make_factory
from virtualbricks.topology import ICON, NAME, Layout, layout, links


class TopologyTestCase(unittest.TestCase):

    def setUp(self):
        self.factory = make_factory(self)

    def brick(self, kind, name, *socks):
        brick = self.factory.new_brick(kind, name)
        for sock in socks:
            brick.connect(sock)
        return brick

    def switch(self, name):
        return self.brick("switch", name)


class TestLinks(TopologyTestCase):

    def test_a_tap_before_its_switch(self):
        sw = self.switch("sw")
        tap = self.brick("tap", "tap", sw.socks[0])
        self.assertEqual(links([sw, tap]), [(tap, sw)])

    def test_a_wire_between_its_ends(self):
        sw1, sw2 = self.switch("sw1"), self.switch("sw2")
        wire = self.brick("wire", "w", sw1.socks[0], sw2.socks[0])
        self.assertEqual(links([wire]), [(sw1, wire), (wire, sw2)])

    def test_a_machine_between_its_switches(self):
        sws = [self.switch(f"sw{i}") for i in range(4)]
        vm = self.brick("qemu", "vm", *(sw.socks[0] for sw in sws))
        # one more than half before
        self.assertEqual(
            links([vm]),
            [(sws[0], vm), (sws[1], vm), (sws[2], vm), (vm, sws[3])],
        )
        vm3 = self.brick("qemu", "vm3", *(sw.socks[0] for sw in sws[:3]))
        self.assertEqual(
            links([vm3]), [(sws[0], vm3), (sws[1], vm3), (vm3, sws[2])]
        )

    def test_the_plugs_not_connected(self):
        sw = self.switch("sw")
        tap = self.brick("tap", "tap")
        wire = self.brick("wire", "w", sw.socks[0])
        vm = self.brick("qemu", "vm", sw.socks[0])
        vm.add_plug(None)
        vm.add_plug(None)
        self.assertEqual(links([sw, tap, wire, vm]), [(sw, wire), (sw, vm)])


class TestLayout(TopologyTestCase):

    def lab(self):
        self.sw1, self.sw2 = self.switch("sw1"), self.switch("sw2")
        self.tap = self.brick("tap", "tap0", self.sw1.socks[0])
        self.wire = self.brick(
            "wire", "w1", self.sw1.socks[0], self.sw2.socks[0]
        )
        return self.factory.bricks

    def nodes(self, result):
        return {node.brick.name: node for node in result.nodes}

    def test_no_bricks(self):
        self.assertEqual(layout([]), Layout(0, 0, (), ()))

    def test_every_brick_in_its_box(self):
        bricks = self.lab()
        result = layout(bricks)
        self.assertEqual([node.brick for node in result.nodes], bricks)
        for node in result.nodes:
            self.assertEqual(node.width, ICON)
            self.assertEqual(node.height, ICON + NAME)
            self.assertGreaterEqual(node.x - node.width / 2, 0)
            self.assertGreaterEqual(node.y - node.height / 2, 0)
            self.assertLessEqual(node.x + node.width / 2, result.width)
            self.assertLessEqual(node.y + node.height / 2, result.height)

    def test_left_to_right(self):
        nodes = self.nodes(layout(self.lab(), "LR"))
        order = sorted(nodes, key=lambda name: nodes[name].x)
        self.assertEqual(order, ["tap0", "sw1", "w1", "sw2"])
        self.assertEqual(nodes["tap0"].y, nodes["sw1"].y)

    def test_top_to_bottom(self):
        result = layout(self.lab(), "TB")
        nodes = self.nodes(result)
        order = sorted(nodes, key=lambda name: nodes[name].y)
        self.assertEqual(order, ["tap0", "sw1", "w1", "sw2"])
        self.assertEqual(nodes["tap0"].x, nodes["sw1"].x)
        # y going down: the first rank at the top
        self.assertEqual(nodes["tap0"].y, (ICON + NAME) / 2)

    def test_the_links(self):
        result = layout(self.lab())
        nodes = self.nodes(result)
        self.assertEqual(
            {(link.tail.name, link.head.name) for link in result.links},
            {("tap0", "sw1"), ("sw1", "w1"), ("w1", "sw2")},
        )
        for link in result.links:
            # a start and three points for each segment
            self.assertEqual(len(link.points) % 3, 1)
            self.assertGreaterEqual(len(link.points), 4)
            tail, head = nodes[link.tail.name], nodes[link.head.name]
            (x0, y0), (x1, y1) = link.points[0], link.points[-1]
            # from the right side of the tail to the left side of the head
            self.assertLess(abs(x0 - (tail.x + tail.width / 2)), 1)
            self.assertLess(abs(x1 - (head.x - head.width / 2)), 1)
            self.assertLessEqual(abs(y0 - tail.y), tail.height / 2)
            self.assertLessEqual(abs(y1 - head.y), head.height / 2)

    def test_one_link_between_two_bricks(self):
        sw = self.switch("sw")
        vm = self.brick("qemu", "vm", sw.socks[0], sw.socks[0])
        [link] = layout([sw, vm]).links
        self.assertEqual({link.tail, link.head}, {sw, vm})

    def test_a_long_name(self):
        sw = self.switch("a-switch-with-a-long-name")
        [node] = layout([sw]).nodes
        self.assertGreater(node.width, ICON)
        self.assertEqual(node.height, ICON + NAME)

    def test_an_unknown_direction(self):
        self.assertRaises(ValueError, layout, [], "RL")
