# -*- test-case-name: virtualbricks.tests.test_base -*-
# Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
# Copyright (C) 2018 Virtualbricks team

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

from virtualbricks import log, observable

import six
if six.PY3:
    def iterFixItem(self):
        super(Config, self).__init__((n, v.default) for n, v
                                     in self.parameters.items())
    def iterFixKeys(self,write):
        for key in sorted(self.keys()):
            write("%s=%s" % (key, self[key]))
    def iterFixItemAttrs(self,attrs):
        for name, value in attrs.items():
            if value != self.config[name]:
                logger.info(attribute_set, attr=name, brick=self, value=value)
                self.config[name] = value
                setter = getattr(self, "cbset_" + name, None)
                if setter:
                    setter(value)
        self.notify_changed()
    def iterFixSave(self,fileobj):
        opt_tmp = "{0}={1}"
        l = []
        for name, param in sorted(self.config.parameters.items()):
            if self.config[name] != param.default:
                value = param.to_string_brick(self.config[name], self)
                l.append(opt_tmp.format(name, value))
        if l:
            l.append("")
        tmp = "[{0}:{1}]\n{2}\n"
        fileobj.write(tmp.format(self.get_type(), self.name, "\n".join(l)))

else:
    def iterFixItem(self):
        super(Config, self).__init__((n, v.default) for n, v
                                     in self.parameters.iteritems())
    def iterFixKeys(self,write):
        for key in sorted(self.iterkeys()):
            write("%s=%s" % (key, self[key]))
    def iterFixItemAttrs(self,attrs):
        for name, value in attrs.iteritems():
            if value != self.config[name]:
                logger.info(attribute_set, attr=name, brick=self, value=value)
                self.config[name] = value
                setter = getattr(self, "cbset_" + name, None)
                if setter:
                    setter(value)
        self.notify_changed()
    def iterFixSave(self,fileobj):
        opt_tmp = "{0}={1}"
        l = []
        for name, param in sorted(self.config.parameters.iteritems()):
            if self.config[name] != param.default:
                value = param.to_string_brick(self.config[name], self)
                l.append(opt_tmp.format(name, value))
        if l:
            l.append("")
        tmp = "[{0}:{1}]\n{2}\n"
        fileobj.write(tmp.format(self.get_type(), self.name, "\n".join(l)))

if False:  # pyflakes
    _ = str


__metaclass__ = type
logger = log.Logger()
attribute_set = log.Event("Attribute {attr} set in {brick} with value "
                          "{value}.")
param_not_found = log.Event("Parameter {param} in {brick} not found. "
                            "(val: {value})")


class Config(dict):

    CONFIG_LINE = re.compile(r"^(\w+?)=(.*)$")
    parameters = {}

    def __init__(self):
        parameters = {}
        reflect.accumulateClassDict(self.__class__, "parameters", parameters)
        self.parameters = parameters
        iterFixItem(self)

    # dict interface

    def __setitem__(self, name, value):
        if name not in self.parameters:
            raise ValueError(_("Parameter %s not found") % name)
        super(Config, self).__setitem__(name, value)

    # NOTE: old interface, values are always strings
    def get(self, name, default=None):
        try:
            val = dict.__getitem__(self, name)
            return self.parameters[name].to_string(val)
        except KeyError:
            return default

    # XXX: check this interface
    def __getattr__(self, name):
        # return always a string
        if name not in self.parameters:
            raise AttributeError(name)
        return self.parameters[name].to_string(self[name])

    def dump(self, write):
        iterFixKeys(self,write)


class Parameter:

    def __init__(self, default):
        self.default = default

    def from_string_brick(self, in_string, brick):
        return self.from_string(in_string)

    def to_string_brick(self, in_object, brick):
        return self.to_string(in_object)

    def from_string(self, in_string):
        pass

    def to_string(self, in_object):
        pass


class Integer(Parameter):

    from_string = int
    to_string = str


class String(Parameter):

    def from_string(self, in_string):
        return in_string

    def to_string(self, in_object):
        return in_object


class Float(Parameter):

    from_string = float
    to_string = repr


class SpinMixin:

    def __init__(self, default=0, min=0, max=100):
        super(SpinMixin, self).__init__(default)
        self.min = min
        self.max = max

    def assert_in_range(self, i):
        if not self.min <= i <= self.max:
            raise ValueError(_("value out range {0} ({1}, {2})").format(
                i, self.min, self.max))

    def from_string(self, in_string):
        i = super(SpinMixin, self).from_string(in_string)
        self.assert_in_range(i)
        return i

    def to_string(self, in_object):
        self.assert_in_range(in_object)
        return super(SpinMixin, self).to_string(in_object)


class SpinInt(SpinMixin, Integer):
    pass


class SpinFloat(SpinMixin, Float):
    pass


class Boolean(Parameter):

    def from_string(self, in_string):
        return in_string.lower() in set(["true", "*", "yes"])

    def to_string(self, in_object):
        return "*" if in_object else ""


class Object(Parameter):
    """A special parameter that is never translated to or from a string."""
    # XXX: pratically the same of a string

    def from_string(self, in_string):
        return in_string

    def to_string(self, in_object):
        return in_object


class ListOf(Parameter):

    def __init__(self, element_type):
        # New there is a problem with this approach, the state is shared across
        # all instances and require that a subclass of Config sets a new value
        # in its contructor.
        # XXX: Is this still true?
        Parameter.__init__(self, [])
        self.element_type = element_type

    def from_string(self, in_string):
        strings = eval(in_string, {}, {})
        return map(self.element_type.from_string, strings)

    def to_string(self, in_object):
        return str(map(self.element_type.to_string, in_object))


class Base(object):

    _restore = False
    # type = None  # if not set in a subclass will raise an AttributeError
    _name = None
    config_factory = Config
    logger = log.Logger()

    def get_name(self):
        return self._name

    getname = get_name

    def set_name(self, name):
        self._name = name
        self.notify_changed()

    name = property(get_name, set_name)

    def __init__(self, factory, name):
        self._observable = observable.Observable("changed")
        self.changed = observable.Event(self._observable, "changed")
        self.factory = factory
        self._name = name
        self.config = self.config_factory()

    def get_type(self):
        return self.type

    def needsudo(self):
        return False

    def set(self, attrs):
        iterFixItemAttrs(self,attrs)

    def get(self, name):
        try:
            return self.config[name]
        except KeyError:
            raise KeyError(_("%s config has no %s option.") %
                           (self.name, name))

    def _getvalue(self, name, value):
        try:
            return self.config.parameters[name].from_string_brick(value, self)
        except KeyError:
            logger.error(param_not_found, param=name, brick=self, value=value)
            raise

    def load_from(self, section):
        self.set(dict((n, self._getvalue(n, v)) for n, v in section))

    def save_to(self, fileobj):
        iterFixSave(self,fileobj)

    def rename(self, name):
        self.set_name(self.factory.normalize_name(name))

    def set_restore(self, restore):
        self._restore = restore

    def notify_changed(self):
        if not self._restore:
            self._observable.notify("changed", self)

    def __format__(self, format_string):
        if format_string == "":
            return repr(self)
        elif format_string == "s":
            return self.get_state()
        elif format_string == "t":
            return self.get_type()
        elif format_string == "n":
            return self.name
        elif format_string == "p":
            return self.get_parameters()
        raise ValueError("Invalid format string %r" % (format_string, ))
