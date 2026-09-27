# Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
# Copyright (C) 2019 Virtualbricks team

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

"""
The Images tab of the main window.

``tab`` is the tab, with its rows, on those of
:mod:`virtualbricks.gui.mainwindow.rowtab`; ``imagemenu`` the menu of an
image; ``imagedetails`` the details of an image, in the tab. What a row says
is :mod:`virtualbricks.gui.imageinfo`'s, which the windows of the images
share.

Only the classes that code outside this package imports from it are exported;
the tests import the others from their modules.
"""

from .tab import ImagesTab

__all__ = ["ImagesTab"]
