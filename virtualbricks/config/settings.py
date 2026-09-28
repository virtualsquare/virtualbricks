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
as the current project. Both files start with a header and have a comment
above every key.
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
    ListOf,
    Path,
    Record,
    Str,
    define,
    dump_record,
    field,
    load_record,
    field_names,
    field_values,
    kind_of,
    notes,
    parse_value,
)
from virtualbricks.config.tomlfile import (
    FORMAT_NOTE,
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
SETTINGS_HEADER = """\
The settings of Virtualbricks that aren't about a project.
Virtualbricks writes this file and its comments, and rewrites it when the
settings change and when it quits: a comment added by hand is lost.
See virtualbricks-config(5).
"""
STATE_HEADER = """\
What Virtualbricks remembers from one run to the next.
Virtualbricks writes this file and its comments, and rewrites it whenever it
opens a project: a comment added by hand is lost.
See virtualbricks-config(5).
"""

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

    cow_format: str = field(
        Choice(*COW_FORMATS),
        default="qcow2",
        help="The format of private copies",
    )
    log_link_loops: bool = field(
        Bool(), default=False, help="Log an error when links make a loop"
    )
    allow_female_plugs: bool = field(
        Bool(),
        default=False,
        help="Let plugs go into the socket cards of machines",
    )
    qemu_path: str = field(
        Path(), default="/usr/bin", help="The folder of the QEMU programs"
    )
    vde_path: str = field(
        Path(), default="/usr/bin", help="The folder of the VDE programs"
    )


@define
class AppSettings:
    """The settings of the application, which aren't about a project."""

    workspace: str = field(
        Path(),
        factory=locations.default_workspace,
        help="The folder of the projects",
    )
    terminal: str = field(
        Str(),
        default="/usr/bin/xterm",
        help="The terminal that opens the consoles of the bricks",
    )
    kernel_samepage_merging: bool = field(
        Bool(),
        default=False,
        help="Share equal memory pages between machines, with KSM",
    )
    tray_icon: bool = field(
        Bool(), default=True, help="Show an icon in the system tray"
    )
    warn_missing_programs: bool = field(
        Bool(),
        default=True,
        help="Warn at start about the programs Virtualbricks can't find",
    )
    # the audio driver of QEMU that plays the sound cards of the machines;
    # it's about this computer, not about a project
    audio_driver: str = field(
        Str(),
        default="alsa",
        help=(
            "The audio driver QEMU plays the sound cards through, as alsa, pa "
            "or pipewire"
        ),
    )


@define
class WorkspaceState:
    """What the application remembers of a workspace."""

    path: str = field(
        Path(required=True), default="", help="The folder of the workspace"
    )
    current_project: str = field(
        Str(),
        default=locations.DEFAULT_PROJECT,
        help="The project that opens at start in this workspace",
    )


@define
class AppState:

    workspaces: list[WorkspaceState] = field(
        ListOf(Record(WorkspaceState)),
        factory=list,
        help="The workspaces used, the last used first",
    )


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
    if _app.kernel_samepage_merging:
        from virtualbricks.ksm import set_ksm

        set_ksm(enable=True)
    return report


def install() -> None:
    from virtualbricks.ksm import check_ksm

    _app.kernel_samepage_merging = check_ksm()
    if store_settings():
        logger.info(settings_installed, filename=_settings_path)


def _write(record: AppSettings | AppState, path: str, header: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    data: Table = {"format": FORMAT, **dump_record(record)}
    file_notes = {("format",): FORMAT_NOTE, **notes(type(record), data)}
    dump_toml(data, path, file_notes, header)


def write_settings(app: AppSettings, path: str) -> None:
    """Write settings.toml, with its header and comments."""

    _write(app, path, SETTINGS_HEADER)


def write_state(state: AppState, path: str) -> None:
    """Write state.toml, with its header and comments."""

    _write(state, path, STATE_HEADER)


def store_settings(path: str | None = None) -> bool:
    """Write every setting; return False if the file wasn't written."""

    path = path or _settings_path or locations.settings_file()
    if _read_only and path == _settings_path:
        logger.warn(not_overwritten, filename=path)
        return False
    try:
        write_settings(_app, path)
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
        write_state(_state, path)
    except OSError:
        logger.failure(cannot_save, filename=path)


def _workspace_state(workspace: str) -> WorkspaceState | None:
    path = os.path.abspath(workspace)
    for state in _state.workspaces:
        if os.path.abspath(state.path) == path:
            return state
    return None


def current_project(workspace: str) -> str:
    """The project open last in a workspace, new_project if none was."""

    state = _workspace_state(workspace)
    if state is None:
        return locations.DEFAULT_PROJECT
    return state.current_project


def set_current_project(workspace: str, name: str) -> None:
    """Remember the project open in a workspace, which comes first."""

    state = _workspace_state(workspace)
    if state is None:
        state = WorkspaceState(os.path.abspath(workspace))
    else:
        _state.workspaces.remove(state)
    state.current_project = name
    _state.workspaces.insert(0, state)
    store_state()
