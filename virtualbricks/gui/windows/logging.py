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
The messages window: the messages of Virtualbricks, as a console.

Each message is one line: its time, the brick or the part of Virtualbricks it
comes from, a symbol of its level and its first line. The other lines of a
message, its traceback and the other lines of the output of a program are
folded behind a toggle. A line for each day separates the days, and a time
repeated within the same second is dimmed.
"""

import os
import tempfile
import textwrap
import time

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk, Pango
from twisted.internet import utils
from twisted.logger import Logger

from virtualbricks import __version__
from virtualbricks.gui import graphics
from virtualbricks.gui.messages import parse_filter, type_name
from virtualbricks.gui.windows.base import _Window
from virtualbricks.i18n import _, ngettext

logger = Logger()

bug_send = "Sending report bug"
bug_sent = "Report bug sent succefully"
bug_error = "{err}\nstderr:\n{stderr}"
bug_report_fail = "Report bug failed with code " "{code}\nstderr:\n{stderr}"
bug_err_unknown = "Error on bug reporting"

BUG_REPORT_ERRORS = {
    1: "Error in command line syntax.",
    2: "One of the files passed on the command line did not exist.",
    3: "A required tool could not be found.",
    4: "The action failed.",
    5: "No permission to read one of the files passed on the command line.",
}

# The console is light whatever the theme.
CSS = b"""
textview.vb-console,
textview.vb-console text {
    background-color: #ffffff;
    color: #2e3436;
}
"""
MARGIN = 12
ICON_SIZE = 16
# the longest source shown in full; the tooltip has it all
SOURCE_CHARS = 14
SCROLL_TOLERANCE = 50

DIM = "#5e6366"
ERROR_TEXT = "#a51d2d"
WARNING_TEXT = "#8a3400"
SYMBOL_COLORS = {
    "debug": "#6f6e73",
    "info": "#1c71d8",
    "warn": "#c64600",
    "error": "#c01c28",
    "critical": "#c01c28",
    "output": "#5e6366",
}
SYMBOL_ICONS = {
    "debug": "dialog-information-symbolic",
    "info": "dialog-information-symbolic",
    "warn": "dialog-warning-symbolic",
    "error": "dialog-error-symbolic",
    "critical": "dialog-error-symbolic",
    "output": "utilities-terminal-symbolic",
}
# when the icon theme has no symbolic icons
SYMBOL_LETTERS = {
    "debug": "D",
    "info": "I",
    "warn": "W",
    "error": "E",
    "critical": "C",
    "output": "›",
}
MESSAGE_TAGS = {
    "debug": ("extra",),
    "info": (),
    "warn": ("warn",),
    "error": ("error",),
    "critical": ("critical",),
}
TAGS = {
    "day": {
        "weight": Pango.Weight.BOLD,
        "foreground": DIM,
        "paragraph_background": "#f1efed",
        "scale": 0.9,
        "pixels_above_lines": 6,
        "pixels_below_lines": 2,
    },
    "time": {"foreground": DIM},
    "time-repeat": {"foreground": "#b8b4b0"},
    "source": {},
    "brick": {"foreground": "#1a5fb4", "weight": Pango.Weight.SEMIBOLD},
    "part": {"foreground": DIM},
    "symbol": {},
    "warn": {"foreground": WARNING_TEXT},
    "error": {"foreground": ERROR_TEXT},
    "critical": {"foreground": ERROR_TEXT, "weight": Pango.Weight.BOLD},
    "output": {"foreground": "#3d4145", "background": "#f6f5f4"},
    "stream": {"foreground": DIM},
    "extra": {"foreground": DIM},
    "toggle": {"foreground": "#1b6acb"},
    "toggle-lines": {},
    "toggle-traceback": {},
    # the geometry comes from the font, see ConsoleView.update_geometry()
    "first": {},
    "more": {},
}
TAGS.update(
    ("symbol-" + kind, {"foreground": color, "weight": Pango.Weight.BOLD})
    for kind, color in SYMBOL_COLORS.items()
)
FOLDS = ("lines", "traceback")

_symbol_icons = {}
_type_icons = {}


def symbol_icon(kind):
    """The symbolic icon of a level, in its colour, or None."""

    if kind not in _symbol_icons:
        pixbuf = None
        color = Gdk.RGBA()
        color.parse(SYMBOL_COLORS[kind])
        theme = Gtk.IconTheme.get_default()
        info = theme.lookup_icon(
            SYMBOL_ICONS[kind], ICON_SIZE, Gtk.IconLookupFlags.FORCE_SIZE
        )
        if info is not None:
            try:
                pixbuf, _symbolic = info.load_symbolic(color, None, None, None)
            except GLib.Error:
                pixbuf = None
        _symbol_icons[kind] = pixbuf
    return _symbol_icons[kind]


def type_icon(source_type):
    """The image of a type of brick, as in the main window, or None."""

    if source_type not in _type_icons:
        pixbuf = None
        filename = graphics.get_data_filename(source_type + ".png")
        if filename and os.path.isfile(filename):
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(
                    filename, ICON_SIZE, ICON_SIZE
                )
            except GLib.Error:
                pixbuf = None
        _type_icons[source_type] = pixbuf
    return _type_icons[source_type]


def clock(entry):
    return time.strftime("%H:%M:%S", time.localtime(entry.time))


def day(entry):
    return time.strftime(_("%A %d %B %Y"), time.localtime(entry.time))


def moment(entry):
    """The date and the time of an entry, to the millisecond."""

    local = time.localtime(entry.time)
    milliseconds = int(entry.time * 1000) % 1000
    return time.strftime(_("%A %d %B %Y, %H:%M:%S"), local) + (
        ".%03d" % milliseconds
    )


def source_text(entry):
    if len(entry.source) > SOURCE_CHARS:
        return entry.source[: SOURCE_CHARS - 1] + "…"
    return entry.source


def source_tooltip(entry):
    if entry.source_type is None:
        return entry.namespace
    parts = [entry.source, type_name(entry.source_type)]
    if entry.stream is not None:
        parts.append(entry.stream)
    parts.append(entry.namespace)
    if entry.pid is not None:
        parts.append(_("pid {pid}").format(pid=entry.pid))
    return " · ".join(parts)


def symbol_tooltip(entry):
    if entry.is_output:
        return _("Output of the program on {stream}").format(
            stream=entry.stream
        )
    names = {
        "debug": _("Debug"),
        "info": _("Info"),
        "warn": _("Warning"),
        "error": _("Error"),
        "critical": _("Critical"),
    }
    return names[entry.level]


def folds_of(entry):
    """The parts of an entry that can be folded."""

    folds = []
    if len(entry.lines) > 1:
        folds.append("lines")
    if entry.traceback:
        folds.append("traceback")
    return folds


class _Rendered:
    """An entry in the console, and the mark where its text starts."""

    __slots__ = ("entry", "mark")

    def __init__(self, entry, mark):
        self.entry = entry
        self.mark = mark


class ConsoleView:
    """
    The text view of the messages: the entries that match the filter.

    It follows the MessageLog it's given until detach() is called.
    """

    def __init__(self, messages):
        self.messages = messages
        self.filter = parse_filter("")
        # (entry number, fold) of the folds that are open
        self.expanded = set()
        self.following = True
        # called when the entries shown change
        self.on_changed = None
        # called when a fold is opened or closed with a click, with True if
        # it's of the last entry
        self.on_folded = None
        self._rendered = []
        self._hovering = False
        self.textview = Gtk.TextView(
            visible=True,
            can_focus=True,
            editable=False,
            cursor_visible=False,
            wrap_mode=Gtk.WrapMode.WORD_CHAR,
            left_margin=MARGIN,
            right_margin=MARGIN,
            top_margin=8,
            bottom_margin=8,
            pixels_above_lines=1,
            monospace=True,
            has_tooltip=True,
        )
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        style = self.textview.get_style_context()
        style.add_provider(provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        style.add_class("vb-console")
        self.buffer = self.textview.get_buffer()
        for name, properties in TAGS.items():
            self.buffer.create_tag(name, **properties)
        self._end = self.buffer.create_mark(
            None, self.buffer.get_end_iter(), False
        )
        self.update_geometry()
        self.textview.connect("style-updated", self.on_style_updated)
        self.textview.connect("query-tooltip", self.on_query_tooltip)
        self.textview.connect(
            "button-release-event", self.on_button_release_event
        )
        self.textview.connect(
            "motion-notify-event", self.on_motion_notify_event
        )
        messages.subscribe(self)
        self.refresh()

    def detach(self):
        self.messages.unsubscribe(self)

    @property
    def shown(self):
        return len(self._rendered)

    def _tag(self, name):
        return self.buffer.get_tag_table().lookup(name)

    # Geometry

    def update_geometry(self):
        """Set the columns and the indents from the width of the font."""

        layout = self.textview.create_pango_layout("0" * 20)
        char = layout.get_pixel_size()[0] / 20
        icon = ICON_SIZE
        stops = []
        x = 10 * char  # after the time
        stops.append(x)
        x += icon + char  # after the image of the type of the brick
        stops.append(x)
        x += (SOURCE_CHARS + 2) * char  # after the source
        stops.append(x)
        x += icon + 2 * char  # after the symbol of the level
        stops.append(x)
        tabs = Pango.TabArray.new(len(stops), True)
        for index, stop in enumerate(stops):
            tabs.set_tab(index, Pango.TabAlign.LEFT, int(stop))
        self.textview.set_tabs(tabs)
        message = int(stops[-1])
        # the other lines of the first line of a message start under it
        self._tag("first").set_property("indent", -message)
        self._tag("more").set_property("left-margin", MARGIN + message)

    def on_style_updated(self, textview):
        self.update_geometry()

    # Rendering

    def _apply(self, name, start_offset, end):
        start = self.buffer.get_iter_at_offset(start_offset)
        self.buffer.apply_tag_by_name(name, start, end)

    def _insert_toggle(self, it, entry, fold):
        is_open = (entry.number, fold) in self.expanded
        if fold == "lines":
            count = len(entry.lines) - 1
            label = ngettext("{0} more line", "{0} more lines", count)
        else:
            count = entry.calls
            label = ngettext(
                "traceback, {0} call", "traceback, {0} calls", count
            )
        arrow = "▾" if is_open else "▸"
        # one piece, never broken over two lines
        text = (arrow + " " + label.format(count)).replace(" ", "\u00a0")
        self.buffer.insert(it, "  ")
        self.buffer.insert_with_tags_by_name(
            it, text, "toggle", "toggle-" + fold
        )

    def _insert_lines(self, it, lines, *tags):
        for line in lines:
            start = it.get_offset()
            self.buffer.insert_with_tags_by_name(it, line, *tags)
            self.buffer.insert(it, "\n")
            self._apply("more", start, it)

    def _insert(self, it, entry, previous):
        """Insert an entry at it, which then points after it."""

        buffer = self.buffer
        same_day = previous is not None and day(previous) == day(entry)
        if not same_day:
            buffer.insert_with_tags_by_name(
                it, day(entry).upper() + "\n", "day"
            )
        start = it.get_offset()
        repeat = same_day and clock(previous) == clock(entry)
        buffer.insert_with_tags_by_name(
            it, clock(entry), "time-repeat" if repeat else "time"
        )
        buffer.insert(it, "\t")
        source = it.get_offset()
        icon = type_icon(entry.source_type) if entry.source_type else None
        if icon is not None:
            buffer.insert_pixbuf(it, icon)
        buffer.insert(it, "\t")
        buffer.insert_with_tags_by_name(
            it, source_text(entry), "brick" if entry.source_type else "part"
        )
        self._apply("source", source, it)
        buffer.insert(it, "\t")
        kind = "output" if entry.is_output else entry.level
        symbol = it.get_offset()
        pixbuf = symbol_icon(kind)
        if pixbuf is not None:
            buffer.insert_pixbuf(it, pixbuf)
        else:
            buffer.insert_with_tags_by_name(
                it, SYMBOL_LETTERS[kind], "symbol-" + kind
            )
        self._apply("symbol", symbol, it)
        buffer.insert(it, "\t")
        first, *more = entry.lines
        if entry.is_output:
            if entry.stream == "stderr":
                buffer.insert_with_tags_by_name(it, "2> ", "stream")
            buffer.insert_with_tags_by_name(it, first, "output")
        else:
            buffer.insert_with_tags_by_name(
                it, first, *MESSAGE_TAGS.get(entry.level, ())
            )
        for fold in folds_of(entry):
            self._insert_toggle(it, entry, fold)
        buffer.insert(it, "\n")
        self._apply("first", start, it)
        if more and (entry.number, "lines") in self.expanded:
            tag = "output" if entry.is_output else "extra"
            self._insert_lines(it, more, tag)
        if entry.traceback and (entry.number, "traceback") in self.expanded:
            self._insert_lines(it, entry.traceback, "extra")

    def _append(self, entry):
        previous = self._rendered[-1].entry if self._rendered else None
        it = self.buffer.get_end_iter()
        mark = self.buffer.create_mark(None, it, True)
        self._insert(it, entry, previous)
        self._rendered.append(_Rendered(entry, mark))

    def _end_of(self, index):
        if index + 1 < len(self._rendered):
            return self.buffer.get_iter_at_mark(self._rendered[index + 1].mark)
        return self.buffer.get_end_iter()

    def _rerender(self, index):
        """Render an entry again, in its place."""

        item = self._rendered[index]
        start = self.buffer.get_iter_at_mark(item.mark)
        self.buffer.delete(start, self._end_of(index))
        it = self.buffer.get_iter_at_mark(item.mark)
        previous = self._rendered[index - 1].entry if index else None
        self._insert(it, item.entry, previous)
        if index + 1 < len(self._rendered):
            self.buffer.move_mark(self._rendered[index + 1].mark, it)

    def refresh(self):
        """Render the entries that match the filter again, all of them."""

        for item in self._rendered:
            self.buffer.delete_mark(item.mark)
        self._rendered = []
        self.buffer.set_text("")
        for entry in self.messages.entries:
            if self.filter.match(entry):
                self._append(entry)
        if self.following:
            self.scroll_to_end()
        self._changed()

    def _changed(self):
        if self.on_changed is not None:
            self.on_changed()

    def scroll_to_end(self):
        self.textview.scroll_to_mark(self._end, 0.0, True, 0.0, 1.0)

    # The MessageLog

    def message_added(self, entry, dropped):
        if (
            dropped is not None
            and self._rendered
            and self._rendered[0].entry is dropped
        ):
            item = self._rendered.pop(0)
            start = self.buffer.get_iter_at_mark(item.mark)
            if self._rendered:
                end = self.buffer.get_iter_at_mark(self._rendered[0].mark)
            else:
                end = self.buffer.get_end_iter()
            self.buffer.delete(start, end)
            self.buffer.delete_mark(item.mark)
            if self._rendered:
                # the first entry now starts the first day
                self._rerender(0)
        if self.filter.match(entry):
            self._append(entry)
            if self.following:
                self.scroll_to_end()
        self._changed()

    def messages_cleared(self):
        self.refresh()

    # Filtering and folding

    def set_filter(self, text):
        self.filter = parse_filter(text)
        self.refresh()

    def toggle(self, index, fold):
        key = (self._rendered[index].entry.number, fold)
        self.expanded ^= {key}
        self._rerender(index)

    def expand_all(self, expand=True):
        self.expanded = set()
        if expand:
            for entry in self.messages.entries:
                for fold in folds_of(entry):
                    self.expanded.add((entry.number, fold))
        self.refresh()

    def _index_at(self, it):
        """The index of the rendered entry that holds it, or None."""

        offset = it.get_offset()
        low, high = 0, len(self._rendered)
        while low < high:
            middle = (low + high) // 2
            mark = self._rendered[middle].mark
            if self.buffer.get_iter_at_mark(mark).get_offset() <= offset:
                low = middle + 1
            else:
                high = middle
        return low - 1 if low else None

    def _iter_at(self, x, y, window_type):
        bx, by = self.textview.window_to_buffer_coords(
            window_type, int(x), int(y)
        )
        found = self.textview.get_iter_at_location(bx, by)
        if isinstance(found, tuple):
            found, it = found
            return it if found else None
        return found

    # Signals

    def on_button_release_event(self, textview, event):
        if event.button != 1 or self.buffer.get_has_selection():
            return False
        it = self._iter_at(event.x, event.y, Gtk.TextWindowType.TEXT)
        if it is None:
            return False
        for fold in FOLDS:
            if it.has_tag(self._tag("toggle-" + fold)):
                index = self._index_at(it)
                if index is not None:
                    self.toggle(index, fold)
                    if self.on_folded is not None:
                        self.on_folded(index == len(self._rendered) - 1)
                return True
        return False

    def on_motion_notify_event(self, textview, event):
        it = self._iter_at(event.x, event.y, Gtk.TextWindowType.TEXT)
        hovering = it is not None and it.has_tag(self._tag("toggle"))
        if hovering != self._hovering:
            self._hovering = hovering
            window = textview.get_window(Gtk.TextWindowType.TEXT)
            cursor = Gdk.Cursor.new_from_name(
                textview.get_display(), "pointer" if hovering else "text"
            )
            window.set_cursor(cursor)
        return False

    def on_query_tooltip(self, textview, x, y, keyboard_mode, tooltip):
        if keyboard_mode:
            return False
        it = self._iter_at(x, y, Gtk.TextWindowType.WIDGET)
        index = None if it is None else self._index_at(it)
        if index is None:
            return False
        entry = self._rendered[index].entry
        if it.has_tag(self._tag("source")):
            tooltip.set_text(source_tooltip(entry))
        elif it.has_tag(self._tag("time")) or it.has_tag(
            self._tag("time-repeat")
        ):
            tooltip.set_text(moment(entry))
        elif it.has_tag(self._tag("symbol")):
            tooltip.set_text(symbol_tooltip(entry))
        else:
            return False
        return True


class LoggingWindow(_Window):
    """
    The messages of Virtualbricks, with a filter, and the actions to save
    them, to clear them and to report a bug.
    """

    def __init__(self, messages):
        """
        :type messages: virtualbricks.gui.messages.MessageLog
        """

        self.messages = messages
        self.build_ui()

    def build_ui(self) -> None:
        self.window = Gtk.Window(
            title=_("Messages"),
            default_width=900,
            default_height=560,
            window_position=Gtk.WindowPosition.CENTER_ON_PARENT,
            destroy_with_parent=True,
        )
        header = Gtk.HeaderBar(
            visible=True, show_close_button=True, title=_("Messages")
        )
        self.filter_entry = Gtk.SearchEntry(
            visible=True,
            width_chars=42,
            placeholder_text=_(
                "Filter, for example level:warning source:tap0"
            ),
        )
        header.pack_start(self.filter_entry)
        menu_button = Gtk.MenuButton(
            visible=True,
            tooltip_text=_("Menu"),
            menu_model=self._build_menu(),
            image=Gtk.Image.new_from_icon_name(
                "open-menu-symbolic", Gtk.IconSize.BUTTON
            ),
        )
        header.pack_end(menu_button)
        self.follow_button = Gtk.ToggleButton(
            visible=True,
            active=True,
            label=_("Following"),
            tooltip_text=_("Show the newest messages as they arrive"),
        )
        header.pack_end(self.follow_button)
        self.window.set_titlebar(header)

        box = Gtk.Box(visible=True, orientation=Gtk.Orientation.VERTICAL)
        self.console = ConsoleView(self.messages)
        self.console.on_changed = self.update_status
        self.console.on_folded = self.on_folded
        scrolled = Gtk.ScrolledWindow(visible=True, vexpand=True)
        scrolled.add(self.console.textview)
        box.pack_start(scrolled, True, True, 0)
        box.pack_start(Gtk.Separator(visible=True), False, False, 0)
        status = Gtk.Box(
            visible=True,
            spacing=18,
            margin_start=MARGIN,
            margin_end=MARGIN,
            margin_top=5,
            margin_bottom=5,
        )
        # dim with its own colours: the dim-label style would fade the colours
        # of the errors and of the warnings too
        self.counts_label = Gtk.Label(visible=True, xalign=0.0)
        self.follow_label = Gtk.Label(visible=True, xalign=1.0)
        self.follow_label.get_style_context().add_class("dim-label")
        status.pack_start(self.counts_label, True, True, 0)
        status.pack_end(self.follow_label, False, False, 0)
        box.pack_start(status, False, False, 0)
        self.window.add(box)

        self.window.insert_action_group("log", self._build_actions())
        self.window.connect("destroy", self.on_window_destroy)
        self.window.connect("key-press-event", self.on_key_press_event)
        self.filter_entry.connect("search-changed", self.on_search_changed)
        self.filter_entry.connect("stop-search", self.on_stop_search)
        self._follow_handler = self.follow_button.connect(
            "toggled", self.on_follow_button_toggled
        )
        self._vadjustment = scrolled.get_vadjustment()
        self._vadjustment.connect(
            "value-changed", self.on_vadjustment_value_changed
        )
        self.update_status()

    def _build_menu(self):
        menu = Gio.Menu()
        fold = Gio.Menu()
        fold.append(_("Expand all"), "log.expand-all")
        fold.append(_("Collapse all"), "log.collapse-all")
        menu.append_section(None, fold)
        share = Gio.Menu()
        share.append(_("Save…"), "log.save")
        share.append(_("Report a bug…"), "log.report-bug")
        menu.append_section(None, share)
        clear = Gio.Menu()
        clear.append(_("Clear"), "log.clear")
        menu.append_section(None, clear)
        return menu

    def _build_actions(self):
        group = Gio.SimpleActionGroup()
        for name, handler in (
            ("expand-all", lambda *args: self.console.expand_all(True)),
            ("collapse-all", lambda *args: self.console.expand_all(False)),
            ("save", self.on_save_activate),
            ("report-bug", self.on_report_bug_activate),
            ("clear", lambda *args: self.messages.clear()),
        ):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", handler)
            group.add_action(action)
        return group

    def get_root_widget(self) -> Gtk.Window:
        return self.window

    # The status bar

    def update_status(self):
        counts = self.messages.counts
        total = len(self.messages.entries)
        shown = self.console.shown
        if shown == total:
            text = ngettext("{0} message", "{0} messages", total).format(total)
        else:
            text = ngettext(
                "{0} of {1} message", "{0} of {1} messages", total
            ).format(shown, total)
        errors = counts["error"]
        warnings = counts["warn"]
        lines = counts["output lines"]
        parts = [
            '<span foreground="{0}">{1}</span>'.format(
                DIM, GLib.markup_escape_text(text)
            ),
            '<span foreground="{0}">{1}</span>'.format(
                ERROR_TEXT,
                GLib.markup_escape_text(
                    ngettext("{0} error", "{0} errors", errors).format(errors)
                ),
            ),
            '<span foreground="{0}">{1}</span>'.format(
                WARNING_TEXT,
                GLib.markup_escape_text(
                    ngettext("{0} warning", "{0} warnings", warnings).format(
                        warnings
                    )
                ),
            ),
            '<span foreground="{0}">{1}</span>'.format(
                DIM,
                GLib.markup_escape_text(
                    ngettext(
                        "{0} line of program output",
                        "{0} lines of program output",
                        lines,
                    ).format(lines)
                ),
            ),
        ]
        self.counts_label.set_markup("   ".join(parts))
        if self.console.following:
            self.follow_label.set_text(_("Following the newest"))
        else:
            self.follow_label.set_text(_("Paused"))

    # Following the newest messages

    def set_following(self, following):
        if following == self.console.following:
            return
        self.console.following = following
        with self.follow_button.handler_block(self._follow_handler):
            self.follow_button.set_active(following)
        self.update_status()

    def on_follow_button_toggled(self, button):
        self.set_following(button.get_active())
        if self.console.following:
            self.console.scroll_to_end()

    def on_folded(self, is_last):
        """A fold was clicked: keep the newest in view, or stop following."""

        if is_last:
            if self.console.following:
                self.console.scroll_to_end()
            return
        adjustment = self._vadjustment
        # opening a message above means reading it: stop following
        if adjustment.get_upper() > adjustment.get_page_size():
            self.set_following(False)

    def on_vadjustment_value_changed(self, adjustment):
        self.set_following(
            adjustment.get_value()
            >= adjustment.get_upper()
            - adjustment.get_page_size()
            - SCROLL_TOLERANCE
        )

    # Signals

    def on_search_changed(self, entry):
        self.console.set_filter(entry.get_text())

    def on_stop_search(self, entry):
        entry.set_text("")

    def on_key_press_event(self, window, event):
        control = event.state & Gdk.ModifierType.CONTROL_MASK
        if control and Gdk.keyval_to_lower(event.keyval) == Gdk.KEY_f:
            self.filter_entry.grab_focus()
            return True
        return False

    def on_window_destroy(self, window):
        self.console.detach()
        return True

    def on_save_activate(self, action, parameter):
        chooser = Gtk.FileChooserDialog(
            title=_("Save the messages"),
            transient_for=self.window,
            action=Gtk.FileChooserAction.SAVE,
        )
        chooser.add_buttons(
            _("_Cancel"),
            Gtk.ResponseType.CANCEL,
            _("_Save"),
            Gtk.ResponseType.OK,
        )
        chooser.set_do_overwrite_confirmation(True)
        chooser.connect("response", self.on_save_dialog_response)
        chooser.show()

    def on_save_dialog_response(self, dialog, response_id):
        try:
            if response_id == Gtk.ResponseType.OK:
                with open(dialog.get_filename(), "w") as fp:
                    fp.write(self.messages.text())
        finally:
            dialog.destroy()
        return True

    def on_report_bug_activate(self, action, parameter):
        logger.info(bug_send)

        def xdg_email_exit_cb(codes):
            stdout, stderr, code = codes
            if code == 0:
                logger.info(bug_sent)
            elif code in BUG_REPORT_ERRORS:
                logger.error(
                    bug_error,
                    err=BUG_REPORT_ERRORS[code],
                    stderr=stderr,
                    hide_to_user=True,
                )
            else:
                logger.error(
                    bug_report_fail,
                    code=code,
                    stderr=stderr,
                    hide_to_user=True,
                )

        body = textwrap.dedent(f"""

            Please keep the following lines as they are.
            The attachment contains the logs of Virtualbricks.

            Virtualbricks version: {__version__}
            """)
        # Do not remove the file once xdg-email exits.
        fd, filename = tempfile.mkstemp(prefix="virtualbricks_log_", text=True)
        with os.fdopen(fd, mode="wt", encoding="utf8") as fp:
            fp.write(self.messages.text())
        params = [
            "--utf8",
            "--subject",
            "[Virtualbricks] ",
            "--body",
            body,
            "--attach",
            filename,
        ]
        env = dict(os.environ, MM_NOTTTY="1")
        proc_d = utils.getProcessOutputAndValue("xdg-email", params, env)
        proc_d.addCallback(xdg_email_exit_cb)
        proc_d.addErrback(lambda f: logger.failure(bug_err_unknown, f))
