# -*- test-case-name: virtualbricks.tests.test_locations -*-
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
# The longest path a Unix socket can have, without the final NUL.
SOCKET_PATH_MAX = 107
# The longest a brick's name adds to the runtime directory: a plug's socket
# inside a switch's directory, "<brick>.ctl/.<pid>-<n>", as libvdeplug names
# them, with the largest pid Linux gives.
BRICK_SOCKET_SUFFIX = len(".ctl/.4194304-00000")
# The lock that every user's Virtualbricks takes, see virtualbricks.locks. It
# isn't in the temporary directory of TMPDIR, which may be the user's own.
SYSTEM_LOCK_FILE = "/tmp/virtualbricks.lock"


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


def user_lock_file():
    # a project's name never starts with a dot, so no project's runtime
    # directory is named like it
    return os.path.join(runtime_dir(), ".lock")


def control_socket():
    """The socket that the Virtualbricks of this user listens on."""

    # named with a dot, as the user lock
    return os.path.join(runtime_dir(), ".control")


def control_lock_file(socket):
    """The lock that the Virtualbricks listening on socket holds."""

    return socket + ".lock"


def brick_name_room(runtime_dir):
    """The bytes a brick's name can have in the sockets under runtime_dir."""

    used = len(os.fsencode(runtime_dir)) + len("/") + BRICK_SOCKET_SUFFIX
    return SOCKET_PATH_MAX - used


def ensure_private_dir(path):
    os.makedirs(path, mode=0o700, exist_ok=True)
    return path
