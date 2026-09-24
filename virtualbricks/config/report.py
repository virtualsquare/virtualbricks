# -*- test-case-name: virtualbricks.tests.config.test_report -*-
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

"""Messages collected while reading, converting or writing configuration."""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, Final, Literal

import attr

if TYPE_CHECKING:
    from twisted.logger import Logger

Level = Literal["info", "warning", "error"]

INFO: Final = "info"
WARNING: Final = "warning"
ERROR: Final = "error"


@attr.define(frozen=True)
class Message:

    level: Level = attr.field()
    text: str = attr.field()
    where: str = attr.field(default="")

    def __str__(self) -> str:
        if self.where:
            return f"{self.where}: {self.text}"
        return self.text


class Report:
    """An ordered list of messages, each with a level and a location."""

    def __init__(self) -> None:
        self.messages: list[Message] = []

    def add(self, level: Level, text: str, where: str = "") -> None:
        self.messages.append(Message(level, text, where))

    def info(self, text: str, where: str = "") -> None:
        self.add(INFO, text, where)

    def warning(self, text: str, where: str = "") -> None:
        self.add(WARNING, text, where)

    def error(self, text: str, where: str = "") -> None:
        self.add(ERROR, text, where)

    def extend(self, other: Report) -> None:
        self.messages.extend(other.messages)

    def count(self, level: Level) -> int:
        return sum(1 for message in self.messages if message.level == level)

    @property
    def warnings(self) -> int:
        return self.count(WARNING)

    @property
    def errors(self) -> int:
        return self.count(ERROR)

    @property
    def has_errors(self) -> bool:
        return self.errors > 0

    def log(self, logger: Logger) -> None:
        emitters = {
            INFO: logger.info,
            WARNING: logger.warn,
            ERROR: logger.error,
        }
        for message in self.messages:
            emitters[message.level]("{message}", message=str(message))

    def __iter__(self) -> Iterator[Message]:
        return iter(self.messages)

    def __len__(self) -> int:
        return len(self.messages)
