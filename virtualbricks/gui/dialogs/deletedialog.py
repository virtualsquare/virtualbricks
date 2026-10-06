# -*- test-case-name: virtualbricks.tests.gui.dialogs.test_deletedialog -*-
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
Delete a brick or an event, as Remove Image removes an image.

The dialog says what changes with it, a line each: the bricks plugged into
it, the events that start or stop it, the bricks that run it when they
start or stop, as the factory's ``users()`` finds them; and that a waiting
event stops. A machine's private copies go with it, to the trash or, without
one, for good, as Start Over sends one: a new machine of the same name would
start from them. A running brick doesn't get here: its Delete is greyed.
"""

from __future__ import annotations

import itertools
import os
from collections.abc import Iterable, Sequence
from typing import Any

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk
from twisted.internet import defer
from twisted.logger import Logger
from twisted.python.failure import Failure

from virtualbricks import errors
from virtualbricks.bricks import Brick, is_running
from virtualbricks.bricks.event import Event, is_event
from virtualbricks.bricks.eventaction import StartAction, StoredAction
from virtualbricks.bricks.plug import Plug
from virtualbricks.bricks.virtualmachine import is_virtualmachine
from virtualbricks.console import ampcommands, ampwire
from virtualbricks.engine import Engine
from virtualbricks.gui import imageinfo
from virtualbricks.gui.dialogs.base import Window, action_dialog, text_label
from virtualbricks.i18n import _, ngettext

logger = Logger()
not_deleted = "Cannot delete {name}: {error}"
copy_stays = "Cannot discard {vm}'s private copy of {device}: {error}"

# the failures of the engine: here, or there over a connection
REFUSALS = (
    OSError,
    errors.Error,
    ampwire.CommandFailed,
    ampcommands.BadArgument,
)


def _unique(names: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(names))


def _plugged(plug: Plug) -> str:
    """A brick plugged in; a machine with its card."""

    brick = plug.brick
    if not is_virtualmachine(brick):
        return brick.name
    number = list(itertools.chain(brick.plugs, brick.socks)).index(plug)
    return _("{vm} (eth{n})").format(vm=brick.name, n=number)


def _actions_words(
    name: str, actions: Sequence[tuple[Event, StoredAction]]
) -> str:
    events = _unique(event.name for event, _action in actions)
    starts = {isinstance(action, StartAction) for _event, action in actions}
    if starts == {True}:
        words = ngettext(
            "The event {events} will no longer start {name}.",
            "The events {events} will no longer start {name}.",
            len(events),
        )
    elif starts == {False}:
        words = ngettext(
            "The event {events} will no longer stop {name}.",
            "The events {events} will no longer stop {name}.",
            len(events),
        )
    else:
        words = ngettext(
            "The event {events} will no longer start or stop {name}.",
            "The events {events} will no longer start or stop {name}.",
            len(events),
        )
    return words.format(events=imageinfo.names(events), name=name)


def _runs_words(name: str, settings: Sequence[tuple[Brick, str]]) -> list[str]:
    lines = []
    for field, singular, plural in (
        (
            "on_start",
            "{bricks} will no longer run {name} when it starts.",
            "{bricks} will no longer run {name} when they start.",
        ),
        (
            "on_stop",
            "{bricks} will no longer run {name} when it stops.",
            "{bricks} will no longer run {name} when they stop.",
        ),
    ):
        bricks = _unique(other.name for other, key in settings if key == field)
        if bricks:
            words = ngettext(singular, plural, len(bricks))
            lines.append(
                words.format(bricks=imageinfo.names(bricks), name=name)
            )
    return lines


def uses_words(item: Brick | Event, users: Any) -> list[str]:
    """What changes with item, of the users the factory found: a line each."""

    lines = []
    plugged = _unique(_plugged(plug) for plug in users.plugs)
    if plugged:
        lines.append(
            ngettext(
                "{bricks} will be plugged into nothing.",
                "{bricks} will be plugged into nothing.",
                len(plugged),
            ).format(bricks=imageinfo.names(plugged))
        )
    if users.actions:
        lines.append(_actions_words(item.name, users.actions))
    lines += _runs_words(item.name, users.settings)
    if not lines:
        lines.append(_("Nothing else uses it."))
    return lines


def copies_words(paths: Sequence[str], size: int, trash: bool) -> str:
    """What happens to the private copies of a machine deleted."""

    files = imageinfo.names([os.path.basename(path) for path in paths])
    if trash:
        words = ngettext(
            "Its private copy goes to the trash, with the changes it keeps:"
            " {files}, {size}.",
            "Its private copies go to the trash, with the changes they keep:"
            " {files}, {size}.",
            len(paths),
        )
    else:
        words = ngettext(
            "Its private copy is deleted for good, with the changes it"
            " keeps: {files}, {size}. There is no trash.",
            "Its private copies are deleted for good, with the changes they"
            " keep: {files}, {size}. There is no trash.",
            len(paths),
        )
    return words.format(files=files, size=imageinfo.human_size(size))


class DeleteDialog(Window):
    """Ask to delete a brick or an event, saying what goes with it."""

    def __init__(self, engine: Engine, item: Brick | Event) -> None:
        self.engine = engine
        self.item = item
        # the files are those of the machine of the bricks
        self.machine = engine.machine
        self.build_ui()

    def get_root_widget(self) -> Gtk.Dialog:
        return self.dialog

    def build_ui(self) -> None:
        name = self.item.name
        if is_event(self.item):
            title = _("Delete Event")
            question = _("Delete the event {name}?")
        else:
            title = _("Delete Brick")
            question = _("Delete the brick {name}?")
        self.dialog, self.delete_button, box = action_dialog(
            title, _("Delete"), destructive=True
        )
        box.pack_start(
            text_label(question.format(name=name), heading=True),
            False,
            False,
            0,
        )
        users = self.engine.factory.users(self.item)
        lines = uses_words(self.item, users)
        if is_event(self.item) and is_running(self.item):
            lines.append(
                _("It is waiting: it stops, and its actions don't run.")
            )
        devices = self.copies()
        if devices and is_virtualmachine(self.item):
            paths = [
                self.item.disk(device).get_cow_path() for device in devices
            ]
            size = sum(self.machine.taken(path) or 0 for path in paths)
            trash = self.machine.can_trash(paths[0])
            lines.append(copies_words(paths, size, trash))
        for line in lines:
            box.pack_start(text_label(line), False, False, 0)
        self.dialog.connect("response", self.on_response)

    def copies(self) -> list[str]:
        """The devices of the private copies of a machine that are there."""

        if not is_virtualmachine(self.item):
            return []
        return [
            disk.device
            for disk in self.item.disks()
            if disk.is_cow() and self.machine.exists(disk.get_cow_path())
        ]

    def on_response(self, dialog: Gtk.Dialog, response_id: int) -> None:
        if response_id == Gtk.ResponseType.OK:
            self.delete()
        dialog.destroy()

    def delete(self) -> defer.Deferred[Any]:
        """The private copies go first, then the item; a refusal is logged."""

        item = self.item
        deleting: defer.Deferred[Any] = defer.succeed(None)
        if is_virtualmachine(item):

            def start_over(_: object, device: str) -> defer.Deferred[bool]:
                return self.engine.start_over(item, device)

            for device in self.copies():
                deleting.addCallback(start_over, device)
                deleting.addErrback(self._copy_stays, device)
        deleting.addCallback(lambda _: self.engine.remove(self.item))
        deleting.addErrback(self._not_deleted)
        return deleting

    def _copy_stays(self, failure: Failure, device: str) -> None:
        failure.trap(*REFUSALS)
        logger.error(
            copy_stays, vm=self.item.name, device=device, error=failure.value
        )

    def _not_deleted(self, failure: Failure) -> None:
        failure.trap(*REFUSALS)
        logger.error(not_deleted, name=self.item.name, error=failure.value)
