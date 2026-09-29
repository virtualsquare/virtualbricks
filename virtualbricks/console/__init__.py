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
The console: commands for the terminal, the scripts and the events.

``command`` declares the commands and the kinds of their arguments,
``parser`` reads a line and completes it, ``dispatch`` runs it with
``run()``, ``output`` lays out the answers, a module per noun has its
commands, and ``terminal`` reads them in the terminal. It loads no GTK.

The package exports nothing: the rest of the code imports what it needs from
each module, as in ``from virtualbricks.console.dispatch import run``.
"""
