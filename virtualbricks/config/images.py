# -*- test-case-name: virtualbricks.tests.config.test_images -*-
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
What the library of disk images knows about an image, without GTK.

An image is a name in the project and a file. ``qemu-img info`` tells what
the file is: its format, the size of the disk that a machine sees, the space
the file takes, its backing file and its snapshots. ``InfoCache`` keeps the
answer while the size and the time of the file don't change.

A disk of a virtual machine uses an image in one of two ways: through a
private copy, ``<vm>_<device>.cow`` in the project, which keeps the changes
of that machine above the image, or by writing the image itself.
``uses()`` says which disks use an image, and how.

The path of an image changes through ``relink()``: it points the private
copies at the new file first, with ``qemu-img rebase -u``, so that no
machine loses its changes at its next start.

The files of the images go in the image folder of the workspace,
``<workspace>/vimages``, which the import fills too; several projects may
use one file, under different names. ``other_projects()`` says which, from
the summaries that the list of the projects reads.

A disk's private copy can start over, empty, or become a new image of its
own, saved by the archive process; ``adopt()`` adds that image.
"""

from __future__ import annotations

import dataclasses
import json
import os
from typing import TYPE_CHECKING, Any, Callable

from twisted.internet import defer
from twisted.logger import Logger

from virtualbricks import errors
from virtualbricks.config.workspace import projects
from virtualbricks.qemu import run as qemu_run

if TYPE_CHECKING:  # pragma: no cover
    from virtualbricks.brickfactory import BrickFactory
    from virtualbricks.bricks.virtualmachine import Image, VirtualMachine
    from virtualbricks.config.workspace import Workspace

logger = Logger()
back_failed = (
    "Cannot point {copy} back at {path}: its machine will start from an"
    " empty private copy"
)

# qemu-img with its arguments: its output, when it ends.
Run = Callable[[list[str]], defer.Deferred]

# The folder of the images, in the workspace.
IMAGE_FOLDER = "vimages"


class RunningError(errors.Error):
    """An image can't change while machines that use it run."""

    def __init__(self, names: list[str]) -> None:
        super().__init__(
            "stop the machines that use it first: " + ", ".join(names)
        )
        self.names = names


@dataclasses.dataclass(frozen=True)
class ImageInfo:
    """What ``qemu-img info`` says of a file; the sizes are in bytes."""

    format: str
    # the size of the disk that a machine sees
    virtual_size: int
    # the space that the file takes
    actual_size: int
    backing_file: str | None
    snapshots: tuple[str, ...]


def parse_info(data: dict[str, Any]) -> ImageInfo:
    """The info of ``qemu-img info --output=json``."""

    backing = data.get("full-backing-filename") or data.get("backing-filename")
    return ImageInfo(
        format=str(data.get("format", "")),
        virtual_size=int(data.get("virtual-size", 0)),
        actual_size=int(data.get("actual-size", 0)),
        backing_file=str(backing) if backing else None,
        snapshots=tuple(
            str(snapshot.get("name", ""))
            for snapshot in data.get("snapshots", ())
        ),
    )


def read_info(path: str, run: Run | None = None) -> defer.Deferred:
    """Run ``qemu-img info`` on path: an ``ImageInfo``, when it ends."""

    if run is None:
        run = qemu_run.qemu_img
    # -U: a running machine locks the image it writes to
    deferred = run(["info", "--output=json", "-U", path])
    deferred.addCallback(lambda output: parse_info(json.loads(output)))
    return deferred


def _stamp(path: str) -> tuple[int, int]:
    stat = os.stat(path)
    return stat.st_size, stat.st_mtime_ns


class InfoCache:
    """
    The info of each file, read once while its size and its time don't
    change.
    """

    def __init__(self, run: Run | None = None) -> None:
        self.run = run
        self._infos: dict[str, tuple[tuple[int, int], ImageInfo]] = {}
        # the files being read, and who waits for them
        self._reading: dict[
            str, tuple[tuple[int, int], list[defer.Deferred]]
        ] = {}

    def get(self, path: str) -> ImageInfo | None:
        """The info of path, if it was read and the file hasn't changed."""

        cached = self._infos.get(path)
        try:
            if cached is not None and cached[0] == _stamp(path):
                return cached[1]
        except OSError:
            pass
        return None

    def read(self, path: str) -> defer.Deferred:
        """The info of path, read again only if the file changed."""

        try:
            stamp = _stamp(path)
        except OSError:
            return defer.fail()
        cached = self._infos.get(path)
        if cached is not None and cached[0] == stamp:
            return defer.succeed(cached[1])
        waiting = defer.Deferred()
        reading = self._reading.get(path)
        if reading is not None and reading[0] == stamp:
            reading[1].append(waiting)
            return waiting
        reading = (stamp, [waiting])
        self._reading[path] = reading
        # it may end at once: the caller waits already
        deferred = read_info(path, self.run)
        deferred.addBoth(self._read, path, reading)
        return waiting

    def _read(self, result, path, reading) -> None:
        if self._reading.get(path) is reading:
            del self._reading[path]
            if isinstance(result, ImageInfo):
                self._infos[path] = (reading[0], result)
        for waiting in reading[1]:
            if isinstance(result, ImageInfo):
                waiting.callback(result)
            else:
                waiting.errback(result)


@dataclasses.dataclass(frozen=True)
class DiskUse:
    """A disk that uses an image."""

    vm: VirtualMachine
    device: str
    # through a private copy, or by writing the image itself
    private: bool
    # the private copy, None while no project is open, as while one
    # loads; and the space it takes, None until it's made
    copy: str | None
    copy_size: int | None
    running: bool


def space_taken(path: str) -> int | None:
    """The space that the file path takes on disk; None if it isn't there."""

    try:
        return os.stat(path).st_blocks * 512
    except OSError:
        return None


def uses(factory: BrickFactory, image: Image) -> list[DiskUse]:
    """
    The disks that use image, machine by machine, in their order. The
    private copies are in the open project: while none is, as while a
    project loads, a disk's copy isn't known.
    """

    found = []
    is_open = projects.current is not None
    for brick in factory.bricks:
        if brick.get_type() != "Qemu":
            continue
        for disk in brick.disks():
            if disk.image is not image:
                continue
            private = bool(disk.is_cow())
            copy = disk.get_cow_path() if private and is_open else None
            found.append(
                DiskUse(
                    vm=brick,
                    device=disk.device,
                    private=private,
                    copy=copy,
                    copy_size=None if copy is None else space_taken(copy),
                    running=brick.__isrunning__(),
                )
            )
    return found


def relink(
    factory: BrickFactory, image: Image, path: str, run: Run | None = None
) -> defer.Deferred:
    """
    Give image the file path. The private copies made on the image are
    pointed at the new file first, in its format, so that none loses its
    changes; if one can't be, those already pointed go back, and the image
    keeps its file. Fail with ``RunningError`` while machines that use the
    image run, and with ``ImageAlreadyInUseError`` if another image has
    path.
    """

    if run is None:
        run = qemu_run.qemu_img
    path = os.path.abspath(path)
    old = image.path
    if path == old:
        return defer.succeed(None)
    other = factory.get_image_by_path(path)
    if other is not None and other is not image:
        return defer.fail(errors.ImageAlreadyInUseError(path))
    disks = uses(factory, image)
    running = [use.vm.name for use in disks if use.running]
    if running:
        return defer.fail(RunningError(sorted(set(running))))
    copies = [use.copy for use in disks if use.copy_size is not None]
    return _relink(image, old, path, copies, run)


@defer.inlineCallbacks
def _relink(image, old, path, copies, run):
    info = yield read_info(path, run)
    done = []
    try:
        for copy in copies:
            yield run(["rebase", "-u", "-b", path, "-F", info.format, copy])
            done.append(copy)
    except Exception:
        for copy in done:
            try:
                yield run(["rebase", "-u", "-b", old, "-F", info.format, copy])
            except Exception:
                logger.failure(back_failed, copy=copy, path=old)
        raise
    image.set_path(path)


# The files


def image_folder(workspace: Workspace) -> str:
    """The folder of the images of the workspace, made if it isn't there."""

    folder = os.path.join(workspace.path, IMAGE_FOLDER)
    os.makedirs(folder, exist_ok=True)
    return folder


def is_inside(path: str, folder: str) -> bool:
    """Whether path is in folder, or in a folder of it."""

    path, folder = os.path.abspath(path), os.path.abspath(folder)
    return os.path.commonpath([path, folder]) == folder


def free_path(folder: str, filename: str) -> str:
    """A path in folder for filename, with a number if it's taken."""

    stem, extension = os.path.splitext(filename)
    path = os.path.join(folder, filename)
    number = 2
    while os.path.lexists(path):
        path = os.path.join(folder, f"{stem}-{number}{extension}")
        number += 1
    return path


def other_projects(workspace: Workspace, path: str) -> list[tuple[str, str]]:
    """
    (project, image): the images of the other projects than the open one
    whose file is path, the most recently used project first.
    """

    path = os.path.abspath(path)
    current = workspace.current.name if workspace.current else None
    found = []
    for summary in workspace.summaries():
        if summary.name == current:
            continue
        for image in summary.images:
            if image.path and os.path.abspath(image.path) == path:
                found.append((summary.name, image.name))
    return found


# The private copies


def discard(path: str, trasher=None) -> bool:
    """
    Move path to the trash, or delete it without one; True if it went to
    the trash. A missing file is gone already.
    """

    if not os.path.lexists(path):
        return False
    if trasher is not None and trasher.can_trash(path):
        trasher.trash(path)
        return True
    os.remove(path)
    return False


def start_over(vm: VirtualMachine, device: str, trasher=None) -> bool:
    """
    The private copy of a disk of vm goes, with its changes: the next start
    makes an empty one. Fail with ``RunningError`` while vm runs. True if
    the copy went to the trash.
    """

    if vm.__isrunning__():
        raise RunningError([vm.name])
    return discard(vm.disk(device).get_cow_path(), trasher)


def adopt(
    factory: BrickFactory,
    vm: VirtualMachine,
    device: str,
    name: str,
    path: str,
    use_it: bool,
    trasher=None,
) -> Image:
    """
    Add the image saved from a disk of vm, name for the file path. use_it
    gives it to the disk, whose private copy goes: its changes are in the
    image now.
    """

    image = factory.new_disk_image(name, path)
    if use_it:
        copy = vm.disk(device).get_cow_path()
        vm.set_image(device, image)
        discard(copy, trasher)
    return image
