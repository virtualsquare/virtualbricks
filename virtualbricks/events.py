# -*- test-case-name: virtualbricks.tests.test_events -*-
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

from twisted.internet import reactor, defer

from virtualbricks import base, errors, console, log


if False:  # pyflakes
    _ = str


process_ended = log.Event("Process ended with exit code {code}")
event_error = log.Event("Error in event action. See the log for more "
                        "informations")


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


class EventConfig(base.Config):

    parameters = {"actions": base.ListOf(Command("")),
                  "delay": base.Integer(0)}

    def __init__(self):
        base.Config.__init__(self)
        self["actions"] = []


class Event(base.Base):

    type = "Event"
    scheduled = None
    config_factory = EventConfig

    def __isrunning__(self):
      return self.scheduled is not None

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
        return len(self.config["actions"]) > 0 and self.config["delay"] > 0

    def get_parameters(self):
        tempstr = _("Delay: %d") % self.config["delay"]
        if len(self.config["actions"]) > 0:
            tempstr += "; " + _("Actions:")
            # Add actions cutting the tail if it's too long
            for s in self.config["actions"]:
                if isinstance(s, console.ShellCommand):
                    tempstr += " \"*%s\"," % s
                else:
                    tempstr += " \"%s\"," % s
            # Remove the last character
            tempstr = tempstr[0:-1]
        return tempstr

    # def connect(self, endpoint):
    #     return True

    # def disconnect(self):
    #     return

    ############################
    ########### Poweron/Poweroff
    ############################

    def poweron(self):
        if self.scheduled:
            return
        if not self.configured():
            raise errors.BadConfigError("Event %s not configured" % self.name)

        deferred = defer.Deferred()
        self.scheduled = reactor.callLater(self.config["delay"],
                                           self.do_actions, deferred)
        self.notify_changed()
        return deferred

    def poweroff(self):
        if self.scheduled is None:
            return
        self.scheduled.cancel()
        self.scheduled = None
        self.notify_changed()

    def toggle(self):
        if self.scheduled is not None:
            self.poweroff()
            return defer.succeed(self)
        else:
            return self.poweron()

    def do_actions(self, deferred):

        def log_err(results):
            for success, status in results:
                if success:
                    self.logger.info(process_ended, code=status)
                else:
                    self.logger.error(event_error, log_failure=status)
            return self

        self.scheduled = None
        procs = [defer.maybeDeferred(action.perform, self.factory)
                 for action in self.config["actions"]]
        dl = defer.DeferredList(procs, consumeErrors=True).addCallback(log_err)
        dl.chainDeferred(deferred)
        self.notify_changed()
