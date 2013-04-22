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

import random
import threading
import time
import sys
import re


def RandMac():
    random.seed()
    mac = "00:aa:"
    mac = mac + "%02x:" % random.getrandbits(8)
    mac = mac + "%02x:" % random.getrandbits(8)
    mac = mac + "%02x:" % random.getrandbits(8)
    mac = mac + "%02x" % random.getrandbits(8)
    return mac


def ValidName(name):
    name = str(name)
    if not re.search("\A[a-zA-Z]", name):
        return None
    while(name.startswith(' ')):
        name = name.lstrip(' ')
    while(name.endswith(' ')):
        name = name.rstrip(' ')

    name = re.sub(' ', '_', name)
    if not re.search("\A[a-zA-Z0-9_\.-]+\Z", name):
        return None
    return name


def NameNotInUse(factory, name):
    """used to determine whether the chosen name can be used or
    it has already a duplicate among bricks or events."""

    for b in factory.bricks:
        if b.name == name:
            return False

    for e in factory.events:
        if e.name == name:
            return False

    for i in factory.disk_images:
        if i.name == name:
            return False
    return True


class LoopingCall:

    daemon = True
    _name = None

    def get_name(self):
        if self._name is None:
            return repr(self)
        return self._name

    def set_name(self, name):
        self._name = name

    name = property(get_name, set_name)

    def __init__(self, timeout, function, args=(), kwds={}):
        self.__function = function
        self.__args = args
        self.__kwds = kwds
        self.__timer = None
        self.start(timeout)

    def start(self, period=None):
        self.stop()
        if period is not None:
            self.__period = period
        self.__timer = threading.Timer(self.__period, self.__call)
        self.__timer.daemon = self.daemon
        self.__timer.name = self.get_name()
        self.__timer.start()

    def stop(self):
        if self.__timer:
            self.__timer.cancel()
            self.__timer = None

    def __call(self):
        self.__function(*self.__args, **self.__kwds)
        self.start()

    def __repr__(self):
        return '<LoopingCall func=%s, args=%s, kwds=%s>' % (self.__function,
                                                            self.__args,
                                                            self.__kwds)


def AutosaveTimer(factory, timeout=180):
    t = LoopingCall(timeout, factory.configfile.save,
                    (factory.settings.get( 'current_project'),))
    t.set_name("AutosaveTimer_%d" % timeout)
    return t


AutoSaveTimer = AutosaveTimer  # backward compatibility
