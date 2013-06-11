# -*- test-case-name: virtualbricks.tests.test_link -*-
# Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
# Copyright (C) 2013 Virtualbricks team

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

import os

from twisted.internet import defer
from twisted.python import log, failure

from virtualbricks import errors


if False:  # pyflakes
    _ = str


class Plug:

    sock = None
    _antiloop = False
    mode = "vde"

    def __init__(self, brick):
        self.brick = brick

    def configured(self):
        return self.sock is not None

    def connected(self):
        if self._antiloop:
            if self.brick.settings.get("erroronloop"):
                log.err(_("Loop link detected: aborting operation. If "
                        "you want to start a looped network, disable the "
                        "check loop feature in the general settings"))
            self._antiloop = False
            return defer.fail(errors.LinkLoopError())

        self._antiloop = True
        if self.sock is None or self.sock.brick is None:
            self._antiloop = False
            return defer.fail(errors.NotConnectedError())

        def clear_antiloop(passthru):
            self._antiloop = False
            return passthru

        d = self.sock.brick.poweron()
        d.addBoth(clear_antiloop)
        return d

    def connect(self, sock):
        if sock is None:
            return False
        else:
            sock.plugs.append(self)
            self.sock = sock
            return True

    def disconnect(self):
        self.sock = None


class Sock(object):

    def __init__(self, brick, name=""):
        self.brick = brick
        self.path = name
        self.nickname = name
        self.plugs = []
        self.mode = "sock"

    def get_free_ports(self):
        return int(self.brick.cfg.numports) - len(self.plugs)

    def has_valid_path(self):
        return os.access(os.path.dirname(self.path), os.W_OK)
