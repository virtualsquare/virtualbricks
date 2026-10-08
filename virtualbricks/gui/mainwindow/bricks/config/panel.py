# -*- test-case-name: virtualbricks.tests.gui.mainwindow.bricks.config.test_panel -*-
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
The panel of a brick: its settings, as the rows of a form on a draft. The
settings of an event and the details of a disk image are panels too, with
widgets of their own.

A panel says which rows it has in ``build()``, and the form makes them; a
panel of several forms, or of widgets of its own, returns the widget that
holds them. The settings page of a tab shows ``widget``, keeps OK sensitive
while the draft has no errors, and on OK takes what is typed and not yet in
the draft, with ``commit()``, then applies the draft; the brick sees nothing
before. While the brick runs, an info bar says what ``running_words()``
says. A change in a row refreshes the rows, then calls the callbacks of
``connect_changed()``. ``gui`` is the main window, for a panel that opens
another tab; ``engine`` is its engine, for a panel that asks the machine,
or else the engine of this machine.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from virtualbricks.bricks.draft import Draft
from virtualbricks.engine import Engine, LocalEngine
from virtualbricks.gui.form import Form, Row
from virtualbricks.i18n import _
from virtualbricks.bricks import is_running

if TYPE_CHECKING:  # pragma: no cover
    from virtualbricks.gui.mainwindow.window import VBGUI


def spin_buttons(widget: Gtk.Widget) -> Iterator[Gtk.SpinButton]:
    """The spin buttons in widget, in the pages of a stack not shown too."""

    if isinstance(widget, Gtk.SpinButton):
        yield widget
    elif isinstance(widget, Gtk.Container):
        for child in widget.get_children():
            yield from spin_buttons(child)


class Panel:
    """The settings of a brick, on a draft."""

    def __init__(self, draft: Draft, gui: VBGUI | None = None) -> None:
        self.draft = draft
        self.gui = gui
        self._callbacks: list[Callable[[Panel], None]] = []
        self.form = Form(
            draft, self.on_changed, gui.engine if gui is not None else None
        )
        root = self.build(self.form)
        self.widget = self.form.widget if root is None else root
        self.refresh()

    def build(self, form: Form) -> Gtk.Widget | None:
        """
        Add the sections and the rows of the panel; return the widget of the
        panel when it isn't the form's.
        """

        raise NotImplementedError

    @property
    def engine(self) -> Engine:
        """What the panel asks of the machine: through the main window."""

        if self.gui is None:
            return LocalEngine(self.draft.brick.factory)
        return self.gui.engine

    @property
    def rows(self) -> dict[str, Row]:
        """The rows of the panel, by their key."""

        return self.form.rows

    def refresh(self) -> None:
        self.form.refresh()

    def connect_changed(self, callback: Callable[[Panel], None]) -> None:
        self._callbacks.append(callback)

    def on_changed(self) -> None:
        self.refresh()
        for callback in self._callbacks:
            callback(self)

    def commit(self) -> None:
        """
        Put in the draft the numbers typed and not yet taken, as a spin
        button takes them when the focus leaves it; OK calls it first.
        """

        for spin in spin_buttons(self.widget):
            spin.update()

    def running(self) -> bool:
        """Whether the brick runs: then the info bar says running_words()."""

        return is_running(self.draft.brick)

    def running_words(self) -> str:
        """What the settings of the brick say while it runs."""

        rows = self.rows
        live = [name for name in self.draft.live() if name in rows]
        brick = self.draft.brick.name
        if not live:
            return _(
                "{brick} is running: the settings take effect when it starts"
                " again."
            ).format(brick=brick)
        settings = ", ".join(rows[name].title.get_text() for name in live)
        if len(live) == len(rows):
            text = _("{brick} is running. These change at once: {settings}.")
        else:
            text = _(
                "{brick} is running. These change at once: {settings}; the"
                " rest when it starts again."
            )
        return text.format(brick=brick, settings=settings)
