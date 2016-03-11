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
import sys
import collections


_Version = collections.namedtuple("_Version", ["major", "minor", "micro",
                                               "prerelease"])


class Version(_Version):
    """Utility class to represent a version.

    Copy&paste from twisted. All rights to them.
    """

    def __new__(self, package, major, minor, micro=0, prerelease=None):
        self.package = package
        return _Version.__new__(self, major, minor, micro, prerelease)

    def _make(cls, package, iterable, new=tuple.__new__, len=len):
        raise NotImplementedError("Version._make not implemented")

    def short(self):
        """
        Return a string in canonical short version format,
        <major>.<minor>.<micro>[+rVer].
        """
        bzrver = self._getBazaarVersion()
        if bzrver:
            return str(self) + '+r' + bzrver
        return str(self)

    def __str__(self):
        if self.prerelease is None:
            pre = ""
        else:
            pre = "~pre%s" % (self.prerelease,)
        return '%d.%d.%d%s' % (self.major,
                               self.minor,
                               self.micro,
                               pre)

    def _getBazaarVersion(self):
        mod = sys.modules.get(self.package)
        if mod:
            bzr = os.path.join(os.path.dirname(mod.__file__), "..", ".bzr")
            if not os.path.exists(bzr):
                return None

            lastrev = os.path.join(bzr, "branch", "last-revision")
            if os.path.exists(lastrev):
                try:
                    with open(lastrev) as fp:
                        return fp.readline().split()[0]
                except Exception:
                    return "Unknown"
