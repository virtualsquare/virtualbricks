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

"""Usage: vbgui [-vqld] [-nogui|-server|-noterm]

    -nogui              start the brickfactory without the gui
    -server             start the server without the gui
    -noterm             start the gui without the console
    Deafult: start the gui and the console

    -v, --verbose       increase log verbosity
    -q, --quiet         decrease log verbosity
    -l, --logfile=      write log messages to file
    -d, --debug         verbose debug output
    -h, --help          print this help and exit

Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
Copyright (C) Virtualbricks team
"""

from __future__ import print_function, absolute_import
import sys


def main(argv=None):
    if argv is None:
        argv = sys.argv
    if "-h" in argv or "--help" in argv:
        print(__doc__)
        return 0
    try:
        idx = argv.index("-nogui")
        from virtualbricks.scripts import vbserver
        del argv[idx]
        return vbserver.main(argv)
    except ValueError:
        pass

    try:
        idx = argv.index("-server")
        from virtualbricks.scripts import vbserver
        argv[idx] = "--server"
        return vbserver.main(argv)
    except ValueError:
        pass

    from virtualbricks.scripts import vbgui
    try:
        idx = argv.index("-noterm")
    except ValueError:
        pass
    return vbgui.main(argv)


def run():
    sys.exit(main())
