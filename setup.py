#!/usr/bin/env python
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

SUPPORTED_LANGS = ['it','nl','fr','de','es']

from distutils.core import setup
import os
import sys
import tempfile

if not os.access('/usr/share/virtualbricks/', os.X_OK):
	try:
		os.mkdir('/usr/share/virtualbricks')
	except:
		print "Cannot create directory. Bye."
		sys.exit(1)


FILES = [
			('/usr/bin', ['main/virtualbricks']),
			('/usr/share/virtualbricks/', ['share/virtualbricks.glade']),
			('/usr/share/applications', ['share/virtualbricks.desktop']),
			('/usr/share/pixmaps', ['share/virtualbricks.png']),
			('/usr/share/pixmaps', ['images/Connect.png']),
			('/usr/share/pixmaps', ['images/Disconnect.png']),
			('/usr/share/pixmaps', ['images/Event.png']),
			('/usr/share/pixmaps', ['images/Qemu.png']),
			('/usr/share/pixmaps', ['images/Switch.png']),
			('/usr/share/pixmaps', ['images/Tap.png']),
			('/usr/share/pixmaps', ['images/Capture.png']),
			('/usr/share/pixmaps', ['images/TunnelConnect.png']),
			('/usr/share/pixmaps', ['images/TunnelListen.png']),
			('/usr/share/pixmaps', ['images/Wirefilter.png']),
			('/usr/share/pixmaps', ['images/Wire.png']),
			('/usr/share/pixmaps', ['images/SwitchWrapper.png'])
]

tempdirs = []

for l in SUPPORTED_LANGS:
	directory_name = tempfile.mkdtemp()
	tempdirs.append(directory_name)
	command = 'msgfmt -o ' + directory_name + '/virtualbricks.mo ' + 'locale/virtualbricks/' + l + '.po'
	os.system(command)
	FILES.append(('/usr/share/locale/'+l+'/LC_MESSAGES/', [directory_name + '/virtualbricks.mo']))

setup( data_files=FILES, name='virtualbricks', version='0.5',
	description='Virtualbricks Virtualization Tools',
	license='GPL2',
	author='Daniele Lacamera, Rainer Haage, Francesco Apollonio, Pierre-Louis Bonicoli, Simone Abbati',
	author_email='qemulator-list@createweb.de',
	url='http://www.virtualbricks.eu/',
	packages=['virtualbricks', 'virtualbricks.gui'],
	package_dir = {'': '.'}
	)

#Remove compiled l10n files
for d in tempdirs:
	try:
		#Remove the compiled file
		os.unlink(d + '/virtualbricks.mo')
		# Clean up the directory
		os.removedirs(d)
	except:
		print "Not critical error while removing: %s(.virtualbricks.mo)" %d
		continue
