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

import base64
import hashlib
import os
import tempfile

APP = "virtualbricks"
DEFAULT_PROJECT = "new_project"
SETTINGS_FILE = "settings.toml"
STATE_FILE = "state.toml"
# The token of the tcp and ssl control sockets, in the config folder.
TOKEN_FILE = "token"
PROJECT_FILE = "project.toml"
LEGACY_SETTINGS_FILE = ".virtualbricks.conf"
LEGACY_PROJECT_FILE = ".project"
# The README of a project, and its name before 3.0.
README = "README.md"
LEGACY_README = "README"
# The longest path a Unix socket can have, without the final NUL.
SOCKET_PATH_MAX = 107
# The longest a brick's name adds to the runtime directory: a plug's socket
# inside a switch's directory, "<brick>.ctl/.<pid>-<n>", as libvdeplug names
# them, with the largest pid Linux gives.
BRICK_SOCKET_SUFFIX = len(".ctl/.4194304-00000")
# The folder of a workspace in the runtime directory is named by a key of its
# path, this long: 40 bits.
WORKSPACE_KEY_SIZE = 8
# The link, in that folder, to the workspace.
WORKSPACE_LINK = ".workspace"
# The socket of --listen alone, in that folder.
CONTROL_SOCKET = ".control"
# The lock of a workspace, in its folder, see virtualbricks.locks: no project
# is named with a dot, and a workspace can be any folder.
WORKSPACE_LOCK_FILE = ".virtualbricks.lock"
# The lock that every user's Virtualbricks takes, see virtualbricks.locks. It
# isn't in the temporary directory of TMPDIR, which may be the user's own.
SYSTEM_LOCK_FILE = "/tmp/virtualbricks.lock"


def home() -> str:
    return os.path.expanduser("~")


def short_path(path: str) -> str:
    """A path, with ~ for the home folder."""

    folder = home()
    if path == folder or path.startswith(folder + os.sep):
        return "~" + path[len(folder) :]
    return path


def _xdg_dir(variable: str, fallback: str) -> str:
    # The specification says to ignore relative paths.
    value = os.environ.get(variable, "")
    if os.path.isabs(value):
        return value
    return os.path.join(home(), fallback)


def config_dir() -> str:
    return os.path.join(_xdg_dir("XDG_CONFIG_HOME", ".config"), APP)


def state_dir() -> str:
    fallback = os.path.join(".local", "state")
    return os.path.join(_xdg_dir("XDG_STATE_HOME", fallback), APP)


def settings_file() -> str:
    return os.path.join(config_dir(), SETTINGS_FILE)


def state_file() -> str:
    return os.path.join(state_dir(), STATE_FILE)


def default_workspace() -> str:
    return os.path.join(home(), ".virtualbricks")


def legacy_settings_file() -> str:
    return os.path.join(home(), LEGACY_SETTINGS_FILE)


def runtime_dir() -> str:
    value = os.environ.get("XDG_RUNTIME_DIR", "")
    if os.path.isabs(value):
        return os.path.join(value, APP)
    return os.path.join(tempfile.gettempdir(), f"{APP}-{os.getuid()}")


def workspace_key(workspace: str) -> str:
    """
    The name of the folder of workspace in the runtime directory.

    The same folder has the same key, whatever path names it.
    """

    path = os.fsencode(os.path.realpath(workspace))
    digest = base64.b32encode(hashlib.sha256(path).digest())
    return digest[:WORKSPACE_KEY_SIZE].decode("ascii").lower()


def workspace_runtime_dir(workspace: str) -> str:
    """The runtime directory of workspace: its projects' own are in it."""

    return os.path.join(runtime_dir(), workspace_key(workspace))


def workspace_lock_file(workspace: str) -> str:
    """The lock of workspace, which one Virtualbricks at a time holds."""

    return os.path.join(workspace, WORKSPACE_LOCK_FILE)


def user_lock_file() -> str:
    # a project's name never starts with a dot, so no project's runtime
    # directory is named like it
    return os.path.join(runtime_dir(), ".lock")


def control_socket(workspace: str) -> str:
    """The socket of --listen alone, of the Virtualbricks of workspace."""

    # named with a dot, as the link to the workspace
    return os.path.join(workspace_runtime_dir(workspace), CONTROL_SOCKET)


def control_lock_file(socket: str) -> str:
    """The lock that the Virtualbricks listening on socket holds."""

    return socket + ".lock"


def token_file() -> str:
    """The token that a client of a tcp or ssl socket proves it knows."""

    return os.path.join(config_dir(), TOKEN_FILE)


def brick_name_room(runtime_dir: str) -> int:
    """The bytes a brick's name can have in the sockets under runtime_dir."""

    used = len(os.fsencode(runtime_dir)) + len("/") + BRICK_SOCKET_SUFFIX
    return SOCKET_PATH_MAX - used


def ensure_private_dir(path: str) -> str:
    os.makedirs(path, mode=0o700, exist_ok=True)
    return path
