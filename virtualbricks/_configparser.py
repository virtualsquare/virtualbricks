# -*- test-case-name: virtualbricks.tests.test_configfile.TestParser -*-
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

import re
import collections

__metaclass__ = type


class Section:

    EMPTY = re.compile(r"^\s*$")
    CONFIG_LINE = re.compile(r"^(\w+)\s*=\s*(.*)$")

    def __init__(self, type, name, fileobj):
        self.type = type
        self.name = name
        self.fileobj = fileobj

    def __iter__(self):
        curpos = self.fileobj.tell()
        line = self.fileobj.readline()
        while line:
            if line.startswith("#") or self.EMPTY.match(line):
                curpos = self.fileobj.tell()
                line = self.fileobj.readline()
                continue
            match = self.CONFIG_LINE.match(line)
            if match:
                name, value = match.groups()
                if value is None:
                    # value is None when the parameter is not set
                    value = ""
                yield name, value
                curpos = self.fileobj.tell()
                line = self.fileobj.readline()
            else:
                self.fileobj.seek(curpos)
                return


Link = collections.namedtuple("Link", ["type", "owner", "sockname", "model",
                                       "mac"])


class Parser:

    EMPTY = re.compile(r"^\s*$")
    SECTION_HEADER = re.compile(r"^\[([a-zA-Z0-9_]+):(.+)\]$")
    LINK = re.compile(r"^(?P<type>link|sock)\|"
                      "(?P<owner>[a-zA-Z][\w.-]*)\|"
                      "(?P<sockname>[a-zA-Z_][\w.-]*)\|"
                      "(?P<model>\w*)\|"
                      "(?P<mac>(?:(?:[0-9a-hA-H]{2}:){5}[0-9a-hA-H]{2})|)$")

    def __init__(self, fileobj):
        self.fileobj = fileobj

    def __iter__(self):
        """Iter through sections. There are two kinds of sections: bricks,
        events and images are one kind of section and links and socks are the
        second kind of section.
        """

        line = self.fileobj.readline()
        while line:
            if line.startswith('#') or self.EMPTY.match(line):
                line = self.fileobj.readline()
                continue
            match = self.SECTION_HEADER.match(line)
            if match:
                yield Section(match.group(1), match.group(2), self.fileobj)
            else:
                match = self.LINK.match(line)
                if match:
                    yield Link._make(match.groups())
            line = self.fileobj.readline()
