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

import attr
from twisted.internet import defer, reactor

from virtualbricks import errors
from virtualbricks.bricks import Base, BaseConfig
from virtualbricks.bricks.eventaction import (
    EventAction,
    ShellAction,
    StartAction,
    StopAction,
    describe,
)
from virtualbricks.console.command import CommandError
from virtualbricks.config.schema import Int, ListOf, define, field

process_ended = "Process ended with exit code {code}"
action_failed = "Event {event}, action {number}, {action}: {error}"


@define
class EventConfig(BaseConfig):

    delay = field(
        Int(), default=0, help="Seconds to wait before the actions run"
    )
    actions = field(
        ListOf(EventAction()),
        factory=list,
        help="The actions: start or stop a brick or an event, or a command"
        " of the console or of the shell",
    )


class Event(Base):

    type = "Event"
    scheduled = None
    config_factory = EventConfig

    def __isrunning__(self):
        return self.scheduled is not None

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
        self.changed.notify(self)
        return deferred

    def poweroff(self):
        if self.scheduled is None:
            return
        self.scheduled.cancel()
        self.scheduled = None
        self.changed.notify(self)

    def do_actions(self, deferred):
        self.scheduled = None
        self.run_actions().chainDeferred(deferred)
        self.changed.notify(self)

    def run_actions(self):
        """Run the actions now; a wait goes on. Each that fails is logged."""

        def logged(results):
            for number, (success, result) in enumerate(results, start=1):
                action = self.config.actions[number - 1]
                if success:
                    if isinstance(action, ShellAction):
                        self.logger.info(process_ended, code=result)
                elif result.check(errors.Error, CommandError, ValueError):
                    self.logger.error(
                        action_failed,
                        event=self.name,
                        number=number,
                        action=describe(action),
                        error=result.getErrorMessage(),
                    )
                else:
                    self.logger.failure(
                        action_failed,
                        result,
                        event=self.name,
                        number=number,
                        action=describe(action),
                        error=result.getErrorMessage(),
                    )
            return self

        actions = list(self.config.actions)
        procs = [
            defer.maybeDeferred(action.perform, self.factory)
            for action in actions
        ]
        return defer.DeferredList(procs, consumeErrors=True).addCallback(
            logged
        )

    def rename_references(self, target, old, new):
        """
        Point the references to old at new: those of the settings, and the
        targets of the actions that start or stop a brick or an event.
        """

        changed = super().rename_references(target, old, new)
        if target in ("brick", "event"):
            actions = [
                (
                    attr.evolve(action, target=new)
                    if isinstance(action, (StartAction, StopAction))
                    and action.target == old
                    else action
                )
                for action in self.config.actions
            ]
            if actions != self.config.actions:
                self.config.actions = actions
                changed = True
        return changed


def is_event(brick):
    return brick.get_type() == "Event"
