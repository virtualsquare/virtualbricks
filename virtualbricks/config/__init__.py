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

The rest of Virtualbricks takes what it needs from this package, by name,
not from its modules: ``from virtualbricks.config import field``. The names
that would be ambiguous outside their module say what they are about:
``get_setting``, ``load_toml``, ``load_record``, ``load_project``,
``dump_toml``, ``dump_record``, ``field_names``, ``create_project`` and so on.
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
    fields,
    info as field_info,
    kind_of,
    load as load_record,
    names as field_names,
    parse as parse_value,
    references,
    rename_references,
    values as field_values,
)
from virtualbricks.config.tomlfile import (
    DecodeError,
    Table,
    Value,
    dump as dump_toml,
    dumps,
    load as load_toml,
    loads,
)
from virtualbricks.config.settings import (
    COW_FORMATS,
    FORMAT as SETTINGS_FORMAT,
    PROJECT_KEYS,
    AppSettings,
    AppState,
    ProjectSettings,
    SettingValue,
    check_format,
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
    set_current_project,
    store as store_settings,
    store_state,
    use_project,
)
from virtualbricks.config.projectfile import (
    DEFAULT_MODEL,
    FORMAT as PROJECT_FORMAT,
    NIC_KEYS,
    SOCKET_NAME,
    ImageTable,
    ProjectFormatError,
    brick_table,
    create as create_project,
    devices_for_image,
    document as project_document,
    image_paths,
    load as load_project,
    read as read_project,
    remap_image,
    resolve as resolve_socket,
    restore as restore_project,
    save as save_project,
    socket_target,
    upgrade as upgrade_project,
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
    "fields",
    "field_info",
    "kind_of",
    "load_record",
    "field_names",
    "parse_value",
    "references",
    "rename_references",
    "field_values",
    "DecodeError",
    "Table",
    "Value",
    "dump_toml",
    "dumps",
    "load_toml",
    "loads",
    "COW_FORMATS",
    "SETTINGS_FORMAT",
    "PROJECT_KEYS",
    "AppSettings",
    "AppState",
    "ProjectSettings",
    "SettingValue",
    "check_format",
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
    "set_current_project",
    "store_settings",
    "store_state",
    "use_project",
    "DEFAULT_MODEL",
    "PROJECT_FORMAT",
    "NIC_KEYS",
    "SOCKET_NAME",
    "ImageTable",
    "ProjectFormatError",
    "brick_table",
    "create_project",
    "devices_for_image",
    "project_document",
    "image_paths",
    "load_project",
    "read_project",
    "remap_image",
    "resolve_socket",
    "restore_project",
    "save_project",
    "socket_target",
    "upgrade_project",
]
