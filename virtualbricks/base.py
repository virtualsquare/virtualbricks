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

from virtualbricks.versions import Version
from virtualbricks.deprecated import deprecated


log = logging.getLogger(__name__)

if False:  # pyflakes
    _ = str


__metaclass__ = type


class Config(dict):
    """Generic configuration for Brick"""

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


class NewConfig:

    parameters = []

    def __init__(self, brick):
        self.__dict__["brick"] = brick
        self.__dict__["_cfg"] = dict((n, t.default) for n, t in self.parameters)

    # dict interface

    def __getitem__(self, name):
        return self._cfg[name]

    def __contains__(self, name):
        return name in self._cfg

    def get(self, name, default=None):
        return self._cfg.get(name, default)

    def keys(self):
        return self._cfg.keys()

    def iterkeys(self):
        return self._cfg.iterkeys()

    def values(self):
        return self.values()

    def itervalues(self):
        return self.itervalues()

    def items(self):
        return self.items()

    def iteritems(self):
        return self.iteritems()

    def __iter__(self):
        return iter(self._cfg)

    # XXX: check this interface

    def __getattr__(self, name):
        try:
            return self._cfg[name]
        except KeyError:
            raise AttributeError(name)

    def __setattr__(self, name, value):
        if name not in self._cfg:
            raise TypeError
        self._cfg[name] = value
        self._set_running(name, value)

    # old config interface

    def set(self, attr):
        kv = attr.split("=")
        if len(kv) < 2:
            return False
        else:
            val = ''
            if len(kv) > 2:
                val = "\"" + "=".join(v.strip('"') for v in kv[1:]) + "\""
            else:
                val += kv[1]
            self._cfg[kv[0]] = val
            #Set value for running brick
            self._set_running(kv[0], val)
            return True

    @deprecated(Version("virtualbricks", 1, 0), "__setitem__")
    def set_obj(self, key, obj):
        self._cfg[key] = obj

    def _set_running(self, name, value):
        """
        Set the value for the running brick,
        if available and running
        """
        setter = getattr(self.brick, "cbset_" + name, None)
        if setter:
            log.debug(_("setter: setting value %s for key %s"), value, name)
            setter(value)

    @deprecated(Version("virtualbricks", 1, 0))
    def dump(self):
        for key in sorted(self._cfg.iterkeys()):
            print "%s=%s" % (key, self._cfg[key])


class Parameter:

    def __init__(self, default):
        self.default = default

    def to_string(self):
        pass

    def from_string(self):
        pass


class Integer(Parameter):

    from_string = int

    def to_string(self, in_object):
        return str(int(in_object))


class SpinInt(Integer):

    def __init__(self, default=32, min=1, max=128):
        Integer.__init__(self, default)
        self.min = min
        self.max = max

    def assert_in_range(self, i):
        if i < self.min or i > self.max:
            raise ValueError(_("value out range %d (%d, %d)") % (i, self.min,
                                                                 self.max))
    def from_string(self, in_object):
        i = int(in_object)
        self.assert_in_range(i)
        return i

    def to_string(self, in_object):
        i = int(in_object)
        self.assert_in_range(i)
        return str(i)


class String(Parameter):

    def from_string(self, in_object):
        return in_object

    def to_string(self, in_object):
        return in_object


class Float(Parameter):

    from_string = float
    to_string = repr


class Boolean(Parameter):

    def from_string(self, in_object):
        return in_object.lower() in set(["true", "*", "yes"])

    def to_string(self, in_object):
        return "True" if in_object else "False"


class Base(gobject.GObject):

    __gsignals__ = {"changed": (gobject.SIGNAL_RUN_FIRST, None, ())}

    # type = None  # if not set in a subclass will raise an AttributeError
    _needsudo = False
    _name = None
    config_factory = Config

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
        self.cfg = self.config_factory()

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
