#!/usr/bin/python
#coding: utf-8

import gobject
import gtk

class BricksModel(gtk.ListStore):
	"""we create brick_added and brick_deleted because row-inserted and
	row-deleted don't allow to fetch the item added/deleted. See entry
	13.28 in pygtk FAQ"""
	BRICK_IDX = 0

	__gsignals__ = {
		'brick-added' : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE,
			(gobject.TYPE_STRING,)),
		'brick-deleted' : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE,
			(gobject.TYPE_STRING,)),
		'engine-closed' : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ()),
		'brick-stopped':  (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ()),
	}

	def __init__(self):
		gtk.ListStore.__init__(self, object)

	def add_brick(self, brick):
		"""add brick to the model and send 'brick_added' signal"""
		new_row = self.append(None)
		self.set_value(new_row, self.BRICK_IDX, brick)
		self.emit("brick-added", brick.name)

	def console_quit(self):
		self.emit("engine-closed")

	def stopped_brick(self):
		self.emit("brick-stopped")

	def del_brick(self, brick):
		"""remove brick from the model and send 'brick_deleted' signal"""
		for idx, row in enumerate(self):
			if row[self.BRICK_IDX] is brick:
				break
		else:
			return
		del self[idx]
		self.emit("brick-deleted", brick.name)

	def change_brick(self, brick):
		"""update brick which is already in the model, send 'brick_modified' signal"""
		for idx, row in enumerate(self):
			if row[self.BRICK_IDX] is brick:
				break
		else:
			# not found
			return
		modified_row = self.get_iter((idx, 0))
		# row-changed will be emitted
		self.set_value(modified_row, 0, brick)

gobject.type_register(BricksModel)

