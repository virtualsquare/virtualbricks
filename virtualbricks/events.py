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

import logging
import subprocess
import threading

from virtualbricks import base, errors, console


if False:  # pyflakes
    _ = str


log = logging.getLogger(__name__)


class Event(base.Base):

    type = "Event"
    active = False
    gui_changed = False
    need_restart_to_apply_changes = False
    internal_console = None
    timer = None

    def __init__(self, factory, name):
        base.Base.__init__(self, factory, name)
        self.cfg.actions = list()
        self.cfg.delay = 0
        # self.emit("changed")

    def get_state(self):
        """return state of the event"""
        if self.active:
            state = _('running')
        elif not self.configured():
            state = _('unconfigured')
        else:
            state = _('off')
        return state

    def change_state(self):
        if self.active:
            self.poweroff()
        else:
            self.poweron()

    def configured(self):
        return (len(self.cfg.actions) > 0 and self.cfg.delay > 0)

    def initialize(self, attrlist):
        if 'add' in attrlist and 'addsh' in attrlist:
            raise errors.InvalidActionError(_("Error: config line must "
                                              "contain add OR addsh."))
        elif('add' in attrlist):
            configactions = list()
            configactions = (' '.join(attrlist)).split('add')
            for action in configactions[1:]:
                action = action.strip()
                self.cfg.actions.append(console.VbShellCommand(action))
                log.info(_("Added vb-shell command: '%s'"), action)
        elif('addsh' in attrlist):
            configactions = list()
            configactions = (' '.join(attrlist)).split('addsh')
            for action in configactions[1:]:
                action = action.strip()
                self.cfg.actions.append(console.ShellCommand(action))
                log.info(_("Added host-shell command: '%s'"), action)
        else:
            for attr in attrlist:
                self.cfg.set(attr)

    def properly_connected(self):
        return True

    def get_parameters(self):
        tempstr = _("Delay") + ": %d" % int(self.cfg.delay)
        l = len(self.cfg.actions)
        if l > 0:
            tempstr += "; " + _("Actions") + ":"
            #Add actions cutting the tail if it's too long
            for s in self.cfg.actions:
                if isinstance(s, console.ShellCommand):
                    tempstr += " \"*%s\"," % s
                else:
                    tempstr += " \"%s\"," % s
            #Remove the last character
            tempstr = tempstr[0:-1]
        return tempstr

    def connect(self, endpoint):
        return True

    def disconnect(self):
        return

    def configure(self, attrlist):
        self.initialize(attrlist)
        # TODO brick should be gobject and a signal should be launched
        self.emit("changed")
        self.timer = threading.Timer(float(self.cfg.delay), self.doactions)

    ############################
    ########### Poweron/Poweroff
    ############################
    def poweron(self):
        if not self.configured():
            raise errors.BadConfigError("Event %s not configured", self.name)
        if self.active:
            self.timer.cancel()
            self.active = False
            self.factory.emit("event-stopped", self.name)
            self.timer = threading.Timer(float(self.cfg.delay), self.doactions)
        try:
            self.timer.start()
        except RuntimeError:
            pass
        self.active = True
        self.factory.emit("event-started", self.name)

    def poweroff(self):
        if not self.active:
            return
        self.timer.cancel()
        self.active = False
        #We get ready for new poweron
        self.timer = threading.Timer(float(self.cfg.delay), self.doactions)
        self.factory.emit("event-stopped", self.name)

    def doactions(self):
        for action in self.cfg.actions:
            if (isinstance(action, console.VbShellCommand)):
                console.Parse(self.factory, action)
            elif (isinstance(action, console.ShellCommand)):
                try:
                    subprocess.Popen(action, shell=True)
                except:
                    log.error("Error: cannot execute shell command %s", action)
                    continue
#            else:
#                #it is an event
#                action.poweron()

        self.active = False
        #We get ready for new poweron
        self.timer = threading.Timer(float(self.cfg.delay), self.doactions, ())
        self.factory.emit("event-accomplished", self.name)

    def on_config_changed(self):
        self.emit("changed")

    #############################
    # Console related operations.
    #############################
    def has_console(self):
            return False

    def close_tty(self):
        return
