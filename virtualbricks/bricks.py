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

from twisted.internet import protocol, reactor, error, defer
from twisted.python import failure

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
        self.brick.process_started(self)
        # self.transport.write("\n")

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
        self.brick.process_exited(self, status)


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
    _started_d = None
    _exited_d = None
    _last_status = None

    @property
    def pid(self):
        if self.proc is None:
            return -1
        return self.proc.pid

    def __init__(self, factory, name):
        base.Base.__init__(self, factory, name)
        self.plugs = []
        self.socks = []
        self.cfg.pon_vbevent = ""
        self.cfg.poff_vbevent = ""
        self.config_socks = []

    # IBrick interface

    def poweron(self):
        if self.proc is not None:
            return defer.succeed(self)

        if not self.configured():
            return defer.fail(failure.Failure(errors.BadConfigError(
                _("Cannot start '%s': not configured") % self.name)))
        if not self._properly_connected():
            return defer.fail(failure.Failure(errors.NotConnectedError(
                _("Cannot start '%s': not connected") % self.name)))

        self._started_d = started = defer.Deferred()
        self._exited_d = defer.Deferred()
        d = self._check_links()
        d.addCallback(self._poweron)
        # here self._started_d could be None because if child process is
        # created before reacing this point, process_stated is already called
        # and then _started_d is unset
        d.addErrback(started.errback)
        d.addCallback(lambda _: self.start_related_events(on=True))
        return started

    def poweroff(self, kill=False):
        if self.proc is None:
            return defer.succeed((self, self._last_status))
        log.msg(_("Shutting down %s (pid: %d)") % (self.name, self.proc.pid))
        try:
            self.proc.signalProcess("KILL" if kill else "TERM")
        except OSError as e:
            return defer.fail(failure.Failure(e))
        except error.ProcessExitedAlready:
            pass
        return self._exited_d

    def get_parameters(self):
        raise NotImplementedError("Bricks.get_parameters() not implemented")

    def configure(self, attrlist):
        attrs = {}
        for name, value in (a.split("=", 2) for a in attrlist):
            attrs[name] = self.cfg.parameters[name].from_string(value)
        self.set(attrs)

    def set(self, attrs):
        if "sock" in attrs:
            attrs["sock"] = self._rewrite_sock_server(attrs["sock"])
        base.Base.set(self, attrs)
        self.on_config_changed()

    def send_signal(self, signal):
        if self.proc:
            self.proc.signalProcess(signal)

    # brick <--> process interface

    def process_started(self, proc):
        started, self._started_d = self._started_d, None
        self.on_config_changed()
        started.callback(self)

    def process_exited(self, proc, status):
        self.proc = None
        self.start_related_events(off=True)
        self.on_config_changed()
        self._last_status = status
        exited, self._exited_d = self._exited_d, None
        exited.callback((self, status))

    # Interal interface

    def _properly_connected(self):
        return all(plug.configured() for plug in self.plugs)

    def configured(self):
        return False

    def _check_links(self):
        l = [plug.connected() for plug in self.plugs]
        return defer.DeferredList(l, fireOnOneErrback=True, consumeErrors=True)

    def args(self):
        return [self.prog()] + self.build_cmd_line()

    def prog(self):
        raise NotImplementedError(_("Brick.prog() not implemented."))

    def build_cmd_line(self):
        res = []

        for switch, value in self.command_builder.items():
            if not switch.startswith("#"):
                if callable(value):
                    value = value()
                else:
                    value = self.cfg.get(value)
                if value is "*":
                    res.append(switch)
                elif value is not None and len(value) > 0:
                    if not switch.startswith("*"):
                        res.append(switch)
                    res.append(value)
        return res

    def _poweron(self, ignore):

        def start_process(value):
            args, prog = value
            log.msg(_("Starting: '%s'") % " ".join(args))
            # usePTY?
            self.proc = reactor.spawnProcess(Process(self), prog, args,
                                             os.environ, usePTY=True)

        l = [defer.maybeDeferred(self.args), defer.maybeDeferred(self.prog)]
        d = defer.gatherResults(l, consumeErrors=True)
        d.addCallback(start_process)
        return d
        # if self.needsudo():
        #     self.proc = self.sudo_factory(self.proc)
        # self.factory.emit("brick-started", self.name)

    def start_related_events(self, on=True, off=False):
        if any([on, off]) and any([on and self.cfg.pon_vbevent, off and
                                   self.cfg.poff_vbevent]):
            name = self.cfg.pon_vbevent if on else self.cfg.poff_vbevent
            ev = self.factory.get_event_by_name(name)
            if ev:
                ev.poweron()
            else:
                log.warning("Warning. The Event '%s' attached to Brick '%s' is"
                            " not available. Skipping execution.",
                            self.cfg.poff_vbevent, self.name)

    #############################
    # Console related operations.
    #############################

    def _rewrite_sock_server(self, sock):
        return os.path.join(settings.VIRTUALBRICKS_HOME,
                            os.path.basename(sock))

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

    def initialize(self, attrlist):
        """TODO attrs : dict attr => value"""
        for attr in attrlist:
            k = attr.split("=")[0]
            self.cfg.set(attr)
            if k == "sock":
                self.cfg.sock = self._rewrite_sock_server(attr.split("=")[1])

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

    def open_console(self):
        term = self.settings.get("term")
        args = [term, "-T", self.name, "-e",
                os.path.join(self.settings.get("vdepath"), self.term_command),
                self.console()]
        log.msg("Opening console for %s\n%s\n" % (self.name, " ".join(args)))
        reactor.spawnProcess(TermProtocol(), term, args, os.environ)

    def send(self, data):
        if self.proc:
            self.proc.write(data)
        # else:
        #     log.msg("Cannot send command, brick is not running.")


    def recv(self):
        pass

    def get_state(self):
        """return state of the brick"""
        if self.proc is not None:
            state = _("running")
        elif not self._properly_connected():
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
            return _LocalBrick.poweron(self)

    def poweroff(self, kill=False):
        if self.homehost:
            self.homehost.send(self.name + " off\n")
        else:
            return _LocalBrick.poweroff(self, kill)
