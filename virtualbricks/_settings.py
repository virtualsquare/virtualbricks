# Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
# Copyright (C) 2018 Virtualbricks team

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

import os
import six
from six.moves import configparser
from virtualbricks import tools, log
from virtualbricks.errors import NoOptionError


if False:  # pyflakes
    _ = str


logger = log.Logger()
config_loaded = log.Event("Configuration loaded ({filename})")
config_installed = log.Event("Default configuration saved ({filename})")
cannot_read_config = log.Event("Cannot read config file {filename}")
cannot_save_config = log.Event("Cannot save default configuration")

LOCK_FILE = "/tmp/vb.lock"
HOME = os.path.expanduser("~")
VIRTUALBRICKS_HOME = os.path.join(HOME, ".virtualbricks")
CONFIGFILE = os.path.join(HOME, ".virtualbricks.conf")
DEFAULT_WORKSPACE = VIRTUALBRICKS_HOME
DEFAULT_PROJECT = "new_project"
DEFAULT_CONF = {
    "term": "/usr/bin/xterm",
    "alt-term": "/usr/bin/gnome-terminal",
    "sudo": "/usr/bin/gksu",
    "kvm": False,
    "ksm": False,
    "cdroms": "",
    "python": False,
    "femaleplugs": False,
    "erroronloop": False,
    "systray": True,
    "workspace": DEFAULT_WORKSPACE,
    "current_project": DEFAULT_PROJECT,
    "cowfmt": "qcow2",
    "show_missing": True,
    "qemupath": "/usr/bin",
    "vdepath": "/usr/bin",
}


class SettingsMeta(type):

    def __new__(cls, name, bases, dct):

        def make_property(opt):

            def get(self):
                return self.config.getboolean(self.DEFAULT_SECTION, opt)

            dct["get_" + opt] = get
            dct[opt] = property(get)

        for opt in dct["__boolean_values__"]:
            make_property(opt)

        return type.__new__(cls, name, bases, dct)


class Settings(six.with_metaclass(SettingsMeta)):

    __boolean_values__ = ('kvm', 'ksm', 'python', 'femaleplugs',
                          'erroronloop', 'systray', 'show_missing')
    DEFAULT_SECTION = "Main"
    DEFAULT_PROJECT = DEFAULT_PROJECT
    VIRTUALBRICKS_HOME = VIRTUALBRICKS_HOME
    DEFAULT_HOME = VIRTUALBRICKS_HOME
    LOCK_FILE = LOCK_FILE
    __name__ = "virtualbricks.settings"

    def __init__(self, filename=CONFIGFILE):
        self.filename = filename
        self.config = configparser.SafeConfigParser()
        self.config.add_section(self.DEFAULT_SECTION)
        for key, value in DEFAULT_CONF.items():
            self.config.set(self.DEFAULT_SECTION, key, str(value))

    def __contrains__(self, name):
        return self.config.has_option(self.DEFAULT_SECTION, name)

    has_option = __contrains__

    def get(self, attr):
        if attr in self.__boolean_values__:
            try:
                return self.config.getboolean(self.DEFAULT_SECTION, attr)
            except configparser.NoOptionError:
                raise NoOptionError(attr)
        if attr == 'sudo' and os.getuid() == 0:
            return ''
        try:
            return self.config.get(self.DEFAULT_SECTION, str(attr))
        except configparser.NoOptionError:
            raise NoOptionError(attr)

    def set(self, attr, value):
        self.config.set(self.DEFAULT_SECTION, attr, str(value))

    def store(self):
        with open(self.filename, "w") as fp:
            self.config.write(fp)

    def load(self):
        try:
            parsed = self.config.read(self.filename)
            if not parsed:
                self.install()
            else:
                logger.info(config_loaded, filename=self.filename)
                tools.enable_ksm(self.get('ksm'), self.get("sudo"))
        except configparser.Error:
            logger.exception(cannot_read_config, filename=self.filename)

    def install(self):
        self.set("ksm", tools.check_ksm())
        try:
            self.store()
            logger.info(config_installed, filename=self.filename)
        except IOError:
            logger.exception(cannot_save_config)


def install(settings):
    import sys
    import virtualbricks
    if "virtualbricks.settings" in sys.modules:
        raise RuntimeError("Settings already parsed.")
    virtualbricks.settings = settings
    sys.modules["virtualbricks.settings"] = settings
