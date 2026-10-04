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
GtkTextView, and :func:`pango_markup` writes them for a GtkLabel, as
:class:`MarkdownLabel` does in a few lines. A new line of the README starts
a new line in all of them.

Only ``http``, ``https`` and ``mailto`` links open, with :func:`open_link`.

A picture is its text, until the view gets its bytes from the ``pictures``
of :meth:`MarkdownView.set_markdown`: then the picture takes the place of
its text, as wide as it is, or narrower to fit in the view. A picture that
doesn't come, or can't be read, stays its text, and so does any picture in
a label.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from urllib.parse import urlsplit

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk, Pango  # noqa: E402
from twisted.internet import defer  # noqa: E402
from twisted.logger import Logger  # noqa: E402

from virtualbricks.markdown import (
    parse,
    picture_path,
    plain_text,
)  # noqa: E402

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
    # on a picture, so that GTK measures its line again: a property of the
    # size, that moves nothing (see MarkdownView._remeasure)
    "picture": {"rise": 0},
}
HEADINGS = {"h1": "h1", "h2": "h2"}
# A rule in the colour of the text: a separator of the theme is too faint on
# the background of a text view.
RULE_CSS = b"separator { background-color: alpha(@theme_fg_color, 0.35); }"
# A line break that doesn't end the paragraph, for Pango.
LINE_SEPARATOR = "\u2028"
# The most pixels of a picture: a larger one stays its text.
PICTURE_PIXELS = 32_000_000


@dataclasses.dataclass
class Run:
    """
    A piece of a line, in its styles; href if it's a link, picture if it's
    the text of a picture of the folder of the project, with its path.
    """

    text: str
    styles: tuple[str, ...] = ()
    href: str | None = None
    picture: str | None = None


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

        def add(text, *more, picture=None):
            if text:
                href = links[-1] if links else None
                runs.append(Run(text, (*styles, *more), href, picture))

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
                path = picture_path(child.attrGet("src") or "")
                text = plain_text(child.children or []) or child.content
                # a picture without a text: its path, until it shows
                add(text or path, "em", picture=path)
        self.add_line(runs)


def read_picture(data: bytes) -> GdkPixbuf.Pixbuf | None:
    """The picture of data, if it's one and isn't too large; else None."""

    loader = GdkPixbuf.PixbufLoader()

    def size_prepared(loader, width, height):
        if width * height > PICTURE_PIXELS:
            # the loader gives up, before it takes the memory
            loader.set_size(0, 0)

    loader.connect("size-prepared", size_prepared)
    try:
        loader.write(data)
        loader.close()
    except GLib.Error:
        return None
    return loader.get_pixbuf()


@dataclasses.dataclass
class _Picture:
    """A picture of the view: before it comes, where its text starts."""

    path: str
    text: str
    # the left margin of its line
    left: int
    mark: Gtk.TextMark | None = None
    anchor: Gtk.TextChildAnchor | None = None
    image: Gtk.Image | None = None
    pixbuf: GdkPixbuf.Pixbuf | None = None


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


def _markup_run(run: Run, links: bool) -> str:
    text = GLib.markup_escape_text(run.text)
    for style, element in (
        ("code", "tt"),
        ("em", "i"),
        ("strong", "b"),
        ("strike", "s"),
    ):
        if style in run.styles:
            text = f"<{element}>{text}</{element}>"
    if run.href is not None and links:
        href = GLib.markup_escape_text(run.href)
        text = f'<a href="{href}">{text}</a>'
    return text


def pango_markup(text: str, links: bool = True) -> str:
    """
    The markup of a README for a label; links are <a href>.

    Pango alone doesn't know <a>: with links False, a link is only its text.
    """

    parts: list[str] = []
    for line in layout(parse(text)):
        if line.rule:
            body = "―" * 6
        else:
            body = "".join(_markup_run(run, links) for run in line.runs)
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


class MarkdownLabel(Gtk.Label):
    """
    A README in Markdown, rendered in a label of at most `lines` lines; the
    last ends with "…" if the README goes on.

    A label limits the lines of each Pango paragraph, and a new line starts
    one: the lines of the README are joined by a line separator, a line break
    inside the paragraph. Pango then trims the last line of the label, but it
    also joins to it the lines of the README after it, without their breaks.
    So the label keeps only the lines of the README that fit its width.

    It chooses them in an idle call once it has its width: GTK forgets a
    resize asked while it gives a widget its size. After a new width, the
    lines that fit show a frame later.
    """

    def __init__(self, lines: int, **properties) -> None:
        super().__init__(
            wrap=True,
            wrap_mode=Pango.WrapMode.WORD_CHAR,
            ellipsize=Pango.EllipsizeMode.END,
            lines=lines,
            xalign=0.0,
            **properties,
        )
        # the markup of each line, and the same without links for Pango
        self._lines: list[str] = []
        self._measured: list[str] = []
        # the width, in Pango units, the lines were fitted to
        self._width: int | None = None
        self._fitting: int | None = None
        self.connect("activate-link", open_link)
        self.connect("size-allocate", self.on_size_allocate)
        self.connect("style-updated", self.on_style_updated)
        self.connect("destroy", self.on_destroy)

    def set_markdown(self, text: str) -> None:
        self._lines = pango_markup(text).split("\n")
        self._measured = pango_markup(text, links=False).split("\n")
        self._width = None
        # trimmed by Pango, the whole README is as high as the lines that
        # fit: the label asks for its height before it knows its width
        self.set_markup(LINE_SEPARATOR.join(self._lines))

    def fit(self) -> None:
        """Keep the lines that fit the width; Pango trims the last one."""

        layout = self.get_layout().copy()
        if layout.get_width() == self._width:
            return
        self._width = layout.get_width()
        layout.set_ellipsize(Pango.EllipsizeMode.NONE)
        limit = self.get_lines()
        shown: list[str] = []
        used = 0
        for line, measured in zip(self._lines, self._measured):
            if used == limit:
                # the lines fill the label, and the README goes on
                shown[-1] += " …"
                break
            shown.append(line)
            layout.set_markup(measured)
            used += layout.get_line_count()
            if used > limit:
                break
        markup = LINE_SEPARATOR.join(shown)
        if markup != self.get_label():
            self.set_markup(markup)

    def _fit_later(self) -> bool:
        self._fitting = None
        self.fit()
        return GLib.SOURCE_REMOVE

    def on_size_allocate(self, label, allocation) -> None:
        if self._fitting is None:
            self._fitting = GLib.idle_add(self._fit_later)

    def on_style_updated(self, label) -> None:
        # another font: the lines take another room
        self._width = None

    def on_destroy(self, label) -> None:
        if self._fitting is not None:
            GLib.source_remove(self._fitting)
            self._fitting = None


class MarkdownView(Gtk.TextView):
    """
    A README in Markdown, rendered: it can be selected, not edited.

    A picture is a GtkImage at an anchor of the text. It fits in the width
    of the view once the view has it: in an idle call after the view gets
    its size, as GTK forgets a resize asked while it gives a widget its
    size. A picture that comes before the view has a width waits as an
    empty image, in its line, and gets its pixels in that idle call.

    That picture meets two flaws of GTK 3 when the view isn't in a
    scrolled window, so that it's as high as it asks to be: the details of
    the Projects window, where they were found before it showed its
    pictures as text. GTK doesn't measure the line of the picture again,
    and the picture covers the lines after it. And when GTK does measure
    the line, the view asks to be higher at a moment when GTK forgets it:
    it keeps its height, and the lines after the picture are cut off.
    _remeasure() and _resize_later() work around them. In a scrolled
    window, as in the Readme tab, neither flaw shows: checked on Broadway
    with GTK 3.24.49, with each workaround taken out.
    """

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
        self._pictures: list[_Picture] = []
        # what each set_markdown() renders, for the pictures that come late
        self._rendering = 0
        self._fitting: int | None = None
        self._resizing: int | None = None
        self._hovering = False
        self._rule_style = Gtk.CssProvider()
        self._rule_style.load_from_data(RULE_CSS)
        self.update_colors()
        self.connect("style-updated", self.on_style_updated)
        self.connect("button-release-event", self.on_button_release_event)
        self.connect("motion-notify-event", self.on_motion_notify_event)
        self.connect("size-allocate", self.on_size_allocate)
        self.connect("destroy", self.on_destroy)

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

    def set_markdown(
        self,
        text: str,
        pictures: Callable[[str], defer.Deferred] | None = None,
    ) -> None:
        """
        Render text; pictures(path), if given, fires with the bytes of a
        picture of the folder of the project.
        """

        self._clear()
        lines = layout(parse(text))
        for number, line in enumerate(lines):
            start = self.buffer.get_char_count()
            left = self.get_left_margin() + INDENT * line.depth
            if line.rule:
                self._add_rule(left)
            else:
                self._add_runs(line, left, pictures is not None)
            if number < len(lines) - 1:
                self.buffer.insert(self.buffer.get_end_iter(), "\n")
            names = (self._margin_tag(left, line.marker), *line.styles)
            for name in names:
                self.buffer.apply_tag_by_name(
                    name,
                    self.buffer.get_iter_at_offset(start),
                    self.buffer.get_end_iter(),
                )
        # once the lines are there: a picture may come at once
        rendering = self._rendering
        for picture in self._pictures:
            asking = defer.maybeDeferred(pictures, picture.path)
            asking.addCallbacks(
                self._picture_came,
                lambda failure: None,
                (picture, rendering),
            )

    def _clear(self) -> None:
        self._rendering += 1
        self.buffer.set_text("")
        table = self.buffer.get_tag_table()
        for name in self._links:
            table.remove(table.lookup(name))
        self._links.clear()
        for separator, _left in self._rules:
            separator.destroy()
        self._rules.clear()
        for picture in self._pictures:
            if picture.image is not None:
                picture.image.destroy()
        self._pictures.clear()

    def _add_runs(self, line: Line, left: int, pictures: bool) -> None:
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
            if run.picture is not None and pictures:
                mark = self.buffer.create_mark(None, end, True)
                self._pictures.append(
                    _Picture(run.picture, run.text, left, mark)
                )
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

    # Pictures

    def _picture_came(self, data, picture, rendering) -> None:
        if rendering != self._rendering:
            # another README now
            return
        pixbuf = read_picture(data)
        if pixbuf is None:
            return
        # the picture takes the place of its text, and its tags
        start = self.buffer.get_iter_at_mark(picture.mark)
        end = start.copy()
        end.forward_chars(len(picture.text))
        tags = start.get_tags()
        self.buffer.delete(start, end)
        picture.anchor = self.buffer.create_child_anchor(
            self.buffer.get_iter_at_mark(picture.mark)
        )
        self.buffer.delete_mark(picture.mark)
        picture.mark = None
        start, end = self._picture_bounds(picture)
        for tag in tags:
            self.buffer.apply_tag(tag, start, end)
        self.buffer.apply_tag_by_name("picture", start, end)
        picture.image = Gtk.Image(visible=True)
        picture.image.get_accessible().set_name(picture.text)
        picture.pixbuf = pixbuf
        self.add_child_at_anchor(picture.image, picture.anchor)
        self._size_picture(picture, self.get_allocated_width())

    def _picture_bounds(self, picture):
        start = self.buffer.get_iter_at_child_anchor(picture.anchor)
        end = start.copy()
        end.forward_char()
        return start, end

    def _size_picture(self, picture, width) -> None:
        """The picture as wide as it is, or as the room in its line."""

        if picture.pixbuf is None or width <= 1:
            # not yet
            return
        room = width - picture.left - self.get_right_margin()
        natural = picture.pixbuf.get_width()
        wide = max(min(natural, room), 1)
        shown = picture.image.get_pixbuf()
        if shown is not None and shown.get_width() == wide:
            return
        if wide == natural:
            picture.image.set_from_pixbuf(picture.pixbuf)
        else:
            high = max(round(picture.pixbuf.get_height() * wide / natural), 1)
            picture.image.set_from_pixbuf(
                picture.pixbuf.scale_simple(
                    wide, high, GdkPixbuf.InterpType.BILINEAR
                )
            )
        self._remeasure(picture)
        if self._resizing is None:
            self._resizing = GLib.idle_add(self._resize_later)

    def _remeasure(self, picture) -> None:
        """
        Make GTK measure the line of a picture again, with its new size.

        GTK 3 keeps the height of each line from when it laid the line
        out. It lays out again the line of a widget that asks for another
        size when it gives the widgets of the view their place, in
        gtk_text_view_allocate_children(), but outside a scrolled window it
        missed an empty image that got its pixels: the picture covered the
        lines after it. Its other check, in
        gtk_text_view_size_request(), compares two answers to the same
        question, asked one after the other, and never finds a change. The
        call that would do it, gtk_text_child_anchor_queue_resize(), is
        internal: its header, gtktextlayout.h, is for GTK's own use only,
        and Python can't call it.

        A tag does it: when a tag comes or goes on some text, GTK lays that
        text out again if the tag can change its size
        (_gtk_text_tag_affects_size(): a font, a margin, a rise...), and
        only draws it again otherwise. The tag "picture" has a rise of 0,
        which moves nothing but counts as a size; it comes off the picture
        and goes back on.
        """

        start, end = self._picture_bounds(picture)
        self.buffer.remove_tag_by_name("picture", start, end)
        start, end = self._picture_bounds(picture)
        self.buffer.apply_tag_by_name("picture", start, end)

    def _resize_later(self) -> bool:
        """
        Ask GTK to size the view again, now that it knows its lines.

        GTK 3 measures the lines of a view while it gives the view its size,
        gtk_text_view_size_allocate(). A view that is then higher asks for
        a new size there, gtk_widget_queue_resize_no_redraw(); but
        gtk_widget_size_allocate() takes a widget whose size it gave as
        settled, and clears what was asked meanwhile: for the view, and for
        each container it's in, whose sizes it's giving too ("Size
        allocation is god", its comment says). Outside a scrolled window,
        the view kept the height of the lines before the picture, and cut
        off those after it.

        Asked here, in an idle call of the default priority, 200, it comes
        after GTK's own: the sizes, 110, and the lines measured, 108 for the
        first ones and 125 for the others; so the view gets the height of
        all its lines.
        """

        self._resizing = None
        self.queue_resize()
        return GLib.SOURCE_REMOVE

    def _fit_later(self) -> bool:
        self._fitting = None
        width = self.get_allocated_width()
        for picture in self._pictures:
            self._size_picture(picture, width)
        return GLib.SOURCE_REMOVE

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
        if self._pictures and self._fitting is None:
            self._fitting = GLib.idle_add(self._fit_later)

    def on_destroy(self, view) -> None:
        for source in (self._fitting, self._resizing):
            if source is not None:
                GLib.source_remove(source)
        self._fitting = self._resizing = None
