# -*- test-case-name: virtualbricks.tests.test_events -*-
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

from twisted.internet import reactor, defer, utils
from twisted.python.deprecate import deprecated

from virtualbricks import version, base, errors, console, _compat


if False:  # pyflakes
    _ = str


log = _compat.getLogger(__name__)


class Command(base.String):

    def from_string(self, in_object):
        if in_object.startswith("add "):
            factory = console.VbShellCommand
        elif in_object.startswith("addsh "):
            factory = console.ShellCommand
        else:
            raise RuntimeError()
        return factory(in_object.split(" ", 1)[1])

    def to_string(self, in_object):
        if isinstance(in_object, console.VbShellCommand):
            return "add " + in_object
        elif isinstance(in_object, console.ShellCommand):
            return "addsh " + in_object
        else:
            raise RuntimeError(_("Invalid command type."))


class EventConfig(base.NewConfig):

    parameters = {"actions": base.ListOf(Command("")),
                  "delay": base.Integer(0)}

    def __init__(self):
        base.NewConfig.__init__(self)
        self._cfg["actions"] = []


class Event(base.Base):

    type = "Event"
    scheduled = None
    config_factory = EventConfig

    def get_state(self):
        """Return state of the event"""

        if self.scheduled is not None:
            state = _("running")
        elif not self.configured():
            state = _("unconfigured")
        else:
            state = _("off")
        return state

    def configured(self):
        return len(self.cfg["actions"]) > 0 and self.cfg["delay"] > 0

    @deprecated(version)
    def initialize(self, attrlist):
        if "add" in attrlist and "addsh" in attrlist:
            raise errors.InvalidActionError(_("Error: config line must "
                                              "contain add OR addsh."))
        elif "add" in attrlist:
            configactions = list()
            configactions = (" ".join(attrlist)).split("add")
            for action in configactions[1:]:
                action = action.strip()
                self.cfg["actions"].append(console.VbShellCommand(action))
                log.msg(_("Added vb-shell command: '%s'") % action)
        elif "addsh" in attrlist:
            configactions = list()
            configactions = (" ".join(attrlist)).split("addsh")
            for action in configactions[1:]:
                action = action.strip()
                self.cfg["actions"].append(console.ShellCommand(action))
                log.msg(_("Added host-shell command: '%s'") % action)
        else:
            for attr in attrlist:
                self.cfg.set(attr)

    def properly_connected(self):
        return True

    def get_parameters(self):
        tempstr = _("Delay: %d") % self.cfg["delay"]
        if len(self.cfg["actions"]) > 0:
            tempstr += "; " + _("Actions:")
            # Add actions cutting the tail if it's too long
            for s in self.cfg["actions"]:
                if isinstance(s, console.ShellCommand):
                    tempstr += " \"*%s\"," % s
                else:
                    tempstr += " \"%s\"," % s
            # Remove the last character
            tempstr = tempstr[0:-1]
        return tempstr

    def connect(self, endpoint):
        return True

    def disconnect(self):
        return

    @deprecated(version)
    def configure(self, attrlist):
        self.initialize(attrlist)
        # TODO brick should be gobject and a signal should be launched
        self.emit("changed")

    ############################
    ########### Poweron/Poweroff
    ############################

    def poweron(self):
        if self.scheduled:
            return
        if not self.configured():
            raise errors.BadConfigError("Event %s not configured" % self.name)

        def call():
            self.scheduled = None
            return self.doactions()
        self.scheduled = reactor.callLater(self.cfg["delay"], call)
        self.factory.emit("event-started", self.name)

    def poweroff(self):
        if self.scheduled is None:
            return
        self.scheduled.cancel()
        self.scheduled = None
        self.factory.emit("event-stopped", self.name)

    def toggle(self):
        if self.scheduled is not None:
            self.poweroff()
        else:
            self.poweron()

    def doactions(self):
        procs = []
        for action in self.cfg["actions"]:
            if isinstance(action, console.VbShellCommand):
                console.Parse(self.factory, action)
            elif isinstance(action, console.ShellCommand):
                procs.append(utils.getProcessValue("sh", action, os.environ))

        def log_err(results):
            for success, value in results:
                if success:
                    log.msg("Process ended with exit code %s" % value)
                else:
                    log.err(value)

        defer.DeferredList(procs, consumeErrors=True).addCallback(log_err)
        return defer
        # self.factory.emit("event-accomplished", self.name)

    change_state = toggle
