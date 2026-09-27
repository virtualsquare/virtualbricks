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
The Events tab of the main window.

``tab`` is the tab, with its rows, on those of
:mod:`virtualbricks.gui.mainwindow.rowtab`; ``eventinfo`` what a row says
about an event, without widgets; ``eventmenu`` the menu of an event;
``eventeditor`` the settings of an event, its delay and its actions; and
``newevent`` the window of New Event.

Only the classes that code outside this package imports from it are exported;
the tests import the others from their modules.
"""

from .tab import EventsTab

__all__ = ["EventsTab"]
