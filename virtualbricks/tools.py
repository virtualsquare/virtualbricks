#!/usr/bin/python
# coding: utf-8

"""
Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
Copyright (C) 2011 Virtualbricks team

This program is free software; you can redistribute it and/or
modify it under the terms of the GNU General Public License
as published by the Free Software Foundation; version 2.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
"""

import random
from threading import Thread
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


class AutoSaveTimer(Thread):

    def __init__(self, factory):
        Thread.__init__(self)
        self.autosave_timeout = 180
        self.factory = factory

    def run(self):
        self.factory.debug("Autosaver started")
        while (self.factory.running_condition):
            for t in range(self.autosave_timeout):
                time.sleep(1)
                if not self.factory.running_condition:
                    sys.exit()
            self.factory.configfile.save(self.factory.settings.get(
                'current_project'))


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
