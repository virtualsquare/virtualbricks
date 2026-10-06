# -*- test-case-name: virtualbricks.tests.bricks.test_netemu -*-
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

"""A network emulator: wirefilter, a wire with a Markov chain of states."""

from __future__ import annotations

import re
from collections.abc import Collection
from typing import TYPE_CHECKING

import attr
from twisted.internet import defer

from virtualbricks import bricks, errors
from virtualbricks.bricks.command import Command, Prepared, socket_path
from virtualbricks.bricks.draft import Draft, Problem
from virtualbricks.bricks.virtualmachine import is_virtualmachine
from virtualbricks.bricks.wire import Wire
from virtualbricks.config.schema import (
    Bool,
    Float,
    Int,
    ListOf,
    Record,
    Str,
    define,
    dump_record,
    field,
    field_default,
    field_names,
    field_values,
    load_record,
    notes,
    rename_references,
)
from virtualbricks.i18n import N_, _
from virtualbricks.programs import ProgramError

if TYPE_CHECKING:  # pragma: no cover
    from virtualbricks.brickfactory import BrickFactory
    from virtualbricks.config.report import Report
    from virtualbricks.config.tomlfile import Notes, Table
    from virtualbricks.programs import VdeInfo

# The options that Netemu passes to its program.
OPTIONS = ("-v", "-b", "-d", "-c", "-l", "--nofifo", "-M")


@define
class NetemuConfig(bricks.BrickConfig):
    """
    The configuration of a Netemu: its events and a state of its Markov chain.

    Each state is a NetemuConfig, and every state has the events of the brick.
    The config of the brick is its current state. In the project file the
    events are keys of the brick and the states are tables without them.
    """

    name: str = field(
        Str(),
        default="default name",
        label=N_("Name"),
        help=N_("The name of the state"),
    )
    # each value both ways, or from left to right and from right to left
    bandwidth: int = field(
        Int(),
        default=125000,
        label=N_("Bandwidth"),
        help=N_(
            "Bytes per second at which the buffer drains, 0 for no limit; left"
            " to right, unless the same both ways"
        ),
    )
    bandwidth_right_to_left: int = field(
        Int(),
        default=125000,
        label=N_("Bandwidth from right to left"),
        help=N_("Bytes per second from right to left"),
        when=("bandwidth_symmetric", False),
    )
    bandwidth_symmetric: bool = field(
        Bool(),
        default=True,
        label=N_("The same bandwidth both ways"),
        help=N_("Use bandwidth both ways"),
    )
    delay: int = field(
        Int(),
        default=0,
        label=N_("Delay"),
        help=N_(
            "One-way delay in ms, added to the time in the buffer; left to"
            " right, unless the same both ways"
        ),
    )
    delay_right_to_left: int = field(
        Int(),
        default=0,
        label=N_("Delay from right to left"),
        help=N_("Delay in ms from right to left"),
        when=("delay_symmetric", False),
    )
    delay_symmetric: bool = field(
        Bool(),
        default=True,
        label=N_("The same delay both ways"),
        help=N_("Use delay both ways"),
    )
    buffer_size: int = field(
        Int(),
        default=75000,
        label=N_("Buffer"),
        help=N_(
            "Bytes the packet queue holds, 0 for no limit; left to right,"
            " unless the same both ways"
        ),
    )
    buffer_size_right_to_left: int = field(
        Int(),
        default=75000,
        label=N_("Buffer from right to left"),
        help=N_("Channel buffer in bytes from right to left"),
        when=("buffer_size_symmetric", False),
    )
    buffer_size_symmetric: bool = field(
        Bool(),
        default=True,
        label=N_("The same buffer both ways"),
        help=N_("Use buffer_size both ways"),
    )
    loss: float = field(
        Float(0, 100),
        default=0.0,
        label=N_("Loss"),
        help=N_(
            "Percentage of packets lost, as 0.1 for one in a thousand; left"
            " to right, unless the same both ways"
        ),
    )
    loss_right_to_left: float = field(
        Float(0, 100),
        default=0.0,
        label=N_("Loss from right to left"),
        help=N_("Percentage of packets lost from right to left"),
        when=("loss_symmetric", False),
    )
    loss_symmetric: bool = field(
        Bool(),
        default=True,
        label=N_("The same loss both ways"),
        help=N_("Use loss both ways"),
    )


BRICK_KEYS = frozenset(field_names(bricks.BrickConfig))
# The keys of a state in the project file.
STATE_KEYS = frozenset(field_names(NetemuConfig)) - BRICK_KEYS


@define
class NetemuTable(bricks.BrickConfig):
    """The table of a Netemu in the project file."""

    transition_period: int = field(
        Int(1),
        default=100,
        help="How often the emulator may change state, in ms",
    )
    transitions: list[list[float]] = field(
        ListOf(ListOf(Float(0))),
        factory=lambda: [[0.0]],
        help=(
            "The probability of going from each state, a row, to each state, "
            "a column, at each period"
        ),
    )
    states: list[NetemuConfig] = field(
        ListOf(Record(NetemuConfig, exclude=BRICK_KEYS), min_length=1),
        factory=lambda: [NetemuConfig()],
        help="The states of the emulator; it starts in the first",
    )


# Each channel emulator has its instance of this manager class
class MarkovConfig:

    # calling __init__ with the current active config (Netemu.config) will link it to state nr. 0
    def __init__(self, config: NetemuConfig) -> None:
        self.states: list[NetemuConfig] = list()
        self.weights: list[list[float]] = list()
        self.weights.append(list())
        self.weights[0].append(0.0)
        self.states.append(config)

    # append a new state with default config at the end of the state list
    # all weights to and from the new state are 0 by default
    def add(self, index: int) -> None:
        # the events belong to the brick, so every state has the same ones
        new = NetemuConfig(
            **{name: getattr(self.states[0], name) for name in BRICK_KEYS}
        )
        length = len(self.states)
        self.weights.insert(index, list())

        unavailable = []
        defaultOccupied = False
        defaultName = str(field_default(NetemuConfig, "name"))

        for i, state in enumerate(self.states):
            self.weights[i].insert(index, 0.0)
            self.weights[index].append(0.0)

            # default naming of each state uses the default name + a positive integer at the end (e.g. default name 0, default name 1...)
            if state.name.startswith(defaultName):
                args = state.name.split(" ")
                defaultArgsLen = len(defaultName.split(" "))
                if len(args) == defaultArgsLen + 1:
                    num = args[defaultArgsLen]
                    if num.isnumeric():
                        unavailable.append(num)
                elif not defaultOccupied and len(args) == defaultArgsLen:
                    defaultOccupied = True

        self.weights[length].append(0.0)

        if not defaultOccupied:
            self.states.insert(index, new)
            return

        unavailable.sort()

        for i, num in enumerate(unavailable):
            if str(i) != num:
                new.name += " " + str(i)
                self.states.insert(index, new)
                return

        new.name += " " + str(len(unavailable))
        self.states.insert(index, new)

    # delete a state and all weights from and to the state
    def remove(self, index: int) -> None:
        if len(self.states) == 1:
            return

        del self.weights[index]

        for weight in self.weights:
            del weight[index]

        del self.states[index]


class NetemuDraft(Draft):
    """
    The settings of a Netemu: its states, one of them selected, whose values
    are the draft's settings; the chances of moving between them, a row for
    each state, in %; and the period of the moves.

    What a state doesn't move to it keeps: its row adds up to 100 at most.
    """

    def __init__(self, brick: Netemu) -> None:
        super().__init__(brick)
        manager = brick.markov_manager
        self.states = [attr.evolve(state) for state in manager.states]
        self.weights = [list(row) for row in manager.weights]
        self.period = brick.transPeriod
        self.selected = 0
        self.settings = self.states[0]

    def select(self, index: int) -> None:
        """Show the values of the state of index."""

        self.selected = index
        self.settings = self.states[index]
        self.refused.clear()

    def add(self) -> int:
        """A new state after the selected one, with no chance of moving."""

        index = self.selected + 1
        first = self.states[0]
        # the events belong to the brick, so every state has the same ones
        state = NetemuConfig(
            **{name: getattr(first, name) for name in BRICK_KEYS}
        )
        names = {other.name for other in self.states}
        number = len(self.states) + 1
        while f"state {number}" in names:
            number += 1
        state.name = f"state {number}"
        self.states.insert(index, state)
        for row in self.weights:
            row.insert(index, 0.0)
        self.weights.insert(index, [0.0] * len(self.states))
        self.select(index)
        return index

    def remove(self) -> None:
        """Remove the selected state, unless it's the only one."""

        if len(self.states) == 1:
            return
        index = self.selected
        del self.states[index]
        del self.weights[index]
        for row in self.weights:
            del row[index]
        self.select(min(index, len(self.states) - 1))

    def set_weight(self, row: int, column: int, value: float) -> None:
        self.weights[row][column] = value

    def stays(self, index: int) -> float:
        """The chance, in %, that the state of index doesn't move."""

        row = self.weights[index]
        return 100.0 - sum(row) + row[index]

    def check(self) -> list[Problem]:
        problems = []
        names = [state.name for state in self.states]
        for name in dict.fromkeys(names):
            if names.count(name) > 1:
                text = _("Two states are called {name}").format(name=name)
                problems.append(Problem("name", text))
        for index, state in enumerate(self.states):
            if self.stays(index) < 0:
                text = _(
                    "From {state} the chances add up to more than 100 %"
                ).format(state=state.name)
                problems.append(Problem("transitions", text))
        left = self.links[0]
        if left is not None and is_virtualmachine(left.brick):
            text = _("A machine's socket card can only be the right end")
            problems.append(Problem("plug0", text))
        return problems + super().check()

    def changes(self) -> dict[str, object]:
        # the states are the brick's own, in apply_extras()
        return {}

    def apply_extras(self) -> bool:
        brick = self.brick
        manager = brick.markov_manager
        if (
            self.states == manager.states
            and self.weights == manager.weights
            and self.period == brick.transPeriod
        ):
            return False
        manager.states = self.states
        manager.weights = self.weights
        brick.transPeriod = self.period
        brick.currentState = min(brick.currentState, len(self.states) - 1)
        brick.config = self.states[brick.currentState]
        # a running emulator gets them all
        brick.update()
        return True


class WFProcessProtocol(bricks.VDEProcessProtocol):

    prompt = re.compile(rb"^VDEwf\$ ", re.M)


class Netemu(Wire):

    type = "Netemu"
    summary = "A wire that emulates a network link"
    # wirefilter runs in place of vde-netemu
    programs = (("vde-netemu", "wirefilter"),)
    config_factory = NetemuConfig
    config: NetemuConfig
    draft_factory = NetemuDraft
    process_protocol = WFProcessProtocol

    def __init__(self, factory: BrickFactory, name: str) -> None:
        Wire.__init__(self, factory, name)
        self.markov_manager = MarkovConfig(self.config)
        self.currentState = (
            0  # used for GUI updating and communicating to Netemu
        )
        self.startupState = 0  # the state the emulator will start into
        self.transPeriod = 100  # default value for Netemu

    def start(self, resume: str = "") -> defer.Deferred[bricks.Brick]:
        d = bricks.Brick.start(self)
        self.currentState = self.startupState
        self.config = self.markov_manager.states[self.currentState]
        self.update()
        return d

    def program(self, vde: VdeInfo | None) -> tuple[str, str | None]:
        """
        The program: vde-netemu, or wirefilter of VDE, which it's a fork of.

        Return the path and a warning, or None.
        """

        assert vde is not None, "prepare() gathers the VDE programs"
        if "vde-netemu" in vde.programs:
            return vde.programs["vde-netemu"], None
        path = vde.programs.get("wirefilter")
        if path is None:
            raise ProgramError(
                "vde-netemu (vde-netemu) isn't installed, nor wirefilter (vde2)"
            )
        lacks = [
            option
            for option in OPTIONS
            if option not in vde.options.get("wirefilter", ())
        ]
        if lacks:
            raise ProgramError(
                "vde-netemu (vde-netemu) isn't installed, and wirefilter has"
                f" no {', '.join(lacks)}"
            )
        warning = (
            f"{self.name}: vde-netemu (vde-netemu) isn't installed:"
            " wirefilter runs in its place"
        )
        return path, warning

    def command(self, prepared: Prepared) -> Command:
        config = self.config
        path, warning = self.program(prepared.vde)
        cmd = Command(path)
        if warning is not None:
            cmd.warn(warning)
        left, right = (socket_path(plug) for plug in self.plugs)
        # -v splits its value at the first colon, that of ptp:// on the left
        if "://" in left:
            raise errors.BadConfigError(
                f"{self.name}: the socket card of a machine can only be the"
                " right end of a Netemu (endpoints)"
            )
        cmd.option("-v", f"{left}:{right}")
        # each value both ways, or left to right (LR) and right to left (RL)
        for option, value, reverse, symmetric in (
            (
                "-b",
                config.bandwidth,
                config.bandwidth_right_to_left,
                config.bandwidth_symmetric,
            ),
            (
                "-d",
                config.delay,
                config.delay_right_to_left,
                config.delay_symmetric,
            ),
            (
                "-c",
                config.buffer_size,
                config.buffer_size_right_to_left,
                config.buffer_size_symmetric,
            ),
            (
                "-l",
                config.loss,
                config.loss_right_to_left,
                config.loss_symmetric,
            ),
        ):
            if symmetric:
                cmd.option(option, value)
            else:
                cmd.option(option, f"LR {value}")
                cmd.option(option, f"RL {reverse}")
        cmd.arg("--nofifo")
        cmd.option("-M", self.console())
        return cmd

    def update_config(self, changes: dict[str, object]) -> None:
        self._set(
            changes,
            "buffer_size_symmetric",
            "buffer_size",
            "buffer_size_right_to_left",
        )
        self._set(changes, "delay_symmetric", "delay", "delay_right_to_left")
        self._set(
            changes,
            "bandwidth_symmetric",
            "bandwidth",
            "bandwidth_right_to_left",
        )
        self._set(changes, "loss_symmetric", "loss", "loss_right_to_left")
        Wire.update_config(self, changes)
        # the events belong to the brick, so every state has the same ones
        for name in BRICK_KEYS:
            value = getattr(self.config, name)
            for state in self.markov_manager.states:
                setattr(state, name, value)

    def _set(
        self,
        attrs: dict[str, object],
        symm: str,
        left_to_right: str,
        right_to_left: str,
    ) -> None:
        if symm in attrs and attrs[symm] != getattr(self.config, symm):
            if left_to_right in attrs:
                setattr(self.config, left_to_right, attrs.pop(left_to_right))
            if right_to_left in attrs:
                setattr(self.config, right_to_left, attrs.pop(right_to_left))

    def rename_references(self, target: str, old: str, new: str) -> bool:
        changed = False
        for state in self.markov_manager.states:
            if rename_references(state, target, old, new):
                changed = True
        return changed

    def config_table(self) -> Table:
        table = dump_record(self.config, exclude=STATE_KEYS)
        table["transition_period"] = self.transPeriod
        table["transitions"] = [
            [float(weight) for weight in row]
            for row in self.markov_manager.weights
        ]
        table["states"] = [
            dump_record(state, exclude=BRICK_KEYS)
            for state in self.markov_manager.states
        ]
        return table

    @classmethod
    def table_notes(cls, table: Table) -> Notes:
        return notes(NetemuTable, table)

    def load_config_table(
        self, table: Table, report: Report, where: str, ignore: Collection[str]
    ) -> None:
        data = load_record(NetemuTable, table, report, where, ignore=ignore)
        states = data.states
        # the states are read without the events, which are the brick's
        for state in states:
            for name in BRICK_KEYS:
                setattr(state, name, getattr(data, name))
        size = len(states)
        weights = data.transitions
        if len(weights) != size or any(len(row) != size for row in weights):
            report.warning(
                f"is not a {size}×{size} matrix, using zeros",
                f"{where}.transitions",
            )
            weights = [[0.0] * size for _ in range(size)]
        self.markov_manager = MarkovConfig(states[0])
        self.markov_manager.states = states
        self.markov_manager.weights = weights
        self.transPeriod = data.transition_period
        self.currentState = self.startupState = 0
        self.config = states[0]

    # the set functions in base.py and wires.py are not suitable anymore for communicating with the emulator
    def update(self) -> None:
        if not self.is_running():
            return

        # state attributes

        self._update("numnodes", len(self.markov_manager.states))

        currentState = self.currentState

        for i, state in enumerate(self.markov_manager.states):
            self.currentState = i
            self.config = self.markov_manager.states[self.currentState]
            for name, value in field_values(state).items():
                self._update(name, value)

        self.currentState = currentState
        self.config = self.markov_manager.states[self.currentState]

        # weight attributes

        for i, weight0 in enumerate(self.markov_manager.weights):
            for j, value in enumerate(weight0):
                self._update("weight", value, i, j)

        # other attributes

        self._update("time", self.transPeriod)

        self.changed.notify(self)

    # utility function with logging like in base.py
    def _update(self, name: str, value: object, *args: int) -> None:
        attribute_set = (
            "Attribute {attr} set in {brick} with value " "{value}."
        )

        self.logger.info(attribute_set, attr=name, brick=self, value=value)
        setter = getattr(self, "cbset_" + name, None)
        if setter:
            setter(*args, value)

    # callbacks for live-management

    def cbset_numnodes(self, value: int) -> None:
        self.send(b"markov-numnodes %d\n" % (value))

    def cbset_weight(self, stateFrom: int, stateTo: int, value: float) -> None:
        self.send(b"setedge %d,%d,%f\n" % (stateFrom, stateTo, value))

    def cbset_time(self, value: int) -> None:
        self.send(b"markov-time %d\n" % (value))

    def cbset_name(self, value: str) -> None:
        self.send(
            b"markov-name %d,%b\n" % (self.currentState, value.encode("UTF-8"))
        )

    def cbset_buffer_size(self, value: int) -> None:
        if self.config.buffer_size_symmetric:
            self.send(b"chanbufsize %d[%d]\n" % (value, self.currentState))
        else:
            self.send(b"chanbufsize LR %d[%d]\n" % (value, self.currentState))

    def cbset_buffer_size_right_to_left(self, value: int) -> None:
        if not self.config.buffer_size_symmetric:
            self.send(b"chanbufsize RL %d[%d]\n" % (value, self.currentState))

    def cbset_buffer_size_symmetric(self, value: bool) -> None:
        self.cbset_buffer_size(self.config.buffer_size)
        self.cbset_buffer_size_right_to_left(
            self.config.buffer_size_right_to_left
        )

    def cbset_delay(self, value: int) -> None:
        if self.config.delay_symmetric:
            self.send(b"delay %d[%d]\n" % (value, self.currentState))
        else:
            self.send(b"delay LR %d[%d]\n" % (value, self.currentState))

    def cbset_delay_right_to_left(self, value: int) -> None:
        if not self.config.delay_symmetric:
            self.send(b"delay RL %d[%d]\n" % (value, self.currentState))

    def cbset_delay_symmetric(self, value: bool) -> None:
        self.cbset_delay(self.config.delay)
        self.cbset_delay_right_to_left(self.config.delay_right_to_left)

    def cbset_loss(self, value: float) -> None:
        if self.config.loss_symmetric:
            self.send(b"loss %f[%d]\n" % (value, self.currentState))
        else:
            self.send(b"loss LR %f[%d]\n" % (value, self.currentState))

    def cbset_loss_right_to_left(self, value: float) -> None:
        if not self.config.loss_symmetric:
            self.send(b"loss RL %f[%d]\n" % (value, self.currentState))

    def cbset_loss_symmetric(self, value: bool) -> None:
        self.cbset_loss(self.config.loss)
        self.cbset_loss_right_to_left(self.config.loss_right_to_left)

    def cbset_bandwidth(self, value: int) -> None:
        if self.config.bandwidth_symmetric:
            self.send(b"bandwidth %d[%d]\n" % (value, self.currentState))
        else:
            self.send(b"bandwidth LR %d[%d]\n" % (value, self.currentState))

    def cbset_bandwidth_right_to_left(self, value: int) -> None:
        if not self.config.bandwidth_symmetric:
            self.send(b"bandwidth RL %d[%d]\n" % (value, self.currentState))

    def cbset_bandwidth_symmetric(self, value: bool) -> None:
        self.cbset_bandwidth(self.config.bandwidth)
        self.cbset_bandwidth_right_to_left(self.config.bandwidth_right_to_left)
