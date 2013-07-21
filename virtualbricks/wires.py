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

from virtualbricks import bricks, settings

if False:  # pyflakes
    _ = str


class Wire(bricks.Brick):

    type = "Wire"

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
        else:
            return _("Not yet configured. Left plug is {0} and right plug is "
                     "{1}").format(p0, p1)

    def configured(self):
        return len(self.plugs) == 2 and all(map(lambda p: p.sock, self.plugs))

    def prog(self):
        return os.path.join(settings.get("vdepath"), "dpipe")

    def args(self):
        return [self.prog(),
                os.path.join(settings.get("vdepath"), "vde_plug"),
                # XXX: this is awful
                self.plugs[0].sock.path.rstrip('[]'), "=",
                os.path.join(settings.get("vdepath"), "vde_plug"),
                self.plugs[1].sock.path.rstrip('[]')]

    def add_plug(self, sock, mac=None, model=None):
        if len(self.plugs) > 2:
            raise ValueError("Cannot add another plug, max reached.")
        plug = self.factory.new_plug(self)
        self.plugs.append(plug)
        plug.connect(sock)
        return plug


class WireFilterConfig(bricks.Config):

    parameters = {
        "bandwidthLR": bricks.String(""),
        "bandwidthRL": bricks.String(""),
        "bandwidth": bricks.String(""),
        "bandwidthLRJ": bricks.String(""),
        "bandwidthRLJ": bricks.String(""),
        "bandwidthJ": bricks.String(""),
        "bandwidthmult": bricks.String("Mega"),
        "bandwidthunit": bricks.String("bit/s"),
        "bandwidthdistribLR": bricks.String("Uniform"),
        "bandwidthdistribRL": bricks.String("Uniform"),
        "bandwidthdistrib": bricks.String("Uniform"),
        "bandwidthsymm": bricks.Boolean(True),

        "speedLR": bricks.String(""),
        "speedRL": bricks.String(""),
        "speed": bricks.String(""),
        "speedLRJ": bricks.String(""),
        "speedRLJ": bricks.String(""),
        "speedJ": bricks.String(""),
        "speedmult": bricks.String("Mega"),
        "speedunit": bricks.String("bit/s"),
        "speeddistribLR": bricks.String("Uniform"),
        "speeddistribRL": bricks.String("Uniform"),
        "speeddistrib": bricks.String("Uniform"),
        "speedsymm": bricks.Boolean(True),
        "speedenable": bricks.Boolean(False),

        "delayLR": bricks.String(""),
        "delayRL": bricks.String(""),
        "delay": bricks.String(""),
        "delayLRJ": bricks.String(""),
        "delayRLJ": bricks.String(""),
        "delayJ": bricks.String(""),
        "delaymult": bricks.String("milli"),
        "delayunit": bricks.String("seconds"),
        "delaydistribLR": bricks.String("Uniform"),
        "delaydistribRL": bricks.String("Uniform"),
        "delaydistrib": bricks.String("Uniform"),
        "delaysymm": bricks.Boolean(True),

        "chanbufsizeLR": bricks.String(""),
        "chanbufsizeRL": bricks.String(""),
        "chanbufsize": bricks.String(""),
        "chanbufsizeLRJ": bricks.String(""),
        "chanbufsizeRLJ": bricks.String(""),
        "chanbufsizeJ": bricks.String(""),
        "chanbufsizemult": bricks.String("Kilo"),
        "chanbufsizeunit": bricks.String("bytes"),
        "chanbufsizedistribLR": bricks.String("Uniform"),
        "chanbufsizedistribRL": bricks.String("Uniform"),
        "chanbufsizedistrib": bricks.String("Uniform"),
        "chanbufsizesymm": bricks.Boolean(True),

        "lossLR": bricks.String(""),
        "lossRL": bricks.String(""),
        "loss": bricks.String(""),
        "lossLRJ": bricks.String(""),
        "lossRLJ": bricks.String(""),
        "lossJ": bricks.String(""),
        "lossmult": bricks.String(""),
        "lossunit": bricks.String("%"),
        "lossdistribLR": bricks.String("Uniform"),
        "lossdistribRL": bricks.String("Uniform"),
        "lossdistrib": bricks.String("Uniform"),
        "losssymm": bricks.Boolean(True),

        "dupLR": bricks.String(""),
        "dupRL": bricks.String(""),
        "dup": bricks.String(""),
        "dupLRJ": bricks.String(""),
        "dupRLJ": bricks.String(""),
        "dupJ": bricks.String(""),
        "dupmult": bricks.String(""),
        "dupunit": bricks.String("%"),
        "dupdistribLR": bricks.String("Uniform"),
        "dupdistribRL": bricks.String("Uniform"),
        "dupdistrib": bricks.String("Uniform"),
        "dupsymm": bricks.Boolean(True),

        "noiseLR": bricks.String(""),
        "noiseRL": bricks.String(""),
        "noise": bricks.String(""),
        "noiseLRJ": bricks.String(""),
        "noiseRLJ": bricks.String(""),
        "noiseJ": bricks.String(""),
        "noisemult": bricks.String("Mega"),
        "noiseunit": bricks.String("bit"),
        "noisedistribLR": bricks.String("Uniform"),
        "noisedistribRL": bricks.String("Uniform"),
        "noisedistrib": bricks.String("Uniform"),
        "noisesymm": bricks.Boolean(True),

        "lostburstLR": bricks.String(""),
        "lostburstRL": bricks.String(""),
        "lostburst": bricks.String(""),
        "lostburstLRJ": bricks.String(""),
        "lostburstRLJ": bricks.String(""),
        "lostburstJ": bricks.String(""),
        "lostburstmult": bricks.String(""),
        "lostburstunit": bricks.String("seconds"),
        "lostburstdistribLR": bricks.String("Uniform"),
        "lostburstdistribRL": bricks.String("Uniform"),
        "lostburstdistrib": bricks.String("Uniform"),
        "lostburstsymm": bricks.Boolean(True),

        "mtuLR": bricks.String(""),
        "mtuRL": bricks.String(""),
        "mtu": bricks.String(""),
        "mtumult": bricks.String("Kilo"),
        "mtuunit": bricks.String("bytes"),
        "mtusymm": bricks.Boolean(True)
    }


class Wirefilter(Wire):

    type = "Wirefilter"
    config_factory = WireFilterConfig

    def __init__(self, factory, name):
        Wire.__init__(self, factory, name)
        self.command_builder = {
            "-N": "nofifo",
            "-M": self.console,
        }

    def args(self):
        res = []
        res.extend([self.prog(), "-v", self.plugs[0].sock.path.rstrip('[]') +
                    ":" + self.plugs[1].sock.path.rstrip('[]')])

        #Bandwidth
        if self.config["bandwidth"] and int(self.config["bandwidth"]) > 0:
            res.extend(["-b", self.compute_bandwidth()])
        else:
            if self.config["bandwidthLR"]:
                res.extend(["-b", "LR" + self.compute_bandwidthLR()])
            if self.config["bandwidthRL"]:
                res.extend(["-b", "RL" + self.compute_bandwidthRL()])

        #Speed
        if self.config["speed"] and int(self.config["speed"]) > 0:
            res.extend(["-s", self.compute_speed()])
        else:
            if self.config["speedLR"]:
                res.extend(["-s", "LR" + self.compute_speedLR()])
            if self.config["speedRL"]:
                res.extend(["-s", "RL" + self.compute_speedRL()])

        #Delay
        if self.config["delay"] and int(self.config["delay"]) > 0:
            res.extend(["-d", self.compute_delay()])
        else:
            if self.config["delayLR"]:
                res.extend(["-d", "LR" + self.compute_delayLR()])
            if self.config["delayRL"]:
                res.extend(["-d", "RL" + self.compute_delayRL()])

        #Chanbufsize
        if self.config["chanbufsize"] and int(self.config["chanbufsize"]) > 0:
            res.append("-c")
            value = self.compute_chanbufsize()
            res.append(value)
        else:
            if self.config["chanbufsizeLR"]:
                res.append("-c")
                value = self.compute_chanbufsizeLR()
                res.append("LR" + value)
            if self.config["chanbufsizeRL"]:
                res.append("-c")
                value = self.compute_chanbufsizeRL()
                res.append("RL" + value)

        #Loss
        if self.config["loss"] and int(self.config["loss"]) > 0:
            res.append("-l")
            value = self.compute_loss()
            res.append(value)
        else:
            if self.config["lossLR"]:
                res.append("-l")
                value = self.compute_lossLR()
                res.append("LR" + value)
            if self.config["lossRL"]:
                res.append("-l")
                value = self.compute_lossRL()
                res.append("RL" + value)

        #Dup
        if self.config["dup"] and int(self.config["dup"]) > 0:
            res.append("-D")
            value = self.compute_dup()
            res.append(value)
        else:
            if self.config["dupLR"]:
                res.append("-D")
                value = self.compute_dupLR()
                res.append("LR" + value)
            if self.config["dupRL"]:
                res.append("-D")
                value = self.compute_dupRL()
                res.append("RL" + value)

        #Noise
        if self.config["noise"] and int(self.config["noise"]) > 0:
            res.append("-n")
            value = self.compute_noise()
            res.append(value)
        else:
            if self.config["noiseLR"]:
                res.append("-n")
                value = self.compute_noiseLR()
                res.append("LR" + value)
            if self.config["noiseRL"]:
                res.append("-n")
                value = self.compute_noiseRL()
                res.append("RL" + value)

        #Lostburst
        if self.config["lostburst"] and int(self.config["lostburst"]) > 0:
            res.append("-L")
            value = self.compute_lostburst()
            res.append(value)
        else:
            if self.config["lostburstLR"]:
                res.append("-L")
                value = self.compute_lostburstLR()
                res.append("LR" + value)
            if self.config["lostburstRL"]:
                res.append("-L")
                value = self.compute_lostburstRL()
                res.append("RL" + value)

        #MTU
        if self.config["mtu"] and int(self.config["mtu"]) > 0:
            res.append("-m")
            value = self.compute_mtu()
            res.append(value)
        else:
            if self.config["mtuLR"]:
                res.append("-m")
                value = self.compute_mtuLR()
                res.append("LR" + value)
            if self.config["mtuRL"]:
                res.append("-m")
                value = self.compute_mtuRL()
                res.append("RL" + value)

        res.extend(bricks.Brick.build_cmd_line(self))
        return res

    def prog(self):
        return os.path.join(settings.get("vdepath"), "wirefilter")

    def gui_to_wf_value(self, base, jitter, distrib, mult, unit, def_mult="",
                        def_unit=""):
        if not base:
            return "0"

        if unit != def_unit:
            if def_unit.startswith("byte"):
                base = float(base) / 8
            else:
                base = float(base) * 8

        value = str(round(float(base), 6))  # f.e. 50

        if mult != def_mult:
            if mult is "milli" and def_mult is "":
                m = "K"
            else:
                m = mult[0]
        else:
            m = ""

        if jitter is not "":
            if def_unit is not "%":
                # GUI = 100K(+-)10% becomes WF = 100+20K
                j = str(round((float(base) * float(jitter) / 100), 6)) + m
            else:
                j = str(round(float(jitter), 6))

        if distrib and distrib[0] is ("G" or "N"):
            d = "N"
        else:
            d = "U"

        if jitter is not "":
            value = value + "+" + j  # f.e. 50+5K
            value = value + d  # f.e. 50+5KU/N
        else:
            value = value + m  # f.e. 50K

        return str(value)

    def compute_bandwidth(self):
        return self.gui_to_wf_value(self.config["bandwidth"],
                                    self.config["bandwidthJ"],
                                    self.config["bandwidthdistrib"],
                                    self.config["bandwidthmult"],
                                    self.config["bandwidthunit"],
                                    "", "byte/s")

    def compute_bandwidthLR(self):
        return self.gui_to_wf_value(self.config["bandwidthLR"],
                                    self.config["bandwidthLRJ"],
                                    self.config["bandwidthdistribLR"],
                                    self.config["bandwidthmult"],
                                    self.config["bandwidthunit"],
                                    "", "byte/s")

    def compute_bandwidthRL(self):
        return self.gui_to_wf_value(self.config["bandwidthRL"],
                                    self.config["bandwidthRLJ"],
                                    self.config["bandwidthdistribRL"],
                                    self.config["bandwidthmult"],
                                    self.config["bandwidthunit"],
                                    "", "byte/s")

    def compute_speed(self):
        return self.gui_to_wf_value(self.config["speed"],
                                    self.config["speedJ"],
                                    self.config["speeddistrib"],
                                    self.config["speedmult"],
                                    self.config["speedunit"],
                                    "", "byte/s")

    def compute_speedLR(self):
        return self.gui_to_wf_value(self.config["speedLR"],
                                    self.config["speedLRJ"],
                                    self.config["speeddistribLR"],
                                    self.config["speedmult"],
                                    self.config["speedunit"],
                                    "", "byte/s")

    def compute_speedRL(self):
        return self.gui_to_wf_value(self.config["speedRL"],
                                    self.config["speedRLJ"],
                                    self.config["speeddistribRL"],
                                    self.config["speedmult"],
                                    self.config["speedunit"],
                                    "", "byte/s")

    def compute_delay(self):
        return self.gui_to_wf_value(self.config["delay"],
                                    self.config["delayJ"],
                                    self.config["delaydistrib"],
                                    self.config["delaymult"],
                                    self.config["delayunit"],
                                    "milli", "seconds")

    def compute_delayLR(self):
        return self.gui_to_wf_value(self.config["delayLR"],
                                    self.config["delayLRJ"],
                                    self.config["delaydistribLR"],
                                    self.config["delaymult"],
                                    self.config["delayunit"],
                                    "milli", "seconds")

    def compute_delayRL(self):
        return self.gui_to_wf_value(self.config["delayRL"],
                                    self.config["delayRLJ"],
                                    self.config["delaydistribRL"],
                                    self.config["delaymult"],
                                    self.config["delayunit"],
                                    "milli", "seconds")

    def compute_chanbufsize(self):
        return self.gui_to_wf_value(self.config["chanbufsize"],
                                    self.config["chanbufsizeJ"],
                                    self.config["chanbufsizedistrib"],
                                    self.config["chanbufsizemult"],
                                    self.config["chanbufsizeunit"],
                                    "", "bytes")

    def compute_chanbufsizeLR(self):
        return self.gui_to_wf_value(self.config["chanbufsizeLR"],
                                    self.config["chanbufsizeLRJ"],
                                    self.config["chanbufsizedistribLR"],
                                    self.config["chanbufsizemult"],
                                    self.config["chanbufsizeunit"],
                                    "", "bytes")

    def compute_chanbufsizeRL(self):
        return self.gui_to_wf_value(self.config["chanbufsizeRL"],
                                    self.config["chanbufsizeRLJ"],
                                    self.config["chanbufsizedistribRL"],
                                    self.config["chanbufsizemult"],
                                    self.config["chanbufsizeunit"],
                                    "", "bytes")

    def compute_loss(self):
        return self.gui_to_wf_value(self.config["loss"],
                                    self.config["lossJ"],
                                    self.config["lossdistrib"],
                                    self.config["lossmult"],
                                    self.config["lossunit"],
                                    "", "%")

    def compute_lossLR(self):
        return self.gui_to_wf_value(self.config["lossLR"],
                                    self.config["lossLRJ"],
                                    self.config["lossdistribLR"],
                                    self.config["lossmult"],
                                    self.config["lossunit"],
                                    "", "%")

    def compute_lossRL(self):
        return self.gui_to_wf_value(self.config["lossRL"],
                                    self.config["lossRLJ"],
                                    self.config["lossdistribRL"],
                                    self.config["lossmult"],
                                    self.config["lossunit"],
                                    "", "%")

    def compute_dup(self):
        return self.gui_to_wf_value(self.config["dup"],
                                    self.config["dupJ"],
                                    self.config["dupdistrib"],
                                    self.config["dupmult"],
                                    self.config["dupunit"],
                                    "", "%")

    def compute_dupLR(self):
        return self.gui_to_wf_value(self.config["dupLR"],
                                    self.config["dupLRJ"],
                                    self.config["dupdistribLR"],
                                    self.config["dupmult"],
                                    self.config["dupunit"],
                                    "", "%")

    def compute_dupRL(self):
        return self.gui_to_wf_value(self.config["dupRL"],
                                    self.config["dupRLJ"],
                                    self.config["dupdistribRL"],
                                    self.config["dupmult"],
                                    self.config["dupunit"],
                                    "", "%")

    def compute_noise(self):
        return self.gui_to_wf_value(self.config["noise"],
                                    self.config["noiseJ"],
                                    self.config["noisedistrib"],
                                    self.config["noisemult"],
                                    self.config["noiseunit"],
                                    "Mega", "bit")

    def compute_noiseLR(self):
        return self.gui_to_wf_value(self.config["noiseLR"],
                                    self.config["noiseLRJ"],
                                    self.config["noisedistribLR"],
                                    self.config["noisemult"],
                                    self.config["noiseunit"],
                                    "Mega", "bit")

    def compute_noiseRL(self):
        return self.gui_to_wf_value(self.config["noiseRL"],
                                    self.config["noiseRLJ"],
                                    self.config["noisedistribRL"],
                                    self.config["noisemult"],
                                    self.config["noiseunit"],
                                    "Mega", "bit")

    def compute_lostburst(self):
        return self.gui_to_wf_value(self.config["lostburst"],
                                    self.config["lostburstJ"],
                                    self.config["lostburstdistrib"],
                                    self.config["lostburstmult"],
                                    self.config["lostburstunit"],
                                    "", "seconds")

    def compute_lostburstLR(self):
        return self.gui_to_wf_value(self.config["lostburstLR"],
                                    self.config["lostburstLRJ"],
                                    self.config["lostburstdistribLR"],
                                    self.config["lostburstmult"],
                                    self.config["lostburstunit"],
                                    "", "seconds")

    def compute_lostburstRL(self):
        return self.gui_to_wf_value(self.config["lostburstRL"],
                                    self.config["lostburstRLJ"],
                                    self.config["lostburstdistribRL"],
                                    self.config["lostburstmult"],
                                    self.config["lostburstunit"],
                                    "", "seconds")

    def compute_mtu(self):
        return self.gui_to_wf_value(self.config["mtu"], "", "",
                                    self.config["mtumult"],
                                    self.config["mtuunit"], "", "bytes")

    def compute_mtuLR(self):
        return self.gui_to_wf_value(self.config["mtuLR"], "", "",
                                    self.config["mtumult"],
                                    self.config["mtuunit"], "", "bytes")

    def compute_mtuRL(self):
        return self.gui_to_wf_value(self.config["mtuRL"], "", "",
                                    self.config["mtumult"],
                                    self.config["mtuunit"], "", "bytes")

    #callbacks for live-management
    def cbset_bandwidthLR(self, arg=0):
        self.send("bandwidth LR " + self.compute_bandwidthLR() + "\n")

    def cbset_bandwidthRL(self, arg=0):
        self.send("bandwidth RL " + self.compute_bandwidthRL() + "\n")

    def cbset_bandwidth(self, arg=0):
        if self.config["bandwidthsymm"]:
            self.send("bandwidth " + self.compute_bandwidth() + "\n")

    def cbset_speedLR(self, arg=0):
        self.send("speed LR " + self.compute_speedLR() + "\n")

    def cbset_speedRL(self, arg=0):
        self.send("speed RL " + self.compute_speedRL() + "\n")

    def cbset_speed(self, arg=0):
        if self.config["speedsymm"] != "*":
            self.send("speed " + self.compute_speed() + "\n")

    def cbset_delayLR(self, arg=0):
        self.send("delay LR " + self.compute_delayLR() + "\n")

    def cbset_delayRL(self, arg=0):
        self.send("delay RL " + self.compute_delayRL() + "\n")

    def cbset_delay(self, arg=0):
        if self.config["delaysymm"]:
            self.send("delay " + self.compute_delay() + "\n")

    def cbset_chanbufsizeLR(self, arg=0):
        self.send("chanbufsize LR " + self.compute_chanbufsizeLR() + "\n")

    def cbset_chanbufsizeRL(self, arg=0):
        self.send("chanbufsize RL " + self.compute_chanbufsizeRL() + "\n")

    def cbset_chanbufsize(self, arg=0):
        if self.config["chanbufsizesymm"]:
            self.send("chanbufsize " + self.compute_chanbufsize() + "\n")

    def cbset_lossLR(self, arg=0):
        self.send("loss LR " + self.compute_lossLR() + "\n")

    def cbset_lossRL(self, arg=0):
        self.send("loss RL " + self.compute_lossRL() + "\n")

    def cbset_loss(self, arg=0):
        if self.config["losssymm"]:
            self.send("loss " + self.compute_loss() + "\n")

    def cbset_dupLR(self, arg=0):
        self.send("dup LR " + self.compute_dupLR() + "\n")

    def cbset_dupRL(self, arg=0):
        self.send("dup RL " + self.compute_dupRL() + "\n")

    def cbset_dup(self, arg=0):
        if self.config["dupsymm"]:
            self.send("dup " + self.compute_dup() + "\n")

    def cbset_noiseLR(self, arg=0):
        self.send("noise LR " + self.compute_noiseLR() + "\n")

    def cbset_noiseRL(self, arg=0):
        self.send("noise RL " + self.compute_noiseRL() + "\n")

    def cbset_noise(self, arg=0):
        if self.config["noisesymm"]:
            self.send("noise " + self.compute_noise() + "\n")

    def cbset_lostburstLR(self, arg=0):
        self.send("lostburst LR " + self.compute_lostburstLR() + "\n")

    def cbset_lostburstRL(self, arg=0):
        self.send("lostburst RL " + self.compute_lostburstRL() + "\n")

    def cbset_lostburst(self, arg=0):
        if self.config["lostburstsymm"]:
            self.send("lostburst " + self.compute_lostburst() + "\n")

    def cbset_mtuLR(self, arg=0):
        self.send("mtu LR " + self.compute_mtuLR() + "\n")

    def cbset_mtuRL(self, arg=0):
        self.send("mtu RL " + self.compute_mtuRL() + "\n")

    def cbset_mtu(self, arg=0):
        if self.config["mtusymm"]:
            self.send("mtu " + self.compute_mtu() + "\n")
