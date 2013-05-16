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


import gobject

from virtualbricks import brickconfig


class Base(gobject.GObject):

    __gsignals__ = {"changed": (gobject.SIGNAL_RUN_FIRST, None, ())}

    # type = None  # if not set in a subclass will raise an AttributeError
    _needsudo = False
    _name = None

    def get_name(self):
        return self._name

    getname = get_name

    def set_name(self, name):
        self._name = name

    name = property(get_name, set_name)

    def __init__(self, factory, name, homehost=None):
        gobject.GObject.__init__(self)
        self.factory = factory
        self._name = name
        self.settings = self.factory.settings
        self.cfg = brickconfig.BrickConfig()

    def get_type(self):
        return self.type

    def needsudo(self):
        return self.factory.TCP is None and self._needsudo

    def get_cbset(self, key):
        return getattr(self, "cbset_" + key, None)

    def signal_connect(self, signal, handler):
        return gobject.GObject.connect(self, signal, handler)

    def signal_disconnect(self, handler_id):
        return gobject.GObject.disconnect(self, handler_id)
