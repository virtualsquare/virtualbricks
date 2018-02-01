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

from zope.interface import implementer
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk
from gi.repository import GObject


from virtualbricks import observable
from virtualbricks.tools import dispose
from virtualbricks.gui import interfaces, graphics


if False:
    _ = str  # make pyflakes happy

try:
    _
except NameError:
    # needed to support glade
    _ = str


def set_cells_data_func(column):
    for cell in column.get_cells():
        column.set_cell_data_func(cell, cell.set_cell_data)


class CellRendererFormattable(Gtk.CellRendererText):

    __gtype_name__ = "CellRendererFormattable"
    __gproperties__ = {
        "formatting-enabled": (
            GObject.TYPE_BOOLEAN,
            _("Enable formatting"),
            _("Whether enable formatting"),
            False,
            GObject.PARAM_READWRITE
        ),
        "format-string": (
            GObject.TYPE_STRING,
            _("Format string"),
            _("The format string understand by the builtin format()"),
            "",
            GObject.PARAM_READWRITE
        ),
        "formatter": (
            GObject.TYPE_PYOBJECT,
            _("Custom formatter"),
            _("An instance of string.Formatter() class"),
            GObject.PARAM_READWRITE
        ),
        "display-member": (
            GObject.TYPE_STRING,
            _("Display member"),
            _("The member used to display the text"),
            "",
            GObject.PARAM_READWRITE
        )
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
            raise TypeError("Unknown property %r" % (pspec.name, ))

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
            raise TypeError("Unknown property %r" % (pspec.name, ))

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


class CellRendererBrickIcon(Gtk.CellRendererPixbuf):

    __gtype_name__ = "CellRendererBrickIcon"

    @staticmethod
    def set_cell_data(cell_layout, cell, model, itr, data=None):
        brick = model.get_value(itr, 0)
        pixbuf = graphics.pixbuf_for_brick_at_size(brick, 48, 48)
        cell.set_property("pixbuf", pixbuf)


SELECT_ALL = object()
SELECT_NONE = object()


class List(Gtk.ListStore):

    __gtype_name__ = "List"
    __gproperties__ = {
        "value-member": (
            GObject.TYPE_STRING,
            _("Value member"),
            _(""),
            "",
            GObject.PARAM_READWRITE
        ),
    }
    _value_member = ""
    _ibinding_list = None

    def __init__(self):
        Gtk.ListStore.__init__(self, GObject.TYPE_PYOBJECT)

    def do_get_property(self, pspec):
        if pspec.name == "value-member":
            return self._value_member
        else:
            raise TypeError("Unknown property %r" % (pspec.name, ))

    def do_set_property(self, pspec, value):
        if pspec.name == "value-member":
            self._value_member = value
        else:
            raise TypeError("Unknown property %r" % (pspec.name, ))

    def set_data_source(self, lst):
        dispose(self)
        self.clear()
        for item in lst:
            self.append((item, ))
        if interfaces.IBindingList.providedBy(lst):
            self._ibinding_list = lst
            lst.added.connect(self.on_add)
            lst.removed.connect(self.on_remove)
            lst.changed.connect(self.on_changed)

    def on_add(self, value):
        self.append((value, ))

    def on_remove(self, value):
        mbr = self._value_member
        itr = self.get_iter_first()
        while itr:
            obj = self.get_value(itr, 0)
            if (mbr and getattr(obj, mbr) == value) or obj == value:
                self.remove(itr)
                return
            itr = self.iter_next(itr)

    def on_changed(self, value):
        mbr = self._value_member
        itr = self.get_iter_first()
        while itr:
            obj = self.get_value(itr, 0)
            if (mbr and getattr(obj, mbr) == value) or obj == value:
                self.row_changed(self.get_path(itr), itr)
            itr = self.iter_next(itr)

    def __dispose__(self):
        if self._ibinding_list is not None:
            dispose(self._ibinding_list)
            self._ibinding_list = None


@implementer(interfaces.IBindingList)
class AbstractBindingList:

    def __init__(self, factory):
        self._factory = factory
        self._observable = observable.Observable("added", "removed", "changed")
        self.added = observable.Event(self._observable, "added")
        self.removed = observable.Event(self._observable, "removed")
        self.changed = observable.Event(self._observable, "changed")

    def _on_added(self, obj):
        self._observable.notify("added", obj)

    def _on_removed(self, obj):
        self._observable.notify("removed", obj)

    def _on_changed(self, obj):
        self._observable.notify("changed", obj)


class ImagesBindingList(AbstractBindingList):

    def __init__(self, factory):
        AbstractBindingList.__init__(self, factory)
        factory.connect("image-added", self._on_added)
        factory.connect("image-removed", self._on_removed)
        factory.connect("image-changed", self._on_changed)

    def __dispose__(self):
        self._factory.disconnect("image-added", self._on_added)
        self._factory.disconnect("image-removed", self._on_removed)
        self._factory.disconnect("image-changed", self._on_changed)

    def __iter__(self):
        return iter(self._factory.disk_images)


class TreeView(Gtk.TreeView):

    __gtype_name__ = "TreeView"

    def get_selection_mode(self):
        return self.get_selection().get_mode()

    def set_selection_mode(self, value):
        self.get_selection().set_mode(value)

    def get_selected_value(self):
        mode = self.get_selection().get_mode()
        if mode in (Gtk.SelectionMode.NONE, Gtk.SelectionMode.SINGLE,
                    Gtk.SelectionMode.BROWSE):
            values = self.get_selected_values()
            if values:
                return values[0]
            return None
        raise ValueError("Invalid selection mode")

    def set_selected_value(self, value):
        if value is SELECT_ALL:
            raise ValueError("Cannot select more than one node")
        elif self.get_selection().get_mode() == Gtk.SelectionMode.NONE:
            raise ValueError("Cannot select any node")
        else:
            self.set_selected_values((value, ))

    def get_selected_values(self):
        selection = self.get_selection()
        mode = selection.get_mode()
        if mode == Gtk.SelectionMode.NONE:
            return ()
        elif mode in (Gtk.SelectionMode.SINGLE, Gtk.SelectionMode.BROWSE):
            model, itr = selection.get_selected()
            if itr is None:
                return ()
            try:
                mbr = model.get_property("value-member")
                if not mbr:
                    raise TypeError
            except TypeError:
                return (model.get_value(itr, 0), )
            else:
                return (getattr(model.get_value(itr, 0), mbr), )
        else:
            model, paths = selection.get_selected_rows()
            try:
                mbr = model.get_property("value-member")
                if not mbr:
                    raise TypeError
            except TypeError:
                return tuple(model.get_value(model.get_iter(path), 0)
                             for path in paths)
            else:
                return tuple(getattr(model.get_value(model.get_iter(path), 0),
                                     mbr) for path in paths)

    def set_selected_values(self, iterable):
        selection = self.get_selection()
        mode = selection.get_mode()
        if iterable is SELECT_ALL:
            if mode != Gtk.SelectionMode.MULTIPLE:
                raise ValueError("Cannot select all the nodes")
            selection.select_all()
        elif iterable is SELECT_NONE:
            selection.unselect_all()
        elif mode == Gtk.SelectionMode.NONE:
            raise ValueError("Cannot select any node")
        else:
            model = self.get_model()
            selection.unselect_all()
            try:
                mbr = model.get_property("value-member")
                if not mbr:
                    raise TypeError
            except TypeError:
                for value in iterable:
                    itr = model.get_iter_first()
                    while itr:
                        obj = model.get_value(itr, 0)
                        if obj == value:
                            selection.select_iter(itr)
                        itr = model.iter_next(itr)
            else:
                for value in iterable:
                    itr = model.get_iter_first()
                    while itr:
                        obj = model.get_value(itr, 0)
                        if getattr(obj, mbr) == value:
                            selection.select_iter(itr)
                        itr = model.iter_next(itr)

    def set_cells_data_func(self):
        for column in self.get_columns():
            set_cells_data_func(column)


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
