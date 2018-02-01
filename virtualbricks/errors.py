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


class InvalidTypeError(Error, ValueError):
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


class LockedImageError(Error):

    def __init__(self, image, master):
        Exception.__init__(self, image, master)
        self.image = image
        self.master = master

    def __repr__(self):
        return "Image {0} already locked by {1}".format(self.image,
                                                        self.master)


class ImageAlreadyInUseError(Error):
    pass


# Project specific errors

class ProjectExistsError(InvalidNameError):
    pass


class ProjectNotExistsError(InvalidNameError):
    pass


class InvalidArchiveError(Error):
    """The archive format is not recognized."""


class BrickRunningError(Error):
    """There is one or more brick that is running."""


class NoOptionError(Error):
    '''The config file has no such option.'''
