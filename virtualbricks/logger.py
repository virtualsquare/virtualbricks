#!/usr/bin/python
# -*- coding: utf-8 -*-

##	Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
##	Copyright (C) 2011 Virtualbricks team
##
##	This program is free software; you can redistribute it and/or
##	modify it under the terms of the GNU General Public License
##	as published by the Free Software Foundation; version 2.
##
##	This program is distributed in the hope that it will be useful,
##	but WITHOUT ANY WARRANTY; without even the implied warranty of
##	MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
##	GNU General Public License for more details.
##
##	You should have received a copy of the GNU General Public License
##	along with this program; if not, write to the Free Software
##	Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
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

	def exception(self, *args, **kwargs):
		self.logger.exception(*args, **kwargs)

class ChildLogger(Logger):
	def __init__(self, logger=None, name=None):
		if logger is None:
			logger = logging.getLogger()
			logger.setLevel(logging.INFO)
			handler = logging.StreamHandler()
			logger.addHandler(handler)

		if name is not None:
			logger = logging.getLogger('%s.%s' % (logger.name, name))

		Logger.__init__(self, logger)

