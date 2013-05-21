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

import re
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

    CONFIG_LINE = re.compile(r"^(\w+?)=([\w*]+?)$")
    parameters = {}

    def __init__(self, brick):
        self.__dict__["brick"] = brick
        self.__dict__["_cfg"] = dict((name, typ.default) for name, typ in
                                     self.parameters.iteritems())

    # dict interface

    def __getitem__(self, name):
        return self._cfg[name]

    def __setitem__(self, name, value):
        self._cfg[name] = value

    def __contains__(self, name):
        return name in self._cfg

    # NOTE: old interface, values are always strings
    def get(self, name, default=None):
        val = self._cfg.get(name, default)
        if val is default:
            return val
        return self.parameters[name].to_string(val)

    def keys(self):
        return self._cfg.keys()

    def iterkeys(self):
        return self._cfg.iterkeys()

    # NOTE: old interface, values are always strings
    def iteritems(self):
        for name, value in self._cfg.iteritems():
            yield name, self.parameters[name].to_string(value)

    def __iter__(self):
        return iter(self._cfg)

    # XXX: check this interface

    def __getattr__(self, name):
        # return always a string
        if name not in self._cfg:
            raise AttributeError(name)
        return self.parameters[name].to_string(self._cfg[name])

    def __setattr__(self, name, value):
        if name not in self._cfg:
            raise TypeError(_("Brick %s(%s) has no parameter %s") %
                            (self.brick.get_name(), self.brick.get_type(),
                             name))
        self._cfg[name] = self.parameters[name].from_string(value)
        self._set_running(name, value)

    # old config interface

    def set(self, attr):
        kv = attr.split("=", 1)
        # if len(kv) < 2:
        #     return False
        if len(kv) > 1:  # == 2
            name, val = kv
            self._cfg[name] = self.parameters[name].from_string(val)
            #Set value for running brick
            self._set_running(name, val)
            # return True

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

    def dump(self, write=None):
        if write is None:
            return self._dump()
        for key in sorted(self._cfg.iterkeys()):
            write("%s=%s" % (key, self._cfg[key]))

    @deprecated(Version("virtualbricks", 1, 0))
    def _dump(self):
        # this function could not be deprecated becase is new, the behavior is
        # deprecated
        for key in sorted(self._cfg.iterkeys()):
            print "%s=%s" % (key, self._cfg[key])

    def save_to(self, fileobj):
        fileobj.write("[{brick.type}:{brick.name}]\n".format(brick=self.brick))
        for name, param in sorted(self.parameters.iteritems()):
            if self[name] != param.default and not isinstance(param, Object):
                fileobj.write("%s=%s\n" % (name, param.to_string(self[name])))

    def load_from(self, fileobj):
        curpos = fileobj.tell()
        line = fileobj.readline()
        while True:
            if not line:
                break
            if line.startswith("#"):
                curpos = fileobj.tell()
                line = fileobj.readline()
                continue
            match = self.CONFIG_LINE.match(line)
            if not match:
                fileobj.seek(curpos)
                break
            else:
                name, value = match.groups()
                self[name] = self.parameters[name].from_string(value)
                curpos = fileobj.tell()
                line = fileobj.readline()


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
        return "*" if in_object else ""


class Object(Parameter):
    """A special parameter that is never translated to or from a string."""
    # XXX: pratically the same of a string

    def from_string(self, in_object):
        return in_object

    def to_string(self, in_object):
        return in_object


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
        if issubclass(self.config_factory, NewConfig):
            self.cfg = self.config_factory(self)
        else:
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
