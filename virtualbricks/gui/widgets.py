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

from gi.repository import Gtk
from gi.repository import GObject

from virtualbricks.i18n import _


class CellRendererFormattable(Gtk.CellRendererText):

    __gtype_name__ = "CellRendererFormattable"
    __gproperties__ = {
        "formatting-enabled": (
            GObject.TYPE_BOOLEAN,
            _("Enable formatting"),
            _("Whether enable formatting"),
            False,
            GObject.PARAM_READWRITE,
        ),
        "format-string": (
            GObject.TYPE_STRING,
            _("Format string"),
            _("The format string understand by the builtin format()"),
            "",
            GObject.PARAM_READWRITE,
        ),
        "formatter": (
            GObject.TYPE_PYOBJECT,
            _("Custom formatter"),
            _("An instance of string.Formatter() class"),
            GObject.PARAM_READWRITE,
        ),
        "display-member": (
            GObject.TYPE_STRING,
            _("Display member"),
            _("The member used to display the text"),
            "",
            GObject.PARAM_READWRITE,
        ),
    }

    _formatting_enabled = False
    _format_string = ""
    _formatter = None
    _display_member = ""

    def do_get_property(self, pspec):
        if pspec.name == "formatting-enabled":
            return self._formatting_enabled
        elif pspec.name == "format-string":
            return self._format_string
        elif pspec.name == "formatter":
            return self._formatter
        elif pspec.name == "display-member":
            return self._display_member
        else:
            raise TypeError("Unknown property %r" % (pspec.name,))

    def do_set_property(self, pspec, value):
        if pspec.name == "formatting-enabled":
            self._formatting_enabled = value
        elif pspec.name == "format-string":
            self._format_string = value
        elif pspec.name == "formatter":
            self._formatter = value
        elif pspec.name == "display-member":
            self._display_member = value
        else:
            raise TypeError("Unknown property %r" % (pspec.name,))

    @staticmethod
    def set_cell_data(cell_layout, cell, model, itr, data=None):
        obj = model.get_value(itr, 0)
        if cell._formatting_enabled:
            if cell._formatter is not None:
                text = cell._formatter.format(cell._format_string, obj)
            else:
                text = format(obj, cell._format_string)
        elif cell._display_member and obj is not None:
            text = str(getattr(obj, cell._display_member))
        else:
            text = str(obj)
        cell.set_property("text", text)

    set_text = set_cell_data


class List(Gtk.ListStore):

    __gtype_name__ = "List"
    __gproperties__ = {
        "value-member": (
            GObject.TYPE_STRING,
            _("Value member"),
            "",
            "",
            GObject.PARAM_READWRITE,
        ),
    }
    _value_member = ""

    def __init__(self):
        Gtk.ListStore.__init__(self, GObject.TYPE_PYOBJECT)

    def do_get_property(self, pspec):
        if pspec.name == "value-member":
            return self._value_member
        else:
            raise TypeError("Unknown property %r" % (pspec.name,))

    def do_set_property(self, pspec, value):
        if pspec.name == "value-member":
            self._value_member = value
        else:
            raise TypeError("Unknown property %r" % (pspec.name,))

    def set_data_source(self, lst):
        self.clear()
        for item in lst:
            self.append((item,))


class ListEntry:

    def __init__(self, value, label):
        self.value = value
        self.label = label

    @classmethod
    def from_tuple(cls, pair):
        return cls(*pair)

    def __format__(self, format_string):
        if format_string == "l":
            return str(self.label)
        elif format_string in ("v", ""):
            return str(self.value)
        raise ValueError("Invalid format string " + repr(format_string))

    def __eq__(self, other):
        if not isinstance(other, self.__class__):
            return NotImplemented
        return self.value == other.value and self.label == other.label

    def __ne__(self, other):
        if not isinstance(other, self.__class__):
            return NotImplemented
        return not self.__eq__(other)


class ComboBox(Gtk.ComboBox):

    __gtype_name__ = "ComboBox"

    def get_selected_value(self):
        model = self.get_model()
        itr = self.get_active_iter()
        if itr:
            obj = model.get_value(itr, 0)
            try:
                member = model.get_property("value-member")
                if not member:
                    return obj
            except TypeError:
                return obj
            else:
                return getattr(obj, member)

    def set_selected_value(self, value):
        model = self.get_model()
        itr = model.get_iter_first()
        try:
            mbr = model.get_property("value-member")
            if not mbr:
                raise TypeError
        except TypeError:
            while itr:
                obj = model.get_value(itr, 0)
                if obj == value:
                    self.set_active_iter(itr)
                    break
                itr = model.iter_next(itr)
        else:
            while itr:
                obj = model.get_value(itr, 0)
                if getattr(obj, mbr) == value:
                    self.set_active_iter(itr)
                    break
                itr = model.iter_next(itr)
