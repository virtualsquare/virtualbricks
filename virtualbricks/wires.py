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

import time
import select
import socket
from threading import Thread
import logging

from virtualbricks import logger
from virtualbricks.bricks import Brick
from virtualbricks.link import Plug

log = logging.getLogger(__name__)

VDESUPPORT = True
try:
    import VdePlug
    log.info("VdePlug support ENABLED.")
except ImportError:
    log.info("VdePlug support not found. I will disable native VDE python "
             "support.")
    VDESUPPORT = False


if False:  # pyflakes
    _ = str


class Wire(logger.ChildLogger(__name__), Brick):

    type = "Wire"
    _pid = -1

    def get_pid(self):
        return self._pid

    def set_pid(self, value):
        self._pid = value

    pid = property(get_pid, set_pid)

    def __init__(self, _factory, _name):
        Brick.__init__(self, _factory, _name)
        self.cfg.name = _name
        self.command_builder = {"#sock left": "sock0", "#sock right": "sock1"}
        self.cfg.sock0 = ""
        self.cfg.sock1 = ""
        self.plugs.append(Plug(self))
        self.plugs.append(Plug(self))

    def restore_self_plugs(self):
        while len(self.plugs) < 2:
            self.plugs.append(Plug(self))

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
        Brick.on_config_changed(self)

    def configured(self):
        return (self.plugs[0].sock is not None and self.plugs[1].sock is not None)

    def prog(self):
        return self.settings.get("vdepath") + "/dpipe"

    def args(self):
        res = []
        res.append(self.prog())
        res.append(self.settings.get("vdepath") + '/vde_plug')
        res.append(self.cfg.sock0)
        res.append('=')
        res.append(self.settings.get("vdepath") + '/vde_plug')
        res.append(self.cfg.sock1)
        return res


class PyWireThread(Thread):

    def __init__(self, wire):
        self.wire = wire
        self.run_condition = False
        Thread.__init__(self)

    def run(self):
        self.run_condition = True
        self.wire.pid = -10
        self.wire.factory.TCP
        host0 = None
        if self.wire.factory.TCP is not None:
        # ON TCP SERVER SIDE OF REMOTE WIRE
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            for port in range(32400, 32500):
                try:
                    s.bind(('', port))
                except:
                    continue
                else:
                    self.wire.factory.TCP.sock.send("udp " + self.wire.name + " remoteport " + str(port) + '\n')
            v = VdePlug.VdePlug(self.wire.plugs[0].sock.path)
            p = select.poll()
            p.register(v.datafd().fileno(), select.POLLIN)
            p.register(s.fileno(), select.POLLIN)
            while self.run_condition:
                res = p.poll(250)
                for f, e in res:
                    if f == v.datafd().fileno() and (e & select.POLLIN):
                        buf = v.recv(2000)
                        s.sendto(buf, (self.wire.factory.TCP.master_address[0], self.wire.remoteport))
                    if f == s.fileno() and (e & select.POLLIN):
                        buf = s.recv(2000)
                        v.send(buf)

        elif self.wire.plugs[1].sock.brick.homehost == self.wire.plugs[0].sock.brick.homehost:
        # LOCAL WIRE
            v0 = VdePlug.VdePlug(self.wire.plugs[0].sock.path)
            v1 = VdePlug.VdePlug(self.wire.plugs[1].sock.path)
            p = select.epoll()
            p.register(v0.datafd().fileno(), select.POLLIN)
            p.register(v1.datafd().fileno(), select.POLLIN)
            while self.run_condition:
                res = p.poll(0.250)
                for f, e in res:
                    if f == v0.datafd().fileno() and (e & select.POLLIN):
                        buf = v0.recv(2000)
                        v1.send(buf)
                    if f == v1.datafd().fileno() and (e & select.POLLIN):
                        buf = v1.recv(2000)
                        v0.send(buf)
        else:
        # ON GUI SIDE OF REMOTE WIRE
            if host0:
                v = VdePlug.VdePlug(self.wire.plugs[1].sock.path)
                remote = self.wire.plugs[0].sock.brick
            else:
                v = VdePlug.VdePlug(self.wire.plugs[0].sock.path)
                remote = self.wire.plugs[1].sock.brick
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            for port in range(32400, 32500):
                try:
                    s.bind(('', port))
                except:
                    continue
                if self.wire.remoteport == 0:
                    remote.homehost.send("udp " + self.wire.name + " " + remote.name + " " + str(port))
            while self.run_condition:
                if self.wire.remoteport == 0:
                    time.sleep(1)
                    continue
                p = select.poll()
                p.register(v.datafd().fileno(), select.POLLIN)
                p.register(s.fileno(), select.POLLIN)
                res = p.poll(250)
                for f, e in res:
                    if f == v.datafd().fileno() and (e & select.POLLIN):
                        buf = v.recv(2000)
                        s.sendto(buf, (remote.homehost.addr[0], self.wire.remoteport))
                    if f == s.fileno() and (e & select.POLLIN):
                        buf = s.recv(2000)
                        v.send(buf)
            remote.homehost.send(self.wire.name + " off")

            self.wire.pid = -1

    def poll(self):
        if self.isAlive():
            return None
        else:
            return True

    def wait(self):
        return self.join()

    def terminate(self):
        self.run_condition = False

    def send_signal(self, signo):
        # TODO: Suspend/resume.
        self.run_condition = False


class PyWire(Wire):

    def __init__(self, factory, name, remoteport=0):
        self.remoteport = remoteport
        Wire.__init__(self, factory, name)

    def on_config_changed(self):
        pass

    def set_remoteport(self, port):
        self.remoteport = int(port)

    def prog(self):
        return ''

    def _poweron(self):
        # self.proc
        self.pid = -1
        self.proc = PyWireThread(self)
        self.proc.start()

    def poweroff(self):
        self.remoteport = 0
        if self.proc:
            self.proc.terminate()
            self.proc.join()
            del(self.proc)
            self.proc = None

#    def configured(self):
#        if self.factory.TCP is not None:
#            return len(self.plugs) != 0 and self.plugs[0].sock is not None
#        else:
#            return (self.plugs[0].sock is not None and self.plugs[1].sock is not None)

#    def connected(self):
#        self.debug( "CALLED PyWire connected" )
#        return True


class Wirefilter(Wire):

    type = "Wirefilter"

    def __init__(self, _factory, _name):
        Wire.__init__(self, _factory, _name)
        self.command_builder = {
            "-N": "nofifo",
            "-M": self.console,
        }

        self.cfg.bandwidthLR = ""
        self.cfg.bandwidthRL = ""
        self.cfg.bandwidth = ""
        self.cfg.bandwidthLRJ = ""
        self.cfg.bandwidthRLJ = ""
        self.cfg.bandwidthJ = ""
        self.cfg.bandwidthmult = "Mega"
        self.cfg.bandwidthunit = "bit/s"
        self.cfg.bandwidthdistribLR = "Uniform"
        self.cfg.bandwidthdistribRL = "Uniform"
        self.cfg.bandwidthdistrib = "Uniform"
        self.cfg.bandwidthsymm = "*"

        self.cfg.speedLR = ""
        self.cfg.speedRL = ""
        self.cfg.speed = ""
        self.cfg.speedLRJ = ""
        self.cfg.speedRLJ = ""
        self.cfg.speedJ = ""
        self.cfg.speedmult = "Mega"
        self.cfg.speedunit = "bit/s"
        self.cfg.speeddistribLR = "Uniform"
        self.cfg.speeddistribRL = "Uniform"
        self.cfg.speeddistrib = "Uniform"
        self.cfg.speedsymm = "*"
        self.cfg.speedenable = ""

        self.cfg.delayLR = ""
        self.cfg.delayRL = ""
        self.cfg.delay = ""
        self.cfg.delayLRJ = ""
        self.cfg.delayRLJ = ""
        self.cfg.delayJ = ""
        self.cfg.delaymult = "milli"
        self.cfg.delayunit = "seconds"
        self.cfg.delaydistribLR = "Uniform"
        self.cfg.delaydistribRL = "Uniform"
        self.cfg.delaydistrib = "Uniform"
        self.cfg.delaysymm = "*"

        self.cfg.chanbufsizeLR = ""
        self.cfg.chanbufsizeRL = ""
        self.cfg.chanbufsize = ""
        self.cfg.chanbufsizeLRJ = ""
        self.cfg.chanbufsizeRLJ = ""
        self.cfg.chanbufsizeJ = ""
        self.cfg.chanbufsizemult = "Kilo"
        self.cfg.chanbufsizeunit = "bytes"
        self.cfg.chanbufsizedistribLR = "Uniform"
        self.cfg.chanbufsizedistribRL = "Uniform"
        self.cfg.chanbufsizedistrib = "Uniform"
        self.cfg.chanbufsizesymm = "*"

        self.cfg.lossLR = ""
        self.cfg.lossRL = ""
        self.cfg.loss = ""
        self.cfg.lossLRJ = ""
        self.cfg.lossRLJ = ""
        self.cfg.lossJ = ""
        self.cfg.lossmult = ""
        self.cfg.lossunit = "%"
        self.cfg.lossdistribLR = "Uniform"
        self.cfg.lossdistribRL = "Uniform"
        self.cfg.lossdistrib = "Uniform"
        self.cfg.losssymm = "*"

        self.cfg.dupLR = ""
        self.cfg.dupRL = ""
        self.cfg.dup = ""
        self.cfg.dupLRJ = ""
        self.cfg.dupRLJ = ""
        self.cfg.dupJ = ""
        self.cfg.dupmult = ""
        self.cfg.dupunit = "%"
        self.cfg.dupdistribLR = "Uniform"
        self.cfg.dupdistribRL = "Uniform"
        self.cfg.dupdistrib = "Uniform"
        self.cfg.dupsymm = "*"

        self.cfg.noiseLR = ""
        self.cfg.noiseRL = ""
        self.cfg.noise = ""
        self.cfg.noiseLRJ = ""
        self.cfg.noiseRLJ = ""
        self.cfg.noiseJ = ""
        self.cfg.noisemult = "Mega"
        self.cfg.noiseunit = "bit"
        self.cfg.noisedistribLR = "Uniform"
        self.cfg.noisedistribRL = "Uniform"
        self.cfg.noisedistrib = "Uniform"
        self.cfg.noisesymm = "*"

        self.cfg.lostburstLR = ""
        self.cfg.lostburstRL = ""
        self.cfg.lostburst = ""
        self.cfg.lostburstLRJ = ""
        self.cfg.lostburstRLJ = ""
        self.cfg.lostburstJ = ""
        self.cfg.lostburstmult = ""
        self.cfg.lostburstunit = "seconds"
        self.cfg.lostburstdistribLR = "Uniform"
        self.cfg.lostburstdistribRL = "Uniform"
        self.cfg.lostburstdistrib = "Uniform"
        self.cfg.lostburstsymm = "*"

        self.cfg.mtuLR = ""
        self.cfg.mtuRL = ""
        self.cfg.mtu = ""
        self.cfg.mtumult = "Kilo"
        self.cfg.mtuunit = "bytes"
        self.cfg.mtusymm = "*"

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
        res.append(self.prog())
        res.append('-v')
        res.append(self.cfg.sock0 + ":" + self.cfg.sock1)

        #Bandwidth
        if len(self.cfg.bandwidth) > 0 and int(self.cfg.bandwidth) > 0:
            res.append("-b")
            value = self.compute_bandwidth()
            res.append(value)
        else:
            if len(self.cfg.bandwidthLR) > 0:
                res.append("-b")
                value = self.compute_bandwidthLR()
                res.append("LR" + value)
            if len(self.cfg.bandwidthRL) > 0:
                res.append("-b")
                value = self.compute_bandwidthRL()
                res.append("RL" + value)

        #Speed
        if len(self.cfg.speed) > 0 and int(self.cfg.speed) > 0:
            res.append("-s")
            value = self.compute_speed()
            res.append(value)
        else:
            if len(self.cfg.speedLR) > 0:
                res.append("-s")
                value = self.compute_speedLR()
                res.append("LR" + value)
            if len(self.cfg.speedRL) > 0:
                res.append("-s")
                value = self.compute_speedRL()
                res.append("RL" + value)

        #Delay
        if len(self.cfg.delay) > 0 and int(self.cfg.delay) > 0:
            res.append("-d")
            value = self.compute_delay()
            res.append(value)
        else:
            if len(self.cfg.delayLR) > 0:
                res.append("-d")
                value = self.compute_delayLR()
                res.append("LR" + value)
            if len(self.cfg.delayRL) > 0:
                res.append("-d")
                value = self.compute_delayRL()
                res.append("RL" + value)

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

        for param in Brick.build_cmd_line(self):
            res.append(param)
        return res

    def prog(self):
        return self.settings.get("vdepath") + "/wirefilter"

    #callbacks for live-management
    def cbset_bandwidthLR(self, arg=0):
        if not self.active:
            return
        value = self.compute_bandwidthLR()
        self.debug(self.name + ": callback 'bandwidth LR' with argument " + value)
        self.send("bandwidth LR " + value + "\n")
        self.debug(self.recv())

    def cbset_bandwidthRL(self, arg=0):
        if not self.active:
            return
        value = self.compute_bandwidthRL()
        self.debug(self.name + ": callback 'bandwidth RL' with argument " + value)
        self.send("bandwidth RL " + value + "\n")
        self.debug(self.recv())

    def cbset_bandwidth(self, arg=0):
        if not self.active:
            return
        if self.cfg.bandwidthsymm != "*":
            return
        value = self.compute_bandwidth()
        self.debug(self.name + ": callback 'bandwidth RL&LR' with argument " + value)
        self.send("bandwidth " + value + "\n")
        self.debug(self.recv())

    def cbset_speedLR(self, arg=0):
        if not self.active:
            return
        value = self.compute_speedLR()
        self.debug(self.name + ": callback 'speed LR' with argument " + value)
        self.send("speed LR " + value + "\n")
        self.debug(self.recv())

    def cbset_speedRL(self, arg=0):
        if not self.active:
            return
        value = self.compute_speedRL()
        self.debug(self.name + ": callback 'speed RL' with argument " + value)
        self.send("speed RL " + value + "\n")
        self.debug(self.recv())

    def cbset_speed(self, arg=0):
        if not self.active:
            return
        if self.cfg.speedsymm != "*":
            return
        value = self.compute_speed()
        self.debug(self.name + ": callback 'speed LR&RL' with argument " + value)
        self.send("speed " + value + "\n")
        self.debug(self.recv())

    def cbset_delayLR(self, arg=0):
        if not self.active:
            return
        value = self.compute_delayLR()
        self.debug(self.name + ": callback 'delay LR' with argument " + value)
        self.send("delay LR " + value + "\n")
        self.debug(self.recv())

    def cbset_delayRL(self, arg=0):
        if not self.active:
            return
        value = self.compute_delayRL()
        self.debug(self.name + ": callback 'delay RL' with argument " + value)
        self.send("delay RL " + value + "\n")
        self.debug(self.recv())

    def cbset_delay(self, arg=0):
        if not self.active:
            return
        if self.cfg.delaysymm != "*":
            return
        value = self.compute_delay()
        self.debug(self.name + ": callback 'delay LR&RL' with argument " + value)
        self.send("delay " + value + "\n")
        self.debug(self.recv())

    def cbset_chanbufsizeLR(self, arg=0):
        if not self.active:
            return
        value = self.compute_chanbufsizeLR()
        self.debug(self.name + ": callback 'chanbufsize (capacity) LR' with argument " + value)
        self.send("chanbufsize LR " + value + "\n")
        self.debug(self.recv())

    def cbset_chanbufsizeRL(self, arg=0):
        if not self.active:
            return
        value = self.compute_chanbufsizeRL()
        self.debug(self.name + ": callback 'chanbufsize (capacity) RL' with argument " + value)
        self.send("chanbufsize RL " + value + "\n")
        self.debug(self.recv())

    def cbset_chanbufsize(self, arg=0):
        if not self.active:
            return
        if self.cfg.chanbufsizesymm != "*":
            return
        value = self.compute_chanbufsize()
        self.debug(self.name + ": callback 'chanbufsize (capacity) LR&RL' with argument " + value)
        self.send("chanbufsize " + value + "\n")
        self.debug(self.recv())

    def cbset_lossLR(self, arg=0):
        if not self.active:
            return
        value = self.compute_lossLR()
        self.debug(self.name + ": callback 'loss LR' with argument " + value)
        self.send("loss LR " + value + "\n")
        self.debug(self.recv())

    def cbset_lossRL(self, arg=0):
        if not self.active:
            return
        value = self.compute_lossRL()
        self.debug(self.name + ": callback 'loss RL' with argument " + value)
        self.send("loss RL " + value + "\n")
        self.debug(self.recv())

    def cbset_loss(self, arg=0):
        if not self.active:
            return
        if self.cfg.losssymm != "*":
            return
        value = self.compute_loss()
        self.debug(self.name + ": callback 'loss LR&RL' with argument " + value)
        self.send("loss " + value + "\n")
        self.debug(self.recv())

    def cbset_dupLR(self, arg=0):
        if not self.active:
            return
        value = self.compute_dupLR()
        self.debug(self.name + ": callback 'dup LR' with argument " + value)
        self.send("dup LR " + value + "\n")
        self.debug(self.recv())

    def cbset_dupRL(self, arg=0):
        if not self.active:
            return
        value = self.compute_dupRL()
        self.debug(self.name + ": callback 'dup RL' with argument " + value)
        self.send("dup RL " + value + "\n")
        self.debug(self.recv())

    def cbset_dup(self, arg=0):
        if not self.active:
            return
        if self.cfg.dupsymm != "*":
            return
        value = self.compute_dup()
        self.debug(self.name + ": callback 'dup RL&LR' with argument " + value)
        self.send("dup " + value + "\n")
        self.debug(self.recv())

    def cbset_noiseLR(self, arg=0):
        if not self.active:
            return
        value = self.compute_noiseLR()
        self.debug(self.name + ": callback 'noise LR' with argument " + value)
        self.send("noise LR " + value + "\n")
        self.debug(self.recv())

    def cbset_noiseRL(self, arg=0):
        if not self.active:
            return
        value = self.compute_noiseRL()
        self.debug(self.name + ": callback 'noise RL' with argument " + value)
        self.send("noise RL " + value + "\n")
        self.debug(self.recv())

    def cbset_noise(self, arg=0):
        if not self.active:
            return
        if self.cfg.noisesymm != "*":
            return
        value = self.compute_noise()
        self.debug(self.name + ": callback 'noise LR&RL' with argument " + value)
        self.send("noise " + value + "\n")
        self.debug(self.recv())

    def cbset_lostburstLR(self, arg=0):
        if not self.active:
            return
        value = self.compute_lostburstLR()
        self.debug(self.name + ": callback 'lostburst LR' with argument " + value)
        self.send("lostburst LR " + value + "\n")
        self.debug(self.recv())

    def cbset_lostburstRL(self, arg=0):
        if not self.active:
            return
        value = self.compute_lostburstRL()
        self.debug(self.name + ": callback 'lostburst RL' with argument " + value)
        self.send("lostburst RL " + value + "\n")
        self.debug(self.recv())

    def cbset_lostburst(self, arg=0):
        if not self.active:
            return
        if self.cfg.lostburstsymm != "*":
            return
        value = self.compute_lostburst()
        self.debug(self.name + ": callback 'lostburst RL&RL' with argument " + value)
        self.send("lostburst " + value + "\n")
        self.debug(self.recv())

    def cbset_mtuLR(self, arg=0):
        if not self.active:
            return
        value = self.compute_mtuLR()
        self.debug(self.name + ": callback 'mtu LR' with argument " + value)
        self.send("mtu LR " + value + "\n")
        self.debug(self.recv())

    def cbset_mtuRL(self, arg=0):
        if not self.active:
            return
        value = self.compute_mtuRL()
        self.debug(self.name + ": callback 'mtu RL' with argument " + value)
        self.send("mtu RL " + value + "\n")
        self.debug(self.recv())

    def cbset_mtu(self, arg=0):
        if not self.active:
            return
        if self.cfg.mtusymm != "*":
            return
        value = self.compute_mtu()
        self.debug(self.name + ": callback 'mtu LR&RL' with argument " + value)
        self.send("mtu " + value + "\n")
        self.debug(self.recv())
