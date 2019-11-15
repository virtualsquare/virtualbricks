# -*- test-case-name: virtualbricks.tests.test_bricks -*-
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


import os
import collections
import functools
import re

from twisted.internet import protocol, reactor, error, defer
from zope.interface import implementer

from virtualbricks import base, errors, settings, log, interfaces
from virtualbricks.base import (Config as _Config, Parameter, String, Integer,
                                SpinInt, Float, SpinFloat, Boolean, Object,
                                ListOf)
from virtualbricks._spawn import abspath_vde


__all__ = ["Brick", "Config", "Parameter", "String", "Integer", "SpinInt",
           "Float", "SpinFloat", "Boolean", "Object", "ListOf"]

if False:  # pyflakes
    _ = str

logger = log.Logger(__name__)
process_started = log.Event("Process started")
process_terminated = log.Event("Process terminated. {status()}")
process_done = log.Event("Process terminated")
event_unavailable = log.Event("Warning. The Event {name} attached to Brick "
                              "{brick} is not available. Skipping execution.")
shutdown_brick = log.Event("Shutting down {name} (pid: {pid})")
start_brick = log.Event("Starting: {args()}")
open_console = log.Event("Opening console for {name}\n%{args()}\n")
console_done = log.Event("Console terminated\n{status}")
console_terminated = log.Event("Console terminated\n{status}\nProcess stdout:"
                               "\n{out()}\nProcess stderr:\n{err()}\n")
invalid_ack = log.Event("ACK received but no command sent.")


class ProcessLogger(object):

    def __init__(self, logger):
        self.logger = logger

    def __get__(self, instance, owner):
        if instance is not None:
            logger = self.logger.__get__(instance, owner)
            logger.emit = functools.partial(logger.emit, pid=instance.pid)
            return logger
        return self.logger.__get__(instance, owner)


@implementer(interfaces.IProcess)
class Process(protocol.ProcessProtocol):

    logger = ProcessLogger(log.Logger())
    debug = True
    debug_child = True

    def __init__(self, brick):
        self.brick = brick

    def connectionMade(self):
        self.logger.info(process_started)
        self.brick.process_started(self)

    def processEnded(self, status):
        if status.check(error.ProcessTerminated):
            self.logger.error(process_terminated,
                              status=lambda: " ".join(status.value.args))
        else:
            assert status.check(error.ProcessDone)
            self.logger.info(process_terminated, status=lambda: "")
        self.brick.process_ended(self, status)

    def outReceived(self, data):
        self.logger.info(data)

    def errReceived(self, data):
        self.logger.error(data, hide_to_user=True)

    # new interface

    @property
    def pid(self):
        return self.transport.pid

    def signal_process(self, signalID):
        self.transport.signalProcess(signalID)

    def write(self, data):
        self.transport.write(data)


@implementer(interfaces.IProcess)
class FakeProcess:

    pid = -1

    def __init__(self, brick):
        self.brick = brick

    def signal_process(self, signo):
        pass

    def write(self, data):
        pass


class VDEProcessProtocol(Process):
    """
    Handle the VDE management console.

    Commands are serialized, until an ACK is received, the next command is not
    sent.

    @cvar delimiter: The line-ending delimiter to use.
    """

    _buffer = ""
    delimiter = u"\n"
    prompt = re.compile(r"^vde(?:\[[^]]*\]:|\$) ", re.MULTILINE)
    PIPELINE_SIZE = 1

    def __init__(self, brick):
        Process.__init__(self, brick)
        self.queue = collections.deque()


    def data_received(self, data):
        """
        Translates bytes into lines, and calls ack_received.
        """
        
        acks = self.prompt.split(self._buffer + data.decode("utf-8"))
        self._buffer = acks.pop(-1)
        for ack in acks:
            self.ack_received(ack)

    def ack_received(self, ack):
        self.logger.info(ack)
        try:
            self.queue.popleft()
        except IndexError:
            self.logger.warn(invalid_ack)
            self.transport.loseConnection()
        else:
            if len(self.queue):
                self._send_command()

    def send_command(self, cmd):
        self.queue.append(cmd)
        if 0 < len(self.queue) <= self.PIPELINE_SIZE:
            self._send_command()

    def _send_command(self):
        cmd = self.queue[0]
        self.logger.info(cmd)
        if cmd.decode("utf-8").endswith(self.delimiter):
            return self.transport.write(cmd)
        return self.transport.writeSequence((cmd, self.delimiter.encode("utf-8")))

    def outReceived(self, data):
        self.data_received(data)

    def write(self, cmd):
        self.send_command(cmd)


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


class Brick(base.Base):

    proc = None
    command_builder = {}
    term_command = "vdeterm"
    _started_d = None
    _exited_d = None
    _last_status = None
    process_protocol = VDEProcessProtocol
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
        self.config_socks = []

    # IBrick interface

    def poweron(self):
        if self.proc is not None:
            return defer.succeed(self)

        if not self.configured():
            return defer.fail(errors.BadConfigError(
                _("Cannot start '%s': not configured") % self.name))
        if not self._properly_connected():
            return defer.fail(errors.NotConnectedError(
                _("Cannot start '%s': not connected") % self.name))

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
            self.proc.signal_process("KILL" if kill else "TERM")
        except OSError as e:
            return defer.fail(e)
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

    def send_signal(self, signal):
        if self.proc:
            self.proc.signal_process(signal)

    # brick <--> process interface

    def process_started(self, proc):
        started, self._started_d = self._started_d, None
        started.callback(self)
        self.notify_changed()

    def process_ended(self, proc, status):
        self.proc = None
        self._start_related_events(off=True)
        self._last_status = status
        # ovvensive programming, raise an exception instead of hide the error
        # behind a lambda (lambda _: None)
        exited, self._exited_d = self._exited_d, None
        exited.callback((self, status))
        self.notify_changed()

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

        # import pdb; pdb.set_trace()
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
        #res.sort()
        #print(res)
        return res

    def _poweron(self, ignore):

        def start_process(value):
            prog, args = value
            logger.info(start_brick, args=lambda: " ".join(args))
            # usePTY?
            if self.needsudo():
                prog = settings.get("sudo")
                args = [settings.get("sudo"), "--"] + args
            self.proc = self.process_protocol(self)
            reactor.spawnProcess(self.proc, prog, args, os.environ)

        l = [defer.maybeDeferred(self.prog), defer.maybeDeferred(self.args)]
        d = defer.gatherResults(l, consumeErrors=True)
        d.addCallback(start_process)
        return d

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
            logger.info(event_unavailable, name=name, brick=self.name)

    #############################
    # Console related operations.
    #############################

    def path(self):
        return "%s/%s.ctl" % (settings.VIRTUALBRICKS_HOME, self.name)

    def console(self):
        return "%s/%s.mgmt" % (settings.VIRTUALBRICKS_HOME, self.name)

    def connect(self, endpoint, *args):
        for p in self.plugs:
            if not p.configured():
                p.connect(endpoint)
                self.notify_changed()
                return

    def disconnect(self):
        for p in self.plugs:
            if p.configured():
                p.disconnect()
        self.notify_changed()

    ############################
    ########### Poweron/Poweroff
    ############################

    def open_console(self):
        term = settings.get("term")
        args = [term, "-e",
                abspath_vde(self.term_command),
                self.console()]
        get_args = lambda: " ".join(args)
        logger.info(open_console, name=self.name, args=get_args)
        reactor.spawnProcess(TermProtocol(), term, args, os.environ)

    def send(self, data):
        if self.proc:
            self.proc.write(data)

    def get_state(self):
        """return state of the brick"""
        if self.proc is not None:
            state = _("running")
        elif not self._properly_connected():
            state = _("disconnected")
        else:
            state = _("off")
        return state

    def __isrunning__(self):
        return self.proc is not None

    def __format__(self, format_string):
        if format_string == "d":
            if self.pid == -10:
                return "python-thread   "
            return str(self.pid)
        return base.Base.__format__(self, format_string)

    def __repr__(self):
        return "<{0.type} {0.name}>".format(self)
