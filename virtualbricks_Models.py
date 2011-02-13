#!/usr/bin/python
#coding: utf-8

import gobject
import gtk

class BricksModel(gtk.ListStore):
	BRICK_IDX = 0

	__gsignals__ = {
		'brick_added' : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE,
			(gobject.TYPE_STRING,)),
		'brick_deleted' : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE,
			(gobject.TYPE_STRING,)),
	}

	def __init__(self):
		gtk.ListStore.__init__(self, object)

	def add_brick(self, brick):
		new_row = self.append(None)
		self.set_value(new_row, self.BRICK_IDX, brick)
		self.emit("brick_added", brick.name)

	def del_brick(self, brick_to_delete):
		for idx, row in enumerate(self):
			if row[self.BRICK_IDX] is brick_to_delete:
				break
		else:
			return
		del self[idx]
		self.emit("brick_deleted", brick_to_delete.name)

gobject.type_register(BricksModel)

