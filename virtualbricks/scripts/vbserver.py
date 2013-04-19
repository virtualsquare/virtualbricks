# Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
# Copyright (C) Virtualbricks team

"""Usage: vbserver [-vqld] [--server]

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
import getopt


class UsageError(Exception):

    def __init__(self, msg):
        self.msg = msg


def main(argv=None):
    if argv is None:
        argv = sys.argv
    try:
        try:
            opts, args = getopt.getopt(argv[1:], 'vqld',
                    ['server', 'help', 'verbose', 'quiet', 'logfile=',
                     'debug'])
        except getopt.error, msg:
            raise UsageError(msg)

        config = {'server': False, 'verbose': 0, 'logfile': None}
        for o, a in opts:
            if o in ('-h', '--help'):
                print(__doc__)
                return 0
            elif o in ('-v', '--verbose'):
                config['verbose'] += 1
            elif o in ('-q', '--quiet'):
                config['verbose'] -= 1
            elif o == '--server':
                config['server'] = True
            elif o in ('-l', '--logfile'):
                config['logfile'] = a
            elif o in ('-d', '--debug'):
                config['verbose'] = 2

        from virtualbricks import app, brickfactory

        runner = app.Runner(config)
        runner.application_factory = brickfactory.Application
        runner.run()
        return 0
    except UsageError, err:
        print(err.msg, file=sys.stderr)
        print("for help use --help", file=sys.stderr)
        return 2


def run():
    return sys.exit(main())
