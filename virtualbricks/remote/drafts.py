# -*- test-case-name: virtualbricks.tests.remote.test_drafts -*-
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

"""
The OK of a panel over a connection (page 19 §7, R7 B): what the draft on
the copy changed, as data, and that data given to a draft of the object of
the Virtualbricks of the bricks, which applies it as its own panel would.

``what_changed()`` reads a draft on the copy: ``changes``, the settings
changed, by name, as the project file writes them; ``links``, the plugs
moved, each an index and the target of its socket, "" for nothing; and
``extras``, what a brick has beyond its settings, only when it changed: the
``cards`` of a machine, and the ``states``, ``transitions`` and ``period``
of a Netemu. ``apply_changes()`` sets them on a new draft of the object of
a factory and applies it: all or nothing, and only what the panel changed,
so the last OK wins for those, and the rest keeps what another window set
meanwhile. A running brick takes at once what it can, as with a panel.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from virtualbricks.bricks.draft import Draft, apply
from virtualbricks.bricks.event import is_event
from virtualbricks.bricks.netemu import NetemuConfig, NetemuDraft
from virtualbricks.bricks.virtualmachine import (
    DISK_IMAGES,
    Card,
    HostonlySock,
    ImageDraft,
    VirtualMachineDraft,
    hostonly_sock,
    is_disk_image,
    is_virtualmachine,
)
from virtualbricks.config.projectfile import HOSTONLY, resolve, socket_target
from virtualbricks.config.report import Report
from virtualbricks.config.schema import (
    dump_record,
    field_names,
    kind_of,
    load_record,
)
from virtualbricks.remote.commands import BRICK, EVENT, IMAGE

if TYPE_CHECKING:  # pragma: no cover
    from virtualbricks.brickfactory import BrickFactory
    from virtualbricks.bricks.plug import Plug
    from virtualbricks.bricks.sock import Sock
    from virtualbricks.bricks.virtualmachine import VirtualMachine
    from virtualbricks.remote.follower import Item


def draft_of(factory: BrickFactory, item: Item) -> Draft:
    """A new draft of item, a brick, an event or an image, as a panel's."""

    if is_disk_image(item):
        return ImageDraft(item, factory)
    if is_event(item):
        return Draft(item)
    return item.draft_factory(item)


def _target(sock: Sock | HostonlySock | None) -> str:
    if sock is None:
        return ""
    if isinstance(sock, HostonlySock):
        return HOSTONLY
    return socket_target(sock)


def _cards_of(brick: VirtualMachine) -> list[Card]:
    return [
        Card("plug", plug.model, plug.mac, plug.sock, plug)
        for plug in brick.plugs
    ] + [
        Card("socket", sock.model, sock.mac, None, sock)
        for sock in brick.socks
    ]


def _card_data(card: Card, links: list[Plug | Sock]) -> dict[str, object]:
    index = next(
        (i for i, link in enumerate(links) if link is card.link), None
    )
    return {
        "kind": card.kind,
        "model": card.model,
        "mac": card.mac,
        "connect": _target(card.sock),
        "link": index,
    }


def what_changed(draft: Draft) -> dict[str, Any]:
    """What the OK of the panel of draft gives: changes, links, extras."""

    settings = draft.settings
    names = set(draft.changes())
    if isinstance(draft, VirtualMachineDraft):
        # the images of the disks, which the draft gives apart
        names |= {
            name
            for name in DISK_IMAGES
            if getattr(settings, name) != getattr(draft.original, name)
        }
    changes = {
        name: kind_of(settings, name).to_data(getattr(settings, name))
        for name in field_names(settings)
        if name in names
    }
    links = [[index, _target(sock)] for index, sock in draft.moved().items()]
    extras: dict[str, object] = {}
    brick = draft.brick
    if isinstance(draft, VirtualMachineDraft):
        links_now = list(brick.plugs) + list(brick.socks)
        cards = [_card_data(card, links_now) for card in draft.cards]
        before = [_card_data(card, links_now) for card in _cards_of(brick)]
        if cards != before:
            extras["cards"] = cards
    if isinstance(draft, NetemuDraft):
        manager = brick.markov_manager
        if (
            draft.states != manager.states
            or draft.weights != manager.weights
            or draft.period != brick.transPeriod
        ):
            extras["states"] = [dump_record(state) for state in draft.states]
            extras["transitions"] = [list(row) for row in draft.weights]
            extras["period"] = draft.period
    return {"changes": changes, "links": links, "extras": extras}


def _socket(
    factory: BrickFactory, target: str, where: str
) -> Sock | HostonlySock | None:
    if not target:
        return None
    if target == HOSTONLY:
        return hostonly_sock
    sock = resolve(factory, target)
    if sock is None:
        raise ValueError(f"{where}: no socket {target}")
    return sock


def apply_changes(
    factory: BrickFactory, kind: str, name: str, data: dict[str, Any]
) -> None:
    """
    Give the object name of kind in factory what a panel changed, data as
    what_changed() makes it. LookupError if there is no such object,
    ValueError if the data doesn't fit it or the draft has errors; either
    way nothing changes.
    """

    item = {
        BRICK: factory.get_brick,
        EVENT: factory.get_event,
        IMAGE: factory.get_image,
    }[kind](name)
    if item is None:
        raise LookupError(f"No {kind} named {name}")
    draft = draft_of(factory, item)
    report = Report()
    for key, value in data.get("changes", {}).items():
        if key not in field_names(draft.settings):
            raise ValueError(f"{name} has no setting {key}")
        try:
            value = kind_of(draft.settings, key).from_data(value, report, key)
        except ValueError as exc:
            raise ValueError(f"{key}: {exc}") from None
        draft.set(key, value)
    for index, target in data.get("links", []):
        if not 0 <= index < len(draft.links):
            raise ValueError(f"{name} has no plug {index}")
        draft.link(index, _socket(factory, target, f"plug {index}"))
    extras = data.get("extras", {})
    if "cards" in extras and isinstance(draft, VirtualMachineDraft):
        assert is_virtualmachine(item), "a machine's draft is of a machine"
        links = list(item.plugs) + list(item.socks)
        draft.cards = [
            Card(
                card["kind"],
                card["model"],
                card["mac"],
                _socket(factory, card.get("connect", ""), "card"),
                links[card["link"]] if card.get("link") is not None else None,
            )
            for card in extras["cards"]
        ]
    if "states" in extras and isinstance(draft, NetemuDraft):
        draft.states = [
            load_record(NetemuConfig, state, report, f"states[{i}]")
            for i, state in enumerate(extras["states"])
        ]
        draft.weights = [list(row) for row in extras["transitions"]]
        draft.period = extras["period"]
    if report.messages:
        message = report.messages[0]
        raise ValueError(f"{message.where}: {message.text}")
    # ValueError if the draft has errors
    apply(draft)
