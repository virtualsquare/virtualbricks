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

"""The messages of the messages window: entries, filter and log."""

from twisted.logger import (
    ILogObserver,
    LogLevel,
    Logger,
    eventAsText,
    globalLogPublisher,
)
from twisted.python.failure import Failure
from twisted.trial import unittest
from zope.interface.verify import verifyObject

from virtualbricks import bricks
from virtualbricks.gui import messages
from virtualbricks.tests import make_factory
from virtualbricks.tests.gui import TIME, entry, event, untranslated


def failure():
    """A failure raised by a function, fail()."""

    def fail():
        raise ValueError("no space left")

    try:
        fail()
    except ValueError:
        return Failure()


class Listener:
    """What a messages window hears from a MessageLog."""

    def __init__(self):
        self.calls = []

    def message_added(self, entry, dropped):
        self.calls.append(("added", entry, dropped))

    def messages_cleared(self):
        self.calls.append(("cleared",))


class TestEntry(unittest.TestCase):

    def test_output(self):
        self.assertFalse(entry().is_output)
        self.assertTrue(entry(stream="stdout").is_output)

    def test_category(self):
        self.assertEqual(entry(level="info").category, "info")
        self.assertEqual(entry(level="warn").category, "warn")
        self.assertEqual(entry(level="error").category, "error")
        self.assertEqual(entry(level="critical").category, "error")
        self.assertEqual(
            entry(level="error", stream="stderr").category, "output"
        )

    def test_rank(self):
        ranks = [entry(level=level).rank for level in messages.LEVELS]
        self.assertEqual(ranks, [0, 1, 2, 3, 4])
        # the output of a program: stderr is a warning, stdout is info
        self.assertEqual(entry(level="error", stream="stderr").rank, 2)
        self.assertEqual(entry(level="info", stream="stdout").rank, 1)

    def test_calls(self):
        self.assertEqual(entry().calls, 0)
        traceback = [
            "Traceback (most recent call last):",
            '  File "project.py", line 373, in autosave',
            "    self.save_current(factory)",
            '  File "tomlfile.py", line 135, in dump',
            "    fd, tmp = tempfile.mkstemp(",
            "builtins.OSError: [Errno 28] No space left on device",
        ]
        self.assertEqual(entry(traceback=traceback).calls, 2)


class TestSource(unittest.TestCase):

    def setUp(self):
        untranslated(self)

    def test_part_name(self):
        for namespace, name in (
            ("virtualbricks.gui.windows.virtualbricks", "Main window"),
            ("virtualbricks.gui.windows.logging", "Windows"),
            ("virtualbricks.gui.gui", "Virtualbricks"),
            ("virtualbricks.gui.gui.Application", "Virtualbricks"),
            ("virtualbricks.migrate.engine", "Migration"),
            ("virtualbricks.config.settings", "Settings"),
            ("virtualbricks.project", "Project"),
            ("virtualbricks.console", "Console"),
            ("virtualbricks.events", "Events"),
            ("virtualbricks.bricks.virtualmachine", "Virtual machines"),
            ("virtualbricks.bricks.switch.Switch", "Bricks"),
            ("virtualbricks.bricks", "Bricks"),
            ("virtualbricks.link", "Connections"),
            ("virtualbricks.brickfactory", "Virtualbricks"),
            ("virtualbricks", "Virtualbricks"),
        ):
            self.assertEqual(messages.part_name(namespace), name, namespace)

    def test_part_name_matches_whole_components(self):
        self.assertEqual(
            messages.part_name("virtualbricks.projects"), "Virtualbricks"
        )

    def test_part_name_outside_virtualbricks(self):
        self.assertEqual(messages.part_name("twisted.internet"), "Twisted")
        self.assertEqual(messages.part_name(""), "Virtualbricks")

    def test_type_name(self):
        self.assertEqual(messages.type_name("qemu"), "virtual machine")
        self.assertEqual(messages.type_name("netemu"), "network emulator")
        self.assertEqual(messages.type_name("tunnelconnect"), "tunnel client")
        self.assertEqual(messages.type_name("spaceship"), "spaceship")

    def test_brick(self):
        switch = make_factory(self).new_brick("switch", "sw1")
        self.assertEqual(
            messages.describe_source(event("x", log_source=switch)),
            ("sw1", "switch"),
        )

    def test_event(self):
        start = make_factory(self).new_event("start")
        self.assertEqual(
            messages.describe_source(event("x", log_source=start)),
            ("start", "event"),
        )

    def test_the_brick_of_a_process(self):
        switch = make_factory(self).new_brick("switch", "sw1")
        process = bricks.Process(switch)
        self.assertEqual(
            messages.describe_source(event("x", log_source=process)),
            ("sw1", "switch"),
        )

    def test_part(self):
        self.assertEqual(
            messages.describe_source(event("x", log_source=object())),
            ("Project", None),
        )
        self.assertEqual(
            messages.describe_source({"log_namespace": "virtualbricks.link"}),
            ("Connections", None),
        )


class TestEntryFromEvent(unittest.TestCase):

    def setUp(self):
        untranslated(self)

    def test_message(self):
        e = event("Restoring project lab", pid=41851)
        new = messages.entry_from_event(e, 7)
        self.assertEqual(new.number, 7)
        self.assertEqual(new.time, TIME)
        self.assertEqual(new.level, "info")
        self.assertIsNone(new.stream)
        self.assertEqual(new.source, "Project")
        self.assertIsNone(new.source_type)
        self.assertEqual(new.namespace, "virtualbricks.project")
        self.assertEqual(new.pid, 41851)
        self.assertEqual(new.lines, ["Restoring project lab"])
        self.assertEqual(new.traceback, [])
        self.assertEqual(new.text, eventAsText(e))

    def test_levels(self):
        for level in (LogLevel.warn, LogLevel.error, LogLevel.critical):
            new = messages.entry_from_event(event("x", level), 1)
            self.assertEqual(new.level, level.name)

    def test_defaults(self):
        new = messages.entry_from_event({"log_format": "x"}, 1)
        self.assertEqual(new.level, "info")
        self.assertEqual(new.time, 0.0)
        self.assertEqual(new.namespace, "")
        self.assertEqual(new.source, "Virtualbricks")

    def test_extra_lines_lose_one_tab(self):
        new = messages.entry_from_event(
            event("KSM not found\n\tcomponents: vde\n\t\tindented\nplain\n"),
            1,
        )
        self.assertEqual(
            new.lines,
            ["KSM not found", "components: vde", "\tindented", "plain"],
        )

    def test_output(self):
        new = messages.entry_from_event(
            event("  one\r\n\ttwo\r\n\n  \n", stream="stdout"), 1
        )
        self.assertEqual(new.stream, "stdout")
        self.assertEqual(new.lines, ["  one", "\ttwo"])

    def test_blank_output(self):
        new = messages.entry_from_event(event("\n\n", stream="stderr"), 1)
        self.assertEqual(new.lines, [""])

    def test_unknown_stream(self):
        new = messages.entry_from_event(event("x", stream="stdin"), 1)
        self.assertIsNone(new.stream)
        self.assertFalse(new.is_output)

    def test_traceback(self):
        new = messages.entry_from_event(
            event(
                "Error while saving", LogLevel.critical, log_failure=failure()
            ),
            1,
        )
        self.assertEqual(new.lines, ["Error while saving"])
        self.assertEqual(
            new.traceback[0], "Traceback (most recent call last):"
        )
        self.assertIn("no space left", new.traceback[-1])
        # how many frames depends on the version of Twisted; fail() is last
        calls = [line for line in new.traceback if line.startswith('  File "')]
        self.assertTrue(calls[-1].endswith(", in fail"), calls[-1])
        self.assertEqual(new.calls, len(calls))

    def test_unprintable_traceback(self):
        class Broken:
            def getTraceback(self):
                raise RuntimeError("no traceback")

        new = messages.entry_from_event(event("x", log_failure=Broken()), 1)
        self.assertEqual(new.traceback, [])

    def test_from_a_process(self):
        """The output of a program comes from its brick, with its pid."""

        events = []
        globalLogPublisher.addObserver(events.append)
        self.addCleanup(globalLogPublisher.removeObserver, events.append)
        switch = make_factory(self).new_brick("switch", "sw1")
        process = bricks.Process(switch)

        class Transport:
            pid = 41851

        process.transport = Transport()
        process.errReceived(b"vde_switch: no such socket\n")
        new = messages.entry_from_event(events[-1], 1)
        self.assertEqual(new.level, "error")
        self.assertEqual(new.stream, "stderr")
        self.assertEqual((new.source, new.source_type), ("sw1", "switch"))
        self.assertEqual(new.pid, 41851)
        self.assertEqual(new.lines, ["vde_switch: no such socket"])

    def test_from_a_brick(self):
        switch = make_factory(self).new_brick("switch", "sw1")
        events = []
        logger = Logger(source=switch, observer=events.append)
        logger.info("Starting: {args}", args="vde_switch -n 32")
        new = messages.entry_from_event(events[0], 1)
        self.assertEqual((new.source, new.source_type), ("sw1", "switch"))
        self.assertEqual(new.lines, ["Starting: vde_switch -n 32"])


class TestFilter(unittest.TestCase):

    def setUp(self):
        self.info = entry(level="info", lines=["Restoring project lab"])
        self.warn = entry(level="warn", lines=["no MAC address"])
        self.error = entry(
            level="error",
            source="tap0",
            source_type="tap",
            lines=["Process terminated"],
        )
        self.critical = entry(level="critical", lines=["Error while saving"])
        self.stdout = entry(
            stream="stdout", source="sw1", source_type="switch", lines=["VDE"]
        )
        self.stderr = entry(
            level="error",
            stream="stderr",
            source="tap0",
            source_type="tap",
            lines=["sudo: a terminal is required", "more"],
        )
        self.all = [
            self.info,
            self.warn,
            self.error,
            self.critical,
            self.stdout,
            self.stderr,
        ]

    def kept(self, text):
        match = messages.parse_filter(text).match
        return [entry for entry in self.all if match(entry)]

    def test_empty(self):
        self.assertEqual(messages.parse_filter(" "), messages.Filter())
        self.assertEqual(self.kept(""), self.all)

    def test_level(self):
        self.assertEqual(
            self.kept("level:warning"),
            [self.warn, self.error, self.critical, self.stderr],
        )
        self.assertEqual(self.kept("level:error"), [self.error, self.critical])
        self.assertEqual(self.kept("level:critical"), [self.critical])
        self.assertEqual(self.kept("level:info"), self.all)

    def test_level_names(self):
        for text, level in (
            ("level:warning", "warn"),
            ("level:warn", "warn"),
            ("LEVEL:Err", "error"),
            ("level:crit", "critical"),
            ("level:debug", "debug"),
        ):
            self.assertEqual(messages.parse_filter(text).level, level, text)

    def test_unknown_level_is_a_word(self):
        parsed = messages.parse_filter("level:loud")
        self.assertIsNone(parsed.level)
        self.assertEqual(parsed.words, ("level:loud",))

    def test_source(self):
        self.assertEqual(self.kept("source:tap0"), [self.error, self.stderr])
        self.assertEqual(
            self.kept("source:TAP0,sw1"),
            [self.error, self.stdout, self.stderr],
        )
        self.assertEqual(
            messages.parse_filter("source:a,,b source:c").sources,
            frozenset(("a", "b", "c")),
        )

    def test_source_by_type_or_part(self):
        self.assertEqual(self.kept("source:switch"), [self.stdout])
        self.assertEqual(
            self.kept("source:project"), [self.info, self.warn, self.critical]
        )

    def test_empty_source_is_a_word(self):
        self.assertEqual(messages.parse_filter("source:").words, ("source:",))

    def test_words(self):
        self.assertEqual(self.kept("SUDO"), [self.stderr])
        # all of them, in the lines or in the source
        self.assertEqual(self.kept("tap0 terminated"), [self.error])
        self.assertEqual(self.kept("more"), [self.stderr])
        self.assertEqual(self.kept("sudo nothing"), [])

    def test_together(self):
        self.assertEqual(
            self.kept("level:warning source:tap0 sudo"), [self.stderr]
        )


class TestMessageLog(unittest.TestCase):

    def setUp(self):
        self.log = messages.MessageLog()
        self.listener = Listener()
        self.log.subscribe(self.listener)

    def test_add_event(self):
        first = self.log.add_event(event("one"))
        second = self.log.add_event(event("two"))
        self.assertEqual((first.number, second.number), (1, 2))
        self.assertEqual(list(self.log.entries), [first, second])
        self.assertEqual(
            self.listener.calls,
            [("added", first, None), ("added", second, None)],
        )

    def test_limit(self):
        log = messages.MessageLog(limit=2)
        log.subscribe(self.listener)
        first = log.add_event(event("one", LogLevel.error))
        second = log.add_event(event("two"))
        third = log.add_event(event("three"))
        self.assertEqual(list(log.entries), [second, third])
        self.assertEqual(self.listener.calls[-1], ("added", third, first))
        self.assertEqual(log.counts["error"], 0)
        self.assertEqual(log.counts["info"], 2)
        # the numbers go on
        self.assertEqual(third.number, 3)

    def test_default_limit(self):
        self.assertEqual(self.log.entries.maxlen, messages.LIMIT)

    def test_counts(self):
        for level in (LogLevel.info, LogLevel.warn, LogLevel.critical):
            self.log.add_event(event("x", level))
        self.log.add_event(event("x", LogLevel.error))
        self.log.add_event(event("a\nb\nc\n", stream="stdout"))
        self.log.add_event(event("d\n", LogLevel.error, stream="stderr"))
        self.assertEqual(
            dict(self.log.counts),
            {"info": 1, "warn": 1, "error": 2, "output lines": 4},
        )

    def test_clear(self):
        self.log.add_event(event("one", LogLevel.error))
        self.log.clear()
        self.assertEqual(list(self.log.entries), [])
        self.assertEqual(dict(self.log.counts), {})
        self.assertEqual(self.listener.calls[-1], ("cleared",))
        # the numbers go on after a clear
        self.assertEqual(self.log.add_event(event("two")).number, 2)

    def test_unsubscribe(self):
        self.log.unsubscribe(self.listener)
        self.log.add_event(event("one"))
        self.log.clear()
        self.assertEqual(self.listener.calls, [])

    def test_unsubscribe_while_notified(self):
        log = self.log

        class Leaving(Listener):
            def message_added(self, entry, dropped):
                super().message_added(entry, dropped)
                log.unsubscribe(self)

        leaving = Leaving()
        log.subscribe(leaving)
        log.add_event(event("one"))
        log.add_event(event("two"))
        self.assertEqual(len(leaving.calls), 1)
        self.assertEqual(len(self.listener.calls), 2)

    def test_text(self):
        self.assertEqual(self.log.text(), "")
        one = event("one")
        two = event("two\nlines", LogLevel.error)
        self.log.add_event(one)
        self.log.add_event(two)
        self.assertEqual(
            self.log.text(), eventAsText(one) + "\n" + eventAsText(two) + "\n"
        )


class TestMessageLogObserver(unittest.TestCase):

    def test_interface(self):
        observer = messages.MessageLogObserver(messages.MessageLog())
        self.assertTrue(verifyObject(ILogObserver, observer))

    def test_adds_in_the_main_loop(self):
        calls = []

        class FakeGLib:
            @staticmethod
            def idle_add(function, *args):
                calls.append((function, args))

        self.patch(messages, "GLib", FakeGLib)
        log = messages.MessageLog()
        observer = messages.MessageLogObserver(log)
        observer(event("one"))
        # nothing until the main loop runs it
        self.assertEqual(list(log.entries), [])
        [(function, args)] = calls
        # once
        self.assertIs(function(*args), False)
        self.assertEqual([e.lines for e in log.entries], [["one"]])
