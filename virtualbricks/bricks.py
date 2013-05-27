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
import sys
import time
import errno
import socket
import select
import copy
import threading
import subprocess
import logging
import tempfile

from virtualbricks import base, errors, settings, versions
from virtualbricks.base import (NewConfig, String, Integer, SpinInt, Float,
                                Boolean, Object)
from virtualbricks.deprecated import deprecated


__all__ = ["Brick", "Config", "String", "Integer", "SpinInt", "Float",
           "Boolean", "Object"]

log = logging.getLogger(__name__)

if False:  # pyflakes
    _ = str


class Process(threading.Thread):

    _pd = None

    @property
    def pid(self):
        return self._pd.pid

    def __init__(self, args):
        threading.Thread.__init__(self, name="Process_%s" % args[0])
        self.daemon = True
        self._raw = {}
        self.args = args

    def poll(self):
        return self._pd.poll()

    def send_signal(self, signo):
        self._pd.send_signal(signo)

    def terminate(self):
        self._pd.terminate()

    def kill(self):
        self._pd.kill()

    def __run(self):
        self._pd = subprocess.Popen(self.args, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE)
        log.debug("Process pid: %d", self._pd.pid)
        stdout, stderr = self._pd.communicate()
        if stdout:
            self.out(stdout)
        if stderr:
            self.err(stderr)

    def run(self):
        log.debug("Starting %s", self.args[0])
        try:
            self.__run()
        except OSError:
            log.exception(_("OSError: Brick startup failed. Check your "
                            "configuration!"))
        else:
            log.debug("Process %d terminated with exit code %d.", self._pd.pid,
                      self._pd.returncode)

    def out(self, data):
        log.info("stdout of process %d:\n%s", self._pd.pid, data)

    def err(self, data):
        log.warning("stderr of process %d:\n%s", self._pd.pid, data)


class Sudo(object):

    pid = None
    process_factory = Process
    returncode = None

    def __init__(self, process, sudo="sudo"):
        if isinstance(process, list):
            process = self.process_factory(process)
        self.process = process
        self.sudo = sudo
        self.pidfile = tempfile.NamedTemporaryFile()
        self.inject_sudo()

    def inject_sudo(self):
        self._args = self.process.args
        self.process.args = [self.sudo] + self._args[:] + \
                ["-P", self.pidfile.name]

    def __getattr__(self, name):
        try:
            return getattr(self.process, name)
        except AttributeError:
            raise AttributeError(name)

    def _handle_exit_status(self, status):
        if os.WIFSIGNALED(status):
            self.returncode = -os.WTERMSIG(status)
        elif os.WIFEXITED(status):
            self.returncode = os.WEXITSTATUS(status)
        else:
            raise RuntimeError("This should never happen")

    # Process interface

    def poll(self):
        if self.returncode is None:
            status = self.process.poll()
            if status is not None:
                self._handle_exit_status(status)
        return self.returncode

    def start(self):
        self.process.start()
        try:
            # wait the thread started
            while self.process._pd is None:
                self.process.join(0.0001)
            # wait the pid is written in the pid file
            while os.stat(self.pidfile.name).st_size == 0:
                self.process.join(0.001)
                status = self.process.poll()
                if status is None:
                    continue
                else:
                    self._handle_exit_status(status)
            with self.pidfile:
                self.pid = int(self.pidfile.read())
        finally:
            self.pidfile.close()

    def send_signal(self, signal):
        return subprocess.call([self.sudo, "kill", "-%s" % signal,
                                str(self.pid)])

    def terminate(self):
        return self.send_signal("SIGTERM")

    def kill(self):
        return self.send_signal("SIGKILL")


class Config(NewConfig):

    parameters = {"pon_vbevent": String(""),
                  "poff_vbevent": String("")}


class _LocalBrick(base.Base):

    active = False
    run_condition = False
    proc = None
    gui_changed = False
    need_restart_to_apply_changes = False
    internal_console = None
    terminal = "vdeterm"
    command_builder = {}
    process_factory = Process
    sudo_factory = Sudo

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
            log.info("Cannot start an already running process.")
            return

        if self.factory.TCP is None:
            if not self.configured():
                raise errors.BadConfigError("Brick %s not configured",
                                            self.name)
            if not self.properly_connected():
                raise errors.NotConnectedError("Brick %s not properly "
                                               "connected", self.name)
            if not self.check_links():
                raise errors.LinkLoopError("Link loop detected")
        self._poweron()
        self.emit("changed")

    def poweroff(self):
        if self.proc is None or not self.run_condition:
            return
        self.run_condition = False
        log.debug(_("Shutting down %s"), self.name)
        try:
            self._poweroff()
        finally:
            self.proc = None
            self.need_restart_to_apply_changes = False
            self.close_internal_console()
            self.factory.emit("brick-stopped", self.name)
            self.post_poweroff()

    def get_parameters(self):
        raise NotImplementedError('Bricks.get_parameters() not implemented')

    def configure(self, attrlist):
        """TODO attrs : dict attr => value"""
        self.initialize(attrlist)
        self.emit("changed")

    # Interal interface

    def _poweron(self):
        self.proc = self.process_factory(self.args())
        if self.needsudo():
            self.proc = self.sudo_factory(self.proc)
        log.debug(_("Starting: '%s'"), ' '.join(self.proc.args))
        self.proc.start()
        self.open_internal_console()
        self.factory.emit("brick-started", self.name)
        self.run_condition = True
        self.post_poweron()

    def _poweroff(self):
        try:
            self.proc.terminate()
        except OSError as e:
            if e.errno != errno.ESRCH:
                raise
        # give the process the chance to stop itself (100ms)
        for i in range(100):
            if self.proc.poll() is None:
                time.sleep(0.001)
            else:
                break
        else:
            # kill it
            try:
                self.proc.kill()
                # while self.proc.poll() is None:
                #     time.sleep(0.0001)
            except OSError as e:
                if e.errno != errno.ESRCH:
                    raise

    def post_poweron(self):
        self.active = True
        self.start_related_events(on=True)

    def post_poweroff(self):
        self.active = False
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

    @deprecated(versions.Version("Virtualbricks", 1, 0), "emit")
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
            if k == 'sock':
                s = self.rewrite_sock_server(attr.split('=')[1])
                self.cfg.sock = s

    def connect(self, endpoint):
        for p in self.plugs:
            if not p.configured():
                if p.connect(endpoint):
                    self.emit("changed")
                    self.gui_changed = True
                    return True
        return False

    def disconnect(self):
        for p in self.plugs:
            if p.configured():
                p.disconnect()
        self.emit("changed")

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
    def has_console(self, closing=False):
        for i in range(500):
            if (self.proc is not None and self.console() and
                os.path.exists(self.console())):
                return True
            else:
                if closing:
                    return False
                time.sleep(0.01)
        return False

    def open_console(self):
        log.debug("open_console")
        if not self.has_console():
            return

        if os.access(self.settings.get('term'), os.X_OK):
            cmdline = [self.settings.get('term'), '-T', self.name, '-e',
                       self.terminal, self.console()]
        elif os.access(self.settings.get('alt-term'), os.X_OK):
            cmdline = [self.settings.get('alt-term'), '-t', self.name, '-e',
                       self.terminal + " " + self.console()]
        else:
            log.error(_("Error: cannot start a terminal emulator"))
            return
        try:
            # console = subprocess.Popen(cmdline)
            subprocess.Popen(cmdline)
        except:
            log.exception(_("Error running command line %s"), cmdline)
            return

    # Must be overridden in Qemu to use appropriate console as internal
    # (stdin, stdout?)
    def open_internal_console(self):
        log.debug("open internal console")
        if not self.has_console():
            log.debug(_("%s does not have a console"), self.get_type())
            return
        try:
            self.internal_console = socket.socket(socket.AF_UNIX)
        except socket.error:
            self.internal_console = None
            log.exception(_("Error while opening internal console"))
            return

        # NOTE: how much time should I wait? actually 5s
        for i in range(500):
            try:
                self.internal_console.connect(self._get_console())
                return
            except socket.error as e:
                if len(e.args) != 2 or e.errno != errno.ECONNREFUSED:
                    log.exception(_("Error while opening internal console"))
                time.sleep(0.01)

        self.internal_console = None
        log.error(_("%s: error opening internal console"), self.get_type())

    def _get_console(self):
        return self.console()

    def send(self, msg):
        if self.internal_console is None or not self.active:
            log.debug("%s: cancel send", self.get_type())
            return
        try:
            log.debug("%s: sending '%s'", self.get_type(), msg)
            self.internal_console.send(msg)
        except Exception:
            log.exception("%s: send failed", self.get_type())

    def recv(self):
        log.debug("recv")
        if self.internal_console is None:
            return ''
        res = ''
        p = select.poll()
        p.register(self.internal_console, select.POLLIN)
        while True:
            pollret = p.poll(300)
            if (len(pollret) == 1 and pollret[0][1] == select.POLLIN):
                line = self.internal_console.recv(100)
                res += line
            else:
                break
        return res

    def close_internal_console(self):
        if self.internal_console is not None:
            try:
                self.internal_console.close()
            finally:
                self.internal_console = None

    def close_tty(self):
        sys.stdin.close()
        sys.stdout.close()
        sys.stderr.close()

    def get_state(self):
        """return state of the brick"""
        if self.proc is not None:
            state = _('running')
        elif not self.properly_connected():
            state = _('disconnected')
        else:
            state = _('off')
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

    def configure(self, attrlist):
        _LocalBrick.configure(self, attrlist)
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
