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

from twisted.internet import defer
from twisted.logger import Logger

from virtualbricks import errors
from virtualbricks.config import get_setting

link_loop = (
    "Loop link detected: aborting operation. If you want "
    "to start a looped network, disable the check loop "
    "feature in the general settings"
)


class Plug:

    sock = None
    _antiloop = False
    mode = "vde"
    logger = Logger()
    model = ""
    mac = ""

    def __init__(self, brick):
        self.brick = brick

    def configured(self):
        return self.sock is not None

    def connected(self):
        if self._antiloop:
            if get_setting("erroronloop"):
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

        def clear_antiloop(passthru):
            self._antiloop = False
            return passthru

        d = self.sock.brick.poweron()
        d.addBoth(clear_antiloop)
        return d

    def connect(self, sock):
        assert sock is not None, "Cannot connect a plug to nothing"
        sock.plugs.append(self)
        self.sock = sock

    def disconnect(self):
        assert self.sock is not None, "Plug not connected"
        assert self in self.sock.plugs, "sock %r has not reference to %r" % (
            self.sock,
            self,
        )
        self.sock.plugs.remove(self)
        self.sock = None
