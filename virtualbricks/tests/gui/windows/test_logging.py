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

"""The messages window: the console and the window around it."""

import os
import tempfile

from twisted.internet import defer
from twisted.logger import LogLevel
from twisted.trial import unittest

from virtualbricks.tests import FakeLogger, make_factory
from virtualbricks.tests.gui import (
    TIME,
    entry,
    event,
    has_display,
    untranslated,
)

if has_display:

    from gi.repository import Gdk, GdkPixbuf, Gtk

    from virtualbricks.gui import messages
    from virtualbricks.gui.windows import logging

DAY = 24 * 60 * 60
TRACEBACK = [
    "Traceback (most recent call last):",
    '  File "project.py", line 373, in autosave',
    "    self.save_current(factory)",
    '  File "tomlfile.py", line 135, in dump',
    "    fd, tmp = tempfile.mkstemp(",
    "builtins.OSError: [Errno 28] No space left on device",
]


class Traceback:
    """A failure, as the log events have it."""

    def getTraceback(self):
        return "\n".join(TRACEBACK) + "\n"


class Button:
    """A button event at a point of the text."""

    def __init__(self, x, y, button=1):
        self.x = x
        self.y = y
        self.button = button


class Key:

    def __init__(self, keyval, state=0):
        self.keyval = keyval
        self.state = state


class Tooltip:

    def __init__(self):
        self.text = None

    def set_text(self, text):
        self.text = text


class ReportLogger(FakeLogger):
    """A FakeLogger that also takes the failure of logger.failure()."""

    def failure(self, format, failure=None, **kwargs):
        self.events.append(("failure", format, kwargs))


class DisplayTestCase(unittest.TestCase):
    """A test of the messages window, in English."""

    if not has_display:  # pragma: no cover
        skip = "GTK can't open a display"

    def setUp(self):
        untranslated(self)
        self.log = messages.MessageLog()

    def add(self, text, **values):
        return self.log.add_event(event(text, **values))


class ConsoleTestCase(DisplayTestCase):
    """The console, with letters instead of the images, to read its text."""

    def setUp(self):
        super().setUp()
        self.patch(logging, "symbol_icon", lambda kind: None)
        self.patch(logging, "type_icon", lambda source_type: None)

    def console(self):
        view = logging.ConsoleView(self.log)
        self.addCleanup(self._detach, view)
        return view

    def _detach(self, view):
        if view in self.log._listeners:
            view.detach()

    def show(self, view):
        """Lay the console out in a window that is not on screen."""

        window = Gtk.OffscreenWindow()
        window.set_default_size(700, 400)
        window.add(view.textview)
        window.show_all()
        self.addCleanup(window.destroy)
        self.flush()

    def flush(self):
        while Gtk.events_pending():
            Gtk.main_iteration()

    def text(self, view):
        return view.buffer.get_text(*view.buffer.get_bounds(), True)

    def lines(self, view):
        return self.text(view).split("\n")

    def line_tags(self, view, line):
        """The names of the tags at the start of a line."""

        it = view.buffer.get_iter_at_line(line)
        return {tag.props.name for tag in it.get_tags()}

    def find(self, view, tag):
        """An iter inside the first text with the tag."""

        it = view.buffer.get_start_iter()
        if not it.has_tag(view._tag(tag)):
            self.assertTrue(it.forward_to_tag_toggle(view._tag(tag)))
        return it

    def point(self, view, it, window_type=None):
        """The point of the window where it is drawn."""

        if window_type is None:
            window_type = Gtk.TextWindowType.TEXT
        rect = view.textview.get_iter_location(it)
        return view.textview.buffer_to_window_coords(
            window_type, rect.x + 2, rect.y + rect.height // 2
        )

    def click(self, view, it, button=1):
        x, y = self.point(view, it)
        return view.on_button_release_event(
            view.textview, Button(x, y, button)
        )

    def tooltip(self, view, it):
        x, y = self.point(view, it, Gtk.TextWindowType.WIDGET)
        tooltip = Tooltip()
        shown = view.on_query_tooltip(view.textview, x, y, False, tooltip)
        return shown, tooltip.text


class TestHelpers(DisplayTestCase):

    def test_clock(self):
        self.assertEqual(logging.clock(entry()), "17:47:09")

    def test_day(self):
        day = logging.day(entry())
        self.assertIn("24", day)
        self.assertIn("2026", day)
        self.assertNotEqual(day, logging.day(entry(time=TIME + DAY)))

    def test_moment(self):
        moment = logging.moment(entry())
        self.assertTrue(moment.startswith(logging.day(entry())))
        self.assertTrue(moment.endswith(", 17:47:09.250"), moment)

    def test_source_text(self):
        self.assertEqual(
            logging.source_text(entry(source="Project")), "Project"
        )
        name = "a" * logging.SOURCE_CHARS
        self.assertEqual(logging.source_text(entry(source=name)), name)
        self.assertEqual(
            logging.source_text(entry(source="virtual_machine_1")),
            "virtual_machi…",
        )

    def test_source_tooltip_of_a_part(self):
        self.assertEqual(
            logging.source_tooltip(entry()), "virtualbricks.project"
        )

    def test_source_tooltip_of_a_brick(self):
        self.assertEqual(
            logging.source_tooltip(
                entry(
                    source="vm1",
                    source_type="qemu",
                    namespace="virtualbricks.bricks.virtualmachine",
                )
            ),
            "vm1 · virtual machine · virtualbricks.bricks.virtualmachine",
        )
        self.assertEqual(
            logging.source_tooltip(
                entry(
                    stream="stderr",
                    source="tap0",
                    source_type="tap",
                    namespace="virtualbricks.bricks.Process",
                    pid=41851,
                )
            ),
            "tap0 · tap · stderr · virtualbricks.bricks.Process · pid 41851",
        )

    def test_symbol_tooltip(self):
        self.assertEqual(
            [
                logging.symbol_tooltip(entry(level=level))
                for level in messages.LEVELS
            ],
            ["Debug", "Info", "Warning", "Error", "Critical"],
        )
        self.assertEqual(
            logging.symbol_tooltip(entry(level="error", stream="stderr")),
            "Output of the program on stderr",
        )

    def test_folds_of(self):
        self.assertEqual(logging.folds_of(entry()), [])
        self.assertEqual(logging.folds_of(entry(lines=["a", "b"])), ["lines"])
        self.assertEqual(
            logging.folds_of(entry(lines=["a", "b"], traceback=TRACEBACK)),
            ["lines", "traceback"],
        )
        self.assertEqual(
            logging.folds_of(entry(traceback=TRACEBACK)), ["traceback"]
        )

    def test_symbol_icon(self):
        self.patch(logging, "_symbol_icons", {})
        for kind in logging.SYMBOL_ICONS:
            icon = logging.symbol_icon(kind)
            # None if the theme has no symbolic icons: the letters are used
            if icon is not None:
                self.assertEqual(icon.get_width(), logging.ICON_SIZE)
            self.assertIs(logging.symbol_icon(kind), icon)

    def test_type_icon(self):
        self.patch(logging, "_type_icons", {})
        icon = logging.type_icon("switch")
        self.assertIsInstance(icon, GdkPixbuf.Pixbuf)
        self.assertEqual(
            (icon.get_width(), icon.get_height()),
            (logging.ICON_SIZE, logging.ICON_SIZE),
        )
        self.assertIs(logging.type_icon("switch"), icon)
        self.assertIsNone(logging.type_icon("spaceship"))


class TestConsoleLines(ConsoleTestCase):

    def test_empty(self):
        view = self.console()
        self.assertEqual(self.text(view), "")
        self.assertEqual(view.shown, 0)

    def test_message(self):
        first = self.add("Restoring project lab")
        view = self.console()
        self.assertEqual(
            self.lines(view),
            [
                logging.day(first).upper(),
                "17:47:09\t\tProject\tI\tRestoring project lab",
                "",
            ],
        )
        self.assertIn("day", self.line_tags(view, 0))
        self.assertEqual(self.line_tags(view, 1), {"time", "first"})
        self.assertEqual(view.shown, 1)

    def test_new_messages(self):
        view = self.console()
        self.add("one")
        self.add("two")
        self.assertEqual(
            self.lines(view)[1:],
            [
                "17:47:09\t\tProject\tI\tone",
                "17:47:09\t\tProject\tI\ttwo",
                "",
            ],
        )
        self.assertEqual(view.shown, 2)

    def test_days_and_repeated_times(self):
        self.add("one")
        self.add("same second", time=TIME + 0.5)
        self.add("next second", time=TIME + 1)
        self.add("next day", time=TIME + DAY)
        view = self.console()
        lines = self.lines(view)
        self.assertEqual(lines[0], logging.day(entry()).upper())
        self.assertEqual(lines[4], logging.day(entry(time=TIME + DAY)).upper())
        self.assertEqual(lines[1].split("\t")[0], "17:47:09")
        self.assertIn("time", self.line_tags(view, 1))
        self.assertIn("time-repeat", self.line_tags(view, 2))
        self.assertTrue(lines[3].startswith("17:47:10\t"))
        self.assertIn("time", self.line_tags(view, 3))
        # a new day, and the time of the day is shown again
        self.assertIn("time", self.line_tags(view, 5))

    def test_brick(self):
        switch = make_factory(self).new_brick("switch", "sw1")
        self.add("Starting: vde_switch", log_source=switch)
        view = self.console()
        self.assertEqual(
            self.lines(view)[1], "17:47:09\t\tsw1\tI\tStarting: vde_switch"
        )
        tags = {tag.props.name for tag in self.find(view, "brick").get_tags()}
        self.assertEqual(tags, {"source", "brick", "first"})

    def test_part(self):
        self.add("Restoring project lab")
        view = self.console()
        tags = {tag.props.name for tag in self.find(view, "part").get_tags()}
        self.assertEqual(tags, {"source", "part", "first"})

    def test_long_source(self):
        self.add("x", namespace="virtualbricks.gui.windows.virtualbricks")
        self.add(
            "y",
            log_source=make_factory(self).new_brick(
                "switch", "a_switch_with_a_long_name"
            ),
        )
        view = self.console()
        self.assertEqual(self.lines(view)[1].split("\t")[2], "Main window")
        self.assertEqual(self.lines(view)[2].split("\t")[2], "a_switch_with…")

    def test_levels(self):
        for level in (
            LogLevel.debug,
            LogLevel.info,
            LogLevel.warn,
            LogLevel.error,
            LogLevel.critical,
        ):
            self.add(level.name, level=level)
        view = self.console()
        self.assertEqual(
            [line.split("\t")[3:] for line in self.lines(view)[1:-1]],
            [
                ["D", "debug"],
                ["I", "info"],
                ["W", "warn"],
                ["E", "error"],
                ["C", "critical"],
            ],
        )
        for line, tag in (
            (1, "extra"),
            (3, "warn"),
            (4, "error"),
            (5, "critical"),
        ):
            it = view.buffer.get_iter_at_line(line)
            it.forward_to_line_end()
            it.backward_char()
            self.assertTrue(it.has_tag(view._tag(tag)), tag)
        it = view.buffer.get_iter_at_line(2)
        it.forward_to_line_end()
        it.backward_char()
        self.assertEqual({tag.props.name for tag in it.get_tags()}, {"first"})

    def test_symbol_tags(self):
        self.add("x", level=LogLevel.warn)
        view = self.console()
        tags = {tag.props.name for tag in self.find(view, "symbol").get_tags()}
        self.assertEqual(tags, {"symbol", "symbol-warn", "first"})

    def test_output(self):
        self.add("VDE switch V.2.3.3\n", stream="stdout")
        self.add(
            "sudo: a terminal is required\n",
            level=LogLevel.error,
            stream="stderr",
        )
        view = self.console()
        self.assertEqual(
            [line.split("\t")[3:] for line in self.lines(view)[1:-1]],
            [
                ["›", "VDE switch V.2.3.3"],
                ["›", "2> sudo: a terminal is required"],
            ],
        )
        stream = self.find(view, "stream")
        self.assertEqual(stream.get_line(), 2)
        self.assertTrue(self.find(view, "output").has_tag(view._tag("output")))
        self.assertEqual(self.find(view, "output").get_line(), 1)

    def test_icons(self):
        """With the images, the type of a brick and the symbol are images."""

        self.patch(logging, "symbol_icon", lambda kind: pixbuf())
        self.patch(logging, "type_icon", lambda source_type: pixbuf())
        switch = make_factory(self).new_brick("switch", "sw1")
        self.add("one")
        self.add("two", log_source=switch)
        view = self.console()
        start, end = view.buffer.get_bounds()
        lines = view.buffer.get_slice(start, end, True).split("\n")
        self.assertEqual(lines[1], "17:47:09\t\tProject\t￼\tone")
        self.assertEqual(lines[2], "17:47:09\t￼\tsw1\t￼\ttwo")


def pixbuf():
    return GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, 16, 16)


class TestConsoleFolds(ConsoleTestCase):

    def test_toggles(self):
        self.add("KSM not found\nsome components\nare missing")
        self.add("Error while saving", log_failure=Traceback())
        self.add("one\ntwo\n", stream="stdout")
        view = self.console()
        self.assertEqual(
            self.lines(view)[1:-1],
            [
                "17:47:09\t\tProject\tI\tKSM not found  ▸\xa02\xa0more\xa0lines",
                "17:47:09\t\tProject\tI\tError while saving  "
                "▸\xa0traceback,\xa02\xa0calls",
                "17:47:09\t\tProject\t›\tone  ▸\xa01\xa0more\xa0line",
            ],
        )
        toggle = self.find(view, "toggle-lines")
        self.assertTrue(toggle.has_tag(view._tag("toggle")))

    def test_open_and_close(self):
        self.add("KSM not found\n\tsome components\n\tare missing")
        self.add("after")
        view = self.console()
        view.toggle(0, "lines")
        self.assertEqual(
            self.lines(view)[1:],
            [
                "17:47:09\t\tProject\tI\tKSM not found  ▾\xa02\xa0more\xa0lines",
                "some components",
                "are missing",
                "17:47:09\t\tProject\tI\tafter",
                "",
            ],
        )
        self.assertEqual(self.line_tags(view, 2), {"extra", "more"})
        # the next entry keeps its place
        self.assertEqual(view._index_at(view.buffer.get_iter_at_line(4)), 1)
        view.toggle(0, "lines")
        self.assertEqual(
            self.lines(view)[1:],
            [
                "17:47:09\t\tProject\tI\tKSM not found  ▸\xa02\xa0more\xa0lines",
                "17:47:09\t\tProject\tI\tafter",
                "",
            ],
        )
        self.assertEqual(view.expanded, set())

    def test_open_keeps_the_day(self):
        self.add("one\ntwo")
        view = self.console()
        view.toggle(0, "lines")
        self.assertEqual(self.lines(view)[0], logging.day(entry()).upper())

    def test_open_between_two_messages(self):
        """Only the first line has the hanging indent of the first line."""

        self.add("one")
        self.add("two\nthree", time=TIME + DAY)
        self.add("four", time=TIME + DAY)
        view = self.console()
        view.toggle(1, "lines")
        self.assertEqual(self.line_tags(view, 2), {"day"})
        self.assertIn("first", self.line_tags(view, 3))
        self.assertEqual(self.line_tags(view, 4), {"extra", "more"})
        self.assertIn("first", self.line_tags(view, 5))

    def test_traceback(self):
        self.add(
            "Error while saving",
            level=LogLevel.critical,
            log_failure=Traceback(),
        )
        view = self.console()
        view.toggle(0, "traceback")
        self.assertEqual(self.lines(view)[2:-1], TRACEBACK)
        self.assertEqual(self.line_tags(view, 2), {"extra", "more"})

    def test_output(self):
        self.add("  one\n  two\n", stream="stdout")
        view = self.console()
        view.toggle(0, "lines")
        self.assertEqual(self.lines(view)[2], "  two")
        self.assertEqual(self.line_tags(view, 2), {"output", "more"})

    def test_expand_all(self):
        first = self.add("one\ntwo", log_failure=Traceback())
        second = self.add("three\nfour")
        self.add("five")
        view = self.console()
        view.expand_all()
        self.assertEqual(
            view.expanded,
            {
                (first.number, "lines"),
                (first.number, "traceback"),
                (second.number, "lines"),
            },
        )
        self.assertEqual(len(self.lines(view)), 2 + 2 + len(TRACEBACK) + 2 + 1)
        view.expand_all(False)
        self.assertEqual(view.expanded, set())
        self.assertEqual(len(self.lines(view)), 5)

    def test_folds_stay_open_when_filtering(self):
        first = self.add("one\ntwo")
        self.add("three", level=LogLevel.error)
        view = self.console()
        view.toggle(0, "lines")
        view.set_filter("level:error")
        view.set_filter("")
        self.assertIn((first.number, "lines"), view.expanded)
        self.assertEqual(self.lines(view)[2], "two")


class TestConsoleLog(ConsoleTestCase):

    def test_filter(self):
        changed = []
        self.add("one")
        self.add("two", level=LogLevel.error)
        view = self.console()
        view.on_changed = lambda: changed.append(view.shown)
        view.set_filter("level:error")
        self.assertEqual(
            self.lines(view)[1:], ["17:47:09\t\tProject\tE\ttwo", ""]
        )
        # a new message that doesn't match
        self.add("three")
        self.add("four", level=LogLevel.critical)
        self.assertEqual(view.shown, 2)
        self.assertEqual(changed, [1, 1, 2])

    def test_filtered_first_message_starts_the_day(self):
        self.add("one")
        self.add("two", level=LogLevel.error)
        view = self.console()
        view.set_filter("level:error")
        self.assertEqual(self.lines(view)[0], logging.day(entry()).upper())
        self.assertIn("time", self.line_tags(view, 1))

    def test_oldest_message_dropped(self):
        self.log = messages.MessageLog(limit=2)
        self.add("one")
        self.add("two", time=TIME + 0.5)
        view = self.console()
        self.add("three", time=TIME + 1)
        self.assertEqual(
            self.lines(view),
            [
                logging.day(entry()).upper(),
                "17:47:09\t\tProject\tI\ttwo",
                "17:47:10\t\tProject\tI\tthree",
                "",
            ],
        )
        # the first message isn't a repeated time any more
        self.assertIn("time", self.line_tags(view, 1))
        self.assertEqual(view.shown, 2)
        self.assertEqual(view._index_at(view.buffer.get_iter_at_line(2)), 1)

    def test_dropped_message_not_shown(self):
        self.log = messages.MessageLog(limit=2)
        self.add("one")
        self.add("two", level=LogLevel.error)
        view = self.console()
        view.set_filter("level:error")
        self.add("three", level=LogLevel.error)
        self.assertEqual(
            [line.split("\t")[-1] for line in self.lines(view)[1:-1]],
            ["two", "three"],
        )

    def test_only_message_dropped(self):
        self.log = messages.MessageLog(limit=1)
        self.add("one")
        view = self.console()
        self.add("two", time=TIME + DAY)
        self.assertEqual(
            self.lines(view),
            [
                logging.day(entry(time=TIME + DAY)).upper(),
                "17:47:09\t\tProject\tI\ttwo",
                "",
            ],
        )

    def test_cleared(self):
        self.add("one")
        view = self.console()
        self.log.clear()
        self.assertEqual(self.text(view), "")
        self.assertEqual(view.shown, 0)

    def test_detach(self):
        view = self.console()
        view.detach()
        self.add("one")
        self.assertEqual(self.text(view), "")

    def test_index_at(self):
        view = self.console()
        self.assertIsNone(view._index_at(view.buffer.get_start_iter()))
        self.add("one\ntwo")
        self.add("three", time=TIME + DAY)
        view.toggle(0, "lines")
        at = view.buffer.get_iter_at_line
        # the day line belongs to the message that starts the day
        self.assertEqual(
            [view._index_at(at(line)) for line in range(5)], [0, 0, 0, 1, 1]
        )
        self.assertEqual(view._index_at(view.buffer.get_end_iter()), 1)


class TestConsoleView(ConsoleTestCase):

    def test_light(self):
        view = self.console()
        self.assertTrue(
            view.textview.get_style_context().has_class("vb-console")
        )

    def test_geometry(self):
        view = self.console()
        tabs = view.textview.get_tabs()
        stops = [tabs.get_tab(index)[1] for index in range(tabs.get_size())]
        self.assertEqual(len(stops), 4)
        self.assertEqual(stops, sorted(stops))
        message = stops[-1]
        self.assertEqual(view._tag("first").props.indent, -message)
        self.assertEqual(
            view._tag("more").props.left_margin, logging.MARGIN + message
        )

    def test_click_a_toggle(self):
        folded = []
        self.add("one\ntwo")
        self.add("three\nfour")
        view = self.console()
        view.on_folded = folded.append
        self.show(view)
        self.assertTrue(self.click(view, self.find(view, "toggle-lines")))
        self.assertEqual(self.lines(view)[2], "two")
        self.assertEqual(folded, [False])
        self.flush()
        # the last message
        it = view.buffer.get_iter_at_line(3)
        self.assertTrue(it.forward_to_tag_toggle(view._tag("toggle-lines")))
        self.assertTrue(self.click(view, it))
        self.assertEqual(self.lines(view)[4], "four")
        self.assertEqual(folded, [False, True])

    def test_click_a_traceback(self):
        self.add("Error while saving", log_failure=Traceback())
        view = self.console()
        self.show(view)
        self.assertTrue(self.click(view, self.find(view, "toggle-traceback")))
        self.assertEqual(self.lines(view)[2], TRACEBACK[0])

    def test_other_clicks(self):
        self.add("one\ntwo")
        view = self.console()
        self.show(view)
        toggle = self.find(view, "toggle-lines")
        self.assertFalse(self.click(view, toggle, button=3))
        self.assertFalse(self.click(view, view.buffer.get_iter_at_line(1)))
        # selecting text isn't a click
        view.buffer.select_range(
            view.buffer.get_start_iter(), view.buffer.get_end_iter()
        )
        self.assertFalse(self.click(view, toggle))
        self.assertEqual(view.expanded, set())

    def test_hover(self):
        self.add("one\ntwo")
        view = self.console()
        self.show(view)
        for it, hovering in (
            (self.find(view, "toggle"), True),
            (view.buffer.get_iter_at_line(1), False),
        ):
            x, y = self.point(view, it)
            self.assertFalse(
                view.on_motion_notify_event(view.textview, Button(x, y))
            )
            self.assertIs(view._hovering, hovering)

    def test_tooltips(self):
        switch = make_factory(self).new_brick("switch", "sw1")
        self.add("one", log_source=switch, level=LogLevel.warn)
        self.add("two", time=TIME + 0.5)
        view = self.console()
        self.show(view)
        self.assertEqual(
            self.tooltip(view, self.find(view, "source")),
            (True, "sw1 · switch · virtualbricks.project"),
        )
        self.assertEqual(
            self.tooltip(view, self.find(view, "symbol")), (True, "Warning")
        )
        self.assertEqual(
            self.tooltip(view, self.find(view, "time")),
            (True, logging.moment(entry())),
        )
        # a repeated time has its own moment
        self.assertEqual(
            self.tooltip(view, self.find(view, "time-repeat")),
            (True, logging.moment(entry(time=TIME + 0.5))),
        )
        message = view.buffer.get_iter_at_line(1)
        message.forward_to_line_end()
        message.backward_char()
        self.assertEqual(self.tooltip(view, message), (False, None))

    def test_no_tooltip_from_the_keyboard(self):
        self.add("one")
        view = self.console()
        self.show(view)
        tooltip = Tooltip()
        self.assertFalse(
            view.on_query_tooltip(view.textview, 1, 1, True, tooltip)
        )
        self.assertIsNone(tooltip.text)

    def test_no_tooltip_without_messages(self):
        view = self.console()
        self.show(view)
        self.assertFalse(
            view.on_query_tooltip(view.textview, 20, 20, False, Tooltip())
        )


class TestLoggingWindow(ConsoleTestCase):

    def window(self):
        window = logging.LoggingWindow(self.log)
        self.addCleanup(self._destroy, window)
        return window

    def _destroy(self, window):
        if window.console in self.log._listeners:
            window.window.destroy()

    def counts(self, window):
        return window.counts_label.get_text()

    def activate(self, window, name):
        window.window.get_action_group("log").activate_action(name, None)

    def test_title(self):
        window = self.window()
        self.assertEqual(window.window.get_title(), "Messages")
        self.assertIs(window.get_root_widget(), window.window)

    def test_status(self):
        window = self.window()
        self.assertEqual(
            self.counts(window),
            "0 messages   0 errors   0 warnings   0 lines of program output",
        )
        self.assertEqual(
            window.follow_label.get_text(), "Following the newest"
        )
        self.add("one")
        self.add("two", level=LogLevel.warn)
        self.add("three", level=LogLevel.error)
        self.add("four", level=LogLevel.critical)
        self.add("five\nsix\n", level=LogLevel.error, stream="stderr")
        self.assertEqual(
            self.counts(window),
            "5 messages   2 errors   1 warning   2 lines of program output",
        )
        self.add("seven\n", stream="stdout")
        self.log.clear()
        self.add("eight", level=LogLevel.error)
        self.assertEqual(
            self.counts(window),
            "1 message   1 error   0 warnings   0 lines of program output",
        )

    def test_status_markup(self):
        self.add("one", level=LogLevel.error)
        window = self.window()
        markup = window.counts_label.get_label()
        self.assertIn(
            f'<span foreground="{logging.ERROR_TEXT}">1 error', markup
        )
        self.assertIn(
            f'<span foreground="{logging.WARNING_TEXT}">0 warnings', markup
        )

    def test_filter(self):
        self.add("one")
        self.add("two", level=LogLevel.error)
        window = self.window()
        window.filter_entry.set_text("level:error")
        window.filter_entry.emit("search-changed")
        self.assertEqual(window.console.shown, 1)
        self.assertTrue(self.counts(window).startswith("1 of 2 messages   "))
        window.filter_entry.emit("stop-search")
        self.assertEqual(window.filter_entry.get_text(), "")

    def test_own_filter(self):
        self.add("one")
        self.add("two", level=LogLevel.error)
        first = self.window()
        second = self.window()
        first.console.set_filter("level:error")
        self.assertEqual((first.console.shown, second.console.shown), (1, 2))

    def test_find(self):
        window = self.window()
        self.assertTrue(
            window.on_key_press_event(
                window.window, Key(Gdk.KEY_f, Gdk.ModifierType.CONTROL_MASK)
            )
        )
        self.assertIs(window.window.get_focus(), window.filter_entry)
        self.assertTrue(
            window.on_key_press_event(
                window.window, Key(Gdk.KEY_F, Gdk.ModifierType.CONTROL_MASK)
            )
        )
        self.assertFalse(
            window.on_key_press_event(window.window, Key(Gdk.KEY_f))
        )
        self.assertFalse(
            window.on_key_press_event(
                window.window, Key(Gdk.KEY_g, Gdk.ModifierType.CONTROL_MASK)
            )
        )

    def test_following(self):
        window = self.window()
        window.set_following(False)
        self.assertFalse(window.console.following)
        self.assertFalse(window.follow_button.get_active())
        self.assertEqual(window.follow_label.get_text(), "Paused")
        window.follow_button.set_active(True)
        self.assertTrue(window.console.following)
        self.assertEqual(
            window.follow_label.get_text(), "Following the newest"
        )
        window.follow_button.set_active(False)
        self.assertFalse(window.console.following)

    def test_scrolling(self):
        window = self.window()
        for value, following in (
            (0, False),
            (900, True),
            (900 - logging.SCROLL_TOLERANCE, True),
            (800, False),
        ):
            window.on_vadjustment_value_changed(adjustment(value, 1000))
            self.assertIs(window.console.following, following, value)

    def test_folded(self):
        window = self.window()
        # all the messages are in view
        self.patch(window, "_vadjustment", adjustment(0, 100))
        window.on_folded(False)
        self.assertTrue(window.console.following)
        window.on_folded(True)
        self.assertTrue(window.console.following)
        # opening the last message keeps the newest in view
        self.patch(window, "_vadjustment", adjustment(900, 1000))
        window.on_folded(True)
        self.assertTrue(window.console.following)
        # opening one above means reading it
        window.on_folded(False)
        self.assertFalse(window.console.following)

    def test_expand_and_collapse(self):
        self.add("one\ntwo")
        window = self.window()
        self.activate(window, "expand-all")
        self.assertEqual(len(window.console.expanded), 1)
        self.activate(window, "collapse-all")
        self.assertEqual(window.console.expanded, set())

    def test_clear(self):
        self.add("one")
        first = self.window()
        second = self.window()
        self.activate(first, "clear")
        self.assertEqual(list(self.log.entries), [])
        self.assertEqual(second.console.shown, 0)
        self.assertTrue(self.counts(second).startswith("0 messages"))

    def test_destroy(self):
        window = self.window()
        window.window.destroy()
        self.assertNotIn(window.console, self.log._listeners)

    def test_save(self):
        self.add("one")
        self.add("two", level=LogLevel.error)
        window = self.window()
        # everything, whatever the filter
        window.console.set_filter("level:error")
        path = self.mktemp()
        dialog = FileDialog(path)
        self.assertTrue(
            window.on_save_dialog_response(dialog, Gtk.ResponseType.OK)
        )
        with open(path) as fp:
            self.assertEqual(fp.read(), self.log.text())
        self.assertTrue(dialog.destroyed)

    def test_save_cancelled(self):
        window = self.window()
        path = self.mktemp()
        dialog = FileDialog(path)
        window.on_save_dialog_response(dialog, Gtk.ResponseType.CANCEL)
        self.assertFalse(os.path.exists(path))
        self.assertTrue(dialog.destroyed)


def adjustment(value, upper):
    """A vertical adjustment of a view 100 pixels high."""

    return Gtk.Adjustment(
        value=value,
        lower=0,
        upper=upper,
        step_increment=10,
        page_increment=100,
        page_size=100,
    )


class FileDialog:

    def __init__(self, filename):
        self.filename = filename
        self.destroyed = False

    def get_filename(self):
        return self.filename

    def destroy(self):
        self.destroyed = True


class TestReportBug(DisplayTestCase):

    def setUp(self):
        super().setUp()
        self.logger = ReportLogger()
        self.patch(logging, "logger", self.logger)
        self.folder = os.path.abspath(self.mktemp())
        os.makedirs(self.folder)
        mkstemp = tempfile.mkstemp
        self.patch(
            logging.tempfile,
            "mkstemp",
            lambda **kwargs: mkstemp(dir=self.folder, **kwargs),
        )
        self.calls = []
        self.result = defer.succeed((b"", b"", 0))
        self.patch(logging.utils, "getProcessOutputAndValue", self.xdg_email)
        self.window = logging.LoggingWindow(self.log)
        self.addCleanup(self.window.window.destroy)

    def xdg_email(self, program, args, env):
        self.calls.append((program, args, env))
        return self.result

    def report(self, result):
        self.result = result
        self.window.window.get_action_group("log").activate_action(
            "report-bug", None
        )

    def test_attaches_the_messages(self):
        self.add("one")
        self.add("two", level=LogLevel.error)
        self.report(defer.succeed((b"", b"", 0)))
        [(program, args, env)] = self.calls
        self.assertEqual(program, "xdg-email")
        self.assertEqual(args[:3], ["--utf8", "--subject", "[Virtualbricks] "])
        self.assertEqual(args[3], "--body")
        self.assertIn(f"Virtualbricks version: {logging.__version__}", args[4])
        self.assertEqual(args[5], "--attach")
        self.assertEqual(os.path.dirname(args[6]), self.folder)
        with open(args[6]) as fp:
            self.assertEqual(fp.read(), self.log.text())
        self.assertEqual(env["MM_NOTTTY"], "1")
        self.assertEqual(
            self.logger.formatted(), [logging.bug_send, logging.bug_sent]
        )

    def test_known_error(self):
        self.report(defer.succeed((b"", b"no tool", 3)))
        self.assertEqual(self.logger.levels(), ["info", "error"])
        level, format, values = self.logger.events[-1]
        self.assertEqual(values["err"], logging.BUG_REPORT_ERRORS[3])
        self.assertEqual(values["stderr"], b"no tool")
        self.assertTrue(values["hide_to_user"])

    def test_unknown_code(self):
        self.report(defer.succeed((b"", b"", 42)))
        level, format, values = self.logger.events[-1]
        self.assertEqual(format, logging.bug_report_fail)
        self.assertEqual(values["code"], 42)

    def test_failure(self):
        self.report(defer.fail(OSError("no xdg-email")))
        self.assertEqual(
            self.logger.events[-1], ("failure", logging.bug_err_unknown, {})
        )
