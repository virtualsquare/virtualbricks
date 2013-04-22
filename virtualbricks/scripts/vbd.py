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

"""Usage: vbd [-vqld] [--server]

    --server            start the server
    -v, --verbose       increase log verbosity
    -q, --quiet         decrease log verbosity
    -l, --logfile=      write log messages to file
    -d, --debug         verbose debug output
    -h, --help          print this help and exit

Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
Copyright (C) Virtualbricks team
"""

from __future__ import print_function
import sys

from virtualbricks import app


def parse_opts(opts, args):
    server = False
    config = {'verbose': 0, 'logfile': None}
    for o, a in opts:
        if o in ('-h', '--help'):
            print(__doc__)
            return 0
        elif o in ('-v', '--verbose'):
            config['verbose'] += 1
        elif o in ('-q', '--quiet'):
            config['verbose'] -= 1
        elif o == '--server':
            server = True
        elif o in ('-l', '--logfile'):
            config['logfile'] = a
        elif o in ('-d', '--debug'):
            config['verbose'] = 2

    from virtualbricks import brickfactory

    if server:
        application = brickfactory.ApplicationServer
    else:
        application = brickfactory.Application
    return app.run(application, config)


short_opts = 'vqld'
long_opts = ['server', 'help', 'verbose', 'quiet', 'logfile=', 'debug']
main = app.usage_wrapper(parse_opts, short_opts, long_opts)


def run():
    return sys.exit(main())
