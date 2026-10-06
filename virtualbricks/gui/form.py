# -*- test-case-name: virtualbricks.tests.gui.test_form -*-
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
The rows of a panel, or of a page of the Settings window, bound to the
settings of a draft.

A form has sections: a title, and the rows under it in a frame. A row is a
setting: its label and its help from the schema, translated, with what the
draft adds to the help; its widget, at the end; and under them what is wrong
with the setting, when something is. The widget comes from the kind of the
field: a switch for true or false, a spin button for a number, between the
limits of the draft, an entry for a text or a path, buttons or a menu for a
choice. A text can have a menu of what it is often, and a setting can be
shown without being changed. A socket row chooses what a plug of the brick
joins, of the draft's sockets.

A pair row has a number both ways, from left to right and back, and a switch
for the same both ways; ``row()`` takes any widget, and a section can frame
any widget instead of rows. ``reload()`` shows the draft's values again, as
when a panel shows another of the states of a Netemu.

A change in a widget goes into the draft, then the form calls back. The panel
then refreshes the rows: a row greys out while the draft doesn't use its
setting, and shows its problem, red for an error, in the colour of warnings
for what only keeps the brick from starting.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from typing import Any

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Pango  # noqa: E402

from virtualbricks.bricks.draft import Draft, Problem  # noqa: E402
from virtualbricks.bricks.sock import Sock  # noqa: E402
from virtualbricks.config.schema import Float, info_of, kind_of  # noqa: E402
from virtualbricks.engine import Engine  # noqa: E402
from virtualbricks.gui.pango import pango_attr_list  # noqa: E402
from virtualbricks.gui.pathentry import PathCompletion  # noqa: E402
from virtualbricks.i18n import _  # noqa: E402

# Between the sections, and around the texts of a row, in pixels.
GAP = 8
# The size of the help of a row, from the size of its label.
HELP_SCALE = 0.9
# The characters of the numbers of a pair row.
PAIR_WIDTH = 7
# The widest range of a spin button whose kind has no limit.
LOWEST = -(2**31)
HIGHEST = 2**31 - 1

_css = Gtk.CssProvider()
_css.load_from_data(b"label.lack { color: @warning_color; }")


def show_problem(label: Gtk.Label, problem: Problem | None) -> None:
    """A problem in label: red for an error, else the colour of warnings."""

    label.set_text("" if problem is None else problem.text)
    label.set_visible(problem is not None)
    context = label.get_style_context()
    context.add_provider(_css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    error = problem is not None and problem.error
    lack = problem is not None and not problem.error
    for name, on in (("error", error), ("lack", lack)):
        if on:
            context.add_class(name)
        else:
            context.remove_class(name)


def _separate(row: Gtk.ListBoxRow, before: Gtk.ListBoxRow | None) -> None:
    """A line between two rows."""

    if before is not None and row.get_header() is None:
        row.set_header(Gtk.Separator(visible=True))


def set_options(combo: Gtk.ComboBoxText, options: Iterable[str]) -> None:
    """
    The menu of a text: options, where "" is a line between those before
    and those after. The text stays as it is.
    """

    combo.remove_all()
    for option in options:
        combo.append(option, option)


def _is_line(model: Gtk.TreeModel, row: Gtk.TreeIter) -> bool:
    return model[row][0] == ""


def socket_name(sock: Sock) -> str:
    """A switch by its name, the socket of another brick by its own."""

    if sock.brick.get_type().startswith("Switch"):
        return sock.brick.name
    return sock.nickname


class Row(Gtk.ListBoxRow):
    """A setting: its label, its help, its widget and its problem."""

    def __init__(
        self, key: str, label: str, help: str, widget: Gtk.Widget
    ) -> None:
        super().__init__(visible=True, activatable=False, selectable=False)
        # widget and name are taken by Gtk.Widget
        self.key = key
        self.control = widget
        self.help = help
        # the other settings of the row, by name, and their widgets
        self.parts: dict[str, Gtk.Widget] = {}
        # shows the draft's value again
        self.load: Callable[[], object] = lambda: None
        grid = Gtk.Grid(
            visible=True,
            column_spacing=16,
            row_spacing=4,
            margin_start=12,
            margin_end=12,
            margin_top=GAP,
            margin_bottom=GAP,
        )
        texts = Gtk.Box(
            visible=True,
            orientation=Gtk.Orientation.VERTICAL,
            spacing=2,
            hexpand=True,
            valign=Gtk.Align.CENTER,
        )
        self.title = Gtk.Label(visible=True, xalign=0.0, label=label)
        # read with the widget, by a screen reader
        self.title.set_mnemonic_widget(widget)
        self.caption = Gtk.Label(
            visible=True,
            xalign=0.0,
            wrap=True,
            label=self.help,
            attributes=pango_attr_list(Pango.attr_scale_new(HELP_SCALE)),
        )
        self.caption.get_style_context().add_class("dim-label")
        texts.pack_start(self.title, False, False, 0)
        texts.pack_start(self.caption, False, False, 0)
        widget.set_valign(Gtk.Align.CENTER)
        widget.set_halign(Gtk.Align.END)
        self.problem = Gtk.Label(
            visible=False,
            xalign=0.0,
            wrap=True,
            attributes=pango_attr_list(Pango.attr_scale_new(HELP_SCALE)),
        )
        self.problem.get_style_context().add_provider(
            _css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        grid.attach(texts, 0, 0, 1, 1)
        grid.attach(widget, 1, 0, 1, 1)
        grid.attach(self.problem, 0, 1, 2, 1)
        self.add(grid)

    def refresh(self, used: bool, note: str, problem: Problem | None) -> None:
        """
        Grey out if not used; the help with the note; the problem, an error
        or what keeps the brick from starting.
        """

        self.set_sensitive(used)
        if note:
            caption = _("{help} · {note}").format(help=self.help, note=note)
        else:
            caption = self.help
        self.caption.set_text(caption)
        show_problem(self.problem, problem)
        error = problem is not None and problem.error
        context = self.control.get_style_context()
        if error:
            context.add_class("error")
        else:
            context.remove_class("error")


class Form:
    """The sections and the rows of a panel, on a draft."""

    def __init__(
        self,
        draft: Draft,
        changed: Callable[[], None],
        engine: Engine | None = None,
    ) -> None:
        self.draft = draft
        self.changed = changed
        # over a connection, the paths are of the machine of the bricks
        self.engine = engine
        self.widget = Gtk.Box(
            visible=True, orientation=Gtk.Orientation.VERTICAL, spacing=6
        )
        self.rows: dict[str, Row] = {}
        self._list: Gtk.ListBox | None = None
        # while the widgets show the draft's values again
        self._loading = False

    def section(self, title: str, content: Gtk.Widget | None = None) -> None:
        """A title, and a frame for the rows that follow, or for content."""

        label = Gtk.Label(
            visible=True,
            xalign=0.0,
            label=title,
            attributes=pango_attr_list(
                Pango.attr_weight_new(Pango.Weight.BOLD)
            ),
        )
        if self.rows:
            label.set_margin_top(GAP)
        frame = Gtk.Frame(visible=True)
        if content is None:
            self._list = Gtk.ListBox(
                visible=True, selection_mode=Gtk.SelectionMode.NONE
            )
            self._list.set_header_func(_separate)
            frame.add(self._list)
        else:
            self._list = None
            frame.add(content)
        self.widget.pack_start(label, False, False, 0)
        self.widget.pack_start(frame, False, False, 0)

    def row(
        self, key: str, widget: Gtk.Widget, label: str = "", help: str = ""
    ) -> Row:
        """
        A row of any widget, with its label and its help; a setting's are
        the schema's.
        """

        return self._row(key, widget, label, help)

    def add(self, widget: Gtk.Widget) -> None:
        """A widget of its own, after the sections."""

        self._list = None
        self.widget.pack_start(widget, False, False, 0)

    def _row(
        self, key: str, widget: Gtk.Widget, label: str = "", help: str = ""
    ) -> Row:
        """A row; a setting's label and help are the schema's."""

        if self._list is None:
            raise ValueError("a row comes after the title of its section")
        if not label:
            info = info_of(self.draft.settings, key)
            label, help = _(info.label), _(info.help)
        row = Row(key, label, help, widget)
        self._list.add(row)
        self.rows[key] = row
        return row

    def _set(self, name: str, value: object) -> None:
        if self._loading:
            return
        self.draft.set(name, value)
        self.changed()

    def reload(self) -> None:
        """The widgets show the draft's values again, then refresh."""

        self._loading = True
        try:
            for row in self.rows.values():
                row.load()
        finally:
            self._loading = False
        self.refresh()

    def switch(self, name: str) -> Gtk.Switch:
        """A setting true or false."""

        switch = Gtk.Switch(visible=True, active=self.draft.get(name))
        switch.connect(
            "notify::active",
            lambda widget, _: self._set(name, widget.get_active()),
        )
        row = self._row(name, switch)
        row.load = lambda: switch.set_active(self.draft.get(name))
        return switch

    def spin(self, name: str) -> Gtk.SpinButton:
        """A number, between the draft's limits."""

        spin = self._number(name)
        row = self._row(name, spin)
        row.load = lambda: spin.set_value(self.draft.get(name))
        return spin

    def pair(self, name: str, reverse: str, symmetric: str) -> Row:
        """
        A number from left to right, the one from right to left, and whether
        the first is the same both ways; the second greys out while it is.
        """

        forward = self._number(name)
        backward = self._number(reverse)
        # the same width, whatever their range
        for spin in (forward, backward):
            spin.set_width_chars(PAIR_WIDTH)
        both = Gtk.Switch(visible=True, active=self.draft.get(symmetric))
        both.connect(
            "notify::active",
            lambda widget, _: self._set(symmetric, widget.get_active()),
        )
        both.set_tooltip_text(_("The same both ways"))
        box = Gtk.Box(visible=True, spacing=6)
        for widget, tip in (
            (Gtk.Label(visible=True, label="→"), _("From left to right")),
            (forward, _("From left to right")),
            (Gtk.Label(visible=True, label="←"), _("From right to left")),
            (backward, _("From right to left")),
            (Gtk.Label(visible=True, label=_("Both ways")), ""),
            (both, ""),
        ):
            if tip:
                widget.set_tooltip_text(tip)
            if isinstance(widget, Gtk.Label):
                widget.get_style_context().add_class("dim-label")
            widget.set_valign(Gtk.Align.CENTER)
            box.pack_start(widget, False, False, 0)
        row = self._row(name, box)
        row.title.set_mnemonic_widget(forward)
        row.parts = {reverse: backward, symmetric: both}

        def load() -> None:
            forward.set_value(self.draft.get(name))
            backward.set_value(self.draft.get(reverse))
            both.set_active(self.draft.get(symmetric))

        row.load = load
        return row

    def _number(self, name: str) -> Gtk.SpinButton:
        value = self.draft.get(name)
        low, high = self.draft.limits(name)
        low = LOWEST if low is None else low
        high = HIGHEST if high is None else high
        is_float = isinstance(kind_of(self.draft.settings, name), Float)
        spin = Gtk.SpinButton(
            visible=True, numeric=True, digits=2 if is_float else 0
        )
        # a value already below its limit stays, and shows its problem
        spin.set_range(min(low, value), max(high, value))
        spin.set_increments(1, 10)
        spin.set_value(value)

        def on_changed(widget: Gtk.SpinButton) -> None:
            number = (
                widget.get_value() if is_float else widget.get_value_as_int()
            )
            self._set(name, number)

        spin.connect("value-changed", on_changed)
        return spin

    def entry(self, name: str, secret: bool = False) -> Gtk.Entry:
        """A text; a secret one shows as dots."""

        entry = Gtk.Entry(
            visible=True,
            text=self.draft.get(name),
            visibility=not secret,
            width_chars=24,
        )
        entry.connect(
            "changed", lambda widget: self._set(name, widget.get_text())
        )
        row = self._row(name, entry)
        row.load = lambda: entry.set_text(self.draft.get(name))
        return entry

    def combo_entry(
        self, name: str, options: Iterable[str] = ()
    ) -> Gtk.ComboBoxText:
        """
        A text, typed or chosen in a menu of options; set_options() changes
        them.
        """

        combo = Gtk.ComboBoxText.new_with_entry()
        combo.show()
        combo.set_row_separator_func(_is_line)
        set_options(combo, options)
        entry = combo.get_child()
        assert isinstance(entry, Gtk.Entry), "new_with_entry() made it"
        entry.set_width_chars(20)
        entry.set_text(self.draft.get(name))
        entry.connect(
            "changed", lambda widget: self._set(name, widget.get_text())
        )
        row = self._row(name, combo)
        row.title.set_mnemonic_widget(entry)
        row.load = lambda: entry.set_text(self.draft.get(name))
        return combo

    def value(self, name: str, show: Callable[[Any], str] = str) -> Gtk.Label:
        """A setting shown, as show() writes it, and not changed."""

        label = Gtk.Label(
            visible=True, selectable=True, label=show(self.draft.get(name))
        )
        row = self._row(name, label)
        row.load = lambda: label.set_text(show(self.draft.get(name)))
        return label

    def path(self, name: str, title: str, folder: bool = False) -> Gtk.Entry:
        """
        A file, or a folder: typed, or chosen in a dialog with the title.
        """

        entry = Gtk.Entry(
            visible=True, text=self.draft.get(name), width_chars=28
        )
        entry.connect(
            "changed", lambda widget: self._set(name, widget.get_text())
        )
        box = Gtk.Box(visible=True)
        box.get_style_context().add_class("linked")
        box.pack_start(entry, True, True, 0)
        if self.engine is not None and not self.engine.local:
            # a chooser shows the files of this computer: typed, with the
            # folders there to complete it (19 R9)
            # kept as long as the entry
            entry.completer = PathCompletion(  # type: ignore[attr-defined]
                self.engine, entry, folder
            )
        else:
            button = Gtk.Button.new_from_icon_name(
                "document-open-symbolic", Gtk.IconSize.BUTTON
            )
            button.set_tooltip_text(_("Choose…"))
            button.show()
            button.connect("clicked", self._choose, entry, title, folder)
            box.pack_start(button, False, False, 0)
        row = self._row(name, box)
        row.title.set_mnemonic_widget(entry)
        row.load = lambda: entry.set_text(self.draft.get(name))
        return entry

    def _choose(
        self, button: Gtk.Button, entry: Gtk.Entry, title: str, folder: bool
    ) -> None:
        if folder:
            action = Gtk.FileChooserAction.SELECT_FOLDER
        else:
            action = Gtk.FileChooserAction.OPEN
        toplevel = button.get_toplevel()
        dialog = Gtk.FileChooserDialog(
            title=title,
            transient_for=(
                toplevel if isinstance(toplevel, Gtk.Window) else None
            ),
            modal=True,
            action=action,
        )
        dialog.add_buttons(
            _("_Cancel"),
            Gtk.ResponseType.CANCEL,
            _("_Select"),
            Gtk.ResponseType.ACCEPT,
        )
        if entry.get_text():
            dialog.set_filename(entry.get_text())

        def on_response(dialog: Gtk.FileChooserDialog, response: int) -> None:
            if response == Gtk.ResponseType.ACCEPT:
                entry.set_text(dialog.get_filename() or "")
            dialog.destroy()

        dialog.connect("response", on_response)
        dialog.show()

    def choice(
        self,
        name: str,
        options: Sequence[tuple[str, str]],
        menu: bool = False,
        missing: str = "",
    ) -> Gtk.Widget:
        """
        One of options, each a value and its words: linked buttons, or a
        menu. A value that isn't one of them stays in the menu, with the
        words of missing, as "{value}, not on this host".
        """

        value = self.draft.get(name)
        if menu:
            combo = Gtk.ComboBoxText(visible=True)
            for option, words in options:
                combo.append(option, words)
            if value not in dict(options):
                combo.append(value, (missing or "{value}").format(value=value))
            combo.set_active_id(value)
            combo.connect(
                "changed",
                lambda widget: self._set(name, widget.get_active_id()),
            )
            row = self._row(name, combo)
            row.load = lambda: combo.set_active_id(self.draft.get(name))
            return combo
        box = Gtk.Box(visible=True)
        box.get_style_context().add_class("linked")
        group = None
        buttons: dict[str, Gtk.RadioButton] = {}
        for option, words in options:
            button = Gtk.RadioButton(
                visible=True, label=words, draw_indicator=False, group=group
            )
            group = group or button
            button.set_active(option == value)
            button.connect("toggled", self._on_toggled, name, option)
            box.pack_start(button, False, False, 0)
            buttons.setdefault(option, button)
        row = self._row(name, box)

        def load() -> None:
            button = buttons.get(self.draft.get(name))
            if button is not None:
                button.set_active(True)

        row.load = load
        return box

    def _on_toggled(
        self, button: Gtk.ToggleButton, name: str, option: str
    ) -> None:
        if button.get_active():
            self._set(name, option)

    def socket(self, index: int, label: str, help: str) -> Gtk.ComboBoxText:
        """What the plug of index joins: one of the draft's sockets, or none."""

        sockets = self.draft.sockets()
        current = self.draft.links[index]
        if current is not None and current not in sockets:
            sockets.append(current)
        combo = Gtk.ComboBoxText(visible=True)
        combo.append("", _("Nothing"))
        for position, sock in enumerate(sockets):
            combo.append(str(position), socket_name(sock))
        if current is None:
            combo.set_active_id("")
        else:
            combo.set_active_id(str(sockets.index(current)))

        def on_changed(widget: Gtk.ComboBoxText) -> None:
            chosen = widget.get_active_id()
            sock = sockets[int(chosen)] if chosen else None
            self.draft.link(index, sock)
            self.changed()

        combo.connect("changed", on_changed)
        self._row(f"plug{index}", combo, label, help)
        return combo

    def refresh(self) -> None:
        """Each row as the draft says: in use or not, its note, its problem."""

        problems: dict[str, Problem] = {}
        for problem in self.draft.problems():
            problems.setdefault(problem.key, problem)
        for name, row in self.rows.items():
            found = [
                problems[key] for key in (name, *row.parts) if key in problems
            ]
            row.refresh(
                self.draft.uses(name),
                self.draft.note(name),
                found[0] if found else None,
            )
            for key, widget in row.parts.items():
                widget.set_sensitive(self.draft.uses(key))
