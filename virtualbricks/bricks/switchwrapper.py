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

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from twisted.internet import defer

from virtualbricks import bricks, errors
from virtualbricks.config.schema import Path, define, field
from virtualbricks.i18n import N_, _

if TYPE_CHECKING:  # pragma: no cover
    from virtualbricks.brickfactory import BrickFactory

sock_not_exists = "Socket does not exists: {path}"


@define
class SwitchWrapperConfig(bricks.BrickConfig):

    # the control folder of a switch that another program runs
    socket_path: str = field(
        Path(),
        default="",
        label=N_("Control folder"),
        help=N_("The control folder of a switch that another program runs"),
    )


class SwitchWrapper(bricks.Brick):

    type = "SwitchWrapper"
    summary = "A VDE switch that another program runs"
    pid = -1
    config_factory = SwitchWrapperConfig
    config: SwitchWrapperConfig

    def __init__(self, factory: BrickFactory, name: str) -> None:
        bricks.Brick.__init__(self, factory, name)
        self.socks.append(factory.new_sock(self, self.name + "_port"))

    def start(self, resume: str = "") -> defer.Deferred[bricks.Brick]:
        if self.is_running():
            return defer.succeed(self)
        elif os.path.exists(self.config.socket_path):
            self.proc = bricks.FakeProcess(self)
            self.changed.notify(self)
            return defer.succeed(self)
        else:
            self.logger.debug(sock_not_exists, path=self.config.socket_path)
            msg = _("Socket does not exists: %s") % self.config.socket_path
            return defer.fail(errors.BadConfigError(msg))

    def stop(
        self, kill: bool = False
    ) -> defer.Deferred[tuple[bricks.Brick, object]]:
        if self.is_running():
            self.proc = None
            self.changed.notify(self)
        return defer.succeed((self, None))

    def configured(self) -> bool:
        return self.socks[0].has_valid_path()

    def cbset_socket_path(self, path: str) -> None:
        self.socks[0].path = path
