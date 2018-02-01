# -*- test-case-name: virtualbricks.tests.test_wires -*-
# Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
# Copyright (C) 2018 Virtualbricks team

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

from virtualbricks import bricks
from virtualbricks._spawn import abspath_vde

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

class NetemuConfig(bricks.Config):

    parameters = {
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


class WFProcessProtocol(bricks.VDEProcessProtocol):

    prompt = re.compile(r"^VDEwf\$ ", re.M)


class Netemu(Wire):

    type = "Netemu"
    config_factory = NetemuConfig
    process_protocol = WFProcessProtocol

    def __init__(self, factory, name):
        Wire.__init__(self, factory, name)
        self.command_builder = {
            "--nofifo": lambda: "*",
            "-M": self.console,
        }

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

    def prog(self):
        return "vde-netemu"

    def set(self, attrs):
        self._set(attrs, "chanbufsizesymm", "chanbufsize", "chanbufsizer")
        self._set(attrs, "delaysymm", "delay", "delayr")
        self._set(attrs, "bandwidthsymm", "bandwidth", "bandwidthr")
        self._set(attrs, "losssymm", "loss", "lossr")
        Wire.set(self, attrs)

    def _set(self, attrs, symm, left_to_right, right_to_left):
        if symm in attrs and attrs[symm] != self.config[symm]:
            if left_to_right in attrs:
                self.config[left_to_right] = attrs.pop(left_to_right)
            if right_to_left in attrs:
                self.config[right_to_left] = attrs.pop(right_to_left)

    # callbacks for live-management

    def cbset_chanbufsize(self, value):
        if self.config["chanbufsizesymm"]:
            self.send("chanbufsize {0}\n".format(value))
        else:
            self.send("chanbufsize LR {0}\n".format(value))

    def cbset_chanbufsizer(self, value):
        if not self.config["chanbufsizesymm"]:
            self.send("chanbufsize RL {0}\n".format(value))

    def cbset_chanbufsizesymm(self, value):
        self.cbset_chanbufsize(self.config["chanbufsize"])
        self.cbset_chanbufsizer(self.config["chanbufsizer"])

    def cbset_delay(self, value):
        if self.config["delaysymm"]:
            self.send("delay {0}\n".format(value))
        else:
            self.send("delay LR {0}\n".format(value))

    def cbset_delayr(self, value):
        if not self.config["delaysymm"]:
            self.send("delay RL {0}\n".format(value))

    def cbset_delaysymm(self, value):
        self.cbset_delay(self.config["delay"])
        self.cbset_delayr(self.config["delayr"])

    def cbset_loss(self, value):
        if self.config["losssymm"]:
            self.send("loss {0}\n".format(value))
        else:
            self.send("loss LR {0}\n".format(value))

    def cbset_lossr(self, value):
        if not self.config["losssymm"]:
            self.send("loss RL {0}\n".format(value))

    def cbset_losssymm(self, value):
        self.cbset_loss(self.config["loss"])
        self.cbset_lossr(self.config["lossr"])

    def cbset_bandwidth(self, value):
        if self.config["bandwidthsymm"]:
            self.send("bandwidth {0}\n".format(value))
        else:
            self.send("bandwidth LR {0}\n".format(value))

    def cbset_bandwidthr(self, value):
        if not self.config["bandwidthsymm"]:
            self.send("bandwidth RL {0}\n".format(value))

    def cbset_bandwidthsymm(self, value):
        self.cbset_bandwidth(self.config["bandwidth"])
        self.cbset_bandwidthr(self.config["bandwidthr"])
