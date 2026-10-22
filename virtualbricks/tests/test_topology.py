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
The layout of a lab: where Graphviz puts the bricks and their links, or
their places.
"""

import pygraphviz
from twisted.trial import unittest

from virtualbricks.bricks import Point
from virtualbricks.tests import make_factory
from virtualbricks.topology import (
    BRICK_GAP,
    CHAR_WIDTH,
    ICON,
    NAME,
    POINTS_PER_INCH,
    RANK_GAP,
    Layout,
    arrange,
    by_hand,
    layout,
    links,
    place_of,
    places,
)


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
        return list(self.factory.bricks)

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
        self.assertEqual(node.width, len(sw.name) * CHAR_WIDTH)
        self.assertEqual(node.height, ICON + NAME)

    def test_the_names_measured(self):
        sw = self.switch("sw")
        vm = self.brick("qemu", "a-long-name", sw.socks[0])
        widths = {"sw": 10, "a-long-name": 150.2}
        result = layout([sw, vm], measure=widths.get)
        nodes = self.nodes(result)
        # never narrower than the icon; whole points
        self.assertEqual(nodes["sw"].width, ICON)
        self.assertEqual(nodes["a-long-name"].width, 151)

    def test_an_unknown_direction(self):
        self.assertRaises(ValueError, layout, [], "RL")

    def test_the_places(self):
        bricks = self.lab()
        result = layout(bricks)
        # Graphviz's corner is where the places start
        self.assertEqual((result.left, result.top), (0, 0))
        tap = self.nodes(result)["tap0"]
        self.assertEqual(
            places(result)[self.tap],
            Point(round(tap.x), round(tap.y - tap.height / 2 + ICON / 2)),
        )
        self.assertEqual(set(places(result)), set(bricks))


class TestByHand(TopologyTestCase):
    """A lab whose bricks have places (page 35)."""

    def nodes(self, result):
        return {node.brick.name: node for node in result.nodes}

    def test_by_hand(self):
        sw1, sw2 = self.switch("sw1"), self.switch("sw2")
        self.assertFalse(by_hand([sw1, sw2]))
        sw2.place = Point(0, 0)
        self.assertTrue(by_hand([sw1, sw2]))
        self.assertFalse(by_hand([]))

    def test_no_bricks(self):
        self.assertEqual(arrange([]), Layout())

    def test_each_brick_at_its_place(self):
        sw1, sw2 = self.switch("sw1"), self.switch("sw2")
        sw1.place, sw2.place = Point(0, 0), Point(200, 100)
        result = arrange([sw1, sw2])
        self.assertEqual([node.brick for node in result.nodes], [sw1, sw2])
        # the corner of the lab, among the places: sw1's box
        self.assertEqual((result.left, result.top), (-ICON / 2, -ICON / 2))
        self.assertEqual(result.width, 200 + ICON)
        self.assertEqual(result.height, 100 + ICON + NAME)
        nodes = self.nodes(result)
        # the box of the icon and the name, the icon at the top
        self.assertEqual(
            (nodes["sw1"].x, nodes["sw1"].y), (ICON / 2, (ICON + NAME) / 2)
        )
        self.assertEqual((nodes["sw1"].width, nodes["sw1"].height), (64, 84))
        self.assertEqual(
            places(result), {sw1: Point(0, 0), sw2: Point(200, 100)}
        )

    def test_a_lab_moved_as_a_whole(self):
        sw1, sw2 = self.switch("sw1"), self.switch("sw2")
        sw1.place, sw2.place = Point(0, 0), Point(200, 100)
        before = arrange([sw1, sw2])
        sw1.place, sw2.place = Point(-500, 40), Point(-300, 140)
        after = arrange([sw1, sw2])
        self.assertEqual(after.nodes, before.nodes)
        self.assertEqual((after.left, after.top), (-532, 8))

    def test_a_long_name_widens_the_box_around_the_icon(self):
        sw = self.switch("a-long-name")
        sw.place = Point(10, 20)
        [node] = arrange([sw], measure={"a-long-name": 150.2}.get).nodes
        self.assertEqual(node.width, 151)
        self.assertEqual(
            place_of(arrange([sw], lambda name: 150.2), node), Point(10, 20)
        )

    def test_the_bricks_without_a_place(self):
        sw1, sw2 = self.switch("sw1"), self.switch("sw2")
        tap = self.brick("tap", "a-tap")
        sw1.place = Point(0, 0)
        widths = {"sw1": 10, "sw2": 10, "a-tap": 100}
        result = arrange([sw2, sw1, tap], measure=widths.get)
        found = places(result)
        self.assertEqual(found[sw1], Point(0, 0))
        # in a row under the others, from their left, in their order
        row = ICON / 2 + NAME + RANK_GAP * POINTS_PER_INCH + ICON / 2
        self.assertEqual(found[sw2], Point(0, round(row)))
        gap = BRICK_GAP * POINTS_PER_INCH
        self.assertEqual(
            found[tap], Point(round(-ICON / 2 + ICON + gap + 50), round(row))
        )
        self.assertEqual(
            [node.brick for node in result.nodes], [sw2, sw1, tap]
        )

    def test_no_brick_with_a_place(self):
        sw1, sw2 = self.switch("sw1"), self.switch("sw2")
        result = arrange([sw1, sw2])
        nodes = self.nodes(result)
        self.assertEqual(nodes["sw1"].y, nodes["sw2"].y)
        self.assertEqual(nodes["sw1"].x, ICON / 2)
        self.assertLess(nodes["sw1"].x, nodes["sw2"].x)

    def test_straight_links(self):
        sw1, sw2 = self.switch("sw1"), self.switch("sw2")
        wire = self.brick("wire", "w1", sw1.socks[0], sw2.socks[0])
        tap = self.brick("tap", "tap0", sw1.socks[0])
        sw1.place, wire.place, sw2.place = (
            Point(0, 0),
            Point(100, 0),
            Point(200, 0),
        )
        tap.place = Point(0, 200)
        result = arrange([sw1, sw2, wire, tap])
        found = {
            (link.tail.name, link.head.name): link for link in result.links
        }
        self.assertEqual(
            set(found), {("sw1", "w1"), ("w1", "sw2"), ("tap0", "sw1")}
        )
        # from the right side of sw1 to the left side of w1, at the middle of
        # their boxes, in thirds
        middle = NAME / 2 - result.top
        self.assertEqual(
            found[("sw1", "w1")].points,
            (
                (64, middle),
                (64 + 36 / 3, middle),
                (64 + 2 * 36 / 3, middle),
                (100, middle),
            ),
        )
        # from the top of tap0 to the bottom of sw1
        (x0, y0), (x1, y1) = found[("tap0", "sw1")].points[::3]
        self.assertEqual((x0, x1), (ICON / 2, ICON / 2))
        self.assertEqual(y0, 200 - ICON / 2 - result.top)
        self.assertEqual(y1, ICON / 2 + NAME - result.top)

    def test_one_link_between_two_bricks(self):
        sw = self.switch("sw")
        vm = self.brick("qemu", "vm", sw.socks[0], sw.socks[0])
        sw.place, vm.place = Point(0, 0), Point(200, 0)
        [link] = arrange([sw, vm]).links
        self.assertEqual({link.tail, link.head}, {sw, vm})

    def test_no_link_to_itself(self):
        vm = self.brick("qemu", "vm")
        sock = vm.add_sock()
        vm.add_plug(sock)
        vm.place = Point(0, 0)
        self.assertEqual(links([vm]), [(vm, vm)])
        self.assertEqual(arrange([vm]).links, ())

    def test_one_brick_on_another(self):
        sw1, sw2 = self.switch("sw1"), self.switch("sw2")
        self.brick("tap", "tap0", sw1.socks[0]).place = Point(5, 5)
        sw1.place = sw2.place = Point(5, 5)
        [link] = arrange(self.factory.bricks).links
        self.assertEqual(set(link.points), {(ICON / 2, (ICON + NAME) / 2)})

    def test_without_graphviz(self):
        def no(*args, **kwargs):
            raise AssertionError("Graphviz ran")

        self.patch(pygraphviz, "AGraph", no)
        sw = self.switch("sw")
        sw.place = Point(0, 0)
        tap = self.brick("tap", "tap0", sw.socks[0])
        self.assertEqual(len(arrange([sw, tap]).nodes), 2)
