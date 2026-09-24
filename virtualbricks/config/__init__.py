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
The configuration: its files, their locations and the schemas of their data.

- ``locations``: where the files are, following the XDG directories.
- ``schema``: the declarative schemas of the settings and of the bricks.
- ``tomlfile``: reading and atomically writing TOML files.
- ``report``: the problems found while reading a file.
- ``settings``: the settings of the application and of the open project.
- ``projectfile``: the project file, ``project.toml``.
"""

# The names that the rest of Virtualbricks takes from the configuration. The
# modules themselves are imported as virtualbricks.config.schema and so on.
from virtualbricks.config.report import ERROR, INFO, WARNING, Message, Report
from virtualbricks.config.schema import (
    Bool,
    Choice,
    Float,
    Int,
    IPv4,
    Kind,
    ListOf,
    Mac,
    Path,
    Record,
    Ref,
    Str,
)
from virtualbricks.config.projectfile import ProjectFormatError

__all__ = [
    "ERROR",
    "INFO",
    "WARNING",
    "Bool",
    "Choice",
    "Float",
    "Int",
    "IPv4",
    "Kind",
    "ListOf",
    "Mac",
    "Message",
    "Path",
    "ProjectFormatError",
    "Record",
    "Ref",
    "Report",
    "Str",
]
