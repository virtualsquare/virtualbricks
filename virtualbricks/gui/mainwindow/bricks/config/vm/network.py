# -*- test-case-name: virtualbricks.tests.gui.mainwindow.bricks.config.vm.test_network -*-
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
The Network section of a virtual machine: its cards, each a row of the
draft, with its model, its MAC address and what it plugs into.

A card plugs into nothing, QEMU's own user network, a switch, or a socket
card of another brick when the settings allow female plugs; or it is a
socket that other bricks plug into. Add Card adds a card in nothing, and a
card's Remove removes it. Nothing reaches the machine before OK.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Pango  # noqa: E402

from virtualbricks.bricks.draft import Problem  # noqa: E402
from virtualbricks.bricks.virtualmachine import (  # noqa: E402
    Card,
    hostonly_sock,
)
from virtualbricks.gui.form import (  # noqa: E402
    show_problem,
    socket_name,
)
from virtualbricks.gui.mainwindow.bricks.config.picker import (  # noqa: E402
    Option,
    Picker,
)
from virtualbricks.gui.mainwindow.bricks.config.vm.machine import (  # noqa: E402
    missing,
)
from virtualbricks.gui.pango import pango_attr_list  # noqa: E402
from virtualbricks.i18n import _  # noqa: E402
from virtualbricks.nic import random_mac  # noqa: E402
from virtualbricks.programs import QemuInfo  # noqa: E402

if TYPE_CHECKING:  # pragma: no cover
    from virtualbricks.gui.mainwindow.bricks.config.vm.panel import (
        Page,
        VirtualMachinePanel,
    )

GAP = 8
NOTHING = ""
HOST = "host"
SOCKET = "socket"


def model_options(info: QemuInfo | None, chosen: str) -> list[Option]:
    """The card models of a QEMU; the chosen one by its own name."""

    if info is None:
        return []
    device = info.device(chosen)
    return [
        Option(
            chosen if other is device else other.name,
            other.name,
            other.description,
        )
        for other in info.devices
        if other.category == "Network devices"
    ]


def build(panel: VirtualMachinePanel, page: Page) -> None:
    cards = Cards(panel)
    panel.cards = cards
    page.form.add(cards)
    page.keys.add("cards")
    page.keys.update(f"card{index}" for index in range(64))
    panel.refreshers.append(cards.refresh)
    panel.fillers.append(cards.fill)


def _bold(text: str) -> Gtk.Label:
    return Gtk.Label(
        visible=True,
        xalign=0.0,
        label=text,
        attributes=pango_attr_list(Pango.attr_weight_new(Pango.Weight.BOLD)),
    )


class CardRow(Gtk.ListBoxRow):
    """A card: eth and its number, its model, its MAC, where it plugs."""

    def __init__(self, cards: Cards, index: int) -> None:
        super().__init__(visible=True, activatable=False, selectable=False)
        self.cards = cards
        self.index = index
        draft = cards.panel.draft
        card = draft.cards[index]
        grid = Gtk.Grid(
            visible=True, column_spacing=12, row_spacing=6, margin=10
        )
        grid.attach(_bold(f"eth{index}"), 0, 0, 1, 1)
        self.remove_button = Gtk.Button.new_from_icon_name(
            "list-remove-symbolic", Gtk.IconSize.BUTTON
        )
        self.remove_button.set_tooltip_text(_("Remove the card"))
        self.remove_button.get_style_context().add_class("flat")
        self.remove_button.set_halign(Gtk.Align.END)
        self.remove_button.set_hexpand(True)
        self.remove_button.show()
        self.remove_button.connect(
            "clicked", lambda button: cards.remove_card(self.index)
        )
        grid.attach(self.remove_button, 2, 0, 1, 1)

        self.model = Picker(card.model, self.on_model, missing(draft))
        self.mac = Gtk.Entry(visible=True, text=card.mac, width_chars=19)
        self.mac.connect("changed", self.on_mac)
        new_mac = Gtk.Button.new_from_icon_name(
            "view-refresh-symbolic", Gtk.IconSize.BUTTON
        )
        new_mac.set_tooltip_text(_("A new random address"))
        new_mac.show()
        new_mac.connect(
            "clicked", lambda button: self.mac.set_text(random_mac())
        )
        mac = Gtk.Box(visible=True)
        mac.get_style_context().add_class("linked")
        mac.pack_start(self.mac, False, False, 0)
        mac.pack_start(new_mac, False, False, 0)
        self.plugged = Gtk.ComboBoxText(visible=True)
        self.sockets = draft.sockets()
        if card.sock is not None and card.sock is not hostonly_sock:
            if card.sock not in self.sockets:
                self.sockets.append(card.sock)
        self.plugged.append(NOTHING, _("Nothing"))
        self.plugged.append(HOST, _("The host only, on QEMU's user network"))
        for position, sock in enumerate(self.sockets):
            self.plugged.append(str(position), socket_name(sock))
        machine = cards.panel.engine.machine
        if card.kind == SOCKET or machine.setting("allow_female_plugs"):
            self.plugged.append(SOCKET, _("Other bricks plug into it"))
        self.plugged.set_active_id(self._plugged_id(card))
        self.plugged.connect("changed", self.on_plugged)
        for line, (words, widget) in enumerate(
            (
                (_("Model"), self.model),
                (_("MAC address"), mac),
                (_("Plugged into"), self.plugged),
            ),
            1,
        ):
            label = Gtk.Label(visible=True, xalign=0.0, label=words)
            label.get_style_context().add_class("dim-label")
            grid.attach(label, 0, line, 1, 1)
            grid.attach(widget, 1, line, 2, 1)
            widget.set_halign(Gtk.Align.START)
        self.problem = Gtk.Label(visible=False, xalign=0.0, wrap=True)
        grid.attach(self.problem, 0, 4, 3, 1)
        self.add(grid)

    def _plugged_id(self, card: Card) -> str:
        if card.kind == SOCKET:
            return SOCKET
        if card.sock is None:
            return NOTHING
        if card.sock is hostonly_sock:
            return HOST
        return str(self.sockets.index(card.sock))

    def on_model(self, value: str) -> None:
        self.cards.change(self.index, model=value)

    def on_mac(self, entry: Gtk.Entry) -> None:
        self.cards.change(self.index, mac=entry.get_text())

    def on_plugged(self, combo: Gtk.ComboBoxText) -> None:
        chosen = combo.get_active_id()
        if chosen == SOCKET:
            self.cards.change(self.index, rebuild=True, kind=SOCKET)
            return
        if chosen == NOTHING:
            sock = None
        elif chosen == HOST:
            sock = hostonly_sock
        else:
            assert chosen is not None, "a choice is always active"
            sock = self.sockets[int(chosen)]
        kind = self.cards.panel.draft.cards[self.index].kind
        self.cards.change(
            self.index, rebuild=kind != "plug", kind="plug", sock=sock
        )

    def show_problem(self, problem: Problem | None) -> None:
        show_problem(self.problem, problem)


class Cards(Gtk.Box):
    """The cards of the draft, and Add Card."""

    def __init__(self, panel: VirtualMachinePanel) -> None:
        super().__init__(
            visible=True, orientation=Gtk.Orientation.VERTICAL, spacing=GAP
        )
        self.panel = panel
        self.pack_start(_bold(_("Network cards")), False, False, 0)
        self.lack = Gtk.Label(visible=False, xalign=0.0, wrap=True)
        self.pack_start(self.lack, False, False, 0)
        self.list = Gtk.ListBox(
            visible=True, selection_mode=Gtk.SelectionMode.NONE
        )
        self.list.set_placeholder(
            Gtk.Label(visible=True, label=_("No network card"), margin=12)
        )
        self.list.set_header_func(self._separate)
        frame = Gtk.Frame(visible=True)
        frame.add(self.list)
        self.pack_start(frame, False, False, 0)
        self.add_button = Gtk.Button(
            visible=True, label=_("Add Card"), halign=Gtk.Align.START
        )
        self.add_button.connect("clicked", lambda button: self.add_card())
        self.pack_start(self.add_button, False, False, 0)
        self.rebuild()

    @staticmethod
    def _separate(row: Gtk.ListBoxRow, before: Gtk.ListBoxRow | None) -> None:
        if before is not None and row.get_header() is None:
            row.set_header(Gtk.Separator(visible=True))

    def rows(self) -> list[CardRow]:
        rows = [
            row for row in self.list.get_children() if isinstance(row, CardRow)
        ]
        return sorted(rows, key=lambda row: row.index)

    def rebuild(self) -> None:
        for row in self.list.get_children():
            row.destroy()
        for index in range(len(self.panel.draft.cards)):
            self.list.add(CardRow(self, index))
        self.fill()

    def fill(self) -> None:
        draft = self.panel.draft
        for row in self.rows():
            card = draft.cards[row.index]
            row.model.missing = missing(draft)
            row.model.set_options(model_options(draft.qemu, card.model))

    def refresh(self) -> None:
        problems = self.panel.draft.problems()
        found: dict[str, Problem] = {}
        for problem in problems:
            found.setdefault(problem.key, problem)
        for row in self.rows():
            row.show_problem(found.get(f"card{row.index}"))
        show_problem(self.lack, found.get("cards"))

    def change(self, index: int, rebuild: bool = False, **values: Any) -> None:
        self.panel.draft.set_card(index, **values)
        if rebuild:
            self.rebuild()
        self.panel.on_changed()

    def add_card(self) -> None:
        self.panel.draft.add_card()
        self.rebuild()
        self.panel.on_changed()

    def remove_card(self, index: int) -> None:
        self.panel.draft.remove_card(index)
        self.rebuild()
        self.panel.on_changed()
