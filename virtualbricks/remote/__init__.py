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
The windows of a Virtualbricks that runs on another machine (page 19).

``commands`` has the AMP commands of the windows and of the pushes, in
protocol 2 beside the typed commands of the console, and ``follower`` the
side of the Virtualbricks that runs the bricks: it sends the project, then
each change, to the connections that follow it. It loads no GTK.

The package exports nothing: the rest of the code imports what it needs from
each module.
"""
