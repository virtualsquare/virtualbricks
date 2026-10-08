# -*- test-case-name: virtualbricks.tests.bricks.test_switchwrapper -*-
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
A switch wrapper: a switch that Virtualbricks doesn't run, by its control
folder. It runs while a switch listens there: Virtualbricks looks at the
folder, every LOOK_EVERY seconds, with look_all().
"""

from __future__ import annotations

import os
import stat
from collections.abc import Collection
from typing import TYPE_CHECKING

from twisted.internet import defer
from twisted.logger import Logger

from virtualbricks import bricks, errors
from virtualbricks.config.report import Report
from virtualbricks.config.schema import Path, define, field
from virtualbricks.config.tomlfile import Table
from virtualbricks.i18n import N_, _

if TYPE_CHECKING:  # pragma: no cover
    from typing_extensions import TypeIs

    from virtualbricks.brickfactory import BrickFactory

logger = Logger()
look_failed = "Cannot look at the control folder of {name}"

# How often the control folders are looked at, in seconds.
LOOK_EVERY = 1.0


def listens(folder: str) -> bool:
    """Whether a VDE switch listens in its control folder: its ctl socket."""

    if not folder:
        return False
    try:
        mode = os.stat(os.path.join(folder, "ctl")).st_mode
    except OSError:
        return False
    return stat.S_ISSOCK(mode)


def switch_pid(folder: str, proc: str = "/proc") -> int | None:
    """
    The process of the switch that listens in folder: the sockets bound to
    its ctl, in proc/net/unix, among the open files of the processes. None
    if the switch is another user's, or Linux tells none.
    """

    ctl = os.path.realpath(os.path.join(folder, "ctl"))
    links = set()
    try:
        with open(os.path.join(proc, "net", "unix")) as table:
            next(table, None)  # the names of the columns
            for line in table:
                # Num RefCount Protocol Flags Type St Inode Path
                columns = line.rstrip("\n").split(None, 7)
                if len(columns) < 8 or os.path.basename(columns[7]) != "ctl":
                    continue
                if os.path.realpath(columns[7]) == ctl:
                    links.add(f"socket:[{columns[6]}]")
    except OSError:
        return None
    if not links:
        return None
    for name in os.listdir(proc):
        if not name.isdigit():
            continue
        fds = os.path.join(proc, name, "fd")
        try:
            files = os.listdir(fds)
        except OSError:
            # another user's
            continue
        for fd in files:
            try:
                if os.readlink(os.path.join(fds, fd)) in links:
                    return int(name)
            except OSError:
                continue
    return None


class ExternalSwitch:
    """
    The process of a switch that another program runs, as a running wrapper
    has it: its number, found once asked for. It takes no signals and no
    input from Virtualbricks.
    """

    def __init__(self, brick: SwitchWrapper, folder: str) -> None:
        self.brick = brick
        self.folder = folder
        self._pid: int | None = None
        self._looked = False

    @property
    def pid(self) -> int | None:
        if not self._looked:
            self._looked = True
            self._pid = switch_pid(self.folder)
        return self._pid

    def signal_process(self, signal: str | int) -> None:
        raise errors.OtherProgramError(not_ours(self.brick))

    def write(self, data: bytes) -> None:
        raise errors.OtherProgramError(not_ours(self.brick))


def not_ours(brick: SwitchWrapper) -> str:
    return _("Another program runs the switch of {name}").format(
        name=brick.name
    )


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
    runs_program = False
    config_factory = SwitchWrapperConfig
    config: SwitchWrapperConfig

    def __init__(self, factory: BrickFactory, name: str) -> None:
        bricks.Brick.__init__(self, factory, name)
        sock = factory.new_sock(self, self.name + "_port")
        # the control folder, once the brick has one
        sock.path = ""
        self.socks.append(sock)

    def look(self, follow: bool = True) -> None:
        """
        Look at the control folder: the brick runs while a switch listens
        there, and says so when that changes. follow runs the events of its
        start and its stop then; the first look at a folder runs none.
        """

        folder = self.socks[0].path
        running = listens(folder)
        if running == self.is_running():
            return
        self.proc = ExternalSwitch(self, folder) if running else None
        if follow:
            self._start_related_events(on=running, off=not running)
        self.changed.notify(self)

    def start(self, resume: str = "") -> defer.Deferred[bricks.Brick]:
        """
        Look at the control folder now: the brick runs if a switch listens
        there, else it can't start.
        """

        if not self.configured():
            msg = _("Cannot start '%s': not configured") % self.name
            return defer.fail(errors.BadConfigError(msg))
        self.look()
        if self.is_running():
            return defer.succeed(self)
        msg = _("No switch listens in %s") % self.socks[0].path
        return defer.fail(errors.BadConfigError(msg))

    def stop(
        self, kill: bool = False
    ) -> defer.Deferred[tuple[bricks.Brick, object]]:
        """Refused while it runs: the other program stops its switch."""

        if self.is_running():
            return defer.fail(errors.OtherProgramError(not_ours(self)))
        return defer.succeed((self, None))

    def configured(self) -> bool:
        return bool(self.socks[0].path)

    def load_config_table(
        self, table: Table, report: Report, where: str, ignore: Collection[str]
    ) -> None:
        super().load_config_table(table, report, where, ignore)
        self.cbset_socket_path(self.config.socket_path)

    def cbset_socket_path(self, path: str) -> None:
        self.socks[0].path = path
        self.proc = None
        self.look(follow=False)


def is_switchwrapper(brick: object) -> TypeIs[SwitchWrapper]:
    return (
        isinstance(brick, bricks.Brick) and brick.get_type() == "SwitchWrapper"
    )


def look_all(factory: BrickFactory) -> None:
    """
    Look at the control folders of the switch wrappers of factory; a
    failure is logged, and the others are looked at.
    """

    for brick in factory.bricks:
        if is_switchwrapper(brick):
            try:
                brick.look()
            except Exception:
                logger.failure(look_failed, name=brick.name)
