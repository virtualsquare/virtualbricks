# -*- test-case-name: virtualbricks.tests.config.test_workspace -*-
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
The workspace: the folder of the projects, and the project that is open.

A project is a folder of the workspace with a ``project.toml``. One project is
open at a time. While it's open its settings win over the app settings, and
the sockets of its bricks are in its runtime directory,
``<runtime dir>/<project>``. A project's name is at most 40 bytes, so that
its bricks' names have room in their socket paths.

Hidden folders are never projects: they are for imports in progress.
"""

from __future__ import annotations

import collections
import dataclasses
import errno
import itertools
import os
import re
import shutil
import time
from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING

from twisted.logger import Logger

from virtualbricks import errors, locations
from virtualbricks.config import projectfile, settings
from virtualbricks.config.projectfile import ProjectFormatError
from virtualbricks.config.report import Report
from virtualbricks.i18n import _

if TYPE_CHECKING:
    from virtualbricks.brickfactory import BrickFactory
    from virtualbricks.config.settings import ProjectSettings
    from virtualbricks.config.tomlfile import Table

# The longest name of a project, in bytes of UTF-8.
NAME_MAX = 40
README = "README"
# Private disks, "<vm>_<device>.cow", and their backups.
PRIVATE_DISK = re.compile(r".+_[a-z0-9]+\.cow(?:\.(?:bak|back)-[0-9_-]+)?\Z")
DEFAULT_PROJECT_RE = re.compile(rf"\A{locations.DEFAULT_PROJECT}(?:_\d+)?\Z")

logger = Logger()
open_project = "Restoring project {name}"
creating_project = "Create project {name}"
cannot_find_project = (
    'Cannot find project "{name}". A new project will be created.'
)
cannot_open_project = (
    'Cannot open project "{name}": {error}. A new project will be created.'
)
autosave_error = "Error while saving the project"


@dataclasses.dataclass(frozen=True)
class ImageSummary:
    """An image of a project's library."""

    name: str
    path: str
    found: bool


@dataclasses.dataclass(frozen=True)
class ProjectSummary:
    """What the list of projects shows of a project, without opening it."""

    name: str
    path: str
    description: str
    # The time of the project file: autosave keeps it current.
    modified: float
    # The number of bricks of each type.
    bricks: dict[str, int]
    events: int
    images: tuple[ImageSummary, ...]
    # Why the project file can't be read, if it can't.
    problem: str | None = None


@dataclasses.dataclass(frozen=True)
class DiskUsage:
    """The space a project takes on disk, in bytes."""

    private_disks: int
    other_files: int

    @property
    def total(self) -> int:
        return self.private_disks + self.other_files


class OpenProject:
    """The project that is open: its folder, its settings and its README."""

    def __init__(self, path: str, project_settings: ProjectSettings) -> None:
        self.path = path
        self.settings = project_settings
        self._description: str | None = None
        self._description_modified = False

    @property
    def name(self) -> str:
        return os.path.basename(self.path)

    @property
    def project_file(self) -> str:
        return os.path.join(self.path, locations.PROJECT_FILE)

    def get_description(self) -> str:
        if self._description is None:
            self._description = read_description(self.path)
        return self._description

    def set_description(self, text: str) -> None:
        self._description = text
        self._description_modified = True

    def save(self, factory: BrickFactory) -> None:
        os.makedirs(self.path, exist_ok=True)
        projectfile.save(factory, self.settings, self.project_file)
        if self._description_modified:
            write_description(self.path, self.get_description())
            self._description_modified = False

    def __repr__(self) -> str:
        return f"<OpenProject {self.name} {self.path}>"


def read_description(path: str) -> str:
    try:
        with open(os.path.join(path, README)) as fp:
            return fp.read()
    except FileNotFoundError:
        return ""


def write_description(path: str, text: str) -> None:
    with open(os.path.join(path, README), "w") as fp:
        fp.write(text)


def project_runtime_dir(name: str) -> str:
    return os.path.join(locations.runtime_dir(), name)


def brick_names(data: Table) -> list[str]:
    bricks = data.get("bricks", {})
    return list(bricks) if isinstance(bricks, dict) else []


def _tables(data: Table, key: str) -> dict[str, Table]:
    value = data.get(key, {})
    if not isinstance(value, dict):
        return {}
    return {k: v for k, v in value.items() if isinstance(v, dict)}


def _usage(path: str) -> int:
    """The bytes a file takes on disk, without its holes."""

    return os.lstat(path).st_blocks * 512


def copy_sparse(src: str, dst: str) -> None:
    """Copy a file, keeping its holes."""

    with open(src, "rb") as fin, open(dst, "wb") as fout:
        size = os.fstat(fin.fileno()).st_size
        offset = 0
        while offset < size:
            try:
                start = os.lseek(fin.fileno(), offset, os.SEEK_DATA)
            except OSError as exc:
                # ENXIO: only a hole is left.
                if exc.errno == errno.ENXIO:
                    break
                raise
            end = os.lseek(fin.fileno(), start, os.SEEK_HOLE)
            fin.seek(start)
            fout.seek(start)
            remaining = end - start
            while remaining:
                chunk = fin.read(min(remaining, 1 << 20))
                if not chunk:
                    break
                fout.write(chunk)
                remaining -= len(chunk)
            offset = end
        fout.truncate(size)
    shutil.copystat(src, dst)


def copy_tree(src: str, dst: str) -> None:
    shutil.copytree(src, dst, symlinks=True, copy_function=copy_sparse)


def trash_file(path: str) -> None:
    """Move path to the desktop's trash; TrashNotSupportedError if none."""

    from gi.repository import Gio, GLib

    try:
        Gio.File.new_for_path(path).trash(None)
    except GLib.Error as exc:
        if exc.matches(Gio.io_error_quark(), Gio.IOErrorEnum.NOT_SUPPORTED):
            raise errors.TrashNotSupportedError(path) from None
        raise OSError(exc.message) from None


def can_trash_file(path: str) -> bool:
    from gi.repository import Gio, GLib

    try:
        info = Gio.File.new_for_path(path).query_info(
            Gio.FILE_ATTRIBUTE_ACCESS_CAN_TRASH,
            Gio.FileQueryInfoFlags.NONE,
            None,
        )
    except GLib.Error:
        return False
    return info.get_attribute_boolean(Gio.FILE_ATTRIBUTE_ACCESS_CAN_TRASH)


class Workspace:
    """The projects in the workspace folder, and the one that is open."""

    current: OpenProject | None = None
    # Replaced by the tests, to not touch the desktop's trash.
    trash_file: Callable[[str], None] = staticmethod(trash_file)
    can_trash_file: Callable[[str], bool] = staticmethod(can_trash_file)

    def __init__(self, path: str | None = None) -> None:
        self._path = path
        # name -> (the time of the project file, its summary)
        self._summaries: dict[str, tuple[float, ProjectSummary]] = {}

    @property
    def path(self) -> str:
        """The workspace folder, from the settings unless given."""

        if self._path is not None:
            return self._path
        return str(settings.get("workspace"))

    def project_path(self, name: str) -> str:
        return os.path.join(self.path, name)

    def _project_file(self, name: str) -> str:
        return os.path.join(self.path, name, locations.PROJECT_FILE)

    def exists(self, name: str) -> bool:
        return self._is_name(name) and os.path.isfile(self._project_file(name))

    def _is_name(self, name: str) -> bool:
        return bool(name) and "/" not in name and name not in (".", "..")

    def names(self) -> list[str]:
        """The names of the projects, sorted."""

        try:
            entries = os.listdir(self.path)
        except FileNotFoundError:
            return []
        return sorted(
            name
            for name in entries
            if not name.startswith(".") and self.exists(name)
        )

    # Names

    def check_name(
        self,
        name: str,
        renaming: str | None = None,
        bricks: Iterable[str] | None = None,
    ) -> str | None:
        """
        Return why name can't be a project's name, or None if it can.

        When renaming, the project's bricks must fit in the socket paths of
        the new name: their names are bricks, or else those in the project
        file of renaming.
        """

        if not name:
            return _("The name is empty")
        if "/" in name:
            return _('The name cannot contain "/"')
        if name.startswith("."):
            return _("The name cannot start with a dot")
        size = len(os.fsencode(name))
        if size > NAME_MAX:
            return _("The name is {size} bytes long, at most {max}").format(
                size=size, max=NAME_MAX
            )
        if name != renaming and os.path.lexists(self.project_path(name)):
            return _("A project with this name already exists")
        room = locations.brick_name_room(project_runtime_dir(name))
        if renaming is not None and bricks is None:
            bricks = self._brick_names(renaming)
        longest = max((len(os.fsencode(b)) for b in bricks or ()), default=0)
        if longest and longest > room:
            return _(
                "The name leaves {room} bytes to the names of the bricks,"
                " and the longest has {longest}"
            ).format(room=max(room, 0), longest=longest)
        return None

    def _brick_names(self, name: str) -> list[str]:
        """The names of the bricks in the project file of name, if any."""

        try:
            return brick_names(projectfile.read(self._project_file(name)))
        except (OSError, ProjectFormatError):
            return []

    def _validate(self, name: str, renaming: str | None = None, bricks=None):
        message = self.check_name(name, renaming, bricks)
        if message is None:
            return
        taken = self._is_name(name) and os.path.lexists(
            self.project_path(name)
        )
        if taken and name != renaming:
            raise errors.ProjectExistsError(name)
        raise errors.InvalidNameError(message)

    def free_name(self, name: str) -> str:
        """Return name, or name-2, name-3... the first that isn't taken."""

        if not os.path.lexists(self.project_path(name)):
            return name
        match = re.fullmatch(r"(.*)-(\d+)", name)
        base = match.group(1) if match else name
        for i in itertools.count(2):  # pragma: no branch
            candidate = f"{base}-{i}"
            if not os.path.lexists(self.project_path(candidate)):
                return candidate

    # Listing

    def summary(self, name: str) -> ProjectSummary:
        """Read the project file of name, or reuse what was read if unchanged."""

        path = self._project_file(name)
        modified = os.stat(path).st_mtime
        cached = self._summaries.get(name)
        if cached and cached[0] == modified:
            return cached[1]
        summary = self._read_summary(name, path, modified)
        self._summaries[name] = (modified, summary)
        return summary

    def _read_summary(
        self, name: str, path: str, modified: float
    ) -> ProjectSummary:
        folder = os.path.dirname(path)
        description = read_description(folder)
        try:
            data = projectfile.upgrade(projectfile.read(path), Report())
        except ProjectFormatError as exc:
            return ProjectSummary(
                name, folder, description, modified, {}, 0, (), str(exc)
            )
        except OSError as exc:
            return ProjectSummary(
                name, folder, description, modified, {}, 0, (), str(exc)
            )
        counts = collections.Counter(
            str(table.get("type", ""))
            for table in _tables(data, "bricks").values()
        )
        images = []
        for image, table in _tables(data, "images").items():
            image_path = str(table.get("path", ""))
            if image_path and not os.path.isabs(image_path):
                image_path = os.path.join(folder, image_path)
            found = bool(image_path) and os.path.exists(image_path)
            images.append(ImageSummary(image, image_path, found))
        return ProjectSummary(
            name,
            folder,
            description,
            modified,
            dict(counts),
            len(_tables(data, "events")),
            tuple(images),
        )

    def summaries(self) -> list[ProjectSummary]:
        """The projects, the most recently used first."""

        summaries = []
        for name in self.names():
            try:
                summaries.append(self.summary(name))
            except FileNotFoundError:
                pass
        for name in set(self._summaries) - {s.name for s in summaries}:
            del self._summaries[name]
        return sorted(summaries, key=lambda s: (-s.modified, s.name))

    def disk_usage(self, name: str) -> DiskUsage:
        private = other = 0
        for folder, dirs, files in os.walk(self.project_path(name)):
            for filename in files:
                size = _usage(os.path.join(folder, filename))
                if folder == self.project_path(name) and PRIVATE_DISK.match(
                    filename
                ):
                    private += size
                else:
                    other += size
        return DiskUsage(private, other)

    # Changing the projects

    def create(self, name: str, description: str = "") -> None:
        """Create a project with the settings new projects start with."""

        self._validate(name)
        path = self.project_path(name)
        try:
            os.makedirs(path)
        except FileExistsError:
            raise errors.ProjectExistsError(name) from None
        projectfile.create(
            self._project_file(name), settings.new_project_settings()
        )
        if description:
            write_description(path, description)
        logger.debug(creating_project, name=name)

    def rename(self, name: str, new: str, bricks=None) -> None:
        """
        Rename a project, the open one included.

        The bricks of the open project keep their sockets until it's opened
        again.
        """

        if name == new:
            return
        if not self.exists(name):
            raise errors.ProjectNotExistsError(name)
        self._validate(new, renaming=name, bricks=bricks)
        os.rename(self.project_path(name), self.project_path(new))
        self._summaries.pop(name, None)
        if self.current is not None and self.current.name == name:
            self.current.path = self.project_path(new)
            settings.set_current_project(new)

    def duplicate(self, name: str, new: str) -> None:
        """Copy a project with its private disks; the copy is used now."""

        if not self.exists(name):
            raise errors.ProjectNotExistsError(name)
        self._validate(new, bricks=self._brick_names(name))
        copy_tree(self.project_path(name), self.project_path(new))
        now = time.time()
        os.utime(self._project_file(new), (now, now))

    def _check_removable(self, name: str) -> None:
        if not self._is_name(name) or not os.path.isdir(
            self.project_path(name)
        ):
            raise errors.ProjectNotExistsError(name)
        if self.current is not None and self.current.name == name:
            raise errors.ProjectOpenError(name)

    def can_trash(self, name: str) -> bool:
        return self.can_trash_file(self.project_path(name))

    def trash(self, name: str) -> None:
        """Move a project that isn't open to the desktop's trash."""

        self._check_removable(name)
        self.trash_file(self.project_path(name))
        self._summaries.pop(name, None)

    def delete(self, name: str) -> None:
        """Delete a project that isn't open, for good."""

        self._check_removable(name)
        shutil.rmtree(self.project_path(name))
        self._summaries.pop(name, None)

    # The open project

    def open(self, name: str, factory: BrickFactory) -> Report:
        """
        Load a project into factory and return the report of reading it.

        Raise ProjectNotExistsError if there is no project file and
        ProjectFormatError if it can't be read; the open project stays open.
        """

        report = Report()
        if self.current is not None and self.current.name == name:
            return report
        if not self._is_name(name):
            raise errors.InvalidNameError(name)
        try:
            data = projectfile.upgrade(
                projectfile.read(self._project_file(name)), report
            )
        except FileNotFoundError:
            raise errors.ProjectNotExistsError(name) from None
        # The project file is readable, so it's safe to close the open one.
        self.close(factory)
        logger.debug(open_project, name=name)
        path = self.project_path(name)
        runtime_dir = project_runtime_dir(name)
        factory.runtime_dir = locations.ensure_private_dir(runtime_dir)
        project_settings = projectfile.restore(factory, data, report, path)
        room = locations.brick_name_room(runtime_dir)
        for brick in factory.bricks:
            if len(os.fsencode(brick.get_name())) > room:
                report.warning(
                    f"the name is longer than the {room} bytes its sockets"
                    " allow; rename it before starting it",
                    f"bricks.{brick.get_name()}",
                )
        report.log(logger)
        self.current = OpenProject(path, project_settings)
        settings.use_project(project_settings)
        settings.set_current_project(name)
        return report

    def close(self, factory: BrickFactory) -> None:
        factory.reset()
        if self.current is not None:
            self.current = None
            settings.use_project(None)

    def save(self, factory: BrickFactory) -> None:
        """Save the open project, if there is one."""

        if self.current is not None:
            self.current.save(factory)

    def autosave(self, factory: BrickFactory) -> None:
        try:
            self.save(factory)
        except Exception:
            logger.failure(autosave_error)

    def open_last(self, factory: BrickFactory) -> Report:
        """
        Open the project that was open last.

        A workspace without projects gets a new_project first. Raise what
        open raises, or InvalidNameError, when the project can't be opened.
        """

        os.makedirs(os.path.join(self.path, "vimages"), exist_ok=True)
        name = settings.current_project()
        if DEFAULT_PROJECT_RE.match(name) and not os.path.lexists(
            self.project_path(name)
        ):
            self.create(name)
        return self.open(name, factory)

    def restore_last(self, factory: BrickFactory) -> Report:
        """Open the last project, or a new new_project_N if it can't be."""

        name = settings.current_project()
        try:
            return self.open_last(factory)
        except errors.ProjectNotExistsError:
            logger.error(cannot_find_project, name=name)
        except errors.InvalidNameError:
            logger.error(cannot_find_project, name=name)
        except ProjectFormatError as exc:
            logger.error(cannot_open_project, name=name, error=exc)
        for i in itertools.count():  # pragma: no branch
            name = f"{locations.DEFAULT_PROJECT}_{i}"
            if not os.path.lexists(self.project_path(name)):
                self.create(name)
                return self.open(name, factory)


projects = Workspace()
