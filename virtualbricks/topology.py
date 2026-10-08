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
Graphviz lays them out; the Topology tab draws them.

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
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Callable, Iterable

import pygraphviz

from virtualbricks.bricks import Brick
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
    """The size of the lab, its bricks in their order, and their links."""

    width: float = 0.0
    height: float = 0.0
    nodes: tuple[Node, ...] = ()
    links: tuple[Link, ...] = ()


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
