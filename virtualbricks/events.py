# -*- test-case-name: virtualbricks.tests.test_events -*-
# Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
# Copyright (C) 2019 Virtualbricks team

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

from virtualbricks import base, console, errors
from virtualbricks.config import schema
from virtualbricks.config.schema import Int

if False:  # pyflakes
    _ = str


process_ended = "Process ended with exit code {code}"
event_error = "Error in event action. See the log for more " "information"


class EventAction(schema.Kind):
    """A console command ("vb") or a shell command ("shell")."""

    kinds = {"vb": console.VbShellCommand, "shell": console.ShellCommand}

    def check(self, value):
        if not isinstance(value, tuple(self.kinds.values())):
            raise ValueError(f"{value!r} is not an event action")

    def to_data(self, value):
        for kind, cls in self.kinds.items():
            if isinstance(value, cls):
                return {"kind": kind, "command": str(value)}

    def from_data(self, data, report, where):
        if not isinstance(data, dict):
            raise ValueError(f"{data!r} is not a table")
        kind = data.get("kind")
        command = data.get("command")
        if kind not in self.kinds:
            raise ValueError(f"{kind!r} is not vb or shell")
        if not isinstance(command, str):
            raise ValueError(f"{command!r} is not a command")
        for key in data.keys() - {"kind", "command"}:
            report.warning("unknown field, dropped", f"{where}.{key}")
        return self.kinds[kind](command)

    def format(self, value):
        return _describe_action(value)


def _describe_action(action):
    if isinstance(action, console.ShellCommand):
        return f'shell "{action}"'
    return f'vb "{action}"'


@schema.define
class EventConfig:

    actions = schema.field(schema.ListOf(EventAction()), factory=list)
    delay = schema.field(Int(), default=0)


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
        return len(self.config.actions) > 0 and self.config.delay > 0

    def get_parameters(self):
        tempstr = _("Delay: %d") % self.config.delay
        if len(self.config.actions) > 0:
            tempstr += "; " + _("Actions:")
            # Add actions cutting the tail if it's too long
            for s in self.config.actions:
                if isinstance(s, console.ShellCommand):
                    tempstr += ' "*%s",' % s
                else:
                    tempstr += ' "%s",' % s
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
        self.scheduled = reactor.callLater(
            self.config.delay, self.do_actions, deferred
        )
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
        procs = [
            defer.maybeDeferred(action.perform, self.factory)
            for action in self.config.actions
        ]
        dl = defer.DeferredList(procs, consumeErrors=True).addCallback(log_err)
        dl.chainDeferred(deferred)
        self.notify_changed()


def is_event(brick):
    return brick.get_type() == "Event"
