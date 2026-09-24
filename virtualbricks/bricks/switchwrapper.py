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

"""A switch wrapper: a switch that Virtualbricks doesn't run, by its socket."""

import os

from twisted.internet import defer

from virtualbricks import bricks, errors
from virtualbricks.config import schema
from virtualbricks.config.schema import Path
from virtualbricks.i18n import _

sock_not_exists = "Socket does not exists: {path}"


@schema.define
class SwitchWrapperConfig(bricks.BrickConfig):

    path = schema.field(Path(), default="")


class SwitchWrapper(bricks.Brick):

    type = "SwitchWrapper"
    pid = -1
    config_factory = SwitchWrapperConfig

    def __init__(self, factory, name):
        bricks.Brick.__init__(self, factory, name)
        self.socks.append(factory.new_sock(self, self.name + "_port"))

    def poweron(self):
        if self.proc is not None:
            return defer.succeed(self)
        elif os.path.exists(self.config.path):
            self.proc = bricks.FakeProcess(self)
            return defer.succeed(self)
        else:
            self.logger.debug(sock_not_exists, path=self.config.path)
            msg = _("Socket does not exists: %s") % self.config.path
            return defer.fail(errors.BadConfigError(msg))

    def poweroff(self, kill=False):
        self.proc = None
        return defer.succeed((self, None))

    def get_parameters(self):
        return self.config.path

    def configured(self):
        return self.socks[0].has_valid_path()

    def cbset_path(self, path):
        self.socks[0].path = path
