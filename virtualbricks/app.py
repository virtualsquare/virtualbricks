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

import logging
log = logging.getLogger('virtualbricks')


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
        try:
            application.start()
        except StandardError:
            log.exception('Someting bad happened')
        finally:
            application.quit()
            self.logger.stop()
