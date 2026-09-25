# -*- test-case-name: virtualbricks.tests.migrate.test_engine -*-
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
Find the files of older versions and migrate them, reporting every step.

A migration writes either in place, next to the old files and in the XDG
directories of the user, or into a new folder laid out like them, to try it
out. The old files are only read.
"""

from __future__ import annotations

import os
import shutil
import stat
from collections.abc import Collection, Iterator
from typing import TYPE_CHECKING, Final, Literal, TypeAlias

import attr
from twisted.python import lockfile

from virtualbricks.config import (
    ERROR,
    INFO,
    PROJECT_KEYS,
    SETTINGS_FORMAT,
    WARNING,
    AppSettings,
    DecodeError,
    ProjectSettings,
    Report,
    dump_record,
    dump_toml,
    field_values,
    load_record,
    load_toml,
    new_project_settings,
)
from virtualbricks import locations
from virtualbricks.migrate import convert, legacy

if TYPE_CHECKING:
    from twisted.logger import Logger

    from virtualbricks.config import Level, Message, Table

Status = Literal["waiting", "migrating", "migrated", "failed", "skipped"]

WAITING: Final = "waiting"
MIGRATING: Final = "migrating"
MIGRATED: Final = "migrated"
FAILED: Final = "failed"
SKIPPED: Final = "skipped"
REPORT_FILE = "migration-report.txt"
BACKUP_SUFFIX = "~"


@attr.define
class Item:
    """The settings or a project, with the state of its migration."""

    name: str = attr.field()
    # a project is a directory, or a single file in the workspace
    kind: Literal["settings", "project", "file"] = attr.field()
    source: str = attr.field()
    status: Status = attr.field(default=WAITING)
    # how many bricks the project has, once converted
    bricks: int | None = attr.field(default=None)
    report: Report = attr.field(factory=Report)

    @property
    def is_project(self) -> bool:
        return self.kind != "settings"


class InPlace:
    """Write next to the old files and in the XDG directories of the user."""

    folder: None = None

    def __init__(self, workspace: str) -> None:
        self.workspace = workspace

    @property
    def settings_file(self) -> str:
        return locations.settings_file()

    @property
    def state_file(self) -> str:
        return locations.state_file()

    @property
    def report_file(self) -> str:
        return os.path.join(locations.state_dir(), REPORT_FILE)

    def project_dir(self, name: str) -> str:
        return os.path.join(self.workspace, name)


class Folder:
    """Write into a new folder, laid out like the XDG directories."""

    def __init__(self, folder: str) -> None:
        self.folder = folder
        self.workspace = os.path.join(folder, "workspace")
        self.settings_file = os.path.join(
            folder, "config", locations.APP, locations.SETTINGS_FILE
        )
        self.state_file = os.path.join(
            folder, "state", locations.APP, locations.STATE_FILE
        )
        self.report_file = os.path.join(folder, REPORT_FILE)

    def project_dir(self, name: str) -> str:
        return os.path.join(self.workspace, name)


# Where a migration writes.
Target: TypeAlias = InPlace | Folder


def project_source(directory: str) -> str | None:
    """Return the old project file of a directory, or None."""

    path = os.path.join(directory, locations.LEGACY_PROJECT_FILE)
    # The old versions put this copy back if a save was interrupted.
    if os.path.isfile(path + BACKUP_SUFFIX):
        return path + BACKUP_SUFFIX
    if os.path.isfile(path):
        return path
    return None


def discover(workspace: str) -> list[Item]:
    """Return an item for each old project of the workspace, by name."""

    items: list[Item] = []
    names: set[str] = set()
    if not os.path.isdir(workspace):
        return items
    for entry in sorted(os.listdir(workspace)):
        path = os.path.join(workspace, entry)
        if entry.startswith("."):
            continue
        if os.path.isdir(path):
            source = project_source(path)
            if source is not None:
                items.append(Item(entry, "project", source))
                names.add(entry)
    for entry in sorted(os.listdir(workspace)):
        path = os.path.join(workspace, entry)
        if entry.startswith(".") or not os.path.isfile(path):
            continue
        if legacy.looks_like_project(path):
            name = base = os.path.splitext(entry)[0]
            count = 1
            while name in names or os.path.isdir(
                os.path.join(workspace, name)
            ):
                if _is_migrated_file(workspace, name, path):
                    break
                name = f"{base}_{count}"
                count += 1
            items.append(Item(name, "file", path))
            names.add(name)
    return items


def _is_migrated_file(workspace: str, name: str, path: str) -> bool:
    # A single-file project migrated in place becomes a directory of the same
    # name without an old project file; running again must skip it.
    directory = os.path.join(workspace, name)
    migrated = os.path.isfile(os.path.join(directory, locations.PROJECT_FILE))
    return migrated and project_source(directory) is None


def _read_app_settings(path: str) -> AppSettings:
    try:
        data = load_toml(path)
    except (OSError, DecodeError):
        return AppSettings()
    return load_record(AppSettings, data, Report(), ignore={"format"})


def _legacy_app_settings(path: str) -> AppSettings:
    report = Report()
    try:
        options = legacy.read_settings(path, os.path.basename(path), report)
    except (OSError, UnicodeDecodeError):
        return AppSettings()
    return convert.convert_settings(options, os.path.basename(path), report)[0]


def _project_settings(app: AppSettings) -> ProjectSettings:
    values = field_values(app)
    return ProjectSettings(**{name: values[name] for name in PROJECT_KEYS})


def _write(data: Table, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    dump_toml(data, path)


def _copy_tree(source: str, destination: str, skip: Collection[str]) -> None:
    """Copy the regular files of a directory; sockets and the like stay."""

    for root, dirs, files in os.walk(source):
        relative = os.path.relpath(root, source)
        target_root = os.path.normpath(os.path.join(destination, relative))
        os.makedirs(target_root, exist_ok=True)
        for filename in files:
            path = os.path.join(root, filename)
            if root == source and filename in skip:
                continue
            if stat.S_ISREG(os.lstat(path).st_mode):
                shutil.copy2(path, os.path.join(target_root, filename))


class Migration:
    """
    The migration of old settings and of the old projects of a workspace.

    ``target`` is an :class:`InPlace` or a :class:`Folder`. The per-project
    settings of the migrated projects come from the old settings, if they are
    migrated too, or from ``app_settings``.
    """

    def __init__(
        self,
        workspace: str,
        target: Target,
        legacy_settings: str | None = None,
        app_settings: AppSettings | None = None,
        dry_run: bool = False,
        copy_files: bool = False,
        verbose: bool = False,
    ) -> None:
        self.workspace = workspace
        self.target = target
        self.dry_run = dry_run
        self.copy_files = copy_files
        self.verbose = verbose
        self.app_settings = app_settings or AppSettings()
        # the current project of the old settings, once migrated
        self.current_project: str | None = None
        self.items: list[Item] = []
        if legacy_settings is not None:
            name = os.path.basename(legacy_settings)
            self.items.append(Item(name, "settings", legacy_settings))
        self.items.extend(discover(workspace))
        self._skip_migrated()

    def _skip_migrated(self) -> None:
        for item in self.items:
            if item.kind == "settings":
                done = os.path.exists(self.target.settings_file)
                reason = f"{self.target.settings_file} already exists"
            else:
                directory = self.target.project_dir(item.name)
                done = os.path.exists(
                    os.path.join(directory, locations.PROJECT_FILE)
                )
                reason = "already migrated"
            if done:
                item.status = SKIPPED
                item.report.info(f"{reason}, skipped")

    @property
    def projects(self) -> list[Item]:
        return [item for item in self.items if item.is_project]

    def pending(self) -> list[Item]:
        return [item for item in self.items if item.status == WAITING]

    def count(self, status: Status, projects_only: bool = True) -> int:
        items = self.projects if projects_only else self.items
        return sum(1 for item in items if item.status == status)

    @property
    def exit_code(self) -> int:
        return 1 if self.count(FAILED, projects_only=False) else 0

    def steps(self) -> Iterator[Item]:
        """Migrate the items one by one, yielding each before and after."""

        for item in self.items:
            if item.status != WAITING:
                continue
            item.status = MIGRATING
            yield item
            try:
                if item.kind == "settings":
                    self._migrate_settings(item)
                else:
                    self._migrate_project(item)
            except (
                OSError,
                UnicodeDecodeError,
                convert.MigrationError,
            ) as exc:
                item.status = FAILED
                item.report.error(_describe_error(exc))
            else:
                item.status = FAILED if item.report.has_errors else MIGRATED
            yield item
        self._finish()

    def run(self) -> Migration:
        for _ in self.steps():
            pass
        return self

    def _migrate_settings(self, item: Item) -> None:
        filename = os.path.basename(item.source)
        options = legacy.read_settings(item.source, filename, item.report)
        if item.report.has_errors:
            return
        app, current = convert.convert_settings(options, filename, item.report)
        if self.target.folder is not None:
            app.workspace = self.target.workspace
            item.report.info(f"workspace set to {app.workspace}")
        self.app_settings = app
        self.current_project = current
        if not self.dry_run:
            data: Table = {
                "format": SETTINGS_FORMAT,
                **dump_record(app),
            }
            _write(data, self.target.settings_file)

    def _migrate_project(self, item: Item) -> None:
        filename = os.path.basename(item.source)
        if filename.endswith(BACKUP_SUFFIX):
            item.report.info(f"{filename}, left by an interrupted save, used")
        project = legacy.read_project(item.source, filename, item.report)
        data, bricks = convert.convert_project(
            project,
            _project_settings(self.app_settings),
            item.report,
            os.path.dirname(item.source),
        )
        item.bricks = bricks
        if self.dry_run:
            return
        directory = self.target.project_dir(item.name)
        _write(data, os.path.join(directory, locations.PROJECT_FILE))
        if self.target.folder is None or item.kind != "project":
            return
        source = os.path.dirname(item.source)
        if self.copy_files:
            skip = {filename, locations.LEGACY_PROJECT_FILE}
            _copy_tree(source, directory, skip)
        elif os.path.isfile(os.path.join(source, "README")):
            shutil.copy2(os.path.join(source, "README"), directory)

    def _finish(self) -> None:
        if self.dry_run:
            return
        if self.current_project is not None:
            state: Table = {"format": SETTINGS_FORMAT}
            state["current_project"] = self.current_project
            _write(state, self.target.state_file)
        path = self.target.report_file
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fp:
            fp.write(self.text())

    # Reporting

    def messages(self, item: Item) -> list[Message]:
        levels = (INFO, WARNING, ERROR) if self.verbose else (WARNING, ERROR)
        return [m for m in item.report if m.level in levels]

    def summary(self) -> str:
        projects = self.projects
        migrated = self.count(MIGRATED)
        failed = self.count(FAILED)
        text = f"{migrated} of {len(projects)} projects migrated"
        if failed:
            text += f", {failed} failed"
        return text + "."

    def text(self) -> str:
        lines: list[str] = []
        width = max([len(item.name) for item in self.items] + [8]) + 2
        for item in self.items:
            lines.append(
                f"{item.name:<{width}}{item.status:<11}{counts(item)}"
            )
        for item in self.items:
            messages = self.messages(item)
            if messages:
                lines.append("")
                lines.append(item.name)
            for message in messages:
                where = f"  {message.where}" if message.where else ""
                lines.append(f"  {message.level:<8}{where}  {message.text}")
        lines.append("")
        lines.append(self.summary())
        return "\n".join(lines).rstrip() + "\n"

    def log(self, logger: Logger) -> None:
        for item in self.items:
            for message in item.report:
                text = str(message)
                if not message.where.startswith(item.name):
                    text = f"{item.name}: {text}"
                if message.level == ERROR:
                    logger.error("{text}", text=text)
                elif message.level == WARNING:
                    logger.warn("{text}", text=text)
                else:
                    logger.info("{text}", text=text)
        logger.info("Migration: {summary}", summary=self.summary())


def counts(item: Item) -> str:
    parts: list[str] = []
    levels: tuple[tuple[Level, str], ...] = (
        (ERROR, "error"),
        (WARNING, "warning"),
    )
    for level, noun in levels:
        number = item.report.count(level)
        if number:
            parts.append(f"{number} {noun}" + ("s" if number > 1 else ""))
    return ", ".join(parts)


def _describe_error(exc: Exception) -> str:
    if isinstance(exc, UnicodeDecodeError):
        return f"not a text file ({exc.reason}); project not migrated"
    if isinstance(exc, OSError):
        text = exc.strerror or str(exc)
        if exc.filename:
            text = f"{text}: {exc.filename}"
        return f"{text}; not migrated"
    return f"{exc}; project not migrated"


def lock_in_place() -> lockfile.FilesystemLock | None:
    """
    Hold the lock of the application while the files of the user change.

    Return the lock, to unlock when done, or None if Virtualbricks is running.
    At startup the application already holds it.
    """

    lock = lockfile.FilesystemLock(locations.LOCK_FILE)
    try:
        if lock.lock():
            return lock
    except OSError:
        # the lock of another user, see the per-user lock in the design
        pass
    return None


def startup_migration() -> Migration | None:
    """Return the migration the app must run before starting, or None."""

    legacy_settings = locations.legacy_settings_file()
    new_settings = locations.settings_file()
    if os.path.isfile(legacy_settings) and not os.path.exists(new_settings):
        app = _legacy_app_settings(legacy_settings)
    else:
        legacy_settings = None
        app = _read_app_settings(new_settings)
    migration = Migration(
        app.workspace, InPlace(app.workspace), legacy_settings, app
    )
    return migration if migration.pending() else None


def in_place_migration(
    legacy_settings: str | None = None, **options: bool
) -> Migration:
    """Return the migration of the files of the user, in place."""

    if legacy_settings is None:
        path = locations.legacy_settings_file()
        legacy_settings = path if os.path.isfile(path) else None
    if legacy_settings is not None:
        app = _legacy_app_settings(legacy_settings)
    else:
        app = _read_app_settings(locations.settings_file())
    target = InPlace(app.workspace)
    return Migration(app.workspace, target, legacy_settings, app, **options)


def migration_for(
    workspace: str,
    legacy_settings: str | None = None,
    output: str | None = None,
    **options: bool,
) -> Migration:
    """
    Return the migration of a workspace: in place, or to the output folder.

    In place, the per-project settings come from the old settings if given,
    else from the new settings of the user.
    """

    if legacy_settings is not None:
        app = _legacy_app_settings(legacy_settings)
    elif output is None:
        app = _read_app_settings(locations.settings_file())
    else:
        app = AppSettings()
    target = InPlace(workspace) if output is None else Folder(output)
    return Migration(workspace, target, legacy_settings, app, **options)


def migrate_imported_project(directory: str) -> Report:
    """Write the project file of an imported archive of an old version."""

    report = Report()
    source = project_source(directory)
    if source is None:
        report.error("no project file found", directory)
        return report
    filename = os.path.basename(source)
    try:
        project = legacy.read_project(source, filename, report)
        data, _ = convert.convert_project(
            project, new_project_settings(), report, directory
        )
        dump_toml(data, os.path.join(directory, locations.PROJECT_FILE))
    except (OSError, UnicodeDecodeError, convert.MigrationError) as exc:
        report.error(_describe_error(exc), directory)
    return report
