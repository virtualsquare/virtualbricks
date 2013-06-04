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
# import time
# import select
# import socket
# from threading import Thread

from virtualbricks import _compat, bricks, link

log = _compat.getLogger(__name__)

# try:
#     import VdePlug
#     # log.info("VdePlug support ENABLED.")
# except ImportError:
#     VdePlug = None
#     # log.info("VdePlug support not found. I will disable native VDE python "
#     #          "support.")


if False:  # pyflakes
    _ = str


class WireConfig(bricks.Config):

    parameters = {
        "name": bricks.String(""),
        "sock0": bricks.String(""),
        "sock1": bricks.String("")
    }


class Wire(bricks.Brick):

    type = "Wire"
    config_factory = WireConfig

    def __init__(self, factory, name):
        bricks.Brick.__init__(self, factory, name)
        self.cfg.name = name
        self.command_builder = {
            "#sock left": "sock0",
            "#sock right": "sock1"
        }
        self.plugs.append(link.Plug(self))
        self.plugs.append(link.Plug(self))

    def restore_self_plugs(self):
        while len(self.plugs) < 2:
            self.plugs.append(link.Plug(self))

    def clear_self_socks(self, sock=None):
        if sock is None:
            self.cfg.sock0 = ""
            self.cfg.sock1 = ""
        elif self.cfg.sock0 == sock:
            self.cfg.sock0 = ""
        elif self.cfg.sock1 == sock:
            self.cfg.sock1 = ""

    def get_parameters(self):
        if self.plugs[0].sock:
            p0 = self.plugs[0].sock.brick.name
        else:
            p0 = _("disconnected")

        if self.plugs[1].sock:
            p1 = self.plugs[1].sock.brick.name
        else:
            p1 = _("disconnected")

        if p0 != _('disconnected') and p1 != _('disconnected'):
            return _("Configured to connect") + " " + p0 + " " + "to" + " " + p1
        else:
            return _("Not yet configured.") + " " +\
                _("Left plug is") + " " + p0 + " " + _("and right plug is") + \
                " " + p1

    def on_config_changed(self):
        if (self.plugs[0].sock is not None):
            self.cfg.sock0 = self.plugs[0].sock.path.rstrip('[]')
        if (self.plugs[1].sock is not None):
            self.cfg.sock1 = self.plugs[1].sock.path.rstrip('[]')
        if (self.proc is not None):
            self.need_restart_to_apply_changes = True
        bricks.Brick.on_config_changed(self)

    def configured(self):
        return (self.plugs[0].sock is not None and self.plugs[1].sock is not None)

    def prog(self):
        return os.path.join(self.settings.get("vdepath"), "dpipe")

    def args(self):
        return [self.prog(),
                os.path.join(self.settings.get("vdepath"), "vde_plug"),
                self.cfg.sock0, "=",
                os.path.join(self.settings.get("vdepath"), "vde_plug"),
                self.cfg.sock1]


# class PyWireThread(Thread):

#     def __init__(self, wire):
#         self.wire = wire
#         self.run_condition = False
#         Thread.__init__(self)

#     def run(self):
#         self.run_condition = True
#         self.wire.pid = -10
#         self.wire.factory.TCP
#         host0 = None
#         if self.wire.factory.TCP is not None:
#         # ON TCP SERVER SIDE OF REMOTE WIRE
#             s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
#             for port in range(32400, 32500):
#                 try:
#                     s.bind(('', port))
#                 except:
#                     continue
#                 else:
#                     self.wire.factory.TCP.sock.send("udp " + self.wire.name + " remoteport " + str(port) + '\n')
#             v = VdePlug.VdePlug(self.wire.plugs[0].sock.path)
#             p = select.poll()
#             p.register(v.datafd().fileno(), select.POLLIN)
#             p.register(s.fileno(), select.POLLIN)
#             while self.run_condition:
#                 res = p.poll(250)
#                 for f, e in res:
#                     if f == v.datafd().fileno() and (e & select.POLLIN):
#                         buf = v.recv(2000)
#                         s.sendto(buf, (self.wire.factory.TCP.master_address[0], self.wire.remoteport))
#                     if f == s.fileno() and (e & select.POLLIN):
#                         buf = s.recv(2000)
#                         v.send(buf)

#         elif self.wire.plugs[1].sock.brick.homehost == self.wire.plugs[0].sock.brick.homehost:
#         # LOCAL WIRE
#             v0 = VdePlug.VdePlug(self.wire.plugs[0].sock.path)
#             v1 = VdePlug.VdePlug(self.wire.plugs[1].sock.path)
#             p = select.epoll()
#             p.register(v0.datafd().fileno(), select.POLLIN)
#             p.register(v1.datafd().fileno(), select.POLLIN)
#             while self.run_condition:
#                 res = p.poll(0.250)
#                 for f, e in res:
#                     if f == v0.datafd().fileno() and (e & select.POLLIN):
#                         buf = v0.recv(2000)
#                         v1.send(buf)
#                     if f == v1.datafd().fileno() and (e & select.POLLIN):
#                         buf = v1.recv(2000)
#                         v0.send(buf)
#         else:
#         # ON GUI SIDE OF REMOTE WIRE
#             if host0:
#                 v = VdePlug.VdePlug(self.wire.plugs[1].sock.path)
#                 remote = self.wire.plugs[0].sock.brick
#             else:
#                 v = VdePlug.VdePlug(self.wire.plugs[0].sock.path)
#                 remote = self.wire.plugs[1].sock.brick
#             s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
#             for port in range(32400, 32500):
#                 try:
#                     s.bind(('', port))
#                 except:
#                     continue
#                 if self.wire.remoteport == 0:
#                     remote.homehost.send("udp " + self.wire.name + " " + remote.name + " " + str(port))
#             while self.run_condition:
#                 if self.wire.remoteport == 0:
#                     time.sleep(1)
#                     continue
#                 p = select.poll()
#                 p.register(v.datafd().fileno(), select.POLLIN)
#                 p.register(s.fileno(), select.POLLIN)
#                 res = p.poll(250)
#                 for f, e in res:
#                     if f == v.datafd().fileno() and (e & select.POLLIN):
#                         buf = v.recv(2000)
#                         s.sendto(buf, (remote.homehost.addr[0], self.wire.remoteport))
#                     if f == s.fileno() and (e & select.POLLIN):
#                         buf = s.recv(2000)
#                         v.send(buf)
#             remote.homehost.send(self.wire.name + " off")

#             self.wire.pid = -1

#     def poll(self):
#         if self.isAlive():
#             return None
#         else:
#             return True

#     def wait(self):
#         return self.join()

#     def terminate(self):
#         self.run_condition = False

#     def send_signal(self, signo):
#         # TODO: Suspend/resume.
#         self.run_condition = False


# class PyWire(Wire):

#     def __init__(self, factory, name, remoteport=0):
#         self.remoteport = remoteport
#         Wire.__init__(self, factory, name)

#     def on_config_changed(self):
#         pass

#     def set_remoteport(self, port):
#         self.remoteport = int(port)

#     def prog(self):
#         return ''

#     def _poweron(self):
#         # self.proc
#         self.pid = -1
#         self.proc = PyWireThread(self)
#         self.proc.start()

#     def poweroff(self):
#         self.remoteport = 0
#         if self.proc:
#             self.proc.terminate()
#             self.proc.join()
#             del(self.proc)
#             self.proc = None

#    def configured(self):
#        if self.factory.TCP is not None:
#            return len(self.plugs) != 0 and self.plugs[0].sock is not None
#        else:
#            return (self.plugs[0].sock is not None and self.plugs[1].sock is not None)

#    def connected(self):
#        self.debug( "CALLED PyWire connected" )
#        return True


class WireFilterConfig(WireConfig):

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
        "bandwidthsymm": bricks.Boolean("*"),

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
        "speedsymm": bricks.Boolean("*"),
        "speedenable": bricks.String(""),

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
        "delaysymm": bricks.Boolean("*"),

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
        "chanbufsizesymm": bricks.Boolean("*"),

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
        "losssymm": bricks.Boolean("*"),

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
        "dupsymm": bricks.Boolean("*"),

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
        "noisesymm": bricks.Boolean("*"),

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
        "lostburstsymm": bricks.Boolean("*"),

        "mtuLR": bricks.String(""),
        "mtuRL": bricks.String(""),
        "mtu": bricks.String(""),
        "mtumult": bricks.String("Kilo"),
        "mtuunit": bricks.String("bytes"),
        "mtusymm": bricks.Boolean("*")
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

    def gui_to_wf_value(self, base, jitter, distrib, mult, unit, def_mult="", def_unit=""):
        b = base
        if not b:
            return "0"

        u = unit
        if u != def_unit:
            if def_unit.startswith("byte"):
                b = float(b) / 8
            else:
                b = float(b) * 8

        value = str(round(float(b), 6))  # f.e. 50

        if mult != def_mult:
            if mult is "milli" and def_mult is "":
                m = "K"
            else:
                m = mult[0]
        else:
            m = ""

        j = jitter
        if j is not "":
            if def_unit is not "%":
                j = str(round((float(b) * float(j) / 100), 6)) + m  # GUI=100K(+-)10% becomes WF=100+20K
            else:
                j = str(round(float(j), 6))

        if distrib and distrib[0] is ("G" or "N"):
            d = "N"
        else:
            d = "U"

        if j is not "":
            value = value + "+" + j  # f.e. 50+5K
            value = value + d  # f.e. 50+5KU/N
        else:
            value = value + m  # f.e. 50K

        return str(value)

    def compute_bandwidth(self):
        return self.gui_to_wf_value(self.cfg.bandwidth, self.cfg.bandwidthJ,
                                self.cfg.bandwidthdistrib, self.cfg.bandwidthmult,
                                self.cfg.bandwidthunit, "", "byte/s")

    def compute_bandwidthLR(self):
        return self.gui_to_wf_value(self.cfg.bandwidthLR, self.cfg.bandwidthLRJ,
                                    self.cfg.bandwidthdistribLR, self.cfg.bandwidthmult,
                                    self.cfg.bandwidthunit, "", "byte/s")

    def compute_bandwidthRL(self):
        return self.gui_to_wf_value(self.cfg.bandwidthRL, self.cfg.bandwidthRLJ, self.cfg.bandwidthdistribRL, self.cfg.bandwidthmult,
                                    self.cfg.bandwidthunit, "", "byte/s")

    def compute_speed(self):
        return self.gui_to_wf_value(self.cfg.speed, self.cfg.speedJ, self.cfg.speeddistrib, self.cfg.speedmult,
                                    self.cfg.speedunit, "", "byte/s")

    def compute_speedLR(self):
        return self.gui_to_wf_value(self.cfg.speedLR, self.cfg.speedLRJ, self.cfg.speeddistribLR, self.cfg.speedmult,
                                    self.cfg.speedunit, "", "byte/s")

    def compute_speedRL(self):
        return self.gui_to_wf_value(self.cfg.speedRL, self.cfg.speedRLJ, self.cfg.speeddistribRL, self.cfg.speedmult,
                                    self.cfg.speedunit, "", "byte/s")

    def compute_delay(self):
        return self.gui_to_wf_value(self.cfg.delay, self.cfg.delayJ, self.cfg.delaydistrib, self.cfg.delaymult,
                                    self.cfg.delayunit, "milli", "seconds")

    def compute_delayLR(self):
        return self.gui_to_wf_value(self.cfg.delayLR, self.cfg.delayLRJ, self.cfg.delaydistribLR, self.cfg.delaymult,
                                    self.cfg.delayunit, "milli", "seconds")

    def compute_delayRL(self):
        return self.gui_to_wf_value(self.cfg.delayRL, self.cfg.delayRLJ, self.cfg.delaydistribRL, self.cfg.delaymult,
                                    self.cfg.delayunit, "milli", "seconds")

    def compute_chanbufsize(self):
        return self.gui_to_wf_value(self.cfg.chanbufsize, self.cfg.chanbufsizeJ, self.cfg.chanbufsizedistrib, self.cfg.chanbufsizemult,
                                    self.cfg.chanbufsizeunit, "", "bytes")

    def compute_chanbufsizeLR(self):
        return self.gui_to_wf_value(self.cfg.chanbufsizeLR, self.cfg.chanbufsizeLRJ, self.cfg.chanbufsizedistribLR, self.cfg.chanbufsizemult,
                                    self.cfg.chanbufsizeunit, "", "bytes")

    def compute_chanbufsizeRL(self):
        return self.gui_to_wf_value(self.cfg.chanbufsizeRL, self.cfg.chanbufsizeRLJ, self.cfg.chanbufsizedistribRL, self.cfg.chanbufsizemult,
                                    self.cfg.chanbufsizeunit, "", "bytes")

    def compute_loss(self):
        return self.gui_to_wf_value(self.cfg.loss, self.cfg.lossJ, self.cfg.lossdistrib, self.cfg.lossmult,
                                    self.cfg.lossunit, "", "%")

    def compute_lossLR(self):
        return self.gui_to_wf_value(self.cfg.lossLR, self.cfg.lossLRJ, self.cfg.lossdistribLR, self.cfg.lossmult,
                                    self.cfg.lossunit, "", "%")

    def compute_lossRL(self):
        return self.gui_to_wf_value(self.cfg.lossRL, self.cfg.lossRLJ, self.cfg.lossdistribRL, self.cfg.lossmult,
                                    self.cfg.lossunit, "", "%")

    def compute_dup(self):
        return self.gui_to_wf_value(self.cfg.dup, self.cfg.dupJ, self.cfg.dupdistrib, self.cfg.dupmult,
                                    self.cfg.dupunit, "", "%")

    def compute_dupLR(self):
        return self.gui_to_wf_value(self.cfg.dupLR, self.cfg.dupLRJ, self.cfg.dupdistribLR, self.cfg.dupmult,
                                    self.cfg.dupunit, "", "%")

    def compute_dupRL(self):
        return self.gui_to_wf_value(self.cfg.dupRL, self.cfg.dupRLJ, self.cfg.dupdistribRL, self.cfg.dupmult,
                                    self.cfg.dupunit, "", "%")

    def compute_noise(self):
        return self.gui_to_wf_value(self.cfg.noise, self.cfg.noiseJ, self.cfg.noisedistrib, self.cfg.noisemult,
                                    self.cfg.noiseunit, "Mega", "bit")

    def compute_noiseLR(self):
        return self.gui_to_wf_value(self.cfg.noiseLR, self.cfg.noiseLRJ, self.cfg.noisedistribLR, self.cfg.noisemult,
                                    self.cfg.noiseunit, "Mega", "bit")

    def compute_noiseRL(self):
        return self.gui_to_wf_value(self.cfg.noiseRL, self.cfg.noiseRLJ, self.cfg.noisedistribRL, self.cfg.noisemult,
                                    self.cfg.noiseunit, "Mega", "bit")

    def compute_lostburst(self):
        return self.gui_to_wf_value(self.cfg.lostburst, self.cfg.lostburstJ, self.cfg.lostburstdistrib, self.cfg.lostburstmult,
                                    self.cfg.lostburstunit, "", "seconds")

    def compute_lostburstLR(self):
        return self.gui_to_wf_value(self.cfg.lostburstLR, self.cfg.lostburstLRJ, self.cfg.lostburstdistribLR, self.cfg.lostburstmult,
                                    self.cfg.lostburstunit, "", "seconds")

    def compute_lostburstRL(self):
        return self.gui_to_wf_value(self.cfg.lostburstRL, self.cfg.lostburstRLJ, self.cfg.lostburstdistribRL, self.cfg.lostburstmult,
                                    self.cfg.lostburstunit, "", "seconds")

    def compute_mtu(self):
        return self.gui_to_wf_value(self.cfg.mtu, "", "", self.cfg.mtumult,
                                    self.cfg.mtuunit, "", "bytes")

    def compute_mtuLR(self):
        return self.gui_to_wf_value(self.cfg.mtuLR, "", "", self.cfg.mtumult,
                                    self.cfg.mtuunit, "", "bytes")

    def compute_mtuRL(self):
        return self.gui_to_wf_value(self.cfg.mtuRL, "", "", self.cfg.mtumult,
                                    self.cfg.mtuunit, "", "bytes")

    def args(self):
        res = []
        res.extend([self.prog(), "-v", self.cfg.sock0 + ":" + self.cfg.sock1])

        #Bandwidth
        if len(self.cfg.bandwidth) > 0 and int(self.cfg.bandwidth) > 0:
            res.extend(["-b", self.compute_bandwidth()])
        else:
            if len(self.cfg.bandwidthLR) > 0:
                res.extend(["-b", "LR" + self.compute_bandwidthLR()])
            if len(self.cfg.bandwidthRL) > 0:
                res.extend(["-b", "RL" + self.compute_bandwidthRL()])

        #Speed
        if len(self.cfg.speed) > 0 and int(self.cfg.speed) > 0:
            res.extend(["-s", self.compute_speed()])
        else:
            if len(self.cfg.speedLR) > 0:
                res.extend(["-s", "LR" + self.compute_speedLR()])
            if len(self.cfg.speedRL) > 0:
                res.extend(["-s", "RL" + self.compute_speedRL()])

        #Delay
        if len(self.cfg.delay) > 0 and int(self.cfg.delay) > 0:
            res.extend(["-d", self.compute_delay()])
        else:
            if len(self.cfg.delayLR) > 0:
                res.extend(["-d", "LR" + self.compute_delayLR()])
            if len(self.cfg.delayRL) > 0:
                res.extend(["-d", "RL" + self.compute_delayRL()])

        #Chanbufsize
        if len(self.cfg.chanbufsize) > 0 and int(self.cfg.chanbufsize) > 0:
            res.append("-c")
            value = self.compute_chanbufsize()
            res.append(value)
        else:
            if len(self.cfg.chanbufsizeLR) > 0:
                res.append("-c")
                value = self.compute_chanbufsizeLR()
                res.append("LR" + value)
            if len(self.cfg.chanbufsizeRL) > 0:
                res.append("-c")
                value = self.compute_chanbufsizeRL()
                res.append("RL" + value)

        #Loss
        if len(self.cfg.loss) > 0 and int(self.cfg.loss) > 0:
            res.append("-l")
            value = self.compute_loss()
            res.append(value)
        else:
            if len(self.cfg.lossLR) > 0:
                res.append("-l")
                value = self.compute_lossLR()
                res.append("LR" + value)
            if len(self.cfg.lossRL) > 0:
                res.append("-l")
                value = self.compute_lossRL()
                res.append("RL" + value)

        #Dup
        if len(self.cfg.dup) > 0 and int(self.cfg.dup) > 0:
            res.append("-D")
            value = self.compute_dup()
            res.append(value)
        else:
            if len(self.cfg.dupLR) > 0:
                res.append("-D")
                value = self.compute_dupLR()
                res.append("LR" + value)
            if len(self.cfg.dupRL) > 0:
                res.append("-D")
                value = self.compute_dupRL()
                res.append("RL" + value)

        #Noise
        if len(self.cfg.noise) > 0 and int(self.cfg.noise) > 0:
            res.append("-n")
            value = self.compute_noise()
            res.append(value)
        else:
            if len(self.cfg.noiseLR) > 0:
                res.append("-n")
                value = self.compute_noiseLR()
                res.append("LR" + value)
            if len(self.cfg.noiseRL) > 0:
                res.append("-n")
                value = self.compute_noiseRL()
                res.append("RL" + value)

        #Lostburst
        if len(self.cfg.lostburst) > 0 and int(self.cfg.lostburst) > 0:
            res.append("-L")
            value = self.compute_lostburst()
            res.append(value)
        else:
            if len(self.cfg.lostburstLR) > 0:
                res.append("-L")
                value = self.compute_lostburstLR()
                res.append("LR" + value)
            if len(self.cfg.lostburstRL) > 0:
                res.append("-L")
                value = self.compute_lostburstRL()
                res.append("RL" + value)

        #MTU
        if len(self.cfg.mtu) > 0 and int(self.cfg.mtu) > 0:
            res.append("-m")
            value = self.compute_mtu()
            res.append(value)
        else:
            if len(self.cfg.mtuLR) > 0:
                res.append("-m")
                value = self.compute_mtuLR()
                res.append("LR" + value)
            if len(self.cfg.mtuRL) > 0:
                res.append("-m")
                value = self.compute_mtuRL()
                res.append("RL" + value)

        res.extend(bricks.Brick.build_cmd_line(self))
        return res

    def prog(self):
        return self.settings.get("vdepath") + "/wirefilter"

    #callbacks for live-management
    def cbset_bandwidthLR(self, arg=0):
        self.send("bandwidth LR " + self.compute_bandwidthLR() + "\n")

    def cbset_bandwidthRL(self, arg=0):
        self.send("bandwidth RL " + self.compute_bandwidthRL() + "\n")

    def cbset_bandwidth(self, arg=0):
        if self.cfg["bandwidthsymm"]:
            self.send("bandwidth " + self.compute_bandwidth() + "\n")

    def cbset_speedLR(self, arg=0):
        self.send("speed LR " + self.compute_speedLR() + "\n")

    def cbset_speedRL(self, arg=0):
        self.send("speed RL " + self.compute_speedRL() + "\n")

    def cbset_speed(self, arg=0):
        if self.cfg["speedsymm"] != "*":
            self.send("speed " + self.compute_speed() + "\n")

    def cbset_delayLR(self, arg=0):
        self.send("delay LR " + self.compute_delayLR() + "\n")

    def cbset_delayRL(self, arg=0):
        self.send("delay RL " + self.compute_delayRL() + "\n")

    def cbset_delay(self, arg=0):
        if self.cfg["delaysymm"]:
            self.send("delay " + self.compute_delay() + "\n")

    def cbset_chanbufsizeLR(self, arg=0):
        self.send("chanbufsize LR " + self.compute_chanbufsizeLR() + "\n")

    def cbset_chanbufsizeRL(self, arg=0):
        self.send("chanbufsize RL " + self.compute_chanbufsizeRL() + "\n")

    def cbset_chanbufsize(self, arg=0):
        if self.cfg["chanbufsizesymm"]:
            self.send("chanbufsize " + self.compute_chanbufsize() + "\n")

    def cbset_lossLR(self, arg=0):
        self.send("loss LR " + self.compute_lossLR() + "\n")

    def cbset_lossRL(self, arg=0):
        self.send("loss RL " + self.compute_lossRL() + "\n")

    def cbset_loss(self, arg=0):
        if self.cfg["losssymm"]:
            self.send("loss " + self.compute_loss() + "\n")

    def cbset_dupLR(self, arg=0):
        self.send("dup LR " + self.compute_dupLR() + "\n")

    def cbset_dupRL(self, arg=0):
        self.send("dup RL " + self.compute_dupRL() + "\n")

    def cbset_dup(self, arg=0):
        if self.cfg["dupsymm"]:
            self.send("dup " + self.compute_dup() + "\n")

    def cbset_noiseLR(self, arg=0):
        self.send("noise LR " + self.compute_noiseLR() + "\n")

    def cbset_noiseRL(self, arg=0):
        self.send("noise RL " + self.compute_noiseRL() + "\n")

    def cbset_noise(self, arg=0):
        if self.cfg["noisesymm"]:
            self.send("noise " + self.compute_noise() + "\n")

    def cbset_lostburstLR(self, arg=0):
        self.send("lostburst LR " + self.compute_lostburstLR() + "\n")

    def cbset_lostburstRL(self, arg=0):
        self.send("lostburst RL " + self.compute_lostburstRL() + "\n")

    def cbset_lostburst(self, arg=0):
        if self.cfg["lostburstsymm"]:
            self.send("lostburst " + self.compute_lostburst() + "\n")

    def cbset_mtuLR(self, arg=0):
        self.send("mtu LR " + self.compute_mtuLR() + "\n")

    def cbset_mtuRL(self, arg=0):
        self.send("mtu RL " + self.compute_mtuRL() + "\n")

    def cbset_mtu(self, arg=0):
        if self.cfg["mtusymm"]:
            self.send("mtu " + self.compute_mtu() + "\n")
