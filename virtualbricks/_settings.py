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

import os
import ConfigParser

from virtualbricks import tools, log


if False:  # pyflakes
    _ = str


logger = log.Logger()
config_loaded = log.Event("Configuration loaded ({filename})")
config_saved = log.Event("Default configuration saved ({filename})")
cannot_read_config = log.Event("Cannot read config file {filename}")
cannot_save_config = log.Event("Cannot save default configuration")


HOME = os.path.expanduser("~")
VIRTUALBRICKS_HOME = os.path.join(HOME, ".virtualbricks")
CONFIGFILE = os.path.join(HOME, ".virtualbricks.conf")
DEFAULT_WORKSPACE = VIRTUALBRICKS_HOME
DEFAULT_PROJECT = "new_project"
DEFAULT_CONF = {
    "term": "/usr/bin/xterm",
    "alt-term": "/usr/bin/gnome-terminal",
    "sudo": "/usr/bin/gksu",
    "qemupath": "/usr/bin",
    "kvm": False,
    "ksm": False,
    "kqemu": False,
    "cdroms": "",
    "vdepath": "/usr/bin",
    "python": False,
    "femaleplugs": False,
    "erroronloop": False,
    "systray": True,
    "workspace": DEFAULT_WORKSPACE,
    "current_project": DEFAULT_PROJECT,
    "cowfmt": "qcow2",
    "show_missing": True
}


class Settings:

    class __metaclass__(type):

        def __new__(cls, name, bases, dct):

            def make_property(opt):

                def get(self):
                    return self.config.getboolean(self.DEFAULT_SECTION, opt)

                def set(self, val):
                    return self.config.set(self.DEFAULT_SECTION, opt,
                                           bool(val))
                dct["get_" + opt] = get
                dct["set_" + opt] = set
                dct[opt] = property(get, set)

            for opt in dct["__boolean_values__"]:
                make_property(opt)

            return type.__new__(cls, name, bases, dct)

    __boolean_values__ = ('kvm', 'ksm', 'kqemu', 'python', 'femaleplugs',
                          'erroronloop', 'systray', 'show_missing')
    DEFAULT_SECTION = "Main"
    DEFAULT_PROJECT = DEFAULT_PROJECT
    VIRTUALBRICKS_HOME = VIRTUALBRICKS_HOME
    DEFAULT_HOME = VIRTUALBRICKS_HOME
    __name__ = "virtualbricks.settings"

    def __init__(self, filename=CONFIGFILE):
        self.filename = filename
        self.config = ConfigParser.SafeConfigParser()
        self.config.add_section(self.DEFAULT_SECTION)
        for key, value in DEFAULT_CONF.items():
            self.config.set(self.DEFAULT_SECTION, key, str(value))

    def has_option(self, name):
        return self.config.has_option(self.DEFAULT_SECTION, name)

    def __contrains__(self, name):
        return self.config.has_option(self.DEFAULT_SECTION, name)

    def get(self, attr):
        if attr in self.__boolean_values__:
            return self.config.getboolean(self.DEFAULT_SECTION, attr)
        if attr == 'sudo' and os.getuid() == 0:
            return ''
        return self.config.get(self.DEFAULT_SECTION, str(attr))

    def set(self, attr, value):
        self.config.set(self.DEFAULT_SECTION, attr, str(value))

    def store(self):
        with open(self.filename, "w") as fp:
            self.config.write(fp)

    def load(self):
        if os.path.exists(self.filename):
            try:
                self.config.read(self.filename)
                log.info(config_loaded, filename=self.filename)
            except ConfigParser.Error:
                log.exception(cannot_read_config, filename=self.filename)
        else:
            log.info(config_loaded, filename=self.filename)
            try:
                with open(self.filename, "w") as fp:
                    self.config.write(fp)
                log.info(config_saved, filename=self.filename)
            except IOError:
                log.exception(cannot_save_config)

        tools.enable_ksm(self.ksm, self.get("sudo"))


def install(settings):
    import sys
    import virtualbricks
    if "virtualbricks.settings" in sys.modules:
        raise RuntimeError("Settings already parsed.")
    virtualbricks.settings = settings
    sys.modules["virtualbricks.settings"] = settings
