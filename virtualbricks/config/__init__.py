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

The package exports only the names that the rest of Virtualbricks imports
from it, by name, not from its modules: ``from virtualbricks.config import
field``. The names that would be ambiguous outside their module say what they
are about: ``get_setting``, ``load_toml``, ``load_record``, ``dump_toml``,
``dump_record``, ``field_names`` and so on. What only the tests need is
imported from its module, as in ``from virtualbricks.config.workspace import
Workspace``. A name is added here when code outside the package starts to need
it, and removed when it stops.
"""

from virtualbricks.config.report import (
    ERROR,
    INFO,
    WARNING,
    Level,
    Message,
    Report,
)
from virtualbricks.config.schema import (
    Bool,
    Choice,
    Float,
    IPv4,
    Int,
    Kind,
    ListOf,
    Mac,
    Path,
    Record,
    Ref,
    Str,
    default as field_default,
    define,
    dump as dump_record,
    field,
    kind_of,
    load as load_record,
    names as field_names,
    parse as parse_value,
    rename_references,
    values as field_values,
)
from virtualbricks.config.tomlfile import (
    DecodeError,
    Table,
    dump as dump_toml,
    load as load_toml,
)
from virtualbricks.config.settings import (
    COW_FORMATS,
    FORMAT as SETTINGS_FORMAT,
    PROJECT_KEYS,
    AppSettings,
    ProjectSettings,
    SettingValue,
    current_project,
    get as get_setting,
    get_app as get_app_setting,
    has_option,
    load as load_settings,
    load_state,
    new_project_settings,
    parse as parse_setting,
    project_settings,
    set as set_setting,
    set_app as set_app_setting,
    store as store_settings,
)
from virtualbricks.config.projectfile import (
    DEFAULT_MODEL,
    SOCKET_NAME,
    ProjectFormatError,
    document as project_document,
)
from virtualbricks.config.workspace import projects
from virtualbricks.config.archive import (
    Cancelled as ArchiveCancelled,
    export_project,
    inspect_archive,
)
from virtualbricks.config.importing import (
    import_project,
    plan_import,
    update_plan,
)

__all__ = [
    "ERROR",
    "INFO",
    "WARNING",
    "Level",
    "Message",
    "Report",
    "Bool",
    "Choice",
    "Float",
    "IPv4",
    "Int",
    "Kind",
    "ListOf",
    "Mac",
    "Path",
    "Record",
    "Ref",
    "Str",
    "field_default",
    "define",
    "dump_record",
    "field",
    "kind_of",
    "load_record",
    "field_names",
    "parse_value",
    "rename_references",
    "field_values",
    "DecodeError",
    "Table",
    "dump_toml",
    "load_toml",
    "COW_FORMATS",
    "SETTINGS_FORMAT",
    "PROJECT_KEYS",
    "AppSettings",
    "ProjectSettings",
    "SettingValue",
    "current_project",
    "get_setting",
    "get_app_setting",
    "has_option",
    "load_settings",
    "load_state",
    "new_project_settings",
    "parse_setting",
    "project_settings",
    "set_setting",
    "set_app_setting",
    "store_settings",
    "DEFAULT_MODEL",
    "SOCKET_NAME",
    "ProjectFormatError",
    "project_document",
    "projects",
    "ArchiveCancelled",
    "export_project",
    "inspect_archive",
    "import_project",
    "plan_import",
    "update_plan",
]
