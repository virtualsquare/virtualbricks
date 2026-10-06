# -*- test-case-name: virtualbricks.tests.gui.mainwindow.events.test_eventeditor -*-
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
The settings of an event, in the Events tab: its delay, and its actions,
chosen instead of typed.

The delay is a number of seconds. Each action is a row: its kind, then the
brick, the event or the command it does it to, and a button that removes it;
Add Action adds one. The kinds are those of
:mod:`virtualbricks.bricks.eventinfo`: start or stop a brick or an
event, a command of the console, a shell command on the host. An event isn't
among the events that it can start or stop.

An action whose brick or event isn't in the project keeps its name, marked
missing, until it changes. An action without a brick, an event or a command
is left out.

The editor is a panel on a draft of the event, of
:mod:`virtualbricks.bricks.draft`: each change goes into the draft, as the
event keeps its actions, and OK gives the event what changed, so that an
event saved without changes stays the same.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from virtualbricks.gui.mainwindow.bricks.config.panel import (  # noqa: E402
    Panel,
)
from virtualbricks.bricks import eventinfo  # noqa: E402
from virtualbricks.console.dispatch import check  # noqa: E402
from virtualbricks.bricks.eventinfo import (  # noqa: E402
    Action,
    Kind,
)
from virtualbricks.gui.mainwindow.tab import icon_button  # noqa: E402
from virtualbricks.i18n import _  # noqa: E402

if TYPE_CHECKING:  # pragma: no cover
    from virtualbricks.brickfactory import BrickFactory
    from virtualbricks.gui.form import Form

# Between the widgets, in pixels.
GAP = 8
# The longest delay, in seconds: the most a spin button holds.
MAX_DELAY = 2**31 - 1

# The kinds of actions in their menu, None for a separator.
KINDS = (
    (Kind.START_BRICK, _("Start a brick")),
    (Kind.STOP_BRICK, _("Stop a brick")),
    (Kind.START_EVENT, _("Start an event")),
    (Kind.STOP_EVENT, _("Stop an event")),
    None,
    (Kind.CONSOLE, _("Console command")),
    (Kind.SHELL, _("Shell command")),
)
SEPARATOR_ID = "separator"
# What the subject of an action of each kind is.
BRICK, EVENT, COMMAND = "brick", "event", "command"
SUBJECTS = {
    Kind.START_BRICK: BRICK,
    Kind.STOP_BRICK: BRICK,
    Kind.START_EVENT: EVENT,
    Kind.STOP_EVENT: EVENT,
    Kind.CONSOLE: COMMAND,
    Kind.SHELL: COMMAND,
}
PLACEHOLDERS = {
    Kind.CONSOLE: _("A command of the console, as “brick set vm1 memory=512”"),
    Kind.SHELL: _("A command for the shell of the host"),
}


def delay_button(seconds: int) -> Gtk.SpinButton:
    """A number of seconds, from 0 to MAX_DELAY."""

    return Gtk.SpinButton(
        visible=True,
        adjustment=Gtk.Adjustment(
            value=seconds,
            lower=0,
            upper=MAX_DELAY,
            step_increment=1,
            page_increment=10,
        ),
        numeric=True,
        digits=0,
        # not as wide as the longest delay
        width_chars=6,
    )


def _is_separator(model: Gtk.TreeModel, itr: Gtk.TreeIter) -> bool:
    # the id of a Gtk.ComboBoxText
    return model[itr][1] == SEPARATOR_ID


class ActionRow(Gtk.Box):
    """
    An action: its kind, the brick, the event or the command it does it to,
    and a button that removes it.
    """

    def __init__(
        self,
        action: Action,
        choices: dict[str, list[str]],
        factory: BrickFactory,
        changed: Callable[[], None],
    ) -> None:
        super().__init__(visible=True, spacing=GAP)
        # the names of the bricks and of the events, by BRICK and EVENT
        self.choices = choices
        self.factory = factory
        # called when the kind or the subject changes
        self.changed = changed
        self.kind = action.kind
        self.kind_combo = Gtk.ComboBoxText(visible=True)
        self.kind_combo.set_row_separator_func(_is_separator)
        for entry in KINDS:
            if entry is None:
                self.kind_combo.append(SEPARATOR_ID, "")
            else:
                kind, label = entry
                self.kind_combo.append(kind.value, label)
        self.kind_combo.set_active_id(action.kind.value)
        self.subject: Gtk.Entry | Gtk.ComboBoxText | None = None
        self.subject_box = Gtk.Box(visible=True)
        self.remove_button = Gtk.Button(
            visible=True, relief=Gtk.ReliefStyle.NONE
        )
        icon_button(
            self.remove_button, "user-trash-symbolic", _("Remove the action")
        )
        self.pack_start(self.kind_combo, False, False, 0)
        self.pack_start(self.subject_box, True, True, 0)
        self.pack_start(self.remove_button, False, False, 0)
        self._show_subject(action.subject)
        self.kind_combo.connect("changed", self.on_kind_changed)

    def _show_subject(self, subject: str) -> None:
        """The field of the subject, for the kind: a choice, or a text."""

        if self.subject is not None:
            self.subject.destroy()
        source = SUBJECTS[self.kind]
        widget: Gtk.Entry | Gtk.ComboBoxText
        if source == COMMAND:
            widget = Gtk.Entry(
                visible=True,
                text=subject,
                placeholder_text=PLACEHOLDERS[self.kind],
            )
            if self.kind is Kind.CONSOLE:
                # the parser says what's wrong, as it's typed
                widget.connect("changed", self._check_command)
                self._check_command(widget)
        else:
            widget = Gtk.ComboBoxText(visible=True)
            names = self.choices[source]
            for name in names:
                widget.append(name, name)
            if subject and subject not in names:
                label = subject
                if eventinfo.missing(Action(self.kind, subject), self.factory):
                    label = _("{name} (missing)").format(name=subject)
                widget.append(subject, label)
            chosen = subject or (names[0] if names else None)
            if chosen is not None:
                widget.set_active_id(chosen)
        widget.connect("changed", lambda widget: self.changed())
        self.subject = widget
        self.subject_box.pack_start(widget, True, True, 0)

    def _check_command(self, entry: Gtk.Entry) -> None:
        text = entry.get_text()
        problem = check(self.factory, text) if text.strip() else None
        where = Gtk.EntryIconPosition.SECONDARY
        entry.set_icon_from_icon_name(
            where, "dialog-warning-symbolic" if problem else None
        )
        entry.set_icon_tooltip_text(where, problem)

    def _subject(self) -> str:
        if isinstance(self.subject, Gtk.Entry):
            return self.subject.get_text()
        assert self.subject is not None, "the row shows its subject"
        return self.subject.get_active_id() or ""

    def action(self) -> Action | None:
        """The action of the row, or None without a subject."""

        subject = self._subject()
        if not subject.strip():
            return None
        return Action(self.kind, subject)

    def on_kind_changed(self, combo: Gtk.ComboBoxText) -> None:
        chosen = combo.get_active_id()
        assert chosen is not None, "a kind is always active"
        kind = Kind(chosen)
        # the brick stays a brick, the command a command
        subject = self._subject()
        if SUBJECTS[kind] != SUBJECTS[self.kind]:
            subject = ""
        self.kind = kind
        self._show_subject(subject)
        self.changed()


class EventEditor(Panel):
    """The delay and the actions of an event, on a draft."""

    def build(self, form: Form) -> Gtk.Box:
        event = self.draft.brick
        factory = event.factory
        self.choices = {
            BRICK: [brick.name for brick in factory.bricks],
            EVENT: [
                other.name for other in factory.events if other is not event
            ],
        }
        self.panel = Gtk.Box(
            visible=True, orientation=Gtk.Orientation.VERTICAL, spacing=GAP
        )

        delay = Gtk.Box(visible=True, spacing=GAP)
        # one sentence for the translators, around the number
        before, _sep, after = _("Wait {delay} seconds, then:").partition(
            "{delay}"
        )
        self.delay = delay_button(self.draft.get("delay"))
        self.delay.connect("value-changed", self.on_delay_changed)
        for widget in (
            Gtk.Label(visible=True, label=before.strip()),
            self.delay,
            Gtk.Label(visible=True, label=after.strip()),
        ):
            delay.pack_start(widget, False, False, 0)

        self.actions = Gtk.Box(
            visible=True, orientation=Gtk.Orientation.VERTICAL, spacing=GAP
        )
        # the kinds of the rows, as wide as the widest
        self._kinds = Gtk.SizeGroup(mode=Gtk.SizeGroupMode.HORIZONTAL)
        for command in self.draft.get("actions"):
            self.add(eventinfo.read(command, factory))

        self.add_button = Gtk.Button(
            visible=True,
            label=_("Add Action"),
            image=Gtk.Image.new_from_icon_name(
                "list-add-symbolic", Gtk.IconSize.BUTTON
            ),
            always_show_image=True,
            halign=Gtk.Align.START,
        )
        self.add_button.connect("clicked", self.on_add_clicked)

        self.panel.pack_start(delay, False, False, 0)
        self.panel.pack_start(self.actions, False, False, 0)
        self.panel.pack_start(self.add_button, False, False, 0)
        return self.panel

    def action_rows(self) -> list[ActionRow]:
        return [
            row
            for row in self.actions.get_children()
            if isinstance(row, ActionRow)
        ]

    def add(self, action: Action) -> ActionRow:
        """A row for action, after the others."""

        row = ActionRow(
            action,
            self.choices,
            self.draft.brick.factory,
            self.take_actions,
        )
        self._kinds.add_widget(row.kind_combo)
        row.remove_button.connect("clicked", self.on_remove_clicked, row)
        self.actions.pack_start(row, False, False, 0)
        return row

    def take_actions(self) -> None:
        """The actions of the rows into the draft, as the event keeps them."""

        actions = [row.action() for row in self.action_rows()]
        self.draft.set(
            "actions",
            [
                eventinfo.write(action)
                for action in actions
                if action is not None
            ],
        )
        self.on_changed()

    def running_words(self) -> str:
        return _(
            "{event} is waiting: when the wait is over, it runs its actions as"
            " they are then; a new delay counts from its next start."
        ).format(event=self.draft.brick.name)

    # Signals

    def on_delay_changed(self, spin: Gtk.SpinButton) -> None:
        self.draft.set("delay", spin.get_value_as_int())
        self.on_changed()

    def on_add_clicked(self, button: Gtk.Button) -> None:
        row = self.add(Action(Kind.START_BRICK, ""))
        self.take_actions()
        row.kind_combo.grab_focus()

    def on_remove_clicked(self, button: Gtk.Button, row: ActionRow) -> None:
        row.destroy()
        self.take_actions()
