# -*- test-case-name: virtualbricks.tests.gui.mainwindow.bricks.config.test_panel -*-
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
The panel of a brick: its settings, as the rows of a form on a draft.

A panel says which rows it has in ``build()``, and the form makes them. The
settings page of the Bricks tab shows ``widget``, keeps OK sensitive while the
draft has no errors, and applies the draft on OK; the brick sees nothing
before. A change in a row refreshes the rows, then calls the callbacks of
``connect_changed()``.
"""

from __future__ import annotations

from collections.abc import Callable

from virtualbricks.gui.mainwindow.bricks.config.form import Form
from virtualbricks.i18n import _


class Panel:
    """The settings of a brick, on a draft."""

    def __init__(self, draft) -> None:
        self.draft = draft
        self._callbacks: list[Callable[[Panel], None]] = []
        self.form = Form(draft, self.on_changed)
        self.build(self.form)
        self.form.refresh()
        self.widget = self.form.widget

    def build(self, form: Form) -> None:
        """Add the sections and the rows of the panel."""

        raise NotImplementedError

    def connect_changed(self, callback: Callable[[Panel], None]) -> None:
        self._callbacks.append(callback)

    def on_changed(self) -> None:
        self.form.refresh()
        for callback in self._callbacks:
            callback(self)

    def running_words(self) -> str:
        """What the settings of the brick say while it runs."""

        rows = self.form.rows
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
