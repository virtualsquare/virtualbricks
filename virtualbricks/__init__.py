# coding: utf-8

"""
Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
Copyright (C) 2011 Virtualbricks team

This program is free software; you can redistribute it and/or
modify it under the terms of the GNU General Public License
as published by the Free Software Foundation; version 2.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
"""

#Gettext stuff
try:
	import gettext
	import locale
except:
	print "locale and/or gettext for language support not installed"
	import sys
	sys.exit(1)

import gtk.glade

APP = 'virtualbricks'
DIR = '/usr/share/locale'
locale.setlocale(locale.LC_ALL, '')
for module in gtk.glade, gettext:
	module.bindtextdomain(APP, DIR)
	module.textdomain(APP)

import __builtin__
__builtin__._ = gettext.gettext

