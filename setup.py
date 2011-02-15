#!/usr/bin/env python

from distutils.core import setup
import sys,os

if not os.access('/usr/share/virtualbricks/', os.X_OK):
	try:
		os.mkdir('/usr/share/virtualbricks')
	except:
		print "Cannot create directory. Bye."
		sys.exit(1)

setup(
	data_files=[
			('/usr/bin', ['main/virtualbricks']),
			('/usr/share/virtualbricks/', ['share/virtualbricks.glade']),
			('/usr/share/pixmaps', ['share/virtualbricks.png']),
			('/usr/share/pixmaps',['images/Event.png']),
			('/usr/share/pixmaps',['images/Qemu.png']),
			('/usr/share/pixmaps',['images/Switch.png']),
			('/usr/share/pixmaps',['images/Tap.png']),
			('/usr/share/pixmaps',['images/TunnelConnect.png']),
			('/usr/share/pixmaps',['images/TunnelListen.png']),
			('/usr/share/pixmaps',['images/Wirefilter.png']),
			('/usr/share/pixmaps',['images/Wire.png'])

		],

	name='virtualbricks',
	version='0.3',
	description='Virtualbricks Virtualization Tools',
	license='GPL2',
	author='Daniele Lacamera, Rainer Haage, Francesco Apollonio, Pierre-Louis Bonicoli, Simone Abbati',
	author_email='qemulator-list@createweb.de',
	url='http://www.virtualbricks.eu/',
	packages=['virtualbricks'],
	package_dir = {'': '.'}
	)

