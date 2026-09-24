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
The application settings, the settings of the open project and the state.

The settings are in ``settings.toml``. Some of them are per project: each
project starts with a copy of them, and while a project is open its copy
wins. The state, in ``state.toml``, is what the application remembers, such
as the current project.
"""

import os

from twisted.logger import Logger

from virtualbricks.config import schema, tomlfile
from virtualbricks import locations
from virtualbricks.errors import NoOptionError
from virtualbricks.config.report import Report
from virtualbricks.config.schema import Bool, Choice, Path, Str

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


def check_format(data, report, where):
    """Return True if data has the current format, reporting otherwise."""

    value = data.get("format")
    is_int = isinstance(value, int) and not isinstance(value, bool)
    if is_int and value == FORMAT:
        return True
    if is_int and value > FORMAT:
        report.error(
            f"written by a newer Virtualbricks (format {value})", where
        )
        return False
    report.warning(f"unknown format {value!r}, read as format {FORMAT}", where)
    return True


@schema.define
class ProjectSettings:
    """The settings that each project has its own copy of."""

    cowfmt = schema.field(Choice(*COW_FORMATS), default="qcow2")
    erroronloop = schema.field(Bool(), default=False)
    femaleplugs = schema.field(Bool(), default=False)
    qemupath = schema.field(Path(), default="/usr/bin")
    vdepath = schema.field(Path(), default="/usr/bin")


@schema.define
class AppSettings(ProjectSettings):
    """All settings; the per-project ones are the start of a new project."""

    workspace = schema.field(Path(), factory=locations.default_workspace)
    term = schema.field(Str(), default="/usr/bin/xterm")
    sudo = schema.field(Str(), default="/usr/bin/gksu")
    ksm = schema.field(Bool(), default=False)
    systray = schema.field(Bool(), default=True)
    show_missing = schema.field(Bool(), default=True)


@schema.define
class AppState:

    current_project = schema.field(Str(), default=locations.DEFAULT_PROJECT)


PROJECT_KEYS = frozenset(schema.names(ProjectSettings))

_app = AppSettings()
_project = None
_state = AppState()
_settings_path = None
_state_path = None
_read_only = False


def _target(name):
    if name not in schema.names(AppSettings):
        raise NoOptionError(name)
    if _project is not None and name in PROJECT_KEYS:
        return _project
    return _app


def has_option(name):
    return name in schema.names(AppSettings)


def get(name):
    """Return the value in effect, from the open project if it has one."""

    if name == "sudo" and os.getuid() == 0:
        return ""
    return getattr(_target(name), name)


def set(name, value):
    setattr(_target(name), name, value)


def get_app(name):
    """Return the application value, even when a project overrides it."""

    _target(name)
    return getattr(_app, name)


def set_app(name, value):
    _target(name)
    setattr(_app, name, value)


def parse(name, text):
    """Convert the text typed in the console for a setting."""

    _target(name)
    return schema.parse(AppSettings, name, text)


def new_project_settings():
    """Return the settings a new project starts with."""

    values = schema.values(_app)
    return ProjectSettings(**{name: values[name] for name in PROJECT_KEYS})


def use_project(project_settings):
    """Make the settings of the open project win; None when it's closed."""

    global _project
    _project = project_settings


def project_settings():
    return _project


def load(path=None):
    """Read the settings, or save the defaults if there is no file yet."""

    global _app, _settings_path, _read_only
    path = path or locations.settings_file()
    _settings_path = path
    _read_only = False
    report = Report()
    try:
        data = tomlfile.load(path)
    except FileNotFoundError:
        _app = AppSettings()
        install()
        return report
    except (OSError, tomlfile.DecodeError) as exc:
        logger.error(cannot_read, filename=path, error=exc)
        _app = AppSettings()
        _read_only = True
        return report
    if not check_format(data, report, path):
        _read_only = True
        _app = AppSettings()
    else:
        _app = schema.load(AppSettings, data, report, ignore={"format"})
        logger.info(settings_loaded, filename=path)
    report.log(logger)
    if _app.ksm:
        from virtualbricks.tools import set_ksm

        set_ksm(enable=True)
    return report


def install():
    from virtualbricks.tools import check_ksm

    _app.ksm = check_ksm()
    if store():
        logger.info(settings_installed, filename=_settings_path)


def _write(data, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tomlfile.dump(data, path)


def store(path=None):
    """Write every setting; return False if the file wasn't written."""

    path = path or _settings_path or locations.settings_file()
    if _read_only and path == _settings_path:
        logger.warn(not_overwritten, filename=path)
        return False
    try:
        _write({"format": FORMAT, **schema.dump(_app)}, path)
    except OSError:
        logger.failure(cannot_save, filename=path)
        return False
    return True


def load_state(path=None):
    global _state, _state_path
    path = path or locations.state_file()
    _state_path = path
    report = Report()
    try:
        data = tomlfile.load(path)
    except FileNotFoundError:
        _state = AppState()
        return report
    except (OSError, tomlfile.DecodeError) as exc:
        logger.error(cannot_read, filename=path, error=exc)
        _state = AppState()
        return report
    check_format(data, report, path)
    _state = schema.load(AppState, data, report, ignore={"format"})
    report.log(logger)
    return report


def store_state(path=None):
    path = path or _state_path or locations.state_file()
    try:
        _write({"format": FORMAT, **schema.dump(_state)}, path)
    except OSError:
        logger.failure(cannot_save, filename=path)


def current_project():
    return _state.current_project


def set_current_project(name):
    _state.current_project = name
    store_state()
