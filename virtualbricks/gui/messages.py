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
The messages of this run of Virtualbricks, for the messages window.

Each log event becomes an :class:`Entry`: its level, where it comes from (a
brick, an event or a part of Virtualbricks), its lines and its traceback, and
whether it's the output of a brick's program. :class:`MessageLog` keeps the
latest entries and tells the windows that show them what changes.
"""

import collections
import itertools

import attr
from gi.repository import GLib
from twisted.logger import ILogObserver, LogLevel, eventAsText, formatEvent
from zope.interface import implementer

from virtualbricks import base
from virtualbricks.i18n import _

# The output of a brick's program is logged with one of these as "stream".
STREAMS = ("stdout", "stderr")
LEVELS = ("debug", "info", "warn", "error", "critical")
LEVEL_NAMES = {"warning": "warn", "err": "error", "crit": "critical"}
LIMIT = 2000


@attr.define(frozen=True)
class Entry:
    """A message of the log, ready to show."""

    number = attr.field()
    time = attr.field()
    level = attr.field()
    # "stdout" or "stderr" for the output of a brick's program, else None
    stream = attr.field()
    # the brick or event, else the part of Virtualbricks
    source = attr.field()
    # the type of the brick or "event", else None
    source_type = attr.field()
    namespace = attr.field()
    pid = attr.field()
    lines = attr.field()
    traceback = attr.field()
    # the whole message as text, for saving and bug reports
    text = attr.field()

    @property
    def is_output(self):
        return self.stream is not None

    @property
    def category(self):
        """What the status bar counts it as: output, error, warn or info."""

        if self.is_output:
            return "output"
        if self.level == "critical":
            return "error"
        return self.level

    @property
    def rank(self):
        """The level, for the level: filter; output of stderr is a warning."""

        if self.stream == "stderr":
            return LEVELS.index("warn")
        if self.stream == "stdout":
            return LEVELS.index("info")
        return LEVELS.index(self.level)

    @property
    def calls(self):
        """The number of calls in the traceback."""

        return sum(1 for line in self.traceback if line.startswith('  File "'))


def part_name(namespace):
    """The part of Virtualbricks that a logger namespace belongs to."""

    parts = (
        ("virtualbricks.gui.windows.virtualbricks", _("Main window")),
        ("virtualbricks.gui.gui", "Virtualbricks"),
        ("virtualbricks.gui", _("Windows")),
        ("virtualbricks.migrate", _("Migration")),
        ("virtualbricks.config", _("Settings")),
        ("virtualbricks.project", _("Project")),
        ("virtualbricks.console", _("Console")),
        ("virtualbricks.events", _("Events")),
        ("virtualbricks.bricks.virtualmachine", _("Virtual machines")),
        ("virtualbricks.bricks", _("Bricks")),
        ("virtualbricks.link", _("Connections")),
        ("virtualbricks", "Virtualbricks"),
    )
    for prefix, name in parts:
        if namespace == prefix or namespace.startswith(prefix + "."):
            return name
    return namespace.split(".")[0].capitalize() or "Virtualbricks"


def type_name(source_type):
    """How the type of a brick is called, in words."""

    names = {
        "capture": _("capture"),
        "event": _("event"),
        "netemu": _("network emulator"),
        "qemu": _("virtual machine"),
        "router": _("router"),
        "switch": _("switch"),
        "switchwrapper": _("switch wrapper"),
        "tap": _("tap"),
        "tunnelconnect": _("tunnel client"),
        "tunnellisten": _("tunnel server"),
        "wire": _("wire"),
    }
    return names.get(source_type, source_type)


def describe_source(event):
    """Return the name and the type of the brick of an event, or its part."""

    source = event.get("log_source")
    if not isinstance(source, base.Base):
        # the process of a brick, a plug, a socket...
        source = getattr(source, "brick", None)
    if isinstance(source, base.Base):
        return source.get_name(), source.get_type().lower()
    return part_name(event.get("log_namespace", "")), None


def _lines(event, stream):
    text = formatEvent(event)
    if stream is not None:
        # as the program printed it, without the empty lines at the end
        lines = [line.rstrip("\r") for line in text.split("\n")]
        while len(lines) > 1 and not lines[-1].strip():
            lines.pop()
        return lines
    lines = text.rstrip("\n").split("\n")
    # the extra lines of the old messages start with a tab
    return lines[:1] + [
        line[1:] if line.startswith("\t") else line for line in lines[1:]
    ]


def _traceback(event):
    failure = event.get("log_failure")
    if failure is None:
        return []
    try:
        text = failure.getTraceback()
    except Exception:
        return []
    return text.rstrip("\n").split("\n")


def entry_from_event(event, number):
    level = event.get("log_level", LogLevel.info)
    stream = event.get("stream")
    if stream not in STREAMS:
        stream = None
    source, source_type = describe_source(event)
    return Entry(
        number=number,
        time=event.get("log_time", 0.0),
        level=level.name if level.name in LEVELS else "info",
        stream=stream,
        source=source,
        source_type=source_type,
        namespace=event.get("log_namespace", ""),
        pid=event.get("pid"),
        lines=_lines(event, stream),
        traceback=_traceback(event),
        text=eventAsText(event),
    )


@attr.define(frozen=True)
class Filter:
    """
    The filter of the messages window: words, ``level:`` and ``source:``.

    ``level:warning`` keeps the warnings and what is worse; the output of a
    program on stderr counts as a warning, on stdout as info.
    ``source:tap0,router1`` keeps the messages of those bricks, or parts, or
    of every brick of a type (``source:qemu``). Every other word must be in
    the message or its source.
    """

    level = attr.field(default=None)
    sources = attr.field(factory=frozenset)
    words = attr.field(factory=tuple)

    def match(self, entry):
        if self.level is not None and entry.rank < LEVELS.index(self.level):
            return False
        if self.sources and not (
            entry.source.lower() in self.sources
            or entry.source_type in self.sources
        ):
            return False
        if self.words:
            text = "\n".join([entry.source] + entry.lines).lower()
            return all(word in text for word in self.words)
        return True


def parse_filter(text):
    level = None
    sources = set()
    words = []
    for token in text.split():
        key, sep, value = token.partition(":")
        key = key.lower()
        value = value.lower()
        if sep and key == "level" and LEVEL_NAMES.get(value, value) in LEVELS:
            level = LEVEL_NAMES.get(value, value)
        elif sep and key == "source" and value:
            sources.update(name for name in value.split(",") if name)
        else:
            words.append(token.lower())
    return Filter(level, frozenset(sources), tuple(words))


class MessageLog:
    """
    The latest messages, and the windows that show them.

    A listener has ``message_added(entry, dropped)``, where ``dropped`` is
    the oldest entry when the log was full, else None, and
    ``messages_cleared()``.
    """

    def __init__(self, limit=LIMIT):
        self.entries = collections.deque(maxlen=limit)
        self.counts = collections.Counter()
        self._numbers = itertools.count(1)
        self._listeners = []

    def subscribe(self, listener):
        self._listeners.append(listener)

    def unsubscribe(self, listener):
        self._listeners.remove(listener)

    def _count(self, entry, sign):
        if entry.is_output:
            self.counts["output lines"] += sign * len(entry.lines)
        else:
            self.counts[entry.category] += sign

    def add_event(self, event):
        entry = entry_from_event(event, next(self._numbers))
        dropped = None
        if len(self.entries) == self.entries.maxlen:
            dropped = self.entries[0]
            self._count(dropped, -1)
        self.entries.append(entry)
        self._count(entry, 1)
        for listener in list(self._listeners):
            listener.message_added(entry, dropped)
        return entry

    def clear(self):
        self.entries.clear()
        self.counts.clear()
        for listener in list(self._listeners):
            listener.messages_cleared()

    def text(self):
        """The messages as text, as the log file has them."""

        return "".join(entry.text + "\n" for entry in self.entries)


@implementer(ILogObserver)
class MessageLogObserver:
    """A log observer that adds the events to a MessageLog."""

    def __init__(self, messages):
        self.messages = messages

    def __call__(self, event):
        # Events can come from any thread: add them in the main loop.
        GLib.idle_add(self._add, event)

    def _add(self, event):
        self.messages.add_event(event)
        # run once
        return False
