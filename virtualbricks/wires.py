# -*- test-case-name: virtualbricks.tests.test_wires -*-
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

import re

from virtualbricks import bricks, log
from virtualbricks.spawn import abspath_vde

if False:  # pyflakes
    _ = str


class Wire(bricks.Brick):

    type = "Wire"

    def __init__(self, factory, name):
        bricks.Brick.__init__(self, factory, name)
        self.plugs.append(factory.new_plug(self))
        self.plugs.append(factory.new_plug(self))

    def get_parameters(self):
        p0 = _("disconnected")
        p1 = _("disconnected")
        if len(self.plugs) == 2:
            if self.plugs[0].sock:
                p0 = self.plugs[0].sock.brick.name
            if self.plugs[1].sock:
                p1 = self.plugs[1].sock.brick.name
            if p0 != _('disconnected') and p1 != _('disconnected'):
                return _("Configured to connect {0} to {1}").format(p0, p1)
        elif len(self.plugs) == 1:
            if self.plugs[0].sock:
                p0 = self.plugs[0].sock.brick.name
            return _("Configured to connect {0} to {1}").format(p0, p1)
        return _("Not yet configured. Left plug is {0} and right plug is {1}"
                ).format(p0, p1)

    def configured(self):
        return len(self.plugs) == 2 and all(map(lambda p: p.sock, self.plugs))

    def prog(self):
        return abspath_vde('dpipe'),

    def args(self):
        return [self.prog(),
                abspath_vde('vde_plug'),
                # XXX: this is awful
                self.plugs[0].sock.path.rstrip('[]'), "=",
                abspath_vde('vde_plug'),
                self.plugs[1].sock.path.rstrip('[]')]

# these parameters no longer represent the only configuration Netemu has, but rather the highlighted configuration such that other functions can still be used
class NetemuConfig(bricks.Config):

    parameters = {
        "name": bricks.String("default name"),
        "bandwidth": bricks.Integer(125000),
        "bandwidthr": bricks.Integer(125000),
        "bandwidthsymm": bricks.Boolean(True),

        "delay": bricks.Integer(0),
        "delayr": bricks.Integer(0),
        "delaysymm": bricks.Boolean(True),

        "chanbufsize": bricks.Integer(75000),
        "chanbufsizer": bricks.Integer(75000),
        "chanbufsizesymm": bricks.Boolean(True),

        "loss": bricks.SpinFloat(0, 0, 100),
        "lossr": bricks.SpinFloat(0, 0, 100),
        "losssymm": bricks.Boolean(True),
    }

# Each channel emulator has its instance of this manager class
class MarkovConfig():

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
        new = NetemuConfig() # create a new config instance for each state
        length = len(self.states)
        self.weights.insert(index, list())

        unavailable = []
        defaultOccupied = False
        defaultName = NetemuConfig.parameters["name"].default

        for i, state in enumerate(self.states):
            self.weights[i].insert(index, 0.0)
            self.weights[index].append(0.0)

            # default naming of each state uses the default name + a positive integer at the end (e.g. default name 0, default name 1...)
            if state["name"].startswith(defaultName):
                args = state["name"].split(" ")
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
                new["name"] += " " + str(i)
                self.states.insert(index, new)
                return
            
        new["name"] += " " + str(len(unavailable))
        self.states.insert(index, new)

    # delete a state and all weights from and to the state
    def remove(self, index):
        if len(self.states) == 1:
            return
        
        del(self.weights[index])

        for weight in self.weights:
            del(weight[index])

        del(self.states[index])

class WFProcessProtocol(bricks.VDEProcessProtocol):

    prompt = re.compile(rb"^VDEwf\$ ", re.M)


class Netemu(Wire):

    type = "Netemu"
    config_factory = NetemuConfig
    process_protocol = WFProcessProtocol

    def __init__(self, factory, name):
        Wire.__init__(self, factory, name)
        self.markov_manager = None # don't know what the default config is yet....
        self.currentState = 0      # used for GUI updating and communicating to Netemu
        self.startupState = 0      # the state the emulator will start into
        self.transPeriod = 100     # default value for Netemu
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
        res = [self.prog(), "-v", self.plugs[0].sock.path.rstrip('[]') + ":" +
               self.plugs[1].sock.path.rstrip('[]')]

        # Bandwidth
        if self.config["bandwidthsymm"]:
            res.extend(["-b", str(self.config["bandwidth"])])
        else:
            res.extend(["-b", "LR {0}".format(self.config["bandwidth"])])
            res.extend(["-b", "RL {0}".format(self.config["bandwidthr"])])

        # Delay
        if self.config["delaysymm"]:
            res.extend(["-d", str(self.config["delay"])])
        else:
            res.extend(["-d", "LR {0}".format(self.config["delay"])])
            res.extend(["-d", "RL {0}".format(self.config["delayr"])])

        # Chanbufsize
        if self.config["chanbufsizesymm"]:
            res.extend(["-c", str(self.config["chanbufsize"])])
        else:
            res.extend(["-c", "LR {0}".format(self.config["chanbufsize"])])
            res.extend(["-c", "RL {0}".format(self.config["chanbufsizer"])])

        # Loss
        if self.config["losssymm"]:
            res.extend(["-l", str(self.config["loss"])])
        else:
            res.extend(["-l", "LR {0}".format(self.config["loss"])])
            res.extend(["-l", "RL {0}".format(self.config["lossr"])])

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

        # this is called while reading the save file which always reads at least 1 state 
        if self.markov_manager is None:
            self.init_markov()

    def _set(self, attrs, symm, left_to_right, right_to_left):
        if symm in attrs and attrs[symm] != self.config[symm]:
            if left_to_right in attrs:
                self.config[left_to_right] = attrs.pop(left_to_right)
            if right_to_left in attrs:
                self.config[right_to_left] = attrs.pop(right_to_left)

    # the set functions in base.py and wires.py are not suitable anymore for communicating with the emulator  
    def update(self):
        if self.proc is None:
            return
        
        # state attributes
        
        self._update("numnodes", len(self.markov_manager.states))

        currentState = self.currentState
        
        for i, state in enumerate(self.markov_manager.states):
            self.currentState = i
            for name, value in state.items():
                self._update(name, value)
        
        self.currentState = currentState

        # weight attributes

        for i, weight0 in enumerate(self.markov_manager.weights):
            for j, value in enumerate(weight0):
                self._update("weight", value, i, j)

        # other attributes

        self._update("time", self.transPeriod)

        self.notify_changed()

    # utility function with logging like in base.py
    def _update(self, name, value, *args):
        attribute_set = log.Event("Attribute {attr} set in {brick} with value ""{value}.")

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
        self.send(b"markov-name %d,%b\n" % (self.currentState, value.encode('UTF-8')))

    def cbset_chanbufsize(self, value):
        if self.config["chanbufsizesymm"]:
            self.send(b"chanbufsize %d[%d]\n" % (value, self.currentState))
        else:
            self.send(b"chanbufsize LR %d[%d]\n" % (value, self.currentState))

    def cbset_chanbufsizer(self, value):
        if not self.config["chanbufsizesymm"]:
            self.send(b"chanbufsize RL %d[%d]\n" % (value, self.currentState))

    def cbset_chanbufsizesymm(self, value):
        self.cbset_chanbufsize(self.config["chanbufsize"])
        self.cbset_chanbufsizer(self.config["chanbufsizer"])

    def cbset_delay(self, value):
        if self.config["delaysymm"]:
            self.send(b"delay %d[%d]\n" % (value, self.currentState))
        else:
            self.send(b"delay LR %d[%d]\n" % (value, self.currentState))

    def cbset_delayr(self, value):
        if not self.config["delaysymm"]:
            self.send(b"delay RL %d[%d]\n" % (value, self.currentState))

    def cbset_delaysymm(self, value):
        self.cbset_delay(self.config["delay"])
        self.cbset_delayr(self.config["delayr"])

    def cbset_loss(self, value):
        if self.config["losssymm"]:
            self.send(b"loss %f[%d]\n" % (value, self.currentState))
        else:
            self.send(b"loss LR %f[%d]\n" % (value, self.currentState))

    def cbset_lossr(self, value):
        if not self.config["losssymm"]:
            self.send(b"loss RL %f[%d]\n" % (value, self.currentState))

    def cbset_losssymm(self, value):
        self.cbset_loss(self.config["loss"])
        self.cbset_lossr(self.config["lossr"])

    def cbset_bandwidth(self, value):
        if self.config["bandwidthsymm"]:
            self.send(b"bandwidth %d[%d]\n" % (value, self.currentState))
        else:
            self.send(b"bandwidth LR %d[%d]\n" % (value, self.currentState))

    def cbset_bandwidthr(self, value):
        if not self.config["bandwidthsymm"]:
            self.send(b"bandwidth RL %d[%d]\n" % (value, self.currentState))

    def cbset_bandwidthsymm(self, value):
        self.cbset_bandwidth(self.config["bandwidth"])
        self.cbset_bandwidthr(self.config["bandwidthr"])

    # custom save and load functions to keep the information about all states, weights and time step without breaking compatibility with older versions
    # all fields are saved if different from their default values
    # in case of multiple states, state 0 fields will appear duplicated

    def save_to(self, fileobj):
        opt_tmp = "{0}={1}"
        new_opt_tmp = "state{0}.{1}"
        double_opt_tmp = "{0}[{1}]"

        fileobj.write("#Syntax used by the old versions (only one state);\nAdded for backwards compatibility only\n")

        l = []
        for name, param in sorted(self.markov_manager.states[0].parameters.items()):
            if name != "name" and self.markov_manager.states[0][name] != param.default:
                value = param.to_string_brick(self.markov_manager.states[0][name], self)
                l.append(opt_tmp.format(name, value))
        tmp = "[{0}:{1}]\n{2}\n"
        fileobj.write(tmp.format(self.get_type(), self.name, "\n".join(l)))

        if len(self.markov_manager.states) == 1:
            fileobj.write("\n")
            return
        
        fileobj.write("- #Syntax used by newer versions\n")
        fileobj.write(opt_tmp.format("states", len(self.markov_manager.states)))
        fileobj.write("\n")

        for i, state in enumerate(self.markov_manager.states):
            l = []
            for name, param in sorted(state.parameters.items()):
                if state[name] != param.default:
                    value = param.to_string_brick(state[name], self)
                    l.append(opt_tmp.format(new_opt_tmp.format(i, name), value))
            
            for j, weight in enumerate(self.markov_manager.weights[i]):
                if j != i and weight != 0:
                    l.append(opt_tmp.format(new_opt_tmp.format(i, double_opt_tmp.format("probability", j)), weight))

            l.append("")
            fileobj.write("\n".join(l))
        
        if self.transPeriod != 100:
            fileobj.write(opt_tmp.format("transperiod", self.transPeriod))
        fileobj.write("\n\n")

    def load_from(self, section):

        # first state

        done = False
        curpos = section.fileobj.tell()
        line = section.fileobj.readline()
        cfg = {}
        while not done and line:
            if line.startswith("#") or section.EMPTY.match(line):
                curpos = section.fileobj.tell()
                line = section.fileobj.readline()
                continue # ...
            match = section.CONFIG_LINE.match(line)
            if match:
                name, value = match.groups()
                if value is None:
                    # value is None when the parameter is not set
                    value = ""
                if self.config.parameters.get(name):
                    cfg[name] = self._getvalue(name, value)
                curpos = section.fileobj.tell()
                line = section.fileobj.readline()
            else:
                self.set(cfg)
                if not line.startswith("-"):
                    section.fileobj.seek(curpos)
                    self.config = self.markov_manager.states[0]
                    return
                
                done = True

        errorMsg = log.Event("Error parsing argument {arg}, {exception}.")            
        cfg = {}
        line = section.fileobj.readline()
        curpos = section.fileobj.tell()
        STATE_LINE = re.compile(r"^state([0-9]+)\.(\w+)\s*=\s*(.*)$")
        DOUBLE_STATE_LINE = re.compile(r"^state([0-9]+)\.(\w+)\[([0-9]+)\]\s*=\s*(.*)$")

        while line:
            if line.startswith("#") or section.EMPTY.match(line):
                curpos = section.fileobj.tell()
                line = section.fileobj.readline()
                continue # ...

            match = DOUBLE_STATE_LINE.match(line)
            if match:
                state, name, stateTo, value = match.groups()
                if state.isnumeric() and stateTo.isnumeric():
                    if value is None:
                        # value is None when the parameter is not set
                        value = ""
                    try:
                        if name == "probability" and max(int(state), int(stateTo)) < len(self.markov_manager.states) and int(state) != int(stateTo):
                            self.markov_manager.weights[int(state)][int(stateTo)] = float(value)    
                    except ValueError:
                        self.logger.error(errorMsg, arg="state" + state + "." + name, exception="Value Error")
                curpos = section.fileobj.tell()
                line = section.fileobj.readline()

            else:
                match = STATE_LINE.match(line)
                if match:
                    state, name, value = match.groups()
                    if state.isnumeric():
                        if value is None:
                            # value is None when the parameter is not set
                            value = ""
                        try:
                            if int(state) < len(self.markov_manager.states) and self.config.parameters.get(name):
                                self.markov_manager.states[int(state)][name] = self._getvalue(name, value)
                        except ValueError:
                            self.logger.error(errorMsg, arg="state" + state + "." + name, exception="Value Error")
                    curpos = section.fileobj.tell()
                    line = section.fileobj.readline()

                else:
                    match = section.CONFIG_LINE.match(line)
                    if match:
                        name, value = match.groups()
                        if value is None:
                            # value is None when the parameter is not set
                            value = ""
                        try:
                            if name.startswith("states") and value.isnumeric():
                                for i in range(len(self.markov_manager.states), int(value)):
                                    self.markov_manager.add(i)
                                
                            elif name.startswith("transperiod") and value.isnumeric():
                                self.transPeriod = int(value)
                        except ValueError:
                            self.logger.error(errorMsg, arg="state" + state + "." + name, exception="Value Error")
                        
                        curpos = section.fileobj.tell()
                        line = section.fileobj.readline()
                    else:   
                        section.fileobj.seek(curpos)
                        self.config = self.markov_manager.states[0]
                        return

        self.config = self.markov_manager.states[0]