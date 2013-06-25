# -*- test-case-name: virtualbricks.tests.test_base -*-
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

from twisted.python import reflect
from twisted.python.versions import Version
from twisted.python.deprecate import deprecated

from virtualbricks import _compat


log = _compat.getLogger(__name__)

if False:  # pyflakes
    _ = str


__metaclass__ = type


class Config(dict):

    CONFIG_LINE = re.compile(r"^(\w+?)=(.*)$")
    parameters = {}

    def __init__(self):
        parameters = {}
        reflect.accumulateClassDict(self.__class__, "parameters", parameters)
        self.parameters = parameters
        super(Config, self).__init__((n, v.default) for n, v
                                     in parameters.iteritems())

    # dict interface

    def __setitem__(self, name, value):
        if name not in self.parameters:
            raise ValueError(_("Parameter %s not found") % name)
        super(Config, self).__setitem__(name, value)

    # NOTE: old interface, values are always strings
    def get(self, name, default=None):
        val = super(Config, self).get(name, default)
        if val is default:
            return val
        return self.parameters[name].to_string(val)

    # XXX: check this interface
    def __getattr__(self, name):
        # return always a string
        if name not in self.parameters:
            raise AttributeError(name)
        return self.parameters[name].to_string(self[name])

    def dump(self, write):
        for key in sorted(self.iterkeys()):
            write("%s=%s" % (key, self[key]))


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


class ListOf(Parameter):

    def __init__(self, element_type):
        # New there is a problem with this approach, the state is shared across
        # all instances and require that a subclass of Config sets a new value
        # in its contructor.
        Parameter.__init__(self, [])
        self.element_type = element_type

    def from_string(self, in_object):
        strings = eval(in_object, {}, {})
        return map(self.element_type.from_string, strings)

    def to_string(self, in_object):
        return str(map(self.element_type.to_string, in_object))


class Base(object):

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

    def __init__(self, factory, name):
        self.factory = factory
        self._name = name
        self.config = self.config_factory()

    def get_type(self):
        return self.type

    def needsudo(self):
        return self._needsudo

    def set(self, attrs):
        for name, value in attrs.iteritems():
            if value != self.config[name]:
                self.config[name] = value
                setter = getattr(self, "cbset_" + name, None)
                if setter:
                    log.msg("%s: callback '%s' with argument %s" %
                            (self.name, name, value))
                    setter(value)

    def get(self, name):
        try:
            return self.config[name]
        except KeyError:
            raise KeyError(_("%s config has no %s option.") % (self.name,
                                                               name))

    def load_from(self, fileobj):
        attrs = {}
        curpos = fileobj.tell()
        line = fileobj.readline()
        while True:
            if not line:
                # end of file
                break
            if line.startswith("#"):
                curpos = fileobj.tell()
                line = fileobj.readline()
                continue
            match = self.config.CONFIG_LINE.match(line)
            if not match:
                fileobj.seek(curpos)
                break
            else:
                name, value = match.groups()
                if value is None:
                    # value is None when the parameter is not set
                    value = ""
                attrs[name] = self.config.parameters[name].from_string(value)
                curpos = fileobj.tell()
                line = fileobj.readline()
        self.set(attrs)

    def save_to(self, fileobj):
        config = self.config
        fileobj.write("[%s:%s]\n" % (self.get_type(), self.name))
        for name, param in sorted(config.parameters.iteritems()):
            if config[name] != param.default and not isinstance(param, Object):
                fileobj.write("%s=%s\n" % (name,
                                           param.to_string(config[name])))
        fileobj.write("\n")
