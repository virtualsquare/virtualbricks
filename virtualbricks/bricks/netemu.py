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

import re

from virtualbricks import bricks, config
from virtualbricks.bricks.wire import Wire
from virtualbricks.config import Bool, Float, Int, ListOf, Record, Str


@config.define
class NetemuConfig(bricks.BrickConfig):
    """
    The configuration of a Netemu: its events and a state of its Markov chain.

    Each state is a NetemuConfig, and every state has the events of the brick.
    The config of the brick is its current state. In the project file the
    events are keys of the brick and the states are tables without them.
    """

    name = config.field(Str(), default="default name")
    bandwidth = config.field(Int(), default=125000)
    bandwidthr = config.field(Int(), default=125000)
    bandwidthsymm = config.field(Bool(), default=True)
    delay = config.field(Int(), default=0)
    delayr = config.field(Int(), default=0)
    delaysymm = config.field(Bool(), default=True)
    chanbufsize = config.field(Int(), default=75000)
    chanbufsizer = config.field(Int(), default=75000)
    chanbufsizesymm = config.field(Bool(), default=True)
    loss = config.field(Float(0, 100), default=0.0)
    lossr = config.field(Float(0, 100), default=0.0)
    losssymm = config.field(Bool(), default=True)


BRICK_KEYS = frozenset(config.names(bricks.BrickConfig))
# The keys of a state in the project file.
STATE_KEYS = frozenset(config.names(NetemuConfig)) - BRICK_KEYS


@config.define
class NetemuTable(bricks.BrickConfig):
    """The table of a Netemu in the project file."""

    transperiod = config.field(Int(1), default=100)
    transitions = config.field(
        ListOf(ListOf(Float(0))), factory=lambda: [[0.0]]
    )
    states = config.field(
        ListOf(Record(NetemuConfig, exclude=BRICK_KEYS), min_length=1),
        factory=lambda: [NetemuConfig()],
    )


# Each channel emulator has its instance of this manager class
class MarkovConfig:

    # calling __init__ with the current active config (Netemu.config) will link it to state nr. 0
    def __init__(self, config):
        self.states = list()
        self.weights = list()
        self.weights.append(list())
        self.weights[0].append(0.0)
        self.states.append(config)

    # append a new state with default config at the end of the state list
    # all weights to and from the new state are 0 by default
    def add(self, index):
        # the events belong to the brick, so every state has the same ones
        new = NetemuConfig(
            pon_vbevent=self.states[0].pon_vbevent,
            poff_vbevent=self.states[0].poff_vbevent,
        )
        length = len(self.states)
        self.weights.insert(index, list())

        unavailable = []
        defaultOccupied = False
        defaultName = config.default(NetemuConfig, "name")

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
    def remove(self, index):
        if len(self.states) == 1:
            return

        del self.weights[index]

        for weight in self.weights:
            del weight[index]

        del self.states[index]


class WFProcessProtocol(bricks.VDEProcessProtocol):

    prompt = re.compile(rb"^VDEwf\$ ", re.M)


class Netemu(Wire):

    type = "Netemu"
    config_factory = NetemuConfig
    process_protocol = WFProcessProtocol

    def __init__(self, factory, name):
        Wire.__init__(self, factory, name)
        self.markov_manager = MarkovConfig(self.config)
        self.currentState = (
            0  # used for GUI updating and communicating to Netemu
        )
        self.startupState = 0  # the state the emulator will start into
        self.transPeriod = 100  # default value for Netemu
        self.command_builder = {
            "--nofifo": lambda: "*",
            "-M": self.console,
        }

    def poweron(self):
        d = bricks.Brick.poweron(self)
        self.currentState = self.startupState
        self.config = self.markov_manager.states[self.currentState]
        self.update()
        return d

    def args(self):
        res = [
            self.prog(),
            "-v",
            self.plugs[0].sock.path.rstrip("[]")
            + ":"
            + self.plugs[1].sock.path.rstrip("[]"),
        ]

        # Bandwidth
        if self.config.bandwidthsymm:
            res.extend(["-b", str(self.config.bandwidth)])
        else:
            res.extend(["-b", "LR {0}".format(self.config.bandwidth)])
            res.extend(["-b", "RL {0}".format(self.config.bandwidthr)])

        # Delay
        if self.config.delaysymm:
            res.extend(["-d", str(self.config.delay)])
        else:
            res.extend(["-d", "LR {0}".format(self.config.delay)])
            res.extend(["-d", "RL {0}".format(self.config.delayr)])

        # Chanbufsize
        if self.config.chanbufsizesymm:
            res.extend(["-c", str(self.config.chanbufsize)])
        else:
            res.extend(["-c", "LR {0}".format(self.config.chanbufsize)])
            res.extend(["-c", "RL {0}".format(self.config.chanbufsizer)])

        # Loss
        if self.config.losssymm:
            res.extend(["-l", str(self.config.loss)])
        else:
            res.extend(["-l", "LR {0}".format(self.config.loss)])
            res.extend(["-l", "RL {0}".format(self.config.lossr)])

        res.extend(bricks.Brick.build_cmd_line(self))
        return res

    def init_markov(self):
        self.markov_manager = MarkovConfig(self.config)

    def prog(self):
        return "vde-netemu"

    def set(self, attrs):
        self._set(attrs, "chanbufsizesymm", "chanbufsize", "chanbufsizer")
        self._set(attrs, "delaysymm", "delay", "delayr")
        self._set(attrs, "bandwidthsymm", "bandwidth", "bandwidthr")
        self._set(attrs, "losssymm", "loss", "lossr")
        Wire.set(self, attrs)
        # the events belong to the brick, so every state has the same ones
        for name in BRICK_KEYS:
            value = getattr(self.config, name)
            for state in self.markov_manager.states:
                setattr(state, name, value)

    def _set(self, attrs, symm, left_to_right, right_to_left):
        if symm in attrs and attrs[symm] != getattr(self.config, symm):
            if left_to_right in attrs:
                setattr(self.config, left_to_right, attrs.pop(left_to_right))
            if right_to_left in attrs:
                setattr(self.config, right_to_left, attrs.pop(right_to_left))

    def rename_references(self, target, old, new):
        changed = False
        for state in self.markov_manager.states:
            if config.rename_references(state, target, old, new):
                changed = True
        return changed

    def config_table(self):
        table = config.dump_record(self.config, exclude=STATE_KEYS)
        table["transperiod"] = self.transPeriod
        table["transitions"] = [
            [float(weight) for weight in row]
            for row in self.markov_manager.weights
        ]
        table["states"] = [
            config.dump_record(state, exclude=BRICK_KEYS)
            for state in self.markov_manager.states
        ]
        return table

    def load_config_table(self, table, report, where, ignore):
        data = config.load_record(
            NetemuTable, table, report, where, ignore=ignore
        )
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
        self.transPeriod = data.transperiod
        self.currentState = self.startupState = 0
        self.config = states[0]

    # the set functions in base.py and wires.py are not suitable anymore for communicating with the emulator
    def update(self):
        if self.proc is None:
            return

        # state attributes

        self._update("numnodes", len(self.markov_manager.states))

        currentState = self.currentState

        for i, state in enumerate(self.markov_manager.states):
            self.currentState = i
            self.config = self.markov_manager.states[self.currentState]
            for name, value in config.values(state).items():
                self._update(name, value)

        self.currentState = currentState
        self.config = self.markov_manager.states[self.currentState]

        # weight attributes

        for i, weight0 in enumerate(self.markov_manager.weights):
            for j, value in enumerate(weight0):
                self._update("weight", value, i, j)

        # other attributes

        self._update("time", self.transPeriod)

        self.notify_changed()

    # utility function with logging like in base.py
    def _update(self, name, value, *args):
        attribute_set = (
            "Attribute {attr} set in {brick} with value " "{value}."
        )

        self.logger.info(attribute_set, attr=name, brick=self, value=value)
        setter = getattr(self, "cbset_" + name, None)
        if setter:
            setter(*args, value)

    # callbacks for live-management

    def cbset_numnodes(self, value):
        self.send(b"markov-numnodes %d\n" % (value))

    def cbset_weight(self, stateFrom, stateTo, value):
        self.send(b"setedge %d,%d,%f\n" % (stateFrom, stateTo, value))

    def cbset_time(self, value):
        self.send(b"markov-time %d\n" % (value))

    def cbset_name(self, value):
        self.send(
            b"markov-name %d,%b\n" % (self.currentState, value.encode("UTF-8"))
        )

    def cbset_chanbufsize(self, value):
        if self.config.chanbufsizesymm:
            self.send(b"chanbufsize %d[%d]\n" % (value, self.currentState))
        else:
            self.send(b"chanbufsize LR %d[%d]\n" % (value, self.currentState))

    def cbset_chanbufsizer(self, value):
        if not self.config.chanbufsizesymm:
            self.send(b"chanbufsize RL %d[%d]\n" % (value, self.currentState))

    def cbset_chanbufsizesymm(self, value):
        self.cbset_chanbufsize(self.config.chanbufsize)
        self.cbset_chanbufsizer(self.config.chanbufsizer)

    def cbset_delay(self, value):
        if self.config.delaysymm:
            self.send(b"delay %d[%d]\n" % (value, self.currentState))
        else:
            self.send(b"delay LR %d[%d]\n" % (value, self.currentState))

    def cbset_delayr(self, value):
        if not self.config.delaysymm:
            self.send(b"delay RL %d[%d]\n" % (value, self.currentState))

    def cbset_delaysymm(self, value):
        self.cbset_delay(self.config.delay)
        self.cbset_delayr(self.config.delayr)

    def cbset_loss(self, value):
        if self.config.losssymm:
            self.send(b"loss %f[%d]\n" % (value, self.currentState))
        else:
            self.send(b"loss LR %f[%d]\n" % (value, self.currentState))

    def cbset_lossr(self, value):
        if not self.config.losssymm:
            self.send(b"loss RL %f[%d]\n" % (value, self.currentState))

    def cbset_losssymm(self, value):
        self.cbset_loss(self.config.loss)
        self.cbset_lossr(self.config.lossr)

    def cbset_bandwidth(self, value):
        if self.config.bandwidthsymm:
            self.send(b"bandwidth %d[%d]\n" % (value, self.currentState))
        else:
            self.send(b"bandwidth LR %d[%d]\n" % (value, self.currentState))

    def cbset_bandwidthr(self, value):
        if not self.config.bandwidthsymm:
            self.send(b"bandwidth RL %d[%d]\n" % (value, self.currentState))

    def cbset_bandwidthsymm(self, value):
        self.cbset_bandwidth(self.config.bandwidth)
        self.cbset_bandwidthr(self.config.bandwidthr)
