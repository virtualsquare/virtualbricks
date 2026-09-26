# -*- test-case-name: virtualbricks.tests.gui.test_markdownview -*-
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
A README in Markdown, rendered in a GtkTextView or in the markup of a label.

:func:`layout` turns the tokens of :mod:`virtualbricks.markdown` into lines,
each a list of runs of text with the names of their styles; it needs no
widget. :class:`MarkdownView` draws the lines with the tags of a read-only
GtkTextView, and :func:`pango_markup` writes them for a GtkLabel. A new line
of the README starts a new line in both.

Only ``http``, ``https`` and ``mailto`` links open, with :func:`open_link`.
"""

from __future__ import annotations

import dataclasses
from urllib.parse import urlsplit

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk, Pango  # noqa: E402
from twisted.logger import Logger

from virtualbricks.markdown import parse, plain_text

logger = Logger()
cannot_open_link = "Cannot open {uri}: {error}"

# The schemes of the links that open, in the browser or the mail client.
OPEN_SCHEMES = frozenset(("http", "https", "mailto"))
# The indent of a level of list or quote, and the room below a block, in
# pixels.
INDENT = 24
BLOCK_SPACE = 8
# The style of each name that the lines use; the colours come from the theme.
STYLES = {
    "h1": {"weight": Pango.Weight.BOLD, "scale": 1.4, "pixels_above_lines": 2},
    "h2": {"weight": Pango.Weight.BOLD, "scale": 1.2, "pixels_above_lines": 6},
    "h3": {
        "weight": Pango.Weight.BOLD,
        "scale": 1.05,
        "pixels_above_lines": 4,
    },
    "em": {"style": Pango.Style.ITALIC},
    "strong": {"weight": Pango.Weight.BOLD},
    "strike": {"strikethrough": True},
    "code": {"family": "monospace"},
    "pre": {"family": "monospace", "right_margin": 12},
    "quote": {},
    "space": {"pixels_below_lines": BLOCK_SPACE},
    "link": {"underline": Pango.Underline.SINGLE},
}
HEADINGS = {"h1": "h1", "h2": "h2"}
# A rule in the colour of the text: a separator of the theme is too faint on
# the background of a text view.
RULE_CSS = b"separator { background-color: alpha(@theme_fg_color, 0.35); }"


@dataclasses.dataclass
class Run:
    """A piece of a line, in its styles; href if it's a link."""

    text: str
    styles: tuple[str, ...] = ()
    href: str | None = None


@dataclasses.dataclass
class Line:
    """A line of the README, as it's drawn."""

    runs: list[Run] = dataclasses.field(default_factory=list)
    # the levels of list and quote it's in
    depth: int = 0
    # the bullet or the number of a list item, on its first line
    marker: str | None = None
    # the styles of the whole line: a heading, code, a quote, the space below
    styles: tuple[str, ...] = ()
    rule: bool = False

    @property
    def text(self) -> str:
        return "".join(run.text for run in self.runs)


def layout(tokens) -> list[Line]:
    """The lines of the tokens of a README, see :func:`markdown.parse`."""

    return _Layout().run(tokens)


class _Layout:

    INLINE = {"em": "em", "strong": "strong", "s": "strike"}

    def __init__(self) -> None:
        self.lines: list[Line] = []
        # the next number of each open list, None for a bulleted one
        self.lists: list[int | None] = []
        self.quotes = 0
        self.heading: str | None = None
        # the marker of the list item whose first line is still to come
        self.marker: str | None = None

    def run(self, tokens) -> list[Line]:
        for token in tokens:
            handler = getattr(self, "on_" + token.type, None)
            if handler is not None:
                handler(token)
        return self.lines

    def add_line(self, runs, styles=(), rule=False) -> None:
        if self.quotes:
            styles = (*styles, "quote")
        if self.heading is not None:
            styles = (*styles, self.heading)
        depth = len(self.lists) + self.quotes
        self.lines.append(Line(runs, depth, self.marker, styles, rule))
        self.marker = None

    def end_block(self) -> None:
        """A block at the top ends: room below its last line."""

        if self.lists or self.quotes or not self.lines:
            return
        last = self.lines[-1]
        if "space" not in last.styles:
            last.styles = (*last.styles, "space")

    # Blocks

    def on_bullet_list_open(self, token) -> None:
        self.lists.append(None)

    def on_ordered_list_open(self, token) -> None:
        start = token.attrGet("start")
        self.lists.append(int(start) if start is not None else 1)

    def on_bullet_list_close(self, token) -> None:
        self.lists.pop()
        self.end_block()

    on_ordered_list_close = on_bullet_list_close

    def on_list_item_open(self, token) -> None:
        number = self.lists[-1]
        if number is None:
            self.marker = "•"
        else:
            self.marker = f"{number}{token.markup or '.'}"
            self.lists[-1] = number + 1

    def on_list_item_close(self, token) -> None:
        if self.marker is not None:
            # an empty item still shows its marker
            self.add_line([])

    def on_blockquote_open(self, token) -> None:
        self.quotes += 1

    def on_blockquote_close(self, token) -> None:
        self.quotes -= 1
        self.end_block()

    def on_heading_open(self, token) -> None:
        self.heading = HEADINGS.get(token.tag, "h3")

    def on_heading_close(self, token) -> None:
        self.heading = None
        self.end_block()

    def on_paragraph_close(self, token) -> None:
        self.end_block()

    def on_fence(self, token) -> None:
        for line in token.content.rstrip("\n").split("\n"):
            self.add_line([Run(line)], ("pre",))
        self.end_block()

    on_code_block = on_fence

    def on_hr(self, token) -> None:
        self.add_line([], rule=True)
        self.end_block()

    # Text

    def on_inline(self, token) -> None:
        styles: list[str] = []
        links: list[str] = []
        runs: list[Run] = []

        def add(text, *more):
            if text:
                href = links[-1] if links else None
                runs.append(Run(text, (*styles, *more), href))

        for child in token.children or []:
            kind = child.type
            if kind in ("softbreak", "hardbreak"):
                self.add_line(runs)
                runs = []
            elif kind.endswith("_open") and kind[:-5] in self.INLINE:
                styles.append(self.INLINE[kind[:-5]])
            elif kind.endswith("_close") and kind[:-6] in self.INLINE:
                styles.pop()
            elif kind == "link_open":
                links.append(child.attrGet("href"))
            elif kind == "link_close":
                links.pop()
            elif kind == "text":
                add(child.content)
            elif kind == "code_inline":
                add(child.content, "code")
            elif kind == "image":
                add(plain_text(child.children or []) or child.content, "em")
        self.add_line(runs)


def can_open(uri: str) -> bool:
    return urlsplit(uri).scheme.lower() in OPEN_SCHEMES


def open_link(widget: Gtk.Widget, uri: str) -> bool:
    """
    Open a link of a README, if it's http, https or mailto.

    It returns True, for the activate-link signal of a label: the other links
    don't open.
    """

    if not can_open(uri):
        return True
    toplevel = widget.get_toplevel()
    window = toplevel if isinstance(toplevel, Gtk.Window) else None
    try:
        Gtk.show_uri_on_window(window, uri, Gdk.CURRENT_TIME)
    except GLib.Error as exc:
        logger.error(cannot_open_link, uri=uri, error=exc.message)
    return True


def _markup_run(run: Run) -> str:
    text = GLib.markup_escape_text(run.text)
    for style, element in (
        ("code", "tt"),
        ("em", "i"),
        ("strong", "b"),
        ("strike", "s"),
    ):
        if style in run.styles:
            text = f"<{element}>{text}</{element}>"
    if run.href is not None:
        href = GLib.markup_escape_text(run.href)
        text = f'<a href="{href}">{text}</a>'
    return text


def pango_markup(text: str) -> str:
    """The markup of a README for a label; links are <a href>."""

    parts: list[str] = []
    for line in layout(parse(text)):
        if line.rule:
            body = "―" * 6
        else:
            body = "".join(_markup_run(run) for run in line.runs)
        if "pre" in line.styles:
            body = f"<tt>{body}</tt>"
        if any(style in line.styles for style in ("h1", "h2", "h3")):
            body = f"<b>{body}</b>"
        if "quote" in line.styles:
            body = f"<i>{body}</i>"
        prefix = "  " * max(line.depth - 1, 0)
        if line.marker is not None:
            prefix += GLib.markup_escape_text(line.marker) + " "
        parts.append(prefix + body)
        if "space" in line.styles:
            parts.append("")
    return "\n".join(parts).strip("\n")


class MarkdownView(Gtk.TextView):
    """A README in Markdown, rendered: it can be selected, not edited."""

    def __init__(self, **properties) -> None:
        properties.setdefault("wrap_mode", Gtk.WrapMode.WORD_CHAR)
        super().__init__(editable=False, cursor_visible=False, **properties)
        self.buffer = self.get_buffer()
        for name, style in STYLES.items():
            self.buffer.create_tag(name, **style)
        # the tag of each link, by name, and its URL
        self._links: dict[str, str] = {}
        # the rules, and the left margin of each
        self._rules: list[tuple[Gtk.Separator, int]] = []
        self._hovering = False
        self._rule_style = Gtk.CssProvider()
        self._rule_style.load_from_data(RULE_CSS)
        self.update_colors()
        self.connect("style-updated", self.on_style_updated)
        self.connect("button-release-event", self.on_button_release_event)
        self.connect("motion-notify-event", self.on_motion_notify_event)
        self.connect("size-allocate", self.on_size_allocate)

    def _tag(self, name: str) -> Gtk.TextTag:
        return self.buffer.get_tag_table().lookup(name)

    def update_colors(self) -> None:
        """The colours of the links, quotes and code, from the theme."""

        context = self.get_style_context()
        text = context.get_color(Gtk.StateFlags.NORMAL)
        dim = Gdk.RGBA(text.red, text.green, text.blue, 0.6)
        tint = Gdk.RGBA(text.red, text.green, text.blue, 0.08)
        self._tag("link").props.foreground_rgba = context.get_color(
            Gtk.StateFlags.LINK
        )
        self._tag("quote").props.foreground_rgba = dim
        self._tag("code").props.background_rgba = tint
        self._tag("pre").props.paragraph_background_rgba = tint

    # Rendering

    def set_markdown(self, text: str) -> None:
        self._clear()
        lines = layout(parse(text))
        for number, line in enumerate(lines):
            start = self.buffer.get_char_count()
            left = self.get_left_margin() + INDENT * line.depth
            if line.rule:
                self._add_rule(left)
            else:
                self._add_runs(line)
            if number < len(lines) - 1:
                self.buffer.insert(self.buffer.get_end_iter(), "\n")
            names = (self._margin_tag(left, line.marker), *line.styles)
            for name in names:
                self.buffer.apply_tag_by_name(
                    name,
                    self.buffer.get_iter_at_offset(start),
                    self.buffer.get_end_iter(),
                )

    def _clear(self) -> None:
        self.buffer.set_text("")
        table = self.buffer.get_tag_table()
        for name in self._links:
            table.remove(table.lookup(name))
        self._links.clear()
        for separator, _left in self._rules:
            separator.destroy()
        self._rules.clear()

    def _add_runs(self, line: Line) -> None:
        end = self.buffer.get_end_iter()
        if line.marker is not None:
            self.buffer.insert(end, line.marker + " ")
        for run in line.runs:
            names = list(run.styles)
            if run.href is not None:
                name = f"link:{len(self._links)}"
                self.buffer.create_tag(name)
                self._links[name] = run.href
                names += ["link", name]
            self.buffer.insert_with_tags_by_name(end, run.text, *names)

    def _add_rule(self, left: int) -> None:
        anchor = self.buffer.create_child_anchor(self.buffer.get_end_iter())
        separator = Gtk.Separator(visible=True, valign=Gtk.Align.CENTER)
        separator.get_style_context().add_provider(
            self._rule_style, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        self.add_child_at_anchor(separator, anchor)
        self._rules.append((separator, left))
        self._size_rule(separator, left, self.get_allocated_width())

    def _margin_tag(self, left: int, marker: str | None) -> str:
        """The left margin of a line; a marker hangs in it, before the text."""

        indent = 0
        if marker is not None:
            indent = -self.create_pango_layout(marker + " ").get_pixel_size()[
                0
            ]
        name = f"margin:{left}:{indent}"
        if self._tag(name) is None:
            self.buffer.create_tag(name, left_margin=left, indent=indent)
        return name

    def _size_rule(self, separator, left, width) -> None:
        room = width - left - self.get_right_margin()
        separator.set_size_request(max(room, 1), -1)

    # Links

    def link_at(self, it: Gtk.TextIter) -> str | None:
        for tag in it.get_tags():
            href = self._links.get(tag.props.name)
            if href is not None:
                return href
        return None

    def _iter_at(self, x, y) -> Gtk.TextIter | None:
        bx, by = self.window_to_buffer_coords(
            Gtk.TextWindowType.TEXT, int(x), int(y)
        )
        found = self.get_iter_at_location(bx, by)
        if isinstance(found, tuple):
            found, it = found
            return it if found else None
        return found

    # Signals

    def on_style_updated(self, view) -> None:
        self.update_colors()

    def on_button_release_event(self, view, event) -> bool:
        if event.button != 1 or self.buffer.get_has_selection():
            return False
        it = self._iter_at(event.x, event.y)
        href = None if it is None else self.link_at(it)
        if href is None:
            return False
        open_link(self, href)
        return True

    def on_motion_notify_event(self, view, event) -> bool:
        it = self._iter_at(event.x, event.y)
        hovering = it is not None and self.link_at(it) is not None
        if hovering != self._hovering:
            self._hovering = hovering
            window = self.get_window(Gtk.TextWindowType.TEXT)
            if window is not None:
                cursor = Gdk.Cursor.new_from_name(
                    self.get_display(), "pointer" if hovering else "text"
                )
                window.set_cursor(cursor)
        return False

    def on_size_allocate(self, view, allocation) -> None:
        for separator, left in self._rules:
            self._size_rule(separator, left, allocation.width)
