# coding: utf-8

import functools
import gtk
import new

from virtualbricks_Logger import ChildLogger

class GUILogger(ChildLogger):
	def __init__(self):
		ChildLogger.__init__(self)

		self.messages_buffer = gtk.TextBuffer()

		tags = {
			'debug': {'foreground': '#a29898'},
			'info': { },
			'warning': {'foreground': '#ff9500'},
			'error': {'foreground': '#b8032e'},
			'critical': {'foreground': '#b8032e', 'background': '#000'},
		}

		for level, properties in tags.iteritems():
			tag = self.messages_buffer.create_tag(level)
			for property_name, value in properties.iteritems():
				tag.set_property(property_name, value)
			function = functools.partial(self._log, level=level)
			method = new.instancemethod(function, None, GUILogger)
			setattr(GUILogger, level, method)

	def _log(self, gui, text, *args, **kwargs):
		level = kwargs.pop('level')
		method = getattr(ChildLogger, level)
		method(self, text, *args, **kwargs)
		text = text % args
		iter = self.messages_buffer.get_end_iter()
		self.messages_buffer.insert_with_tags_by_name(iter, "%s\n" % text, level)


