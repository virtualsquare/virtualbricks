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


import logging

import gobject


log = logging.getLogger(__name__)

if False:  # pyflakes
    _ = str


class BrickConfig(dict):
    """Generic configuration for Brick

    >>> cfg = BrickConfig()
    >>> cfg.enabled = True
    >>> cfg['enabled'] == True
    True
    >>> cfg.enabled == True
    True
    >>> cfg.disabled = True
    >>> cfg['disabled'] == True
    True
    >>> cfg.disabled == True
    True
    >>> from copy import deepcopy
    >>> cfg2 = deepcopy(cfg)
    """
    def __getattr__(self, name):
        """override dict.__getattr__"""
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name)

    def __setattr__(self, name, value):
        """override dict.__setattr__"""
        self[name] = value
        #Set value for running brick
        self.set_running(name, value)

    def set(self, attr):
        kv = attr.split("=")
        if len(kv) < 2:
            return False
        else:
            val = ''
            if len(kv) > 2:
                val = '"'
                for c in kv[1:]:
                    val += c.lstrip('"').rstrip('"')
                    val += "="
                val = val.rstrip('=') + '"'
            else:
                val += kv[1]
            self[kv[0]] = val
            #Set value for running brick
            self.set_running(kv[0], val)
            return True

    def set_obj(self, key, obj):
        self[key] = obj

    def set_running(self, key, value):
        """
        Set the value for the running brick,
        if available and running
        """
        import inspect
        stack = inspect.stack()
        frame = stack[2][0]
        obj = frame.f_locals.get('self', None)
        if obj is not None:
            if hasattr(obj, "get_cbset"):
                setter = obj.get_cbset(key)
                if setter is not None:
                    log.debug(_("setter: setting value %s for key %s"), value,
                              key)
                    setter(value)

    def dump(self):
        keys = sorted(self.keys())
        for k in keys:
            print "%s=%s" % (k, self[k])


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
        self.cfg = BrickConfig()

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
