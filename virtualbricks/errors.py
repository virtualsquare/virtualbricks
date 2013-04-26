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
    """Inherit from errors.InvalidName for backward compatibility."""

InvalidName = InvalidNameError


class NameAlreadyInUseError(InvalidNameError):
    pass


class InvalidTypeError(Error):
    pass


class BadConfigError(Error):
    pass

BadConfig = BadConfigError


class NotConnectedError(Error):
    pass

NotConnected = NotConnectedError


class LinkloopError(Error):
    pass

Linkloop = LinkloopError


class UnmanagedTypeError(Error):
    pass

UnmanagedType = UnmanagedTypeError


class InvalidActionError(Error):
    pass

InvalidAction = InvalidActionError


class DiskLockedError(Error):
    pass

DiskLocked = DiskLockedError
