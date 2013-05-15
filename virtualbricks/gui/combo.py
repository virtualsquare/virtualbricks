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

COMBOBOXES = dict()


def ComboBox(widget):
    if widget not in COMBOBOXES:
        COMBOBOXES[widget] = ComboBoxObj(widget)
    return COMBOBOXES[widget]


class ComboBoxObj:

    def __init__(self, widget):
        self.widget = widget
        self.model = self.widget.get_model()
        self.options = dict()

    def populate(self, args, selected=None, clear=True):
        """args is dict[showing_name] = real name"""
        if clear:
            self.clear()
        self.options.update(args)
        items = sorted((v, k) for k, v in self.options.items())
        for k, v in ((k, v) for v, k in items):
            self.widget.append_text(k)
        if selected:
            self.select(selected)

    def clear(self):
        self.options.clear()
        self.widget.set_model(None)
        self.model.clear()
        self.widget.set_model(self.model)

    def select(self, regexp):
        index = self.model.get_iter_first()
        while index is not None:
            value = self.model.get_value(index, 0)
            if value == regexp:
                self.widget.set_active_iter(index)
                break
            index = self.model.iter_next(index)

    def get_selected(self):
        return self.options.get(self.widget.get_active_text(), None)
