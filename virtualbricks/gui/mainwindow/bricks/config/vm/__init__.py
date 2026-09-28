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
The panel of a virtual machine: a sidebar of sections, and the one chosen.

The machine's QEMU program says what it has, as it does to the start: the
lists of the pickers are its answers, and what it lacks shows under the
settings, with the words of the start. A section with a problem has a mark
in the sidebar. The panel asks again when the program or the machine type
changes; until the answers come, a picker shows only the machine's choice.
"""
