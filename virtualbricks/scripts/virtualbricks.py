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

"""Usage: virtualbricks [-vqld] [-noterm]

    -noterm             start the gui without the console

    -v, --verbose       increase log verbosity
    -q, --quiet         decrease log verbosity
    -l, --logfile=      write log messages to file
    -b, --debug         verbose debug output
    -h, --help          print this help and exit

Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
Copyright (C) Virtualbricks team
"""

from __future__ import print_function, absolute_import
import sys
from os.path import exists
from os import getpid, remove
from virtualbricks import _settings

def rem_lock():
    try: 
	remove(_settings.LOCK_FILE)
    except e:
	pass

def run(argv=None):

    if argv is None:
        argv = sys.argv
    if "-h" in argv or "--help" in argv:
        print(__doc__)
        return 0

    try:
	if not exists(_settings.LOCK_FILE):
		f = open(_settings.LOCK_FILE,"w")
		f.write(str(getpid()))
		f.close()
    	else:
       		print("Another Virtualbricks instance is running. If this is an error, please delete /tmp/vb.lock to start Virtualbricks")
		return 0
    except e:
	pass 

    from virtualbricks.scripts import gui

    try:
        idx = argv.index("-noterm")
        argv[idx] = "--noterm"
    except ValueError:
        pass

    try:
	gui.run()
    finally:
	print("Bye bye...")
	rem_lock()
