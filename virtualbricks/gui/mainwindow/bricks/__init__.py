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
The Bricks tab of the main window.

``tab`` is the tab, on the rows of
:mod:`virtualbricks.gui.mainwindow.rowtab`; ``bricklist`` its list, a row
per brick; and ``brickmenu`` the menu of a brick, which the Topology tab
opens too. What a row says about a brick is in
:mod:`virtualbricks.bricks.brickinfo`, which the console shares. The sub
package ``config`` has the settings of each kind of brick, which the tab
shows in place of the list.

Only the classes that code outside this package imports from it are exported;
the tests import the others from their modules.
"""

from .tab import BricksTab

__all__ = ["BricksTab"]
