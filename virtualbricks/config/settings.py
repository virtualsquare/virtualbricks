# -*- test-case-name: virtualbricks.tests.config.test_settings -*-
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
The settings of the application and of the open project, and the state.

The settings of the application, in ``settings.toml``, are the preferences
that aren't about a project: the workspace, the terminal, KSM, the tray icon.
The settings of a project are in its project file: a new project copies those
of the open project, and while no project is open they have their default
values. The state, in ``state.toml``, is what the application remembers, such
as the current project.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, TypeAlias, cast

from twisted.logger import Logger

from virtualbricks import locations
from virtualbricks.config.report import Report
from virtualbricks.config.schema import (
    Bool,
    Choice,
    Path,
    Str,
    define,
    dump_record,
    field,
    load_record,
    field_names,
    field_values,
    kind_of,
    parse_value,
)
from virtualbricks.config.tomlfile import (
    DecodeError,
    dump_toml,
    load_toml,
)

if TYPE_CHECKING:  # pragma: no cover
    from virtualbricks.config.schema import Kind
    from virtualbricks.config.tomlfile import Table

# The settings are strings and booleans.
SettingValue: TypeAlias = str | bool

FORMAT = 1
COW_FORMATS = ("cow", "qcow", "qcow2")

logger = Logger()
settings_loaded = "Settings loaded from {filename}"
settings_installed = "Default settings saved to {filename}"
cannot_read = "Cannot read {filename}: {error}"
cannot_save = "Cannot save {filename}"
not_overwritten = (
    "Not saving {filename}: it couldn't be read or a newer Virtualbricks "
    "wrote it"
)


def check_format(data: Table, report: Report, where: str) -> bool:
    """Return True if data has the current format, reporting otherwise."""

    value = data.get("format")
    if isinstance(value, int) and not isinstance(value, bool):
        if value == FORMAT:
            return True
        if value > FORMAT:
            report.error(
                f"written by a newer Virtualbricks (format {value})", where
            )
            return False
    report.warning(f"unknown format {value!r}, read as format {FORMAT}", where)
    return True


@define
class ProjectSettings:
    """The settings that each project has its own copy of."""

    cowfmt: str = field(Choice(*COW_FORMATS), default="qcow2")
    erroronloop: bool = field(Bool(), default=False)
    femaleplugs: bool = field(Bool(), default=False)
    qemupath: str = field(Path(), default="/usr/bin")
    vdepath: str = field(Path(), default="/usr/bin")


@define
class AppSettings:
    """The settings of the application, which aren't about a project."""

    workspace: str = field(Path(), factory=locations.default_workspace)
    term: str = field(Str(), default="/usr/bin/xterm")
    ksm: bool = field(Bool(), default=False)
    systray: bool = field(Bool(), default=True)
    show_missing: bool = field(Bool(), default=True)


@define
class AppState:

    current_project: str = field(Str(), default=locations.DEFAULT_PROJECT)


PROJECT_KEYS = frozenset(field_names(ProjectSettings))

_app = AppSettings()
_project: ProjectSettings | None = None
_state = AppState()
_settings_path: str | None = None
_state_path: str | None = None
_read_only = False


def _owner(name: str) -> type[AppSettings] | type[ProjectSettings]:
    return ProjectSettings if name in PROJECT_KEYS else AppSettings


def has_option(name: str) -> bool:
    return name in PROJECT_KEYS or name in field_names(AppSettings)


def setting_kind(name: str) -> Kind[object]:
    """The kind of a setting, which formats and parses its values."""

    return kind_of(_owner(name), name)


def get_setting(name: str) -> SettingValue:
    """
    Return the value of a setting.

    A setting of a project is the open project's, or its default while no
    project is open.
    """

    if name not in PROJECT_KEYS:
        return getattr(_app, name)
    return getattr(_project or ProjectSettings(), name)


def set_setting(name: str, value: SettingValue) -> None:
    """Change a setting; ValueError for one of a project, if none is open."""

    if name not in PROJECT_KEYS:
        setattr(_app, name, value)
    elif _project is None:
        raise ValueError(f"{name} is a setting of a project, and none is open")
    else:
        setattr(_project, name, value)


def parse_setting(name: str, text: str) -> SettingValue:
    """Convert the text typed in the console for a setting."""

    return cast(SettingValue, parse_value(_owner(name), name, text))


def new_project_settings() -> ProjectSettings:
    """The settings a new project starts with: a copy of the open one's."""

    if _project is None:
        return ProjectSettings()
    return ProjectSettings(**field_values(_project))


def use_project(project_settings: ProjectSettings | None) -> None:
    """Make the settings of the open project win; None when it's closed."""

    global _project
    _project = project_settings


def project_settings() -> ProjectSettings | None:
    return _project


def load_settings(path: str | None = None) -> Report:
    """Read the settings, or save the defaults if there is no file yet."""

    global _app, _settings_path, _read_only
    path = path or locations.settings_file()
    _settings_path = path
    _read_only = False
    report = Report()
    try:
        data = load_toml(path)
    except FileNotFoundError:
        _app = AppSettings()
        install()
        return report
    except (OSError, DecodeError) as exc:
        logger.error(cannot_read, filename=path, error=exc)
        _app = AppSettings()
        _read_only = True
        return report
    if not check_format(data, report, path):
        _read_only = True
        _app = AppSettings()
    else:
        _app = load_record(AppSettings, data, report, ignore={"format"})
        logger.info(settings_loaded, filename=path)
    report.log(logger)
    if _app.ksm:
        from virtualbricks.ksm import set_ksm

        set_ksm(enable=True)
    return report


def install() -> None:
    from virtualbricks.ksm import check_ksm

    _app.ksm = check_ksm()
    if store_settings():
        logger.info(settings_installed, filename=_settings_path)


def _write(data: Table, path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    dump_toml(data, path)


def store_settings(path: str | None = None) -> bool:
    """Write every setting; return False if the file wasn't written."""

    path = path or _settings_path or locations.settings_file()
    if _read_only and path == _settings_path:
        logger.warn(not_overwritten, filename=path)
        return False
    try:
        _write({"format": FORMAT, **dump_record(_app)}, path)
    except OSError:
        logger.failure(cannot_save, filename=path)
        return False
    return True


def load_state(path: str | None = None) -> Report:
    global _state, _state_path
    path = path or locations.state_file()
    _state_path = path
    report = Report()
    try:
        data = load_toml(path)
    except FileNotFoundError:
        _state = AppState()
        return report
    except (OSError, DecodeError) as exc:
        logger.error(cannot_read, filename=path, error=exc)
        _state = AppState()
        return report
    check_format(data, report, path)
    _state = load_record(AppState, data, report, ignore={"format"})
    report.log(logger)
    return report


def store_state(path: str | None = None) -> None:
    path = path or _state_path or locations.state_file()
    try:
        _write({"format": FORMAT, **dump_record(_state)}, path)
    except OSError:
        logger.failure(cannot_save, filename=path)


def current_project() -> str:
    return _state.current_project


def set_current_project(name: str) -> None:
    _state.current_project = name
    store_state()
