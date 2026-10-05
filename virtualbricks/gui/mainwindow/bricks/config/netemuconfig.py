# -*- test-case-name: virtualbricks.tests.gui.mainwindow.bricks.config.test_netemuconfig -*-
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
The panel of a Netemu: its two ends; its states, a list, and the values of
the one selected; and the chances of moving between the states, at each
period, a row for each.

A value goes from left to right, or both ways; the one from right to left
greys out while it's the same both ways. What a state doesn't move to, it
keeps: the grid shows it, and a row that adds up to more than 100 % is an
error.
"""

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Pango  # noqa: E402

from virtualbricks.gui.form import (
    HIGHEST,
)  # noqa: E402
from virtualbricks.gui.mainwindow.bricks.config.panel import (
    Panel,
)  # noqa: E402
from virtualbricks.gui.pango import pango_attr_list  # noqa: E402
from virtualbricks.i18n import _  # noqa: E402

# Around the texts of a state, and between the cells of the grid, in pixels.
GAP = 6


def summary(state) -> str:
    """What a state does, in a line."""

    return _("{bandwidth} bytes/s · {delay} ms · {loss:g} % lost").format(
        bandwidth=state.bandwidth, delay=state.delay, loss=state.loss
    )


def _bold(text: str) -> Gtk.Label:
    return Gtk.Label(
        visible=True,
        xalign=0.0,
        label=text,
        attributes=pango_attr_list(Pango.attr_weight_new(Pango.Weight.BOLD)),
    )


class StateRow(Gtk.ListBoxRow):
    """A state in the list: its name, and what it does."""

    def __init__(self, state) -> None:
        super().__init__(visible=True)
        box = Gtk.Box(
            visible=True,
            orientation=Gtk.Orientation.VERTICAL,
            margin_start=12,
            margin_end=12,
            margin_top=GAP,
            margin_bottom=GAP,
        )
        self.name = _bold("")
        self.words = Gtk.Label(visible=True, xalign=0.0)
        self.words.get_style_context().add_class("dim-label")
        box.pack_start(self.name, False, False, 0)
        box.pack_start(self.words, False, False, 0)
        self.add(box)
        self.update(state)

    def update(self, state) -> None:
        self.name.set_text(state.name)
        self.words.set_text(summary(state))


class Transitions(Gtk.Grid):
    """The chances of moving between the states, in %: a row for each."""

    def __init__(self, draft, changed) -> None:
        super().__init__(visible=True, column_spacing=GAP, row_spacing=GAP)
        self.draft = draft
        self.changed = changed
        # what each state keeps, by its index
        self.stays: dict[int, Gtk.Label] = {}
        self.names: list[str] = []
        self.rebuild()

    def rebuild(self) -> None:
        for child in self.get_children():
            child.destroy()
        states = self.draft.states
        self.names = [state.name for state in states]
        self.stays = {}
        self.attach(
            Gtk.Label(visible=True, label=_("From ↓ to →")), 0, 0, 1, 1
        )
        for column, state in enumerate(states, 1):
            self.attach(_bold(state.name), column, 0, 1, 1)
        for row, state in enumerate(states, 1):
            self.attach(_bold(state.name), 0, row, 1, 1)
            for column in range(1, len(states) + 1):
                self.attach(self._cell(row - 1, column - 1), column, row, 1, 1)
        self.update_stays()

    def _cell(self, row: int, column: int) -> Gtk.Widget:
        if row == column:
            label = Gtk.Label(visible=True, xalign=0.0)
            label.get_style_context().add_class("dim-label")
            self.stays[row] = label
            return label
        spin = Gtk.SpinButton(visible=True, numeric=True, digits=2)
        spin.set_range(0, 100)
        spin.set_increments(1, 10)
        spin.set_value(self.draft.weights[row][column])
        spin.set_tooltip_text(
            _("From {first} to {second}").format(
                first=self.draft.states[row].name,
                second=self.draft.states[column].name,
            )
        )
        spin.connect("value-changed", self.on_value_changed, row, column)
        return spin

    def update_stays(self) -> None:
        for index, label in self.stays.items():
            percent = round(self.draft.stays(index), 2)
            label.set_text(_("{percent:g} % stays").format(percent=percent))

    def on_value_changed(self, spin, row: int, column: int) -> None:
        self.draft.set_weight(row, column, spin.get_value())
        self.update_stays()
        self.changed()


class NetemuPanel(Panel):
    """The settings of a Netemu."""

    def build(self, form):
        form.section(_("Ends"))
        form.socket(0, _("Left end"), _("The switch at one end of the link"))
        form.socket(1, _("Right end"), _("The switch at the other end"))

        self.states = Gtk.ListBox(visible=True)
        self.states.connect("row-selected", self.on_state_selected)
        self.add_button = Gtk.Button.new_from_icon_name(
            "list-add-symbolic", Gtk.IconSize.BUTTON
        )
        self.add_button.set_tooltip_text(_("Add a state after this one"))
        self.remove_button = Gtk.Button.new_from_icon_name(
            "list-remove-symbolic", Gtk.IconSize.BUTTON
        )
        self.remove_button.set_tooltip_text(_("Remove this state"))
        self.add_button.connect("clicked", self.on_add_clicked)
        self.remove_button.connect("clicked", self.on_remove_clicked)
        tools = Gtk.Box(visible=True, spacing=GAP, margin=GAP)
        for button in (self.add_button, self.remove_button):
            button.get_style_context().add_class("flat")
            button.show()
            tools.pack_start(button, False, False, 0)
        first = Gtk.Label(
            visible=True, label=_("The emulator starts in the first state")
        )
        first.get_style_context().add_class("dim-label")
        tools.pack_end(first, False, False, 0)
        box = Gtk.Box(visible=True, orientation=Gtk.Orientation.VERTICAL)
        box.pack_start(self.states, False, False, 0)
        box.pack_start(Gtk.Separator(visible=True), False, False, 0)
        box.pack_start(tools, False, False, 0)
        form.section(_("States"), box)

        form.section(_("Values"))
        form.entry("name")
        form.pair(
            "bandwidth", "bandwidth_right_to_left", "bandwidth_symmetric"
        )
        form.pair("delay", "delay_right_to_left", "delay_symmetric")
        form.pair(
            "buffer_size", "buffer_size_right_to_left", "buffer_size_symmetric"
        )
        form.pair("loss", "loss_right_to_left", "loss_symmetric")

        form.section(_("Transitions"))
        self.period = Gtk.SpinButton(visible=True, numeric=True)
        self.period.set_range(1, HIGHEST)
        self.period.set_increments(10, 100)
        self.period.set_value(self.draft.period)
        self.period.connect("value-changed", self.on_period_changed)
        form.row(
            "period",
            self.period,
            _("Period"),
            _("How often, in ms, the emulator may change state"),
        )
        self.transitions = Transitions(self.draft, self.on_changed)
        form.row(
            "transitions",
            self.transitions,
            _("Chances"),
            _(
                "At each period, the chance in % of moving from a state, a row,"
                " to another"
            ),
        )
        self._fill()

    def _fill(self) -> None:
        """The list of the states, the selected one selected."""

        self._filling = True
        try:
            for row in self.states.get_children():
                row.destroy()
            for state in self.draft.states:
                self.states.add(StateRow(state))
            self.states.select_row(
                self.states.get_row_at_index(self.draft.selected)
            )
        finally:
            self._filling = False
        self.remove_button.set_sensitive(len(self.draft.states) > 1)

    def on_changed(self) -> None:
        row = self.states.get_row_at_index(self.draft.selected)
        if row is not None:
            row.update(self.draft.states[self.draft.selected])
        if [
            state.name for state in self.draft.states
        ] != self.transitions.names:
            self.transitions.rebuild()
        super().on_changed()

    def _show_another(self) -> None:
        self.form.reload()
        self.on_changed()

    def on_state_selected(self, listbox, row) -> None:
        if row is None or getattr(self, "_filling", False):
            return
        self.draft.select(row.get_index())
        self._show_another()

    def on_add_clicked(self, button) -> None:
        self.draft.add()
        self._fill()
        self.transitions.rebuild()
        self._show_another()

    def on_remove_clicked(self, button) -> None:
        self.draft.remove()
        self._fill()
        self.transitions.rebuild()
        self._show_another()

    def on_period_changed(self, spin) -> None:
        self.draft.period = spin.get_value_as_int()
        self.on_changed()

    def running_words(self) -> str:
        return _(
            "{brick} is running. The states and the transitions change at"
            " once; the ends when it starts again."
        ).format(brick=self.draft.brick.name)
