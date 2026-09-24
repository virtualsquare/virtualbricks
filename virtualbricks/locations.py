# -*- test-case-name: virtualbricks.tests.config.test_locations -*-
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

"""Where Virtualbricks keeps its files, following the XDG base directories."""

import os
import tempfile

APP = "virtualbricks"
DEFAULT_PROJECT = "new_project"
SETTINGS_FILE = "settings.toml"
STATE_FILE = "state.toml"
PROJECT_FILE = "project.toml"
LEGACY_SETTINGS_FILE = ".virtualbricks.conf"
LEGACY_PROJECT_FILE = ".project"


def home():
    return os.path.expanduser("~")


def _xdg_dir(variable, fallback):
    # The specification says to ignore relative paths.
    value = os.environ.get(variable, "")
    if os.path.isabs(value):
        return value
    return os.path.join(home(), fallback)


def config_dir():
    return os.path.join(_xdg_dir("XDG_CONFIG_HOME", ".config"), APP)


def state_dir():
    fallback = os.path.join(".local", "state")
    return os.path.join(_xdg_dir("XDG_STATE_HOME", fallback), APP)


def settings_file():
    return os.path.join(config_dir(), SETTINGS_FILE)


def state_file():
    return os.path.join(state_dir(), STATE_FILE)


def default_workspace():
    return os.path.join(home(), ".virtualbricks")


def legacy_settings_file():
    return os.path.join(home(), LEGACY_SETTINGS_FILE)


def runtime_dir():
    value = os.environ.get("XDG_RUNTIME_DIR", "")
    if os.path.isabs(value):
        return os.path.join(value, APP)
    return os.path.join(tempfile.gettempdir(), f"{APP}-{os.getuid()}")


def ensure_private_dir(path):
    os.makedirs(path, mode=0o700, exist_ok=True)
    return path


LOCK_FILE = "/tmp/vb.lock"
