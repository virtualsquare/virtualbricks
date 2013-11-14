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
import operator
import itertools

from twisted.internet import protocol, reactor, error, defer
from twisted.python import failure

from virtualbricks import base, errors, settings, log
from virtualbricks.base import (Config as _Config, Parameter, String, Integer,
                                SpinInt, Float, Boolean, Object, ListOf)


__all__ = ["Brick", "Config", "Parameter", "String", "Integer", "SpinInt",
           "Float", "Boolean", "Object", "ListOf"]

if False:  # pyflakes
    _ = str

logger = log.Logger(__name__)
process_started = log.Event("Process started")
process_terminated = log.Event("Process terminated. {status()}")
process_done = log.Event("Process terminated")
event_unavailable = log.Event("Warning. The Event {event} attached to Brick "
                              "{brick} is not available. Skipping execution.")
shutdown_brick = log.Event("Shutting down {name} (pid: {pid})")
start_brick = log.Event("Starting: '{args()}'")
open_console = log.Event("Opening console for {name}\n%{args()}\n")
host_not_connected = log.Event("Error: You must be connected to the host to "
                               "perform this action")
console_done = log.Event("Console terminated\n{status}")
console_terminated = log.Event("Console terminated\n{status}\nProcess stdout:"
                               "\n{out()}\nProcess stderr:\n{err()}\n")


class Process(protocol.ProcessProtocol):

    pid = None
    logger = None

    def __init__(self, brick):
        self.brick = brick

    def connectionMade(self):
        self.pid = self.transport.pid
        self.logger = log.Logger("virtualbricks.bricks.Process.%d" % self.pid)
        self.logger.info(process_started)
        self.brick.process_started(self)

    def outReceived(self, data):
        self.brick.out_received(data)

    def errReceived(self, data):
        self.brick.err_received(data)

    def processEnded(self, status):
        if status.check(error.ProcessTerminated):
            self.logger.error(process_terminated,
                              status=lambda: " ".join(status.value.args))
        else:
            assert status.check(error.ProcessDone)
            self.logger.info(process_terminated, status=lambda: "")
        self.brick.process_ended(self, status)


class ProcessLogger:
    """Log the output of a process.

    Limit is useful to prevent uncontrolled output of a process.
    """

    delay = 1
    limit = 1024
    logger = log.Logger()

    def __init__(self, proc):
        self.pid = proc.transport.pid
        self.buffer = []
        self.scheduled = None

    def log(self, data):
        self.logger.info(data)

    def log_e(self, data):
        self.logger.error(data, hide_to_user=True)

    def flush(self):
        loggers = [self.log, self.log_e]
        get_data = operator.itemgetter(0)
        is_error = operator.itemgetter(1)
        for idx, group in itertools.groupby(self.buffer, is_error):
            logger = loggers[idx]
            data = "".join(map(get_data, group))
            logger(data)
        del self.buffer[:]

    def enqueue(self, data, is_error=False):
        self.buffer.append((data, is_error))
        if self.scheduled is None or not self.scheduled.active():
            self.scheduled = reactor.callLater(self.delay, self.flush)
        elif sum(len(e[0]) for e in self.buffer) > self.limit:
            self.scheduled.cancel()
            self.flush()
        else:
            self.scheduled.reset(self.delay)

    def in_(self, data):
        self.enqueue(data)

    def out(self, data):
        self.enqueue(data)

    def err(self, data):
        self.enqueue(data, True)


class TermProtocol(protocol.ProcessProtocol):

    logger = log.Logger()

    def __init__(self):
        self.out = []
        self.err = []

    def connectionMade(self):
        self.transport.closeStdin()

    def outReceived(self, data):
        self.out.append(data)

    def errReceived(self, data):
        self.err.append(data)

    def processEnded(self, status):
        if isinstance(status.value, error.ProcessTerminated):
            self.logger.error(console_terminated, status=status.value,
                              out=lambda: "".join(self.out),
                              err=lambda: "".join(self.err))
        else:
            self.logger.info(console_done, status=status.value)


class Config(_Config):

    parameters = {"pon_vbevent": String(""),
                  "poff_vbevent": String("")}


class _LocalBrick(base.Base):

    proc = None
    command_builder = {}
    term_command = "vdeterm"
    _started_d = None
    _exited_d = None
    _last_status = None
    process_logger = ProcessLogger
    config_factory = Config

    @property
    def pid(self):
        if self.proc is None:
            return -1
        return self.proc.pid

    def __init__(self, factory, name):
        base.Base.__init__(self, factory, name)
        self.plugs = []
        self.socks = []
        self.config["pon_vbevent"] = ""
        self.config["poff_vbevent"] = ""
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

        def start_related_events(_):
            self._start_related_events(on=True)
            return self

        d.addCallback(start_related_events)

        def eb(failure):
            if failure.check(defer.FirstError):
                failure = failure.value.subFailure
            started.errback(failure)

        # here self._started_d could be None because if child process is
        # created before reaching this point, process_stated is already called
        # and then self._started_d is unset
        d.addErrback(eb)
        return started

    def poweroff(self, kill=False):
        if self.proc is None:
            return defer.succeed((self, self._last_status))
        logger.info(shutdown_brick, name=self.name, pid=self.proc.pid)
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
            attrs[name] = self.config.parameters[name].from_string(value)
        self.set(attrs)

    def set(self, attrs=None, **kwds):
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
        logger = self.process_logger(proc)
        self.in_received = logger.in_
        self.out_received = logger.out
        self.err_received = logger.err
        self.on_config_changed()
        started.callback(self)

    def process_ended(self, proc, status):
        self.proc = None
        self._start_related_events(off=True)
        self.on_config_changed()
        self._last_status = status
        # ovvensive programming, raise an exception instead of hide the error
        # behind a lambda (lambda _: None)
        self.in_received = self.out_received = self.err_received = None
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
        # TODO: documents the behavior of all cases (#, *, etc.)
        res = []

        for switch, value in self.command_builder.items():
            if not switch.startswith("#"):
                if callable(value):
                    value = value()
                else:
                    value = self.config.get(value)
                if value is "*":
                    res.append(switch)
                elif value is not None and len(value) > 0:
                    if not switch.startswith("*"):
                        res.append(switch)
                    res.append(value)
        return res

    def _poweron(self, ignore):

        def start_process(value):
            prog, args = value
            get_args = lambda: " ".join(args)
            logger.info(start_brick, args=get_args)
            # usePTY?
            if self.needsudo():
                prog = settings.get('sudo')
                args = [settings.get('sudo')] + args
            self.proc = reactor.spawnProcess(Process(self), prog, args,
                                             os.environ)
        l = [defer.maybeDeferred(self.prog), defer.maybeDeferred(self.args)]
        d = defer.gatherResults(l, consumeErrors=True)
        d.addCallback(start_process)
        return d
        # if self.needsudo():
        #     self.proc = self.sudo_factory(self.proc)

    def _start_related_events(self, on=True, off=False):
        if on and self.config["pon_vbevent"]:
            name = self.config["pon_vbevent"]
        elif off and self.config["poff_vbevent"]:
            name = self.config["poff_vbevent"]
        else:
            return

        event = self.factory.get_event_by_name(name)
        if event:
            event.poweron()
        else:
            logger.info(event_unavailable, event=name, brick=self.name)

    #############################
    # Console related operations.
    #############################

    def _rewrite_sock_server(self, sock):
        return os.path.join(settings.VIRTUALBRICKS_HOME,
                            os.path.basename(sock))

    def path(self):
        return "%s/%s.ctl" % (settings.VIRTUALBRICKS_HOME, self.name)

    def console(self):
        return "%s/%s.mgmt" % (settings.VIRTUALBRICKS_HOME, self.name)

    def on_config_changed(self):
        pass

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
        term = settings.get("term")
        args = [term, "-e",
                os.path.join(settings.get("vdepath"), self.term_command),
                self.console()]
        get_args = lambda: " ".join(args)
        logger.info(open_console, name=self.name, args=get_args)
        reactor.spawnProcess(TermProtocol(), term, args, os.environ)

    def send(self, data):
        if self.proc:
            self.proc.write(data)
            self.in_received(data)
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

    def __repr__(self):
        return "<{0.type} {0.name}>".format(self)


class Brick(_LocalBrick):

    homehost = None

    def __init__(self, factory, name, homehost=None):
        _LocalBrick.__init__(self, factory, name)
        if homehost is not None:
            self.set_host(homehost)

    def set_host(self, hostname):
        self.homehost = self.factory.get_host_by_name(hostname)
        self.config["homehost"] = hostname

    def set(self, attrs=None, **kwds):
        if attrs is None:
            attrs = kwds
        else:
            attrs.update(kwds)
        _LocalBrick.set(self, attrs)
        if self.homehost and self.homehost.connected:
            self.homehost.putconfig(self)

    def poweron(self):
        if self.homehost:
            if not self.homehost.connected:
                logger.error(host_not_connected)
            else:
                self.homehost.send(self.name + " on")
        else:
            return _LocalBrick.poweron(self)

    def poweroff(self, kill=False):
        if self.homehost:
            self.homehost.send(self.name + " off\n")
        else:
            return _LocalBrick.poweroff(self, kill)
