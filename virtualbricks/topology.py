# -*- test-case-name: virtualbricks.tests.test_topology -*-
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
The places of the bricks of a project, and of the links between them, as
Graphviz lays them out, or by hand; the Topology tab draws them.

The places are in points, from the top left corner of the lab, y going
down; at 100% a point is a pixel. Each brick has a box: its icon, ICON
points wide and high, and below it its name, NAME points high. A long name
widens the box: the caller measures the names, in the font it draws them
with. Graphviz gets no text: a Graphviz with its own Pango, as the
pygraphviz wheels have, would lay it out with a second Pango in a process
where GTK loaded the system's. A link is a curve of cubic Bézier segments, its points as
Graphviz gives them: the start, then three points for each segment.

The links go from the bricks' plugs to the sockets they are connected to,
and their order places the bricks: a tap before its switch, a wire between
its two ends, and a virtual machine after the switches of its first plugs,
one more than half of them, and before those of the others. Two links
between the same two bricks are drawn as one.

A lab whose bricks have places is laid out by hand (page 35): each brick
where its place puts the middle of its icon, and the bricks without a place
in a row under the others, from the left, in their order. Its links are
straight, from the edge of a box to the edge of the other, aimed at their
middles; a brick plugged into itself has none. The layout keeps where its
top left corner is among the places, to give a point of the lab its place.
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Callable, Iterable

import pygraphviz

from virtualbricks.bricks import Brick, Point
from virtualbricks.bricks.sock import Sock

# The icon and the line of the name, at 100%.
ICON = 64
NAME = 20
# Without a measure, the width of a character of a name.
CHAR_WIDTH = 8
# The gap between the columns of a left to right layout, the rows of a top
# to bottom one, and between the bricks of a column or a row, in inches.
RANK_GAP = 1.0
BRICK_GAP = 0.4
# Left to right, and top to bottom.
DIRECTIONS = ("LR", "TB")

POINTS_PER_INCH = 72


@dataclasses.dataclass(frozen=True)
class Node:
    """A brick and its box: its centre, width and height."""

    brick: Brick
    x: float
    y: float
    width: float
    height: float


@dataclasses.dataclass(frozen=True)
class Link:
    """A link between two bricks, as a curve."""

    tail: Brick
    head: Brick
    points: tuple[tuple[float, float], ...]


@dataclasses.dataclass(frozen=True)
class Layout:
    """
    The size of the lab, its bricks in their order, and their links; and
    where its top left corner is among the places.
    """

    width: float = 0.0
    height: float = 0.0
    nodes: tuple[Node, ...] = ()
    links: tuple[Link, ...] = ()
    left: float = 0.0
    top: float = 0.0


def links(bricks: Iterable[Brick]) -> list[tuple[Brick, Brick]]:
    """
    The links of the bricks, as (tail, head): the tail comes first in the
    layout.
    """

    result = []
    for brick in bricks:
        connected = 0
        for plug in brick.plugs:
            # in nothing, or in the host-only network: no brick at the end
            if not isinstance(plug.sock, Sock):
                continue
            other = plug.sock.brick
            if brick.get_type() == "Tap":
                result.append((brick, other))
            elif len(brick.plugs) == 2:
                if connected == 0:
                    result.append((other, brick))
                else:
                    result.append((brick, other))
            elif connected < (len(brick.plugs) + 1) / 2:
                result.append((other, brick))
            else:
                result.append((brick, other))
            connected += 1
    return result


def _points(position: str) -> tuple[tuple[float, float], ...]:
    """The points of a pos attribute; the links have no arrows."""

    return tuple(
        (float(x), float(y))
        for x, y in (point.split(",") for point in position.split())
    )


def _inches(value: str) -> float:
    # to points, as precise as Graphviz's: its inches have five decimals
    return round(float(value) * POINTS_PER_INCH, 2)


def estimate(name: str) -> float:
    """The width of a name, roughly, when nothing measures it."""

    return len(name) * CHAR_WIDTH


def layout(
    bricks: Iterable[Brick],
    direction: str = "LR",
    measure: Callable[[str], float] = estimate,
) -> Layout:
    """
    Lay the bricks out, left to right ("LR") or top to bottom ("TB").
    measure(name) is the width of a name at 100%, in points.
    """

    if direction not in DIRECTIONS:
        raise ValueError(f"Unknown direction {direction!r}")
    bricks = list(bricks)
    if not bricks:
        return Layout()
    # strict: one link between two bricks
    graph = pygraphviz.AGraph(strict=True, directed=False)
    graph.graph_attr.update(
        rankdir=direction, ranksep=RANK_GAP, nodesep=BRICK_GAP
    )
    for brick in bricks:
        width = max(ICON, math.ceil(measure(brick.name)))
        graph.add_node(
            brick.name,
            label="",
            shape="box",
            fixedsize="true",
            width=width / POINTS_PER_INCH,
            height=(ICON + NAME) / POINTS_PER_INCH,
        )
    for tail, head in links(bricks):
        graph.add_edge(tail.name, head.name)
    graph.layout("dot")

    left, bottom, right, top = (
        float(value) for value in graph.graph_attr["bb"].split(",")
    )

    def place(x: float, y: float) -> tuple[float, float]:
        # from Graphviz's bottom left corner, y going up
        return x - left, top - y

    nodes = []
    for brick in bricks:
        node = graph.get_node(brick.name)
        x, y = _points(node.attr["pos"])[0]
        nodes.append(
            Node(
                brick,
                *place(x, y),
                _inches(node.attr["width"]),
                _inches(node.attr["height"]),
            )
        )
    by_name = {brick.name: brick for brick in bricks}
    edges = []
    for edge in graph.edges():
        points = tuple(place(x, y) for x, y in _points(edge.attr["pos"]))
        edges.append(Link(by_name[edge[0]], by_name[edge[1]], points))
    return Layout(right - left, top - bottom, tuple(nodes), tuple(edges))


def by_hand(bricks: Iterable[Brick]) -> bool:
    """Whether the lab is laid out by hand: one of its bricks has a place."""

    return any(brick.place is not None for brick in bricks)


def place_of(layout: Layout, node: Node) -> Point:
    """The place of a node of layout: the middle of its icon."""

    return Point(
        round(node.x + layout.left),
        round(node.y - node.height / 2 + ICON / 2 + layout.top),
    )


def places(layout: Layout) -> dict[Brick, Point]:
    """The place of each brick, where layout has it."""

    return {node.brick: place_of(layout, node) for node in layout.nodes}


def _edge(node: Node, towards: tuple[float, float]) -> tuple[float, float]:
    """Where the line from the middle of node's box to towards leaves it."""

    dx, dy = towards[0] - node.x, towards[1] - node.y
    if dx == 0 and dy == 0:
        return node.x, node.y
    t = min(
        node.width / 2 / abs(dx) if dx else math.inf,
        node.height / 2 / abs(dy) if dy else math.inf,
    )
    return node.x + dx * t, node.y + dy * t


def straight(tail: Node, head: Node) -> Link:
    """A straight link between two nodes, as a curve of one segment."""

    x0, y0 = _edge(tail, (head.x, head.y))
    x1, y1 = _edge(head, (tail.x, tail.y))
    dx, dy = x1 - x0, y1 - y0
    return Link(
        tail.brick,
        head.brick,
        (
            (x0, y0),
            (x0 + dx / 3, y0 + dy / 3),
            (x0 + 2 * dx / 3, y0 + 2 * dy / 3),
            (x1, y1),
        ),
    )


def arrange(
    bricks: Iterable[Brick], measure: Callable[[str], float] = estimate
) -> Layout:
    """
    Lay the bricks out by hand, from their places; measure(name) is the
    width of a name at 100%, in points.
    """

    bricks = list(bricks)
    if not bricks:
        return Layout()
    height = ICON + NAME
    widths = {
        brick: max(ICON, math.ceil(measure(brick.name))) for brick in bricks
    }
    nodes: dict[Brick, Node] = {}
    for brick in bricks:
        place = brick.place
        if place is not None:
            # the icon is at the top of the box
            nodes[brick] = Node(
                brick,
                place.x,
                place.y - ICON / 2 + height / 2,
                widths[brick],
                height,
            )
    # the others in a row under them
    row_x = row_y = 0.0
    if nodes:
        row_x = min(node.x - node.width / 2 for node in nodes.values())
        row_y = max(node.y + node.height / 2 for node in nodes.values())
        row_y += RANK_GAP * POINTS_PER_INCH
    for brick in bricks:
        if brick.place is None:
            width = widths[brick]
            nodes[brick] = Node(
                brick, row_x + width / 2, row_y + height / 2, width, height
            )
            row_x += width + BRICK_GAP * POINTS_PER_INCH
    ordered = [nodes[brick] for brick in bricks]
    left = min(node.x - node.width / 2 for node in ordered)
    top = min(node.y - node.height / 2 for node in ordered)
    right = max(node.x + node.width / 2 for node in ordered)
    bottom = max(node.y + node.height / 2 for node in ordered)
    # one link between two bricks, none from a brick to itself
    pairs: dict[frozenset[Brick], tuple[Brick, Brick]] = {}
    for tail, head in links(bricks):
        if tail is not head:
            pairs.setdefault(frozenset((tail, head)), (tail, head))
    edges = [
        straight(nodes[tail], nodes[head]) for tail, head in pairs.values()
    ]
    return Layout(
        right - left,
        bottom - top,
        tuple(
            dataclasses.replace(node, x=node.x - left, y=node.y - top)
            for node in ordered
        ),
        tuple(
            dataclasses.replace(
                edge,
                points=tuple((x - left, y - top) for x, y in edge.points),
            )
            for edge in edges
        ),
        left,
        top,
    )
