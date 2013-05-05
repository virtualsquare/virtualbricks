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
	for k, v in COMBOBOXES.items():
		if k == widget:
			return v
	COMBOBOXES[widget] = ComboBoxObj(widget)
	return COMBOBOXES[widget]


class ComboBoxObj:
	def __init__(self, _widget):
		self.widget = _widget
		self.model = self.widget.get_model()
		self.options = dict()

	def populate(self, args, selected=None, _clear=True):
		"""args is dict[showing_name] = real name"""
		if _clear:
			self.clear()
		for (k, v) in args.items():
			self.options[k] = v

		items = [(v, k) for k, v in self.options.items()]
		items.sort()
		items = [(k, v) for v, k in items]
		for k, v in items:
			self.widget.append_text(k)

		if selected:
			self.select(selected)

	def clear(self):
		self.options = {}
		self.widget.set_model(None)
		self.model.clear()
		self.widget.set_model(self.model)

	def select(self, regexp):
		index = self.model.get_iter_first()
		active = -1
		while index is not None:
			value = self.model.get_value(index, 0)
			if value == regexp:
				active = index
				self.widget.set_active_iter(active)
				break
			index = self.model.iter_next(index)

	def get_selected(self):
		txt = self.widget.get_active_text()
		try:
			return self.options[txt]
		except KeyError:
			return None

