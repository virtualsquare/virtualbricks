#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging

class Logger(object):
	def __init__(self, logger):
		self.logger = logger

		self.debug = self.logger.debug
		self.info = self.logger.info
		self.warning = self.logger.warning
		self.error = self.logger.error
		self.critical = self.logger.critical

class ChildLogger(Logger):
	def __init__(self, logger=None, name=None):
		if logger is None:
			logger = logging.getLogger()
			logger.setLevel(logging.DEBUG)
			handler = logging.StreamHandler()
			logger.addHandler(handler)

		if name is not None:
			logger = logging.getLogger('%s.%s' % (logger.name, name))

		Logger.__init__(self, logger)

