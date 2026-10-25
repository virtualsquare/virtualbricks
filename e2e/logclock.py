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
The clock of the messages of a Virtualbricks of the tests: a log observer
for its --logger, ``e2e.logclock.observer``.

The first message is at E2E_LOG_CLOCK, as 2024-08-02 10:00:00, local time,
and each next one STEP after it, whenever they come: the Logs window shows
the same times at each run. The observer is the first of Virtualbricks: it
changes the time of each message before the others read it. A debug message
has the time of the message before it.
"""

import itertools
import os
import time

from twisted.logger import LogLevel

# Between a message and the next
STEP = 0.4

_start = time.mktime(
    time.strptime(os.environ["E2E_LOG_CLOCK"], "%Y-%m-%d %H:%M:%S")
)
_count = itertools.count()
_last = [_start]


def observer(event):
    if event.get("log_level") is not LogLevel.debug:
        _last[0] = _start + STEP * next(_count)
    event["log_time"] = _last[0]
