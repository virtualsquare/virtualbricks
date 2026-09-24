# -*- test-case-name: virtualbricks.tests.test_base -*-
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

from twisted.logger import Logger

from virtualbricks import observable
from virtualbricks.config import schema

if False:  # pyflakes
    _ = str


logger = Logger()
attribute_set = "Attribute {attr} set in {brick} with value {value}."


class Base:

    _restore = False
    # type = None  # if not set in a subclass will raise an AttributeError
    _name = None
    config_factory = None
    logger = Logger()

    def get_name(self):
        return self._name

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

    def _check_option(self, name):
        if name not in schema.names(self.config):
            raise KeyError(
                _("%(config)s config has no %(option)s option.")
                % {"config": self.name, "option": name}
            )

    def set(self, attrs):
        for name, value in attrs.items():
            self._check_option(name)
            if value != getattr(self.config, name):
                logger.info(attribute_set, attr=name, brick=self, value=value)
                setattr(self.config, name, value)
                setter = getattr(self, "cbset_" + name, None)
                if setter:
                    setter(value)
        self.notify_changed()

    def get(self, name):
        self._check_option(name)
        return getattr(self.config, name)

    def rename(self, name):
        return self.factory.rename(self, name)

    def rename_references(self, target, old, new):
        """Point the references to the image or event ``old`` at ``new``."""

        return schema.rename_references(self.config, target, old, new)

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
        raise ValueError("Invalid format string %r" % (format_string,))
