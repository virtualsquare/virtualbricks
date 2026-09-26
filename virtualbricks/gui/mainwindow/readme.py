# -*- test-case-name: virtualbricks.tests.gui.mainwindow.test_readme -*-
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
The Readme tab of the main window: the README rendered, or its text to edit.

The tab opens on the preview. Two icon buttons float over its top right
corner: the pencil shows the editor, the eye the preview, drawn again from
the text of the editor. While the editor shows, a third icon opens the
syntax. The views keep a margin as wide as the buttons, so no text goes
under them; it's measured again when the buttons get their room, as a new
theme can change them.

The editor holds the README of the open project: the tab loads it when a
project opens and when it shows, and saves it when another tab shows, when
the project is saved, and 30 seconds after an edit.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402
from twisted.internet import reactor  # noqa: E402

from virtualbricks.config import projects  # noqa: E402
from virtualbricks.gui.mainwindow.tab import Tab  # noqa: E402
from virtualbricks.gui.markdownview import MarkdownView  # noqa: E402
from virtualbricks.i18n import _  # noqa: E402

# The room around the text, and between the buttons and the corner, in
# pixels.
MARGIN = 12
GAP = 6
# The seconds from an edit to its save.
SAVE_AFTER = 30
# The syntax, as the popover shows it: what to write, and what it does.
SYNTAX = (
    ("# Heading", _("a heading; ## for a smaller one")),
    ("*italic* **bold**", _("emphasis; ~~struck~~")),
    ("`code`", _("code; ``` above and below a block")),
    ("- item", _("a list; 1. for a numbered one")),
    ("> quote", _("a quote")),
    ("[text](https://…)", _("a link; a bare URL is one too")),
    ("---", _("a line across")),
)


def _icon_button(button, icon, name):
    """An icon, with a name for the tooltip and the screen readers."""

    button.set_image(Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.BUTTON))
    button.set_tooltip_text(name)
    button.get_accessible().set_name(name)
    return button


def _syntax_popover(button):
    grid = Gtk.Grid(
        visible=True, column_spacing=18, row_spacing=6, margin=MARGIN
    )
    title = Gtk.Label(visible=True, xalign=0.0)
    title.set_markup(f"<b>{GLib.markup_escape_text(_('Markdown'))}</b>")
    grid.attach(title, 0, 0, 2, 1)
    for row, (source, meaning) in enumerate(SYNTAX, 1):
        code = Gtk.Label(visible=True, xalign=0.0)
        code.set_markup(f"<tt>{GLib.markup_escape_text(source)}</tt>")
        grid.attach(code, 0, row, 1, 1)
        description = Gtk.Label(visible=True, label=meaning, xalign=0.0)
        description.get_style_context().add_class("dim-label")
        grid.attach(description, 1, row, 1, 1)
    anything_else = Gtk.Label(
        visible=True,
        label=_("Anything else shows as you typed it."),
        xalign=0.0,
        margin_top=6,
    )
    grid.attach(anything_else, 0, len(SYNTAX) + 1, 2, 1)
    popover = Gtk.Popover(relative_to=button)
    popover.add(grid)
    return popover


def _scrolled(view):
    scrolled = Gtk.ScrolledWindow(visible=True)
    scrolled.add(view)
    return scrolled


class ReadmeTab(Tab, Gtk.Overlay):
    """The README of the open project rendered, or its text in the editor."""

    title = _("Readme")

    def __init__(self, workspace=None, clock=None) -> None:
        super().__init__(visible=True)
        self.workspace = projects if workspace is None else workspace
        self.clock = reactor if clock is None else clock
        # the save of an edit, on its way
        self._saving = None
        margins = {
            "left_margin": MARGIN,
            "top_margin": MARGIN,
            "bottom_margin": MARGIN,
        }
        self.editor = Gtk.TextView(
            visible=True, wrap_mode=Gtk.WrapMode.WORD_CHAR, **margins
        )
        self.preview = MarkdownView(visible=True, **margins)
        self.empty_label = Gtk.Label(
            visible=True,
            label=_(
                "No README yet. The pencil, at the top right, writes one."
            ),
            wrap=True,
            xalign=0.0,
            yalign=0.0,
            margin=MARGIN,
        )
        self.empty_label.get_style_context().add_class("dim-label")
        # on the background of the views
        empty = Gtk.Box(visible=True)
        empty.get_style_context().add_class("view")
        empty.pack_start(self.empty_label, True, True, 0)
        self.stack = Gtk.Stack(visible=True)
        self.stack.add_named(_scrolled(self.preview), "preview")
        self.stack.add_named(empty, "empty")
        self.stack.add_named(_scrolled(self.editor), "editor")
        self.add(self.stack)

        self.buttons = Gtk.Box(
            visible=True,
            spacing=GAP,
            halign=Gtk.Align.END,
            valign=Gtk.Align.START,
            margin=GAP,
        )
        self.buttons.get_style_context().add_class("osd")
        self.switch = Gtk.Box(visible=True)
        self.switch.get_style_context().add_class("linked")
        self.edit_button = _icon_button(
            Gtk.RadioButton(visible=True, draw_indicator=False),
            "document-edit-symbolic",
            _("Edit"),
        )
        self.preview_button = _icon_button(
            Gtk.RadioButton(
                visible=True, draw_indicator=False, group=self.edit_button
            ),
            "view-reveal-symbolic",
            _("Preview"),
        )
        self.switch.pack_start(self.edit_button, False, False, 0)
        self.switch.pack_start(self.preview_button, False, False, 0)
        self.buttons.pack_start(self.switch, False, False, 0)
        self.syntax_button = _icon_button(
            Gtk.MenuButton(), "dialog-question-symbolic", _("Syntax")
        )
        self.syntax_button.set_popover(_syntax_popover(self.syntax_button))
        self.buttons.pack_start(self.syntax_button, False, False, 0)
        self.add_overlay(self.buttons)

        self._measuring: int | None = None
        self.preview_button.set_active(True)
        self._switch()
        # the eye goes on or off at each switch
        self.preview_button.connect("toggled", self.on_toggled)
        self.editor.get_buffer().connect("changed", self.on_changed)
        self.editor.get_buffer().connect(
            "modified-changed", self.on_modified_changed
        )
        self.buttons.connect("size-allocate", self.on_size_allocate)
        self.connect("destroy", self.on_destroy)

    def show_preview(self) -> None:
        self.preview_button.set_active(True)

    def load(self) -> None:
        """The README of the open project, in the editor: not an edit."""

        textbuffer = self.editor.get_buffer()
        textbuffer.set_text(self.workspace.current.get_description())
        textbuffer.set_modified(False)

    def save(self) -> None:
        """Save the edits of the README, if there are any."""

        textbuffer = self.editor.get_buffer()
        if textbuffer.get_modified():
            text = textbuffer.get_property("text")
            self.workspace.current.set_description(text)
            textbuffer.set_modified(False)

    def _save_later(self) -> None:
        self._saving = None
        self.save()

    def showing_preview(self) -> bool:
        return self.preview_button.get_active()

    def _switch(self) -> None:
        if self.showing_preview():
            self._render()
        else:
            self.stack.set_visible_child_name("editor")
            self.editor.grab_focus()
        self.syntax_button.set_visible(not self.showing_preview())
        self._set_margin()

    def _render(self) -> None:
        text = self.editor.get_buffer().get_property("text")
        self.preview.set_markdown(text)
        self.stack.set_visible_child_name(
            "preview" if text.strip() else "empty"
        )

    def _set_margin(self) -> None:
        """A right margin on what shows, as wide as the buttons over it."""

        _, width = self.buttons.get_preferred_width()
        if self.showing_preview():
            self.preview.set_right_margin(width)
            self.empty_label.set_margin_end(width)
        else:
            self.editor.set_right_margin(width)

    def _set_margin_later(self) -> bool:
        self._measuring = None
        self._set_margin()
        return GLib.SOURCE_REMOVE

    # What the main window tells

    def on_open(self) -> None:
        self.load()
        self.show_preview()

    def on_save(self) -> None:
        self.save()

    def on_quit(self) -> None:
        self.save()

    def on_shown(self) -> None:
        self.load()

    def on_left(self) -> None:
        self.save()

    # Signals

    def on_toggled(self, button) -> None:
        self._switch()

    def on_changed(self, textbuffer) -> None:
        # loaded while the preview shows
        if self.showing_preview():
            self._render()

    def on_modified_changed(self, textbuffer) -> None:
        # saved a while after the first edit, unless it's saved before
        if textbuffer.get_modified():
            if self._saving is None:
                self._saving = self.clock.callLater(
                    SAVE_AFTER, self._save_later
                )
        elif self._saving is not None:
            self._saving.cancel()
            self._saving = None

    def on_size_allocate(self, box, allocation) -> None:
        # the buttons in another theme; not now, GTK would lose the resize
        # of the view
        if self._measuring is None:
            self._measuring = GLib.idle_add(self._set_margin_later)

    def on_destroy(self, tab) -> None:
        if self._measuring is not None:
            GLib.source_remove(self._measuring)
            self._measuring = None
