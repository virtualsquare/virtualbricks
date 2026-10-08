# -*- test-case-name: virtualbricks.tests.gui.mainwindow.bricks.config.test_picker -*-
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
A picker: a button that shows what is chosen, and a popover with a search
and the options, each a name and a description.

The options can come later, as the answers of a QEMU program:
``set_options()``. A value chosen that isn't one of them stays at the top,
with the words of ``missing``, until another is chosen. The options that say
they're deprecated come last, dimmed. Choosing one calls ``chose`` with its
value.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import attr
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Pango  # noqa: E402

from virtualbricks.gui.pango import pango_attr_list  # noqa: E402
from virtualbricks.i18n import _  # noqa: E402

# Between the texts of an option, and around them, in pixels.
GAP = 6
# The characters of the words beside a name, at most.
WORDS_WIDTH = 28
# The height of the list of options, at most, in pixels.
LIST_HEIGHT = 320
DEPRECATED = "(deprecated)"


@attr.define(frozen=True)
class Option:
    value: str
    name: str
    description: str = ""

    @property
    def deprecated(self) -> bool:
        return DEPRECATED in self.description


def _label(text: str, dim: bool = False, bold: bool = False) -> Gtk.Label:
    label = Gtk.Label(visible=True, xalign=0.0, label=text)
    if dim:
        # the name shows whole, its words as they fit
        label.set_ellipsize(Pango.EllipsizeMode.END)
        label.set_max_width_chars(WORDS_WIDTH)
    if dim:
        label.get_style_context().add_class("dim-label")
    if bold:
        label.set_attributes(
            pango_attr_list(Pango.attr_weight_new(Pango.Weight.BOLD))
        )
    return label


class OptionRow(Gtk.ListBoxRow):
    """An option of the list: its name, its description, and a mark."""

    def __init__(self, option: Option, chosen: bool) -> None:
        super().__init__(visible=True)
        self.option = option
        box = Gtk.Box(visible=True, spacing=GAP, margin=GAP)
        check = Gtk.Image(visible=True, icon_name="object-select-symbolic")
        check.set_opacity(1.0 if chosen else 0.0)
        texts = Gtk.Box(visible=True, orientation=Gtk.Orientation.VERTICAL)
        self.name = _label(option.name, dim=option.deprecated, bold=True)
        texts.pack_start(self.name, False, False, 0)
        if option.description:
            texts.pack_start(
                _label(option.description, dim=True), False, False, 0
            )
        box.pack_start(check, False, False, 0)
        box.pack_start(texts, True, True, 0)
        self.add(box)

    def matches(self, text: str) -> bool:
        text = text.casefold()
        option = self.option
        return (
            text in option.name.casefold()
            or text in option.description.casefold()
        )


class Picker(Gtk.MenuButton):
    """What is chosen of a list, and the list, with a search."""

    def __init__(
        self,
        chosen: str,
        chose: Callable[[str], None],
        missing: str = "",
    ) -> None:
        super().__init__(visible=True)
        self.value = chosen
        self.chose = chose
        self.missing = missing
        self.options: list[Option] = []
        box = Gtk.Box(visible=True, spacing=GAP)
        self.name = _label("")
        self.words = _label("", dim=True)
        box.pack_start(self.name, False, False, 0)
        box.pack_start(self.words, True, True, 0)
        box.pack_start(
            Gtk.Image(visible=True, icon_name="pan-down-symbolic"),
            False,
            False,
            0,
        )
        self.add(box)

        self.search = Gtk.SearchEntry(
            visible=True, margin=GAP, placeholder_text=_("Search")
        )
        self.search.connect(
            "search-changed", lambda entry: self.list.invalidate_filter()
        )
        self.list = Gtk.ListBox(visible=True)
        self.list.set_filter_func(self._matches)
        self.list.connect("row-activated", self.on_row_activated)
        scrolled = Gtk.ScrolledWindow(
            visible=True,
            hscrollbar_policy=Gtk.PolicyType.NEVER,
            max_content_height=LIST_HEIGHT,
            propagate_natural_height=True,
            width_request=320,
        )
        scrolled.add(self.list)
        content = Gtk.Box(visible=True, orientation=Gtk.Orientation.VERTICAL)
        content.pack_start(self.search, False, False, 0)
        content.pack_start(scrolled, True, True, 0)
        self.popover = Gtk.Popover()
        self.popover.add(content)
        self.set_popover(self.popover)
        self._fill()

    def set_options(self, options: Sequence[Option]) -> None:
        """The options, the deprecated ones last."""

        self.options = sorted(options, key=lambda option: option.deprecated)
        self._fill()

    def option(self, value: str) -> Option | None:
        for option in self.options:
            if option.value == value:
                return option
        return None

    def _fill(self) -> None:
        for row in self.list.get_children():
            row.destroy()
        chosen = self.option(self.value)
        if chosen is None:
            self.list.add(
                OptionRow(Option(self.value, self.value, self.missing), True)
            )
        for option in self.options:
            self.list.add(OptionRow(option, option is chosen))
        if chosen is None:
            self.name.set_text(self.value)
            self.words.set_text(self.missing)
        else:
            self.name.set_text(chosen.name)
            self.words.set_text(chosen.description)

    def _matches(self, row: OptionRow) -> bool:
        return row.matches(self.search.get_text())

    def choose(self, value: str) -> None:
        self.value = value
        self._fill()
        self.popover.popdown()
        self.chose(value)

    def on_row_activated(self, listbox: Gtk.ListBox, row: OptionRow) -> None:
        self.choose(row.option.value)
