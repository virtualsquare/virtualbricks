# -*- test-case-name: virtualbricks.tests.bricks.test_plug -*-
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

"""A plug: the end of a link that goes into a socket."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from twisted.internet import defer

from virtualbricks import errors

if TYPE_CHECKING:  # pragma: no cover
    from virtualbricks.bricks import Brick
    from virtualbricks.bricks.sock import Sock
    from virtualbricks.bricks.virtualmachine import HostonlySock


class Plug:

    # the socket it's in: a brick's, QEMU's own user network, or none
    sock: Sock | HostonlySock | None = None
    mode = "vde"
    model = ""
    mac = ""

    def __init__(self, brick: Brick) -> None:
        self.brick = brick

    def configured(self) -> bool:
        return self.sock is not None

    def connected(self) -> defer.Deferred[Any]:
        """
        Start the brick of the socket, the one this plug's brick needs.

        A loop of links is the start's to find: the brick that starts is
        asked to start again before its first start returns.
        """

        if self.sock is None or self.sock.brick is None:
            return defer.fail(errors.NotConnectedError())

        # special case where a brick (vm) is plugged to itself:
        # brick -> plug -> sock <- brick
        if self.sock.brick is self.brick:
            return defer.succeed(self.brick)

        return self.sock.brick.start()

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
