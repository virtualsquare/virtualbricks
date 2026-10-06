# -*- test-case-name: virtualbricks.tests.bricks.test_sock -*-
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

"""A socket: what the plugs of other bricks go into."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from virtualbricks.bricks import Brick
    from virtualbricks.bricks.plug import Plug


class Sock:

    model = ""
    mac = ""

    def __init__(self, brick: Brick, name: str = "") -> None:
        self.brick = brick
        self.path = name
        self.nickname = name
        self.plugs: list[Plug] = []
        self.mode = "sock"

    def has_valid_path(self) -> bool:
        return os.access(os.path.dirname(self.path), os.W_OK)
