#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging

class Logger(object):
	def __init__(self, logger):
		self.logger = logger

	def debug(self, *args, **kwargs):
		self.logger.debug(*args, **kwargs)

	def info(self, *args, **kwargs):
		self.logger.info(*args, **kwargs)

	def warning(self, *args, **kwargs):
		self.logger.warning(*args, **kwargs)

	def error(self, *args, **kwargs):
		self.logger.error(*args, **kwargs)

	def critical(self, *args, **kwargs):
		self.logger.critical(*args, **kwargs)

class ChildLogger(Logger):
	def __init__(self, logger, name=None):
		if name is not None:
			logger = logging.getLogger('%s.%s' % (logger.name, name))

		Logger.__init__(self, logger)

