# -*- test-case-name: virtualbricks.tests.bricks.test_event -*-
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

"""An event: actions that run after a delay."""

from twisted.internet import defer, reactor

from virtualbricks import base, errors
from virtualbricks.bricks.eventaction import EventAction
from virtualbricks.config.schema import Int, ListOf, define, field
from virtualbricks.i18n import _

process_ended = "Process ended with exit code {code}"
event_error = "Error in event action. See the log for more " "information"


@define
class EventConfig(base.BaseConfig):

    delay = field(
        Int(), default=0, help="Seconds to wait before the actions run"
    )
    actions = field(
        ListOf(EventAction()),
        factory=list,
        help="The actions: console or shell commands",
    )


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
        # a delay of 0 runs the actions at once
        return len(self.config.actions) > 0

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
        self.scheduled = None
        self.run_actions().chainDeferred(deferred)
        self.notify_changed()

    def run_actions(self):
        """Run the actions now; a wait goes on."""

        def log_err(results):
            for success, status in results:
                if success:
                    self.logger.info(process_ended, code=status)
                else:
                    self.logger.error(event_error, log_failure=status)
            return self

        procs = [
            defer.maybeDeferred(action.perform, self.factory)
            for action in self.config.actions
        ]
        return defer.DeferredList(procs, consumeErrors=True).addCallback(
            log_err
        )


def is_event(brick):
    return brick.get_type() == "Event"
