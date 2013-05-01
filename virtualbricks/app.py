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

from __future__ import print_function

import sys
import getopt
import logging


log = logging.getLogger('virtualbricks')


class UsageError(Exception):

    def __init__(self, msg):
        self.msg = msg


class QuitError(Exception):

    def __init__(self, msg, exit_code):
        self.msg = msg
        self.exit_code = exit_code


class Logger:

    def __init__(self, config):
        self._logfilename = config.get('logfile', None)
        self._verbose = config.get('verbose', 0)

    def start(self, application):
        if self._verbose:
            log.setLevel(self._get_log_level(self._verbose))
        handler = application.get_logging_handler()

        if handler is None:
            handler = self._get_handler()
        log.addHandler(handler)
        log.info('Start logging')

    def stop(self):
        log.info('Shutting down logging')
        logging.shutdown()

    def _get_handler(self):
        if self._logfilename == '-' or not self._logfilename:
            handler = logging.StreamHandler()
        else:
            handler = logging.FileHandler(self._logfilename)
        return handler

    def _get_log_level(self, verbosity):
        if verbosity >= 2:
            return logging.DEBUG
        elif verbosity == 1:
            return logging.INFO
        elif verbosity == -1:
            return logging.ERROR
        elif verbosity <= -2:
            return logging.CRITICAL


class Runner:

    logger_factory = Logger

    def __init__(self, config):
        self.config = config
        self.logger = self.logger_factory(config)

    def run(self):
        application = self.application_factory(self.config)
        self.logger.start(application)
        application.install_locale()
        application.install_sys_hooks()
        try:
            application.start()
        finally:
            application.quit()
            self.logger.stop()


def usage_wrapper(func, short_opts, long_opts):
    def main(argv=None):
        if argv is None:
            argv = sys.argv
        try:
            try:
                opts, args = getopt.getopt(argv[1:], short_opts, long_opts)
            except getopt.error, msg:
                raise UsageError(msg)

            return func(opts, args)
        except UsageError, err:
            print(err.msg, file=sys.stderr)
            print("for help use --help", file=sys.stderr)
            return 2
    return main


def run(application, config):
    runner = Runner(config)
    runner.application_factory = application
    try:
        runner.run()
    except QuitError, err:
        print(err.msg, file=sys.stderr)
        return err.exit_code
    except KeyboardInterrupt:
        # I don't wanna catch SystemExit exception because is raised only
        # programmatically, so if someone thinks that is a good idea to
        # raise it I think he knows what he is doing. KeyboardInterrupt is
        # different because by default python translate SIG_INT into
        # KeyboardInterrupt
        pass
    return 0
