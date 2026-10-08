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
   ``.importing-<name>-*``, which the list of projects ignores; a README of
   before 3.0 becomes ``README.md``.
2. The images copied from the archive go to the shared images,
   ``<workspace>/shared_images``.
3. The project file gets the paths of the images and, if chosen, this
   computer's paths.
4. The private disks are pointed at their images with ``qemu-img rebase -u``.
5. The folder is renamed into place, with the next free name if the name
   was taken meanwhile.

An import never replaces a project.
"""

from __future__ import annotations

import dataclasses
import os
import shutil
import tempfile
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

from twisted.internet.interfaces import IReactorProcess

from virtualbricks import locations
from virtualbricks.config.archive import (
    BSDTAR,
    CONTENTS,
    DISK,
    IMAGE,
    IMAGES,
    LEGACY_IMAGES,
    ArchiveContents,
    ArchiveError,
    ArchiveJob,
    Emit,
    Member,
    Progress,
    QemuImg,
    Tool,
    extract,
    member_kind,
    read_contents,
    report_from_list,
    report_to_list,
    sparsify,
)
from virtualbricks.config.projectfile import (
    ProjectFormatError,
    devices_for_image,
    image_paths,
    read_project_file,
    remap_image,
    upgrade_project,
    upgrade_readme,
    write_project_file,
)
from virtualbricks.config.report import Report
from virtualbricks.config.settings import get_setting
from virtualbricks.config.tomlfile import Table
from virtualbricks.i18n import _

if TYPE_CHECKING:  # pragma: no cover
    from virtualbricks.config.workspace import Workspace

# The paths of the machine a project comes from, that can be replaced.
MACHINE_PATHS = ("qemu_path", "vde_path")

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
    # The shared images, where the copies go.
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
    image: ImageUse, library: str, complete: bool, member: Member | None
) -> None:
    """Give image its default choice; member is its copy in the archive."""

    archive_size = member.size if member is not None else None
    image.in_archive = archive_size
    image.known = complete or member is not None
    choice, path = _local_default(image.original, library, image.name)
    image.fallback = path if choice == USE else ""
    if member is None:
        if image.known:
            image.choice, image.path = choice, path
        else:
            # Copied if the archive turns out to have it.
            image.choice = COPY
            image.path = free_file(_library_file(library, image))
        return
    ours = os.path.join(library, _file_name(image))
    # a packed image is compared by its size before packing
    if os.path.isfile(ours) and os.path.getsize(ours) == member.original_size:
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
    library = os.path.join(workspace.path, locations.SHARED_IMAGES)
    in_archive = contents.images
    images = []
    for image_name, path in image_paths(data).items():
        used_by = [
            f"{vm}.{device}"
            for vm, device in devices_for_image(data, image_name)
        ]
        image = ImageUse(image_name, used_by, str(path), None)
        plan_image(
            image, library, contents.complete, in_archive.get(image_name)
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
        ours = str(get_setting(key))
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
        if image.known:
            image.in_archive = member.size if member else None
        else:
            plan_image(image, plan.library, True, member)


def import_project(
    plan: ImportPlan,
    workspace: Workspace,
    on_progress: Callable[[str, int, int], None] | None = None,
    qemu_img: str = "",
    reactor: IReactorProcess | None = None,
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
        return cls(table["name"], report_from_list(table["report"]))


# The process's side


class _Import:
    """An import running in the archive process."""

    def __init__(self, job: Table, emit: Emit, tool: Tool) -> None:
        self.job = job
        self.emit = emit
        self.tool = tool
        self.staging = str(job["staging"])
        self.qemu_img = str(job.get("qemu_img", ""))
        self.qemu = QemuImg(self.qemu_img) if self.qemu_img else None
        self.report = Report()
        self.created: list[str] = []
        # The members that qemu-img compressed, from contents.toml.
        self.packed: dict[str, Member] = {}
        # image name -> where its copy went
        self.copied: dict[str, str] = {}
        # private disk -> (its image, the image's format)
        self.rebased: dict[str, tuple[str, str]] = {}

    def run(self) -> dict[str, Any]:
        os.makedirs(self.staging, exist_ok=True)
        extract(str(self.job["archive"]), self.staging, self.tool, self.emit)
        self.read_contents()
        upgrade_readme(self.staging)
        project_file = os.path.join(self.staging, locations.PROJECT_FILE)
        if os.path.isfile(project_file):
            data = self.read_project(project_file)
        else:
            data = self.convert_project()
        paths = self.place_images()
        for name, path in paths.items():
            remap_image(data, name, path)
        table = data.setdefault("settings", {})
        if isinstance(table, dict):
            # as the plan's job() writes them
            table.update(cast("Table", self.job.get("settings", {})))
        write_project_file(data, project_file)
        self.rebase(data, paths)
        self.unpack()
        if self.tool.name != BSDTAR:
            self.sparsify()
        return {"name": self.move_into_place(), "report": self.messages()}

    def read_contents(self) -> None:
        """Which members are packed; contents.toml isn't the project's."""

        path = os.path.join(self.staging, CONTENTS)
        if not os.path.isfile(path):
            return
        with open(path, "rb") as fp:
            members = read_contents(fp.read())
        os.remove(path)
        self.packed = {m.name: m for m in members if m.packed}

    def unpack(self) -> None:
        """Turn the packed disks back into normal ones."""

        todo: list[tuple[str, str, tuple[str, str] | None]] = []
        for name, member in self.packed.items():
            if member.kind == IMAGE:
                path = self.copied.get(member.image)
                if path is not None:
                    todo.append((name, path, None))
            elif member.kind == DISK:
                path = os.path.join(self.staging, name)
                if path in self.rebased:
                    todo.append((name, path, self.rebased[path]))
                elif os.path.isfile(path):
                    self.report.warning(
                        "left compressed, as its image is unset or can't be"
                        " read; it works as it is",
                        name,
                    )
        if not todo:
            return
        qemu = self.qemu
        if qemu is None:
            for name, _path, _backing in todo:
                self.report.warning(
                    "qemu-img not found: left compressed, it works as it is",
                    name,
                )
            return
        total = sum(os.path.getsize(path) for _, path, _ in todo)
        progress = Progress(self.emit, "unpack", total)
        for name, path, backing in todo:
            size = os.path.getsize(path)
            start = progress.done

            def on_percent(
                percent: float, start: int = start, size: int = size
            ) -> None:
                progress.done = start
                progress.advance(int(size * percent / 100))

            unpacked = path + ".unpacking"
            try:
                qemu.convert(path, unpacked, False, backing, on_percent)
            except ArchiveError as exc:
                if os.path.lexists(unpacked):
                    os.remove(unpacked)
                self.report.warning(f"left compressed: {exc}", name)
            else:
                os.replace(unpacked, path)
            progress.done = start + size
        progress.send()

    def messages(self) -> list[list[str]]:
        return report_to_list(self.report)

    def read_project(self, path: str) -> Table:
        try:
            data = read_project_file(path)
            return upgrade_project(data, self.report)
        except ProjectFormatError as exc:
            raise ArchiveError(str(exc)) from None

    def convert_project(self) -> Table:
        from virtualbricks.migrate import convert_imported_project

        data = convert_imported_project(self.staging, self.report)
        if data is None:
            raise ArchiveError(
                "the archive has no project file that can be read"
            )
        return data

    def place_images(self) -> dict[str, str]:
        """Copy, use or leave unset each image; return their paths."""

        paths = {}
        # as the plan's job() writes them
        for image in cast("list[Table]", self.job.get("images", [])):
            name = str(image["name"])
            choice = str(image["choice"])
            source = self.image_file(name)
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
                self.copied[name] = destination
            elif choice == USE:
                paths[name] = str(image["path"])
            else:
                self.report.warning(
                    "left unset: give its disks an image in their settings",
                    f"images.{name}",
                )
                paths[name] = ""
        for folder in (IMAGES, LEGACY_IMAGES):
            shutil.rmtree(
                os.path.join(self.staging, folder), ignore_errors=True
            )
        return paths

    def image_file(self, name: str) -> str:
        """The file of an image in the archive, in .images in an old one."""

        path = os.path.join(self.staging, IMAGES, name)
        legacy = os.path.join(self.staging, LEGACY_IMAGES, name)
        if not os.path.isfile(path) and os.path.isfile(legacy):
            return legacy
        return path

    def rebase(self, data: Table, paths: dict[str, str]) -> None:
        """Point each private disk at its image, in the image's format."""

        for name, path in paths.items():
            for vm, device in devices_for_image(data, name):
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
                if self.qemu is None:
                    self.report.warning(
                        "qemu-img not found, the private disk isn't pointed"
                        f" at {path}",
                        where,
                    )
                    continue
                try:
                    self.rebase_disk(self.qemu, cow, path)
                except ArchiveError as exc:
                    self.report.warning(str(exc), where)

    def rebase_disk(self, qemu: QemuImg, cow: str, image: str) -> None:
        image_format = str(qemu.info(image).get("format", "qcow2"))
        qemu.rebase(cow, image, image_format)
        self.rebased[cow] = (image, image_format)

    def sparsify(self) -> None:
        for entry in os.listdir(self.staging):
            path = os.path.join(self.staging, entry)
            if member_kind(entry) == DISK:
                sparsify(path)
        for path in self.created:
            sparsify(path)

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


def run_import(job: Table, emit: Emit, tool: Tool) -> dict[str, Any]:
    """Run an import in the archive process; clean up if it fails."""

    running = _Import(job, emit, tool)
    try:
        return running.run()
    except BaseException:
        running.clean_up()
        raise
