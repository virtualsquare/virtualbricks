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

A project is a folder of the workspace with a ``project.toml``. The workspace
is the folder of the ``workspace`` setting, unless the command line gives
another, and the state remembers the project open last in each. One project is
open at a time. While it's open its settings are in effect, a new project
starts with a copy of them, and the sockets of its bricks are in its runtime
directory, ``<runtime dir>/<key>/<project>``, where the key names the
workspace, so that two projects of the same name in two workspaces are apart.
A project's name is at most 40 bytes, so that its bricks' names have room in
their socket paths.

Hidden folders are never projects: they are for imports in progress. The
README of a project shows pictures of its folder only, those that a link
doesn't take out of it.
``opened`` tells when a project opens, or the open one is renamed.
"""

from __future__ import annotations

import collections
import dataclasses
import errno
import itertools
import os
import re
import shutil
import stat
import time
from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING, Protocol

from twisted.logger import Logger

from virtualbricks import errors, locations
from virtualbricks.config.projectfile import (
    ProjectFormatError,
    create_project_file,
    read_project_file,
    restore_project,
    save_project,
    upgrade_project,
    upgrade_readme,
)
from virtualbricks.config.report import Report
from virtualbricks.config.settings import (
    current_project,
    get_setting,
    new_project_settings,
    set_current_project,
    use_project,
)
from virtualbricks.i18n import N_, _
from virtualbricks.observable import Observable, Signal

if TYPE_CHECKING:  # pragma: no cover
    from virtualbricks.brickfactory import BrickFactory
    from virtualbricks.config.settings import ProjectSettings
    from virtualbricks.config.tomlfile import Table

# The longest name of a project, in bytes of UTF-8.
NAME_MAX = 40
# The largest picture of a README that the windows show, in bytes.
PICTURE_MAX = 10_000_000
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
        save_project(factory, self.settings, self.project_file)
        if self._description_modified:
            write_description(self.path, self.get_description())
            self._description_modified = False

    def __repr__(self) -> str:
        return f"<OpenProject {self.name} {self.path}>"


def read_description(path: str) -> str:
    # A project opened since 3.0 has README.md; one of before, README.
    for name in (locations.README, locations.LEGACY_README):
        try:
            with open(os.path.join(path, name)) as fp:
                return fp.read()
        except FileNotFoundError:
            pass
    return ""


def write_description(path: str, text: str) -> None:
    with open(os.path.join(path, locations.README), "w") as fp:
        fp.write(text)


def picture_file(folder: str, path: str) -> str:
    """
    The file of picture path of the README of the project in folder: path is
    relative to the folder, and the file stays in it once the links are
    followed. ValueError for any other.
    """

    inside = os.path.realpath(folder)
    file = os.path.realpath(os.path.join(inside, path))
    if (
        os.path.isabs(path)
        or file == inside
        or os.path.commonpath((inside, file)) != inside
    ):
        raise ValueError(
            _("The picture {path} isn't in the folder of the project").format(
                path=path
            )
        )
    return file


def read_picture(
    folder: str, path: str, offset: int = 0, length: int = PICTURE_MAX
) -> tuple[bytes, int]:
    """
    At most length bytes of picture path of the README of the project in
    folder, from offset, and the size of its file. ValueError if the file
    isn't in the folder, isn't a file or is larger than PICTURE_MAX.
    """

    file = picture_file(folder, path)
    # a FIFO would wait for a writer
    fd = os.open(file, os.O_RDONLY | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError(
                _("The picture {path} isn't a file").format(path=path)
            )
        if info.st_size > PICTURE_MAX:
            raise ValueError(
                _("The picture {path} is larger than {most} bytes").format(
                    path=path, most=PICTURE_MAX
                )
            )
        return os.pread(fd, length, offset), info.st_size
    finally:
        os.close(fd)


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


def _no_such_project(name: str) -> errors.InvalidNameError:
    return errors.InvalidNameError(
        _('There is no project "{name}"').format(name=name)
    )


class Trasher(Protocol):
    """
    The trash of a desktop.

    Only the GUI has one: this module doesn't import the libraries of the
    desktop, so that the workspace works in a console or a script.
    """

    def can_trash(self, path: str) -> bool:
        """Whether path can be moved to the trash."""

    def trash(self, path: str) -> None:
        """Move path to the trash; TrashNotSupportedError if it can't."""


# why a name can't be that of a new project
TAKEN = N_("A project with this name already exists")


def name_problem(name: str) -> str | None:
    """Why name can't be a project's name, whatever the projects; or None."""

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
    return None


def room_problem(runtime_dir: str, bricks: Iterable[str] | None) -> str | None:
    """
    Why the bricks can't have their sockets in runtime_dir, the runtime
    folder of a project: their names are too long; or None.
    """

    room = locations.brick_name_room(runtime_dir)
    longest = max((len(os.fsencode(b)) for b in bricks or ()), default=0)
    if longest and longest > room:
        return _(
            "The name leaves {room} bytes to the names of the bricks,"
            " and the longest has {longest}"
        ).format(room=max(room, 0), longest=longest)
    return None


def free_name(name: str, taken: Callable[[str], bool]) -> str:
    """name, or name-2, name-3... the first that isn't taken(name)."""

    if not taken(name):
        return name
    match = re.fullmatch(r"(.*)-(\d+)", name)
    base = match.group(1) if match else name
    for i in itertools.count(2):  # pragma: no branch
        candidate = f"{base}-{i}"
        if not taken(candidate):
            return candidate


class Workspace:
    """The projects in the workspace folder, and the one that is open."""

    current: OpenProject | None = None
    # Set by the GUI. Without it, a project that is removed is deleted.
    trasher: Trasher | None = None

    def __init__(self, path: str | None = None) -> None:
        self._path = path
        # the workspace, when a project opens, or the open one is renamed
        self.opened = Signal(Observable(), "opened")
        # name -> (the time of the project file, its summary)
        self._summaries: dict[str, tuple[float, ProjectSummary]] = {}

    @property
    def path(self) -> str:
        """The workspace folder, from the settings unless given."""

        if self._path is not None:
            return self._path
        return str(get_setting("workspace"))

    @path.setter
    def path(self, path: str | None) -> None:
        # Before a project is opened; None follows the setting again.
        self._path = path
        self._summaries.clear()

    def project_path(self, name: str) -> str:
        return os.path.join(self.path, name)

    def _project_file(self, name: str) -> str:
        return os.path.join(self.path, name, locations.PROJECT_FILE)

    def runtime_dir(self, name: str) -> str:
        """The runtime directory of the project name: its bricks' sockets."""

        return os.path.join(locations.workspace_runtime_dir(self.path), name)

    def make_runtime_dir(self) -> str:
        """
        Make the runtime directory of the workspace, and in it the link to
        the workspace, which tells whose it is; return it.
        """

        locations.ensure_private_dir(locations.runtime_dir())
        folder = locations.workspace_runtime_dir(self.path)
        locations.ensure_private_dir(folder)
        link = os.path.join(folder, locations.WORKSPACE_LINK)
        target = os.path.abspath(self.path)
        try:
            if os.readlink(link) == target:
                return folder
        except OSError:
            pass
        # replaced at once, so that the link is never missing
        tmp = f"{link}-{os.getpid()}"
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        os.symlink(target, tmp)
        os.replace(tmp, link)
        return folder

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

        message = name_problem(name)
        if message is not None:
            return message
        if name != renaming and os.path.lexists(self.project_path(name)):
            return _(TAKEN)
        if renaming is not None and bricks is None:
            bricks = self._brick_names(renaming)
        return room_problem(self.runtime_dir(name), bricks)

    def _brick_names(self, name: str) -> list[str]:
        """The names of the bricks in the project file of name, if any."""

        try:
            return brick_names(read_project_file(self._project_file(name)))
        except (OSError, ProjectFormatError):
            return []

    def _validate(self, name: str, renaming: str | None = None, bricks=None):
        message = self.check_name(name, renaming, bricks)
        if message is not None:
            raise errors.InvalidNameError(message)

    def free_name(self, name: str) -> str:
        """Return name, or name-2, name-3... the first that isn't taken."""

        return free_name(
            name, lambda name: os.path.lexists(self.project_path(name))
        )

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
            data = upgrade_project(read_project_file(path), Report())
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

    def picture(
        self, name: str, path: str, offset: int = 0, length: int = PICTURE_MAX
    ) -> tuple[bytes, int]:
        """A picture of the README of project name, see read_picture()."""

        if not self.exists(name):
            raise _no_such_project(name)
        return read_picture(self.project_path(name), path, offset, length)

    # Changing the projects

    def create(self, name: str, description: str = "") -> None:
        """Create a project with a copy of the settings of the open one."""

        self._validate(name)
        path = self.project_path(name)
        try:
            os.makedirs(path)
        except FileExistsError:
            raise errors.InvalidNameError(
                _("A project with this name already exists")
            ) from None
        create_project_file(self._project_file(name), new_project_settings())
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
            raise _no_such_project(name)
        self._validate(new, renaming=name, bricks=bricks)
        os.rename(self.project_path(name), self.project_path(new))
        self._summaries.pop(name, None)
        if self.current is not None and self.current.name == name:
            self.current.path = self.project_path(new)
            set_current_project(self.path, new)
            self.opened.notify(self)

    def duplicate(self, name: str, new: str) -> None:
        """Copy a project with its private disks; the copy is used now."""

        if not self.exists(name):
            raise _no_such_project(name)
        self._validate(new, bricks=self._brick_names(name))
        copy_tree(self.project_path(name), self.project_path(new))
        now = time.time()
        os.utime(self._project_file(new), (now, now))

    def _check_removable(self, name: str) -> None:
        if not self._is_name(name) or not os.path.isdir(
            self.project_path(name)
        ):
            raise _no_such_project(name)
        if self.current is not None and self.current.name == name:
            raise errors.ProjectOpenError(name)

    def can_trash(self, name: str) -> bool:
        """Whether trash() moves the project to the trash of a desktop."""

        trasher = self.trasher
        return trasher is not None and trasher.can_trash(
            self.project_path(name)
        )

    def trash(self, name: str) -> bool:
        """
        Move a project that isn't open to the trash of the desktop.

        Without a desktop, as in a console or a script, there's no trash: the
        project is deleted for good. Return whether it went to the trash.
        Raise TrashNotSupportedError if the desktop can't trash it, as on a
        drive without a trash; can_trash() says so beforehand.
        """

        if self.trasher is None:
            self.delete(name)
            return False
        self._check_removable(name)
        self.trasher.trash(self.project_path(name))
        self._summaries.pop(name, None)
        return True

    def delete(self, name: str) -> None:
        """Delete a project that isn't open, for good."""

        self._check_removable(name)
        shutil.rmtree(self.project_path(name))
        self._summaries.pop(name, None)

    # The open project

    def open(self, name: str, factory: BrickFactory) -> Report:
        """
        Load a project into factory and return the report of reading it.

        The project that is open is saved first, so its changes aren't lost
        when the factory is reset. Raise InvalidNameError if there is no
        project file and ProjectFormatError if it can't be read; the open
        project stays open, and so it does if it can't be saved.
        """

        report = Report()
        if self.current is not None and self.current.name == name:
            return report
        if not self._is_name(name):
            raise _no_such_project(name)
        try:
            data = upgrade_project(
                read_project_file(self._project_file(name)), report
            )
        except FileNotFoundError:
            raise _no_such_project(name) from None
        # The project file is readable, so it's safe to close the open one,
        # once it's saved: nothing else keeps what the factory holds.
        self.save(factory)
        self.close(factory)
        logger.debug(open_project, name=name)
        path = self.project_path(name)
        try:
            upgrade_readme(path)
        except OSError as exc:
            report.warning(
                f"cannot rename it to {locations.README}: {exc.strerror}",
                locations.LEGACY_README,
            )
        self.make_runtime_dir()
        runtime_dir = self.runtime_dir(name)
        factory.runtime_dir = locations.ensure_private_dir(runtime_dir)
        project_settings = restore_project(factory, data, report, path)
        room = locations.brick_name_room(runtime_dir)
        for brick in factory.bricks:
            if len(os.fsencode(brick.name)) > room:
                report.warning(
                    f"the name is longer than the {room} bytes its sockets"
                    " allow; rename it before starting it",
                    f"bricks.{brick.name}",
                )
        report.log(logger)
        self.current = OpenProject(path, project_settings)
        use_project(project_settings)
        set_current_project(self.path, name)
        self.opened.notify(self)
        return report

    def close(self, factory: BrickFactory) -> None:
        factory.reset()
        if self.current is not None:
            self.current = None
            use_project(None)

    def save(self, factory: BrickFactory) -> None:
        """Save the open project, if there is one."""

        if self.current is not None:
            self.current.save(factory)

    def autosave(self, factory: BrickFactory) -> None:
        try:
            self.save(factory)
        except Exception:
            logger.failure(autosave_error)

    def last_name(self) -> str:
        """The name of the project open last in this workspace."""

        return current_project(self.path)

    def open_last(self, factory: BrickFactory) -> Report:
        """
        Open the project that was open last in this workspace.

        A workspace without projects gets a new_project first, and a folder
        that isn't there yet is made. Raise what open raises, or
        InvalidNameError, when the project can't be opened.
        """

        os.makedirs(os.path.join(self.path, "vimages"), exist_ok=True)
        name = self.last_name()
        if DEFAULT_PROJECT_RE.match(name) and not os.path.lexists(
            self.project_path(name)
        ):
            self.create(name)
        return self.open(name, factory)

    def restore_last(self, factory: BrickFactory) -> Report:
        """Open the last project, or a new new_project_N if it can't be."""

        name = self.last_name()
        try:
            return self.open_last(factory)
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
