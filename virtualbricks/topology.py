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

The links are straight, curved or at right angles, as the project chooses
(LINES); Graphviz draws them so in its own layouts. Its program in Graphviz
2.42 fails on some labs at right angles: their links are curved.

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

Its links can be curved or at right angles instead (page 36): Graphviz
routes them around the boxes, and moves no brick. Two boxes too close for a
link between them have their links routed around their icons; when two
icons are that close, the links stay straight.
"""

from __future__ import annotations

import dataclasses
import itertools
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
# The lines of the links, as the setting link_lines of a project has them:
# straight, Graphviz's curves around the bricks, or its right angles.
STRAIGHT = "straight"
CURVED = "curved"
RIGHT_ANGLES = "right-angles"
LINES = (STRAIGHT, CURVED, RIGHT_ANGLES)
_SPLINES = {STRAIGHT: "false", CURVED: "true", RIGHT_ANGLES: "ortho"}

POINTS_PER_INCH = 72

# Graphviz routes curved links this far around a box, in points. Two boxes
# closer than twice that touch, a point more in Graphviz 14, which counts
# the outline of a box, and then it draws every link straight: bricks this
# close are routed around their icons. TOUCH has a point to spare. Right
# angles touch only when the boxes do, but the same bricks go round.
MARGIN = 3.2
TOUCH = 2 * MARGIN + 2


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


def _check_lines(lines: str) -> None:
    if lines not in LINES:
        raise ValueError(f"Unknown lines {lines!r}")


def _lay_out(graph: pygraphviz.AGraph, program: str, lines: str) -> None:
    """Lay graph out with program; right angles it can't route, as curves."""

    try:
        graph.layout(program)
    except OSError:
        # the program of Graphviz 2.42 fails an assertion on a lab now and
        # then; pygraphviz 2 runs a later Graphviz, without the program
        if lines != RIGHT_ANGLES:
            raise
        graph.graph_attr["splines"] = _SPLINES[CURVED]
        graph.layout(program)


def layout(
    bricks: Iterable[Brick],
    direction: str = "LR",
    measure: Callable[[str], float] = estimate,
    lines: str = CURVED,
) -> Layout:
    """
    Lay the bricks out, left to right ("LR") or top to bottom ("TB"), their
    links drawn with lines, one of LINES. measure(name) is the width of a
    name at 100%, in points.
    """

    if direction not in DIRECTIONS:
        raise ValueError(f"Unknown direction {direction!r}")
    _check_lines(lines)
    bricks = list(bricks)
    if not bricks:
        return Layout()
    # strict: one link between two bricks
    graph = pygraphviz.AGraph(strict=True, directed=False)
    graph.graph_attr.update(
        rankdir=direction,
        ranksep=RANK_GAP,
        nodesep=BRICK_GAP,
        splines=_SPLINES[lines],
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
    _lay_out(graph, "dot", lines)

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


def _box(node: Node, icon: bool = False) -> tuple[float, float, float, float]:
    """The middle of node's box, its width and its height; or its icon's."""

    if icon:
        return node.x, node.y - node.height / 2 + ICON / 2, ICON, ICON
    return node.x, node.y, node.width, node.height


def _touch(
    box: tuple[float, float, float, float],
    other: tuple[float, float, float, float],
) -> bool:
    """Whether two boxes are too close for Graphviz to route between."""

    (x0, y0, width0, height0), (x1, y1, width1, height1) = box, other
    return (
        abs(x0 - x1) < (width0 + width1) / 2 + TOUCH
        and abs(y0 - y1) < (height0 + height1) / 2 + TOUCH
    )


def route(layout: Layout, lines: str = CURVED) -> Layout:
    """
    A layout by hand with its links routed around the bricks by Graphviz,
    as curves or at right angles; or as it is if its lines are straight, it
    has no link, or two icons touch.
    """

    _check_lines(lines)
    if lines == STRAIGHT or not layout.links:
        return layout
    close: set[Brick] = set()
    for node, other in itertools.combinations(layout.nodes, 2):
        if _touch(_box(node), _box(other)):
            close.update((node.brick, other.brick))
    boxes = {
        node.brick: _box(node, node.brick in close) for node in layout.nodes
    }
    for icon, other_icon in itertools.combinations(close, 2):
        if _touch(boxes[icon], boxes[other_icon]):
            return layout
    graph = pygraphviz.AGraph(strict=True, directed=False)
    # the places in points, and the bricks pinned to them
    graph.graph_attr.update(
        splines=_SPLINES[lines],
        inputscale=POINTS_PER_INCH,
        notranslate="true",
        esep=f"+{MARGIN}",
    )
    for brick, (x, y, width, height) in boxes.items():
        graph.add_node(
            brick.name,
            label="",
            shape="box",
            fixedsize="true",
            width=width / POINTS_PER_INCH,
            height=height / POINTS_PER_INCH,
            # y going up
            pos=f"{x},{-y}!",
        )
    for link in layout.links:
        graph.add_edge(link.tail.name, link.head.name)
    _lay_out(graph, "neato", lines)

    # Graphviz moves the whole drawing, as far as it moves any brick
    first = layout.nodes[0].brick
    x, y = boxes[first][:2]
    [(gx, gy)] = _points(graph.get_node(first.name).attr["pos"].rstrip("!"))
    dx, dy = x - gx, -y - gy
    links = []
    for link in layout.links:
        route = graph.get_edge(link.tail.name, link.head.name).attr["pos"]
        points = tuple((px + dx, -(py + dy)) for px, py in _points(route))
        links.append(dataclasses.replace(link, points=points))
    return dataclasses.replace(layout, links=tuple(links))
