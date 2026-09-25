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
The migration of the files of Virtualbricks 2.1 and older.

This package is the only code that reads the old formats: the rest of
Virtualbricks reads and writes only the current one, and takes what it needs
from here. The migration window is in ``virtualbricks.migrate.gui``: it
imports GTK, so it isn't imported with the package.
"""

from virtualbricks.migrate.legacy import (
    Link,
    looks_like_project,
    parse_bool,
    parse_list,
    parse_project,
    parse_settings_bool,
    read_project,
    read_settings,
    where,
)
from virtualbricks.migrate.convert import (
    MigrationError,
    convert_project,
    convert_settings,
    convert_value,
)
from virtualbricks.migrate.engine import (
    FAILED,
    MIGRATED,
    MIGRATING,
    REPORT_FILE,
    SKIPPED,
    WAITING,
    Folder,
    InPlace,
    Item,
    Migration,
    counts,
    discover,
    in_place_migration,
    lock_in_place,
    migrate_imported_project,
    migration_for,
    project_source,
    startup_migration,
)
from virtualbricks.migrate.cli import (
    EXIT_RUNNING,
    RUNNING,
    main,
)

__all__ = [
    "Link",
    "looks_like_project",
    "parse_bool",
    "parse_list",
    "parse_project",
    "parse_settings_bool",
    "read_project",
    "read_settings",
    "where",
    "MigrationError",
    "convert_project",
    "convert_settings",
    "convert_value",
    "FAILED",
    "MIGRATED",
    "MIGRATING",
    "REPORT_FILE",
    "SKIPPED",
    "WAITING",
    "Folder",
    "InPlace",
    "Item",
    "Migration",
    "counts",
    "discover",
    "in_place_migration",
    "lock_in_place",
    "migrate_imported_project",
    "migration_for",
    "project_source",
    "startup_migration",
    "EXIT_RUNNING",
    "RUNNING",
    "main",
]
