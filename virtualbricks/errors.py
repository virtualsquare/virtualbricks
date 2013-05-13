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


class Error(Exception):
    pass


class InvalidNameError(Error):
    pass


class NameAlreadyInUseError(InvalidNameError):

    def __init__(self, name):
        InvalidNameError.__init__(self, name)
        self.name = name

    def __str__(self):
        return _("Normalized name %s already in use") % self.name


class InvalidTypeError(Error):
    pass


class BadConfigError(Error):
    pass


class NotConnectedError(Error):
    pass


class LinkLoopError(Error):
    pass


class UnmanagedTypeError(Error):
    pass


class InvalidActionError(Error):
    pass


class DiskLockedError(Error):
    pass
