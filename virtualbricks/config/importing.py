# -*- test-case-name: virtualbricks.tests.config.test_importing -*-
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
Importing a project from an archive.

The application plans the import from what an inspection of the archive
found (``plan_import``); every choice has a default. The archive process runs
it (``run_import``):

1. The archive is extracted into a hidden folder of the workspace,
   ``.importing-<name>-*``, which the list of projects ignores.
2. The images copied from the archive go to the image library,
   ``<workspace>/vimages``.
3. The project file gets the paths of the images and, if chosen, this
   computer's paths.
4. The private disks are pointed at their images with ``qemu-img rebase -u``.
5. The folder is renamed into place, with the next free name if the name
   was taken meanwhile.

An import never replaces a project.
"""

from __future__ import annotations

import dataclasses
import json
import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from virtualbricks import locations
from virtualbricks.config import archive, projectfile, settings, tomlfile
from virtualbricks.config.archive import ArchiveContents, ArchiveJob, Tool
from virtualbricks.config.report import Report
from virtualbricks.i18n import _

if TYPE_CHECKING:
    from virtualbricks.config.tomlfile import Table
    from virtualbricks.config.workspace import Workspace

LIBRARY = "vimages"
# The paths of the machine a project comes from, that can be replaced.
MACHINE_PATHS = ("qemupath", "vdepath")

# The choices for an image.
COPY = "copy"
USE = "use"
SKIP = "skip"


@dataclasses.dataclass
class ImageUse:
    """An image of the project, and where it comes from on this computer."""

    name: str
    # The disks that use it, "vm.hda".
    used_by: list[str]
    # The path in the project file, on the computer it comes from.
    original: str
    # Its size in the archive; None if the archive doesn't have it, or if it
    # isn't known yet.
    in_archive: int | None
    choice: str = SKIP
    # Where a copy goes, or the file used.
    path: str = ""
    # Whether the archive has been read far enough to know if it has it.
    known: bool = True
    # For an image not known yet: the default if the archive doesn't have it.
    fallback: str = ""


@dataclasses.dataclass
class MachinePath:
    """A path of the project's settings that doesn't match this computer."""

    key: str
    theirs: str
    ours: str
    use_ours: bool


@dataclasses.dataclass
class ImportPlan:
    contents: ArchiveContents
    name: str
    images: list[ImageUse]
    machine_paths: list[MachinePath]
    # The image library, where the copies go.
    library: str
    open: bool = True

    def problems(self, workspace: Workspace) -> list[str]:
        """What stops the import; the Import button waits for none."""

        problems = []
        message = workspace.check_name(
            self.name, bricks=projectfile_bricks(self.contents.data)
        )
        if message is not None:
            problems.append(message)
        for image in self.images:
            if image.choice == USE and not os.path.isfile(image.path):
                problems.append(
                    _("{name}: {path} doesn't exist").format(
                        name=image.name, path=image.path or '""'
                    )
                )
        return problems

    def bytes_to_copy(self) -> int:
        return sum(
            image.in_archive or 0
            for image in self.images
            if image.choice == COPY
        )

    def job(self, workspace: Workspace, staging: str, qemu_img: str) -> Table:
        return {
            "job": "import",
            "archive": self.contents.path,
            "staging": staging,
            "destination": workspace.project_path(self.name),
            "images": [
                {
                    "name": image.name,
                    "choice": image.choice if image.known else "auto",
                    "path": image.path,
                    "fallback": image.fallback,
                }
                for image in self.images
            ],
            "settings": {
                p.key: p.ours for p in self.machine_paths if p.use_ours
            },
            "qemu_img": qemu_img,
        }


def projectfile_bricks(data: Table) -> list[str]:
    bricks = data.get("bricks", {})
    return list(bricks) if isinstance(bricks, dict) else []


def archive_name(path: str) -> str:
    """The name the archive suggests: its file name without the extension."""

    name = os.path.basename(path)
    for extension in (".tar.gz", ".tar.xz", ".tar.bz2", ".tgz", ".vbp"):
        if name.lower().endswith(extension):
            return name[: -len(extension)]
    return os.path.splitext(name)[0] or name


def _shorten(name: str, size: int) -> str:
    while len(os.fsencode(name)) > size:
        name = name[:-1]
    return name


def free_file(path: str) -> str:
    """path, or deb.1.qcow2, deb.2.qcow2... the first that doesn't exist."""

    if not os.path.lexists(path):
        return path
    base, extension = os.path.splitext(path)
    i = 1
    while os.path.lexists(f"{base}.{i}{extension}"):
        i += 1
    return f"{base}.{i}{extension}"


def _local_default(original: str, library: str, image: str) -> tuple[str, str]:
    """The default for an image not in the archive: use a file, or skip."""

    if original and os.path.isfile(original):
        return USE, original
    for name in (os.path.basename(original), image):
        path = os.path.join(library, name)
        if name and os.path.isfile(path):
            return USE, path
    return SKIP, ""


def plan_image(
    image: ImageUse, library: str, complete: bool, archive_size: int | None
) -> None:
    """Give image its default choice."""

    image.in_archive = archive_size
    image.known = complete or archive_size is not None
    choice, path = _local_default(image.original, library, image.name)
    image.fallback = path if choice == USE else ""
    if archive_size is None:
        if image.known:
            image.choice, image.path = choice, path
        else:
            # Copied if the archive turns out to have it.
            image.choice = COPY
            image.path = free_file(_library_file(library, image))
        return
    ours = os.path.join(library, _file_name(image))
    if os.path.isfile(ours) and os.path.getsize(ours) == archive_size:
        image.choice, image.path = USE, ours
    else:
        image.choice, image.path = COPY, free_file(ours)


def _file_name(image: ImageUse) -> str:
    return os.path.basename(image.original) or image.name


def _library_file(library: str, image: ImageUse) -> str:
    return os.path.join(library, _file_name(image))


def plan_import(contents: ArchiveContents, workspace: Workspace) -> ImportPlan:
    """The import of the archive with the default of every choice."""

    data = contents.data
    # Room for "-2" and the like.
    name = _shorten(archive_name(contents.path), 38).lstrip(".")
    name = workspace.free_name(name or "imported")
    library = os.path.join(workspace.path, LIBRARY)
    in_archive = contents.images
    images = []
    for image_name, path in projectfile.image_paths(data).items():
        used_by = [
            f"{vm}.{device}"
            for vm, device in projectfile.devices_for_image(data, image_name)
        ]
        image = ImageUse(image_name, used_by, str(path), None)
        member = in_archive.get(image_name)
        plan_image(
            image,
            library,
            contents.complete,
            member.size if member else None,
        )
        images.append(image)
    return ImportPlan(contents, name, images, machine_paths(data), library)


def machine_paths(data: Table) -> list[MachinePath]:
    project_settings = data.get("settings", {})
    if not isinstance(project_settings, dict):
        return []
    paths = []
    for key in MACHINE_PATHS:
        theirs = project_settings.get(key)
        ours = str(settings.get_app(key))
        if isinstance(theirs, str) and theirs != ours:
            paths.append(
                MachinePath(key, theirs, ours, not os.path.isdir(theirs))
            )
    return paths


def update_plan(plan: ImportPlan, contents: ArchiveContents) -> None:
    """The archive was read to its end: settle the images not known yet."""

    plan.contents = contents
    in_archive = contents.images
    for image in plan.images:
        member = in_archive.get(image.name)
        size = member.size if member else None
        if image.known:
            image.in_archive = size
        else:
            plan_image(image, plan.library, True, size)


def import_project(
    plan: ImportPlan,
    workspace: Workspace,
    on_progress: Callable[[str, int, int], None] | None = None,
    qemu_img: str = "",
    reactor=None,
) -> ArchiveJob:
    """Run the import in the archive process; done fires with its result."""

    os.makedirs(workspace.path, exist_ok=True)
    staging = tempfile.mkdtemp(
        prefix=f".importing-{plan.name}-", dir=workspace.path
    )
    job = ArchiveJob(
        plan.job(workspace, staging, qemu_img),
        on_progress,
        leftovers=[staging],
    ).start(reactor)
    job.done.addCallback(ImportResult.from_table)
    return job


@dataclasses.dataclass
class ImportResult:
    name: str
    report: Report

    @classmethod
    def from_table(cls, table: dict[str, Any]) -> ImportResult:
        return cls(table["name"], archive.report_from_list(table["report"]))


# The process's side


class _Import:
    """An import running in the archive process."""

    def __init__(self, job: Table, emit, tool: Tool) -> None:
        self.job = job
        self.emit = emit
        self.tool = tool
        self.staging = str(job["staging"])
        self.images = os.path.join(self.staging, archive.IMAGES)
        self.qemu_img = str(job.get("qemu_img", ""))
        self.report = Report()
        self.created: list[str] = []

    def run(self) -> dict[str, Any]:
        os.makedirs(self.staging, exist_ok=True)
        archive.extract(
            str(self.job["archive"]), self.staging, self.tool, self.emit
        )
        project_file = os.path.join(self.staging, locations.PROJECT_FILE)
        if os.path.isfile(project_file):
            data = self.read_project(project_file)
        else:
            data = self.convert_project()
        paths = self.place_images()
        for name, path in paths.items():
            projectfile.remap_image(data, name, path)
        table = data.setdefault("settings", {})
        if isinstance(table, dict):
            table.update(self.job.get("settings", {}))
        tomlfile.dump(data, project_file)
        self.rebase(data, paths)
        if self.tool.name != archive.BSDTAR:
            self.sparsify()
        return {"name": self.move_into_place(), "report": self.messages()}

    def messages(self) -> list[list[str]]:
        return archive.report_to_list(self.report)

    def read_project(self, path: str) -> Table:
        try:
            data = projectfile.read(path)
            return projectfile.upgrade(data, self.report)
        except projectfile.ProjectFormatError as exc:
            raise archive.ArchiveError(str(exc)) from None

    def convert_project(self) -> Table:
        from virtualbricks.migrate import convert_imported_project

        data = convert_imported_project(self.staging, self.report)
        if data is None:
            raise archive.ArchiveError(
                "the archive has no project file that can be read"
            )
        return data

    def place_images(self) -> dict[str, str]:
        """Copy, use or leave unset each image; return their paths."""

        paths = {}
        for image in self.job.get("images", []):
            name = str(image["name"])
            choice = str(image["choice"])
            source = os.path.join(self.images, name)
            if choice == "auto":
                if os.path.isfile(source):
                    choice = COPY
                elif image.get("fallback"):
                    choice, image["path"] = USE, image["fallback"]
                else:
                    choice = SKIP
            if choice == COPY:
                if not os.path.isfile(source):
                    self.report.warning(
                        "not in the archive, left unset", f"images.{name}"
                    )
                    paths[name] = ""
                    continue
                destination = free_file(str(image["path"]))
                os.makedirs(os.path.dirname(destination), exist_ok=True)
                self.emit({"created": destination})
                self.created.append(destination)
                shutil.move(source, destination)
                paths[name] = destination
            elif choice == USE:
                paths[name] = str(image["path"])
            else:
                self.report.warning(
                    "left unset: give its disks an image in their settings",
                    f"images.{name}",
                )
                paths[name] = ""
        shutil.rmtree(self.images, ignore_errors=True)
        return paths

    def rebase(self, data: Table, paths: dict[str, str]) -> None:
        """Point each private disk at its image, in the image's format."""

        for name, path in paths.items():
            for vm, device in projectfile.devices_for_image(data, name):
                cow = os.path.join(self.staging, f"{vm}_{device}.cow")
                if not os.path.isfile(cow):
                    continue
                where = f"bricks.{vm}.disks.{device}"
                if not path:
                    self.report.warning(
                        "its image is unset, the private disk is left as"
                        " it is",
                        where,
                    )
                    continue
                if not self.qemu_img:
                    self.report.warning(
                        "qemu-img not found, the private disk isn't pointed"
                        f" at {path}",
                        where,
                    )
                    continue
                try:
                    self.rebase_disk(cow, path)
                except archive.ArchiveError as exc:
                    self.report.warning(str(exc), where)

    def _qemu_img(self, args: list[str]) -> str:
        try:
            result = subprocess.run(
                [self.qemu_img, *args], capture_output=True, text=True
            )
        except OSError as exc:
            raise archive.ArchiveError(f"qemu-img: {exc}") from None
        if result.returncode != 0:
            raise archive.ArchiveError(f"qemu-img: {result.stderr.strip()}")
        return result.stdout

    def rebase_disk(self, cow: str, image: str) -> None:
        info = json.loads(self._qemu_img(["info", "--output=json", image]))
        image_format = info.get("format", "qcow2")
        self._qemu_img(["rebase", "-u", "-b", image, "-F", image_format, cow])

    def sparsify(self) -> None:
        for entry in os.listdir(self.staging):
            path = os.path.join(self.staging, entry)
            if archive.member_kind(entry) == archive.DISK:
                archive.sparsify(path)
        for path in self.created:
            archive.sparsify(path)

    def move_into_place(self) -> str:
        destination = str(self.job["destination"])
        workspace = os.path.dirname(destination)
        name = os.path.basename(destination)
        if os.path.lexists(destination):
            from virtualbricks.config.workspace import Workspace

            name = Workspace(workspace).free_name(name)
            self.report.info(
                f'a project named "{os.path.basename(destination)}" appeared'
                f' meanwhile, imported as "{name}"'
            )
        # mkdtemp made the folder private; a project folder isn't.
        umask = os.umask(0)
        os.umask(umask)
        os.chmod(self.staging, 0o777 & ~umask)
        os.rename(self.staging, os.path.join(workspace, name))
        return name

    def clean_up(self) -> None:
        shutil.rmtree(self.staging, ignore_errors=True)
        for path in self.created:
            if os.path.lexists(path):
                os.remove(path)


def run_import(job: Table, emit, tool: Tool) -> dict[str, Any]:
    """Run an import in the archive process; clean up if it fails."""

    running = _Import(job, emit, tool)
    try:
        return running.run()
    except BaseException:
        running.clean_up()
        raise
