# -*- test-case-name: virtualbricks.tests.test_bricks -*-
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
import copy

from twisted.internet import protocol, reactor, error

from virtualbricks import base, errors, settings, _compat
from virtualbricks.base import (NewConfig, String, Integer, SpinInt, Float,
                                Boolean, Object)


__all__ = ["Brick", "Config", "String", "Integer", "SpinInt", "Float",
           "Boolean", "Object"]

if False:  # pyflakes
    _ = str

log = _compat.getLogger(__name__)


class Process(protocol.ProcessProtocol):

    def __init__(self, brick):
        self.brick = brick

    def connectionMade(self):
        # log.msg("Started process (%d)" % self.transport.pid)
        self.transport.write("\n")

    def outReceived(self, data):
        pass
        # log.msg("process %s stdout:\n%s" % (self.transport.pid, data))
        # self.brick.recv(data)

    def errReceived(self, data):
        pass
        # log.msg("process %s stderr:\n%s" % (self.transport.pid, data),
        #         isError=True, show_to_user=False)
        # self.brick.recv(data)

    def processExited(self, status):
        log.msg(str(status.value),
                isError=isinstance(status.value, error.ProcessTerminated),
                show_to_user=False)

    def processEnded(self, status):
        self.brick.process_ended(self, status)
        del self.brick


class TermProtocol(protocol.ProcessProtocol):

    def __init__(self):
        self.out = []
        self.err = []

    def connectionMade(self):
        self.transport.closeStdin()

    def outReceived(self, data):
        self.out.append(data)

    def errReceived(self, data):
        self.err.append(data)

    def processExited(self, status):
        msg = "Console terminated\n%s" % status.value
        terminated = isinstance(status.value, error.ProcessTerminated)
        if terminated:
            out = "".join(self.out)
            err = "".join(self.err)
            msg += "\nProcess stdout:\n%s\nProcess stderr:\n%s\n" % (out, err)
        log.msg(msg, isError=terminated)


class Config(NewConfig):

    parameters = {"pon_vbevent": String(""),
                  "poff_vbevent": String("")}


class _LocalBrick(base.Base):

    proc = None
    command_builder = {}
    term_command = "vdeterm"

    @property
    def pid(self):
        if self.proc is None:
            return -1
        return self.proc.pid

    def __init__(self, factory, name):
        base.Base.__init__(self, factory, name)
        self.plugs = []
        self.socks = []
        self.comm = []
        self.cfg.pon_vbevent = ""
        self.cfg.poff_vbevent = ""
        self.config_socks = []

    # IBrick interface

    def poweron(self):
        if self.proc is not None:
            log.msg("Cannot start an already running process.")
            return

        if self.factory.TCP is None:
            if not self.configured():
                raise errors.BadConfigError(_("Cannot start '%s': not "
                                              "configured") % self.name)
            if not self.properly_connected():
                raise errors.NotConnectedError(_("Cannot start '%s': not "
                                                 "connected") % self.name)
            if not self.check_links():
                raise errors.LinkLoopError("Link loop detected")
        del self.comm[:]
        self._poweron()
        self.start_related_events(on=True)
        self.on_config_changed()

    def poweroff(self, kill=False):
        if self.proc is None:
            return
        log.msg(_("Shutting down %s (pid: %d)") % (self.name, self.proc.pid))
        try:
            if self.proc:
                self.proc.signalProcess("KILL" if kill else "TERM")
        finally:
            self._poweroff()

    def get_parameters(self):
        raise NotImplementedError("Bricks.get_parameters() not implemented")

    def configure(self, attrlist):
        attrs = {}
        for name, value in (a.split("=", 2) for a in attrlist):
            attrs[name] = self.cfg.parameters[name].from_string(value)
        self.set(attrs)

    def set(self, attrs):
        if "sock" in attrs:
            attrs["sock"] = self.rewrite_sock_server(attrs["sock"])
        base.Base.set(self, attrs)
        self.on_config_changed()

    def send_signal(self, signal):
        if self.proc:
            self.proc.signalProcess(signal)

    # Interal interface

    def _poweron(self):
        prog = self.prog()
        args = self.args()
        log.debug(_("Starting: '%s'"), ' '.join(args))
        # usePTY?
        self.proc = reactor.spawnProcess(Process(self), prog, args, os.environ,
                                         usePTY=True)
        # if self.needsudo():
        #     self.proc = self.sudo_factory(self.proc)
        self.factory.emit("brick-started", self.name)

    def _poweroff(self):
        self.proc = None
        self.factory.emit("brick-stopped", self.name)
        self.start_related_events(off=True)

    def build_cmd_line(self):
        res = []

        for (switch, v) in self.command_builder.items():
            if not switch.startswith("#"):
                if callable(v):
                    value = v()
                else:
                    value = self.cfg.get(v)
                if value is "*":
                    res.append(switch)
                elif value is not None and len(value) > 0:
                    if not switch.startswith("*"):
                        res.append(switch)
                    res.append(value)
        return res

    def args(self):
        return [self.prog()] + self.build_cmd_line()

    def prog(self):
        raise NotImplementedError(_("Brick.prog() not implemented."))

    def process_ended(self, process, status):
        self._poweroff()

    def rewrite_sock_server(self, v):
        return os.path.join(settings.VIRTUALBRICKS_HOME, os.path.basename(v))

    def restore_self_plugs(self):  # DO NOT REMOVE
        pass

    def clear_self_socks(self, sock=None):  # DO NOT REMOVE
        pass

    def __deepcopy__(self, memo):
        newname = self.factory.normalize(self.factory.next_name(
            "Copy_of_%s" % self.name))
        new_brick = type(self)(self.factory, newname)
        new_brick.cfg = copy.deepcopy(self.cfg, memo)
        return new_brick

    def path(self):
        return "%s/%s.ctl" % (settings.VIRTUALBRICKS_HOME, self.name)

    def console(self):
        return "%s/%s.mgmt" % (settings.VIRTUALBRICKS_HOME, self.name)

    def on_config_changed(self):
        self.emit("changed")

    def configured(self):
        return False

    def properly_connected(self):
        for p in self.plugs:
            if not p.configured():
                return False
        return True

    def check_links(self):
        for p in self.plugs:
            if not p.connected():
                return False
        return True

    def initialize(self, attrlist):
        """TODO attrs : dict attr => value"""
        for attr in attrlist:
            k = attr.split("=")[0]
            self.cfg.set(attr)
            if k == "sock":
                self.cfg.sock = self.rewrite_sock_server(attr.split("=")[1])

    def connect(self, endpoint):
        for p in self.plugs:
            if not p.configured():
                if p.connect(endpoint):
                    self.on_config_changed()
                    return True
        return False

    def disconnect(self):
        for p in self.plugs:
            if p.configured():
                p.disconnect()
        self.on_config_changed()

    ############################
    ########### Poweron/Poweroff
    ############################

    def start_related_events(self, on=True, off=False):

        if on is False and off is False:
            return

        if ((off and not self.cfg.poff_vbevent) or
            (on and not self.cfg.pon_vbevent)):
            return

        if off:
            ev = self.factory.get_event_by_name(self.cfg.poff_vbevent)
        elif on:
            ev = self.factory.get_event_by_name(self.cfg.pon_vbevent)

        if ev:
            ev.poweron()
        else:
            log.warning("Warning. The Event '%s' attached to Brick '%s' is "
                        "not available. Skipping execution.",
                        self.cfg.poff_vbevent, self.name)

    #############################
    # Console related operations.
    #############################

    def open_console(self):
        term = self.settings.get("term")
        args = [term, "-T", self.name, "-e",
                os.path.join(self.settings.get("vdepath"), self.term_command),
                self.console()]
        log.msg("Opening console for %s\n%s\n" % (self.name, " ".join(args)))
        reactor.spawnProcess(TermProtocol(), term, args, os.environ)

    def send(self, data):
        # import pdb; pdb.set_trace()
        if self.proc:
            self.comm.append(data)
            self.proc.write(data)
        # else:
        #     log.msg("Cannot send command, brick is not running.")

    # def recv(self, data):
    #     self.comm.append(data)

    def recv(self):
        pass

    def get_state(self):
        """return state of the brick"""
        if self.proc is not None:
            state = _("running")
        elif not self.properly_connected():
            state = _("disconnected")
        else:
            state = _("off")
        return state


class Brick(_LocalBrick):

    homehost = None

    def __init__(self, factory, name, homehost=None):
        _LocalBrick.__init__(self, factory, name)
        if homehost is not None:
            self.set_host(homehost)

    def set_host(self, hostname):
        self.homehost = self.factory.get_host_by_name(hostname)
        self.cfg.homehost = hostname

    def initialize(self, attrlist):
        attributes = []
        homehosts = []
        for attr in attrlist:
            if not attr.startswith("homehost="):
                attributes.append(attr)
            else:
                homehosts.append(attr)
        _LocalBrick.initialize(self, attributes)
        for homehost in homehosts:
            self.cfg.set(homehost)
            self.set_host(homehost.split('=')[1])

    def set(self, attrs):
        _LocalBrick.set(self, attrs)
        if self.homehost and self.homehost.connected:
            self.homehost.putconfig(self)

    def poweron(self):
        if self.homehost:
            if not self.homehost.connected:
                log.error(_("Error: You must be connected to the "
                            "host to perform this action"))
            else:
                self.homehost.send(self.name + " on")
        else:
            _LocalBrick.poweron(self)

    def poweroff(self):
        if self.homehost:
            self.homehost.send(self.name + " off\n")
        else:
            _LocalBrick.poweroff(self)
