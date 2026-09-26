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
The configuration: its files and the schemas of their data.

- ``schema``: the declarative schemas of the settings and of the bricks.
- ``tomlfile``: reading and atomically writing TOML files.
- ``report``: the problems found while reading a file.
- ``settings``: the settings of the application and of the open project.
- ``projectfile``: the project file, ``project.toml``.
- ``workspace``: the projects of the workspace, and the one that is open.
- ``archive``: archives of projects, read and written in a process of their
  own.
- ``importing``: importing a project from an archive.

The package exports nothing: the rest of Virtualbricks imports each name
from its module, as in ``from virtualbricks.config.settings import
get_setting``.
"""
