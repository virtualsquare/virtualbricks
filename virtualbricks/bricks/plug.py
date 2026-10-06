# -*- test-case-name: virtualbricks.tests.bricks.test_plug -*-
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

"""A plug: the end of a link that goes into a socket."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from twisted.internet import defer
from twisted.logger import Logger

from virtualbricks import errors
from virtualbricks.config.settings import get_setting

if TYPE_CHECKING:  # pragma: no cover
    from virtualbricks.bricks import Brick
    from virtualbricks.bricks.sock import Sock
    from virtualbricks.bricks.virtualmachine import HostonlySock

link_loop = "The links make a loop: the bricks on it don't start."


class Plug:

    # the socket it's in: a brick's, QEMU's own user network, or none
    sock: Sock | HostonlySock | None = None
    _antiloop = False
    mode = "vde"
    logger = Logger()
    model = ""
    mac = ""

    def __init__(self, brick: Brick) -> None:
        self.brick = brick

    def configured(self) -> bool:
        return self.sock is not None

    def connected(self) -> defer.Deferred[Any]:
        if self._antiloop:
            if get_setting("log_link_loops"):
                self.logger.error(link_loop)
            self._antiloop = False
            return defer.fail(errors.LinkLoopError())

        self._antiloop = True
        if self.sock is None or self.sock.brick is None:
            self._antiloop = False
            return defer.fail(errors.NotConnectedError())

        # special case where a brick (vm) is plugged to itself:
        # brick -> plug -> sock <- brick
        if self.sock.brick is self.brick:
            self._antiloop = False
            return defer.succeed(self.brick)

        def clear_antiloop(passthru: object) -> object:
            self._antiloop = False
            return passthru

        d = self.sock.brick.start()
        d.addBoth(clear_antiloop)
        return d

    def connect(self, sock: Sock | HostonlySock) -> None:
        assert sock is not None, "Cannot connect a plug to nothing"
        sock.plugs.append(self)
        self.sock = sock

    def disconnect(self) -> None:
        assert self.sock is not None, "Plug not connected"
        assert self in self.sock.plugs, "sock %r has not reference to %r" % (
            self.sock,
            self,
        )
        self.sock.plugs.remove(self)
        self.sock = None
